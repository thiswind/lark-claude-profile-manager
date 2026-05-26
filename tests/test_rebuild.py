from pathlib import Path

import pytest

from lcp.docker_adapter import ExecResult
from lcp.models import default_profile
from lcp.rebuild import RebuildError, check_claude_continuity, rebuild_profile
from lcp.store import LcpStore


class FakeContainer:
    def __init__(self, name="lcp-project1") -> None:
        self.name = name
        self.status = "running"
        self.stopped = False
        self.started = False
        self.removed = False

    def stop(self) -> None:
        self.status = "exited"
        self.stopped = True

    def start(self) -> None:
        self.status = "running"
        self.started = True

    def rename(self, name) -> None:
        self.name = name

    def remove(self, force=False) -> None:
        self.removed = True


class FakeContainers:
    def __init__(self, container) -> None:
        self.by_name = {container.name: container}
        self.created = []

    def get(self, name):
        return self.by_name[name]

    def create(self, **kwargs):
        container = FakeContainer(kwargs["name"])
        self.by_name[container.name] = container
        self.created.append(kwargs)
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
