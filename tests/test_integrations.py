from pathlib import Path

from typer.testing import CliRunner

from lcp import cli
from lcp.docker_adapter import ExecResult
from lcp.integrations.models import HostCheck, IntegrationCapabilities, ProfileIntegrationState
from lcp.integrations.registry import IntegrationRegistry
from lcp.integrations.service import IntegrationService
from lcp.integrations.base import IntegrationProvider
from lcp.integrations.providers.github import GitHubProvider
from lcp.integrations.providers.ssh import SshProvider
from lcp.integrations.providers.vercel import VercelProvider
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

    def verify_commands(self, profile, external: bool = False):
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


def test_default_registry_includes_ssh_provider() -> None:
    assert IntegrationRegistry().get("ssh").name == "ssh"


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


def test_github_install_falls_back_when_exact_apt_version_is_unavailable(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("github", ProfileIntegrationState())
    state.desired.hostVersion = "2.92.0"

    commands = GitHubProvider().install_commands(profile)

    assert len(commands) == 1
    assert "apt-get -o Acquire::Retries=3 install -y gh=2.92.0" in commands[0]
    assert "exact gh 2.92.0 unavailable from apt" in commands[0]
    assert "apt-get -o Acquire::Retries=3 install -y gh))" in commands[0]


def test_github_provider_configures_git_credential_helper(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    commands = GitHubProvider().configure_commands(profile)

    assert commands == ["gh auth setup-git"]


def test_github_provider_verifies_git_credential_helper(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    commands = GitHubProvider().verify_commands(profile)

    assert commands == [
        "gh --version",
        "gh auth status",
        "git config --global --get-all credential.https://github.com.helper | grep -F 'gh auth git-credential'",
    ]


def test_github_provider_external_verify_smoke_tests_https_git(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    commands = GitHubProvider().verify_commands(profile, external=True)

    assert "git ls-remote https://github.com/thiswind/lark-claude-profile-manager.git HEAD >/dev/null" in commands


def test_ssh_provider_prepares_least_privilege_snapshot(tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text("Host sofia\n  HostName sofia.example\n", encoding="utf-8")
    (ssh_dir / "known_hosts").write_text("sofia.example ssh-ed25519 AAAA\n", encoding="utf-8")
    (ssh_dir / "id_sofia").write_text("PRIVATE", encoding="utf-8")
    (ssh_dir / "id_other").write_text("OTHER", encoding="utf-8")
    state = profile.integrations.providers.setdefault("ssh", ProfileIntegrationState())
    state.desired.enabled = True
    state.desired.config = {"sshDir": str(ssh_dir), "key": str(ssh_dir / "id_sofia"), "includePrivateKeys": "true"}

    provider = SshProvider()
    provider.prepare(store, profile)
    mounts = provider.mounts(store, profile)

    snapshot = Path(state.desired.snapshotPath)
    assert (snapshot / "config").exists()
    assert (snapshot / "known_hosts").exists()
    assert (snapshot / "id_sofia").exists()
    assert not (snapshot / "id_other").exists()
    assert mounts[0].mode == "ro"
    assert mounts[0].containerPath == "/home/thiswind/.ssh"


def test_ssh_provider_rejects_private_keys_without_explicit_key(tmp_path: Path, monkeypatch) -> None:
    ssh_dir = tmp_path / ".ssh"
    ssh_dir.mkdir()
    (ssh_dir / "config").write_text("Host sofia\n", encoding="utf-8")
    provider = SshProvider()
    monkeypatch.setattr(provider, "check_host", lambda: HostCheck(provider="ssh", ok=True, version="OpenSSH", authPath=str(ssh_dir)))

    check = provider.check_config({"sshDir": str(ssh_dir), "includePrivateKeys": "true"})

    assert check.ok is False
    assert "requires explicit" in check.message


def test_ssh_provider_verify_checks_readonly_mount(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    commands = SshProvider().verify_commands(profile)

    assert "test ! -w ~/.ssh" in commands[0]
    assert "known_hosts" in commands[0]


def test_vercel_verify_uses_token_snapshot_when_present(tmp_path: Path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    commands = VercelProvider().verify_commands(profile)

    assert "lcp-token.json" in commands[0]
    assert "HOME=\"$tmp\" vercel whoami --token" in commands[0]
    assert "HOME=\"$tmp\" vercel whoami;" in commands[0]
