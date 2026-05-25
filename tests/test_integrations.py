from pathlib import Path

from typer.testing import CliRunner

from lcp import cli
from lcp.docker_adapter import ExecResult
from lcp.integrations.models import HostCheck, IntegrationCapabilities, ProfileIntegrationState
from lcp.integrations.registry import IntegrationRegistry
from lcp.integrations.service import IntegrationService
from lcp.integrations.base import IntegrationProvider
from lcp.models import default_profile


runner = CliRunner()


class FakeProvider(IntegrationProvider):
    name = "fake"
    description = "Fake provider"

    def capabilities(self) -> IntegrationCapabilities:
        return IntegrationCapabilities(requiresHostAuth=False, requiresContainerInstall=True, canVerifyContainer=True)

    def check_host(self) -> HostCheck:
        return HostCheck(provider=self.name, ok=True, version="1.2.3", details={"value": "ok"})

    def install_commands(self, profile, reuse_matching: bool = False):
        return ["install fake"]

    def configure_commands(self, profile):
        return ["configure fake"]

    def verify_commands(self, profile):
        return ["verify fake"]


class FakeAdapter:
    def __init__(self):
        self.commands = []

    def exec(self, profile, command):
        self.commands.append(command)
        return ExecResult(0, f"ran {command}")


class FakeContainer:
    name = "lcp-project1"
    status = "running"


class FakeApplyAdapter(FakeAdapter):
    recreated = False

    def __init__(self, store):
        super().__init__()
        self.store = store

    def get_container_or_none(self, profile):
        return FakeContainer()

    def recreate_container(self, profile):
        self.recreated = True
        return FakeContainer()


def test_service_grant_and_apply_updates_state(tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store, IntegrationRegistry({"fake": FakeProvider()}))

    profile = service.grant(profile, "fake")
    profile, results = service.apply(FakeAdapter(), profile)

    assert profile.integrations.providers["fake"].desired.enabled is True
    assert profile.integrations.providers["fake"].effective.status == "active"
    assert [result.command for result in results] == ["verify fake"]


def test_integration_apply_requires_yes_for_real_apply(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("fake", ProfileIntegrationState())
    state.desired.enabled = True
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeApplyAdapter)
    monkeypatch.setattr(cli, "IntegrationService", lambda store: IntegrationService(store, IntegrationRegistry({"fake": FakeProvider()})))

    result = runner.invoke(cli.app, ["integration", "apply", "project1"], input="n\n")

    assert result.exit_code == 1


def test_integration_apply_dry_run_does_not_recreate(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("fake", ProfileIntegrationState())
    state.desired.enabled = True
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeApplyAdapter)
    monkeypatch.setattr(cli, "IntegrationService", lambda store: IntegrationService(store, IntegrationRegistry({"fake": FakeProvider()})))

    result = runner.invoke(cli.app, ["integration", "apply", "project1", "--dry-run"])

    assert result.exit_code == 0
    assert "fake: install" in result.output
    assert "fake: verify" in result.output
