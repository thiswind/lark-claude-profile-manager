from pathlib import Path

import pytest

from lcp.docker_adapter import ExecResult
from lcp.integrations.models import IntegrationVerifyResult, ProfileIntegrationState
from lcp.models import default_profile
from lcp import rebuild as rebuild_module
from lcp.rebuild import RebuildError, check_claude_continuity, cleanup_rollback_containers, list_rollback_containers, rebuild_profile
from lcp.store import LcpStore


class FakeContainer:
    def __init__(self, name="lcp-project1") -> None:
        self.name = name
        self.status = "running"
        self.stopped = False
        self.started = False
        self.removed = False
        self.registry = None

    def stop(self) -> None:
        self.status = "exited"
        self.stopped = True

    def start(self) -> None:
        self.status = "running"
        self.started = True

    def rename(self, name) -> None:
        if self.registry is not None:
            self.registry.pop(self.name, None)
            self.registry[name] = self
        self.name = name

    def remove(self, force=False) -> None:
        self.removed = True
        if self.registry is not None:
            self.registry.pop(self.name, None)


class FakeContainers:
    def __init__(self, container) -> None:
        self.by_name = {container.name: container}
        container.registry = self.by_name
        self.created = []
        self.created_containers = []

    def get(self, name):
        return self.by_name[name]

    def list(self, all=False, filters=None):
        if filters == {"label": "lcp.profile=project1"}:
            return list(self.by_name.values())
        return []

    def create(self, **kwargs):
        container = FakeContainer(kwargs["name"])
        container.registry = self.by_name
        self.by_name[container.name] = container
        self.created.append(kwargs)
        self.created_containers.append(container)
        return container


class FakeAdapter:
    def __init__(self, store, container=None) -> None:
        self.store = store
        self.container = container or FakeContainer()
        self.client = type("FakeClient", (), {"containers": FakeContainers(self.container)})()
        self.built = False
        self.started = False
        self.commands = []
        self.bridge_running = False

    def get_container(self, profile):
        return self.client.containers.get(profile.container.name)

    def get_container_or_none(self, profile):
        return self.client.containers.by_name.get(profile.container.name)

    def list_profile_containers(self, profile):
        return self.client.containers.list(all=True, filters={"label": f"lcp.profile={profile.name}"})

    def build_profile_image(self, profile):
        self.built = True

    def create_profile_container(self, profile, build_image=True):
        assert build_image is False
        return self.client.containers.create(name=profile.container.name)

    def start(self, profile):
        self.started = True
        self.get_container(profile).start()

    def exec(self, profile, command):
        self.commands.append(command)
        if "bridge-supervisor.pid" in command:
            return ExecResult(0, "stopped")
        return ExecResult(0, "ok")


class FakeIntegrationService:
    calls = 0
    results = [IntegrationVerifyResult(provider="fake", command="verify fake", ok=True, output="ok")]

    def __init__(self, store) -> None:
        self.store = store

    def apply(self, adapter, profile, reuse_matching=False):
        FakeIntegrationService.calls += 1
        assert reuse_matching is True
        return profile, self.results


def make_profile(tmp_path: Path):
    claude_dir = tmp_path / ".claude"
    (claude_dir / "projects").mkdir(parents=True)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    profile.mounts.claude.hostClaudeDir = str(claude_dir)
    profile.mounts.claude.hostClaudeJson = str(claude_json)
    return profile


def test_claude_continuity_is_safe_when_host_state_is_mounted(tmp_path: Path) -> None:
    profile = make_profile(tmp_path)

    check = check_claude_continuity(profile)

    assert check.safe is True
    assert check.reasons == []


def test_claude_continuity_is_unsafe_when_projects_are_missing(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    profile.mounts.claude.hostClaudeDir = str(claude_dir)
    profile.mounts.claude.hostClaudeJson = str(claude_json)

    check = check_claude_continuity(profile)

    assert check.safe is False
    assert "Claude projects directory not found" in check.reasons[0]


def test_rebuild_profile_replaces_container_and_keeps_rollback(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    store.save_profile(profile)
    old_container = FakeContainer(profile.container.name)
    adapter = FakeAdapter(store, old_container)

    result = rebuild_profile(store, adapter, profile)

    assert adapter.built is True
    assert adapter.started is True
    assert result.rollbackContainer.startswith("lcp-project1-rollback-")
    assert adapter.client.containers.by_name[profile.container.name].started is True
    assert old_container.name == result.rollbackContainer
    assert old_container.stopped is True
    assert "test -d ~/.claude/projects" in adapter.commands


def test_rebuild_profile_refuses_unsafe_claude_continuity(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    profile.mounts.claude.hostClaudeDir = str(tmp_path / "missing-claude")
    profile.mounts.claude.hostClaudeJson = str(tmp_path / "missing-claude.json")
    store.save_profile(profile)
    adapter = FakeAdapter(store, FakeContainer(profile.container.name))

    with pytest.raises(RebuildError) as exc:
        rebuild_profile(store, adapter, profile)

    assert "Claude Code continuity is unsafe" in str(exc.value)
    assert adapter.built is False


def test_rebuild_profile_reapplies_active_integrations(monkeypatch, tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    profile.integrations.providers["fake"] = ProfileIntegrationState()
    profile.integrations.providers["fake"].desired.enabled = True
    store.save_profile(profile)
    adapter = FakeAdapter(store, FakeContainer(profile.container.name))
    FakeIntegrationService.calls = 0
    monkeypatch.setattr(rebuild_module, "IntegrationService", FakeIntegrationService)

    result = rebuild_profile(store, adapter, profile)

    assert FakeIntegrationService.calls == 1
    assert result.integrations == FakeIntegrationService.results


def test_rebuild_profile_rolls_back_when_integration_reapply_fails(monkeypatch, tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    profile.integrations.providers["fake"] = ProfileIntegrationState()
    profile.integrations.providers["fake"].desired.enabled = True
    store.save_profile(profile)
    old_container = FakeContainer(profile.container.name)
    adapter = FakeAdapter(store, old_container)

    class FailingIntegrationService(FakeIntegrationService):
        results = [IntegrationVerifyResult(provider="fake", command="verify fake", ok=False, output="bad")]

    monkeypatch.setattr(rebuild_module, "IntegrationService", FailingIntegrationService)

    with pytest.raises(RebuildError) as exc:
        rebuild_profile(store, adapter, profile)

    assert "integration reapply failed" in str(exc.value)
    assert "bad" in exc.value.recovery
    assert adapter.client.containers.created_containers[0].removed is True
    assert adapter.client.containers.by_name[profile.container.name] is old_container


def test_list_rollback_containers_filters_by_profile_prefix(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(store, FakeContainer(profile.container.name))
    rollback = FakeContainer("lcp-project1-rollback-20260526010101")
    other = FakeContainer("lcp-other-rollback-20260526010101")
    for container in [rollback, other]:
        container.registry = adapter.client.containers.by_name
        adapter.client.containers.by_name[container.name] = container

    rollbacks = list_rollback_containers(adapter, profile)

    assert [container.name for container in rollbacks] == ["lcp-project1-rollback-20260526010101"]


def test_cleanup_rollback_containers_removes_only_matching_rollbacks(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(store, FakeContainer(profile.container.name))
    rollback = FakeContainer("lcp-project1-rollback-20260526010101")
    current = adapter.client.containers.by_name[profile.container.name]
    for container in [rollback]:
        container.registry = adapter.client.containers.by_name
        adapter.client.containers.by_name[container.name] = container

    result = cleanup_rollback_containers(adapter, profile)

    assert result.removed == ["lcp-project1-rollback-20260526010101"]
    assert rollback.removed is True
    assert current.removed is False
    assert profile.container.name in adapter.client.containers.by_name
