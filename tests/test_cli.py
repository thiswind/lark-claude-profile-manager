from pathlib import Path

from typer.testing import CliRunner

from lcp import cli
from lcp.models import default_profile

runner = CliRunner()


class FakeContainer:
    def __init__(self, status="running") -> None:
        self.name = "lcp-project1"
        self.status = status
        self.removed = False

    def remove(self, force=False) -> None:
        self.removed = True

    def start(self) -> None:
        self.status = "running"


class FakeAdapter:
    container = None
    started = False

    def __init__(self, store) -> None:
        self.store = store

    def get_container(self, profile):
        return self.container or FakeContainer()

    def get_container_or_none(self, profile):
        return self.container

    def remove_container(self, profile):
        if self.container is None:
            return False
        self.container.remove(force=True)
        return True

    def start(self, profile):
        self.started = True


class FakeCreatorAdapter(FakeAdapter):
    created = []
    started_profiles = []

    def create_profile_container(self, profile):
        self.created.append(profile.name)
        return FakeContainer()

    def start(self, profile):
        self.started_profiles.append(profile.name)


class FakeSnapshotAdapter(FakeAdapter):
    def snapshot(self, profile, output_dir=None):
        return Path(output_dir or "/tmp") / f"{profile.name}-snapshot.tar"

    def load_image(self, image_tar):
        self.loaded = image_tar


def make_store(tmp_path: Path) -> cli.LcpStore:
    store = cli.LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    return store


def test_help_short_option_works() -> None:
    result = runner.invoke(cli.app, ["-h"])

    assert result.exit_code == 0
    assert "Manage Lark Claude profile containers" in result.output


def test_help_shows_grouped_commands_and_hides_legacy_lifecycle_commands() -> None:
    result = runner.invoke(cli.app, ["--help"])

    assert result.exit_code == 0
    assert " profile " in result.output
    assert " bridge " in result.output
    assert " create " not in result.output
    assert " list " not in result.output
    assert " status " not in result.output
    assert " shell " not in result.output
    assert " verify " not in result.output
    assert " snapshot " not in result.output
    assert " restore " not in result.output
    assert " rm " not in result.output
    assert " start " not in result.output
    assert " stop " not in result.output
    assert " restart " not in result.output
    assert " logs " not in result.output


def test_profile_help_shows_lifecycle_commands() -> None:
    result = runner.invoke(cli.app, ["profile", "--help"])

    assert result.exit_code == 0
    for command in ["create", "list", "status", "shell", "verify", "snapshot", "restore", "rm"]:
        assert command in result.output


def test_profile_without_command_shows_help() -> None:
    result = runner.invoke(cli.app, ["profile"])

    assert "Manage profiles" in result.output
    assert "create" in result.output


def test_bridge_help_shows_common_actions() -> None:
    result = runner.invoke(cli.app, ["bridge", "-h"])

    assert result.exit_code == 0
    assert "lcp bridge <profile> run" in result.output
    assert "lcp bridge <profile> start" in result.output
    assert "Foreground QR/debug" in result.output
    assert "Background run" in result.output


def test_rm_container_is_hidden_debug_and_idempotent(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = None
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["rm", "container", "project1", "--yes"])

    assert result.exit_code == 0
    assert "container already absent: lcp-project1" in result.output
    assert "profile state kept" in result.output


def test_rm_profile_is_hidden_debug_and_removes_profile_state(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["rm", "profile", "project1", "--yes"])

    assert result.exit_code == 0
    assert "removed profile state" in result.output
    assert not store.profile_dir("project1").exists()


def test_profile_rm_removes_container_and_profile_state(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    container = FakeContainer()
    FakeAdapter.container = container
    stopped = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "stop_bridge", lambda adapter, profile: stopped.append(profile.name))

    result = runner.invoke(cli.app, ["profile", "rm", "project1", "--yes"])

    assert result.exit_code == 0
    assert stopped == ["project1"]
    assert container.removed
    assert "removed container: lcp-project1" in result.output
    assert "removed profile state" in result.output
    assert not store.profile_dir("project1").exists()


def test_profile_create_uses_create_path(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    FakeCreatorAdapter.created = []
    FakeCreatorAdapter.started_profiles = []
    FakeCreatorAdapter.container = None
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeCreatorAdapter)
    monkeypatch.setattr(cli, "install_runtime", lambda adapter, profile: [])
    monkeypatch.setattr(
        cli,
        "collect_init_report",
        lambda desktop=None: type(
            "Report",
            (),
            {
                "has_required_failures": False,
                "checks": [],
                "config": type(
                    "Config",
                    (),
                    {
                        "desktop": type("Desktop", (), {"hostPath": str(tmp_path / "Desktop")})(),
                        "platform": type("Platform", (), {"environment": "linux", "arch": "amd64"})(),
                        "hostUser": type("HostUser", (), {"name": "thiswind", "uid": 1000, "gid": 1000, "displayName": None})(),
                    },
                )(),
            },
        )(),
    )

    result = runner.invoke(cli.app, ["profile", "create", "project1", "--no-install"])

    assert result.exit_code == 0
    assert "created: lcp-project1" in result.output
    assert FakeCreatorAdapter.created == ["project1"]
    assert FakeCreatorAdapter.started_profiles == ["project1"]


def test_profile_create_refuses_existing_profile(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeCreatorAdapter.created = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeCreatorAdapter)

    result = runner.invoke(cli.app, ["profile", "create", "project1", "--no-install"])

    assert result.exit_code == 1
    assert "profile already exists" in result.output
    assert "lcp profile rm project1" in result.output
    assert FakeCreatorAdapter.created == []


def test_profile_create_refuses_existing_container(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    FakeCreatorAdapter.created = []
    FakeCreatorAdapter.container = FakeContainer()
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeCreatorAdapter)
    monkeypatch.setattr(
        cli,
        "collect_init_report",
        lambda desktop=None: type(
            "Report",
            (),
            {
                "has_required_failures": False,
                "checks": [],
                "config": type(
                    "Config",
                    (),
                    {
                        "desktop": type("Desktop", (), {"hostPath": str(tmp_path / "Desktop")})(),
                        "platform": type("Platform", (), {"environment": "linux", "arch": "amd64"})(),
                        "hostUser": type("HostUser", (), {"name": "thiswind", "uid": 1000, "gid": 1000, "displayName": None})(),
                    },
                )(),
            },
        )(),
    )

    result = runner.invoke(cli.app, ["profile", "create", "project1", "--no-install"])

    assert result.exit_code == 1
    assert "container already exists: lcp-project1" in result.output
    assert not (store.profile_dir("project1") / "profile.json").exists()
    assert FakeCreatorAdapter.created == []
    FakeCreatorAdapter.container = None


def test_profile_list_shows_missing_container(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = None
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "list"])

    assert result.exit_code == 0
    assert "project1" in result.output
    assert "lcp-project1" in result.output
    assert "missing" in result.output


def test_legacy_list_still_works_hidden(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = None
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["list"])

    assert result.exit_code == 0
    assert "project1" in result.output


def test_bridge_proxies_args_to_container(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "ps"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "ps"]]


def test_bridge_proxies_unknown_options(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "run", "--skip-check-lark-cli"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "run", "--skip-check-lark-cli"]]


def test_bridge_start_uses_lcp_runtime_not_upstream_start(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    starts = []
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)
    monkeypatch.setattr(cli, "start_bridge", lambda adapter, profile: starts.append(profile.name) or type("Status", (), {"running": True, "pid": "123", "detail": ""})())

    result = runner.invoke(cli.app, ["bridge", "project1", "start"])

    assert result.exit_code == 0
    assert "bridge started: 123" in result.output
    assert starts == ["project1"]
    assert calls == []


def test_bridge_run_stays_foreground_proxy(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "run"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "run"]]
