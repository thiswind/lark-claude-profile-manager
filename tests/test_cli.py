from pathlib import Path

from typer.testing import CliRunner

from lcp import cli
from lcp.docker_adapter import ExecResult
from lcp.models import default_profile

runner = CliRunner()


class FakeContainer:
    def __init__(self, status="running", name="lcp-project1") -> None:
        self.name = name
        self.status = status
        self.removed = False

    def remove(self, force=False) -> None:
        self.removed = True

    def start(self) -> None:
        self.status = "running"


class FakeAdapter:
    container = None
    containers = []
    started = False

    def __init__(self, store) -> None:
        self.store = store

    def get_container(self, profile):
        return self.container or FakeContainer()

    def get_container_or_none(self, profile):
        return self.container

    def list_profile_containers(self, profile):
        return self.containers

    def remove_container(self, profile):
        if self.container is None:
            return False
        self.container.remove(force=True)
        return True

    def start(self, profile):
        self.started = True

    def stop(self, profile):
        self.stopped = True

    def exec(self, profile, command):
        return ExecResult(1, "stopped")


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


def test_version_option_shows_package_version() -> None:
    result = runner.invoke(cli.app, ["--version"])

    assert result.exit_code == 0
    assert result.output.strip() == "lcp 0.2.2"


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
    for command in ["create", "list", "status", "shell", "verify", "rebuild", "snapshot", "restore", "rm"]:
        assert command in result.output


def test_profile_without_command_shows_help() -> None:
    result = runner.invoke(cli.app, ["profile"])

    assert "Manage profiles" in result.output
    assert "create" in result.output


def test_profile_rebuild_requires_name_or_all() -> None:
    result = runner.invoke(cli.app, ["profile", "rebuild", "--dry-run"])

    assert result.exit_code == 1
    assert "profile name required" in result.output


def test_profile_rebuild_rejects_name_with_all(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["profile", "rebuild", "project1", "--all", "--dry-run"])

    assert result.exit_code == 1
    assert "choose either a profile name or --all" in result.output


def test_profile_rebuild_all_dry_run_lists_profiles(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    claude_dir = tmp_path / ".claude"
    (claude_dir / "projects").mkdir(parents=True)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    for name in ["project1", "project2"]:
        profile = default_profile(name, tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
        profile.mounts.claude.hostClaudeDir = str(claude_dir)
        profile.mounts.claude.hostClaudeJson = str(claude_json)
        store.save_profile(profile)
    monkeypatch.setattr(FakeAdapter, "container", FakeContainer())
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "rebuild", "--all", "--dry-run"])

    assert result.exit_code == 0
    assert "profile: project1" in result.output
    assert "profile: project2" in result.output
    assert result.output.count("dry-run: would rebuild") == 2


def test_profile_cleanup_rollbacks_dry_run_lists_rollback_containers(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    rollback = FakeContainer("exited", "lcp-project1-rollback-20260526010101")
    current = FakeContainer("running", "lcp-project1")
    other = FakeContainer("exited", "lcp-other-rollback-20260526010101")
    monkeypatch.setattr(FakeAdapter, "containers", [rollback, current, other])
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "cleanup-rollbacks", "project1", "--dry-run"])

    assert result.exit_code == 0
    assert "rollback: lcp-project1-rollback-20260526010101 (exited)" in result.output
    assert "lcp-other" not in result.output
    assert "dry-run: would remove 1 rollback container(s)" in result.output
    assert rollback.removed is False


def test_profile_cleanup_rollbacks_requires_yes(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    monkeypatch.setattr(FakeAdapter, "containers", [FakeContainer("exited", "lcp-project1-rollback-20260526010101")])
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "cleanup-rollbacks", "project1"])

    assert result.exit_code == 1
    assert "rollback cleanup requires explicit confirmation" in result.output


def test_profile_cleanup_rollbacks_yes_removes_matching_containers(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    rollback = FakeContainer("exited", "lcp-project1-rollback-20260526010101")
    current = FakeContainer("running", "lcp-project1")
    monkeypatch.setattr(FakeAdapter, "containers", [rollback, current])
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "cleanup-rollbacks", "project1", "--yes"])

    assert result.exit_code == 0
    assert rollback.removed is True
    assert current.removed is False
    assert "removed rollback: lcp-project1-rollback-20260526010101" in result.output


def test_bridge_help_shows_common_actions() -> None:
    result = runner.invoke(cli.app, ["bridge", "-h"])

    assert result.exit_code == 0
    assert "lcp bridge <profile> run" in result.output
    assert "lcp bridge <profile> start" in result.output
    assert "lcp bridge <profile> bind-lark-cli" in result.output
    assert "Foreground QR/debug" in result.output
    assert "Background run" in result.output


def test_version_lock_show_lists_locked_dependencies() -> None:
    result = runner.invoke(cli.app, ["version-lock", "show"])

    assert result.exit_code == 0
    assert "LCP: 0.2.2" in result.output
    assert "feishu-claude-code-bridge:" in result.output
    assert "policy: controlled-fork" in result.output
    assert "repo: https://github.com/thiswind/feishu-claude-code-bridge-lcp-0.2" in result.output
    assert "tag: lcp-0.2.2" in result.output
    assert "lark-cli:" in result.output


def test_version_lock_verify_passes() -> None:
    result = runner.invoke(cli.app, ["version-lock", "verify"])

    assert result.exit_code == 0
    assert "ok: version_lock" in result.output


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
                        "gitIdentity": type("GitIdentity", (), {"name": "thiswind", "email": "thiswind@gmail.com"})(),
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
                        "gitIdentity": type("GitIdentity", (), {"name": "thiswind", "email": "thiswind@gmail.com"})(),
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
    FakeAdapter.container = FakeContainer()
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "ps"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "ps"]]


def test_bridge_proxies_unknown_options(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "run", "--skip-check-lark-cli"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "run", "--skip-check-lark-cli"]]


def test_bridge_start_uses_lcp_runtime_not_upstream_start(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    starts = []
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)
    monkeypatch.setattr(cli, "bind_lark_cli", lambda adapter, profile: ExecResult(0, "bound: cli_test"))
    monkeypatch.setattr(cli, "start_bridge", lambda adapter, profile: starts.append(profile.name) or type("Status", (), {"running": True, "pid": "123", "detail": ""})())

    result = runner.invoke(cli.app, ["bridge", "project1", "start"])

    assert result.exit_code == 0
    assert "bound: cli_test" in result.output
    assert "bridge started: 123" in result.output
    assert starts == ["project1"]
    assert calls == []


def test_bridge_start_fails_before_starting_bridge_when_lark_cli_bind_fails(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    starts = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "bind_lark_cli", lambda adapter, profile: ExecResult(2, "missing-config"))
    monkeypatch.setattr(cli, "start_bridge", lambda adapter, profile: starts.append(profile.name))

    result = runner.invoke(cli.app, ["bridge", "project1", "start"])

    assert result.exit_code == 1
    assert "missing-config" in result.output
    assert "error: lark-cli bind failed for profile: project1" in result.output
    assert "lcp bridge project1 run" in result.output
    assert starts == []


def test_bridge_bind_lark_cli_runs_manual_bind(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    binds = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "bind_lark_cli", lambda adapter, profile: binds.append(profile.name) or ExecResult(0, "bound: cli_test"))

    result = runner.invoke(cli.app, ["bridge", "project1", "bind-lark-cli"])

    assert result.exit_code == 0
    assert "bound: cli_test" in result.output
    assert binds == ["project1"]


def test_bridge_bind_lark_cli_failure_exits(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "bind_lark_cli", lambda adapter, profile: ExecResult(1, "app mismatch"))

    result = runner.invoke(cli.app, ["bridge", "project1", "bind-lark-cli"])

    assert result.exit_code == 1
    assert "app mismatch" in result.output
    assert "error: lark-cli bind failed for profile: project1" in result.output


def test_bridge_restart_binds_lark_cli_before_starting_bridge(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    events = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "stop_bridge", lambda adapter, profile: events.append("stop-bridge"))
    monkeypatch.setattr(cli, "bind_lark_cli", lambda adapter, profile: events.append("bind") or ExecResult(0, "bound: cli_test"))
    monkeypatch.setattr(cli, "start_bridge", lambda adapter, profile: events.append("start-bridge") or type("Status", (), {"running": True, "pid": "123", "detail": ""})())

    result = runner.invoke(cli.app, ["bridge", "project1", "restart"])

    assert result.exit_code == 0
    assert events == ["stop-bridge", "bind", "start-bridge"]
    assert "restarted: lcp-project1" in result.output


def test_profile_verify_checks_lark_cli_bot_identity(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    commands = []

    def fake_verify(adapter, profile, run_claude=True):
        from lcp.verify import verify_profile

        adapter.exec = lambda profile, command: commands.append(command) or ExecResult(0, "ok")
        return verify_profile(adapter, profile, run_claude=False)

    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli, "verify_profile", fake_verify)

    result = runner.invoke(cli.app, ["profile", "verify", "project1", "--no-run-claude"])

    assert result.exit_code == 0
    assert "ok: lark_cli_bot_identity" in result.output
    assert any(".lark-cli/lark-channel/config.json" in command for command in commands)


def test_bridge_run_stays_foreground_proxy(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = FakeContainer()
    calls = []
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)
    monkeypatch.setattr(cli.subprocess, "call", lambda command: calls.append(command) or 0)

    result = runner.invoke(cli.app, ["bridge", "project1", "run"])

    assert result.exit_code == 0
    assert calls == [["docker", "exec", "-it", "lcp-project1", "lark-channel-bridge", "run"]]


def test_missing_profile_shows_friendly_error(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["profile", "status", "missing"])

    assert result.exit_code == 1
    assert "error: profile not found: missing" in result.output
    assert "lcp profile list" in result.output


def test_missing_container_shows_friendly_error(monkeypatch, tmp_path: Path) -> None:
    store = make_store(tmp_path)
    FakeAdapter.container = None
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["profile", "status", "project1"])

    assert result.exit_code == 1
    assert "error: container not found: lcp-project1" in result.output
    assert "stale profile state" in result.output


def test_invalid_profile_name_shows_friendly_error(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["profile", "create", "bad/name", "--no-install"])

    assert result.exit_code == 1
    assert "error: invalid profile name" in result.output
    assert "letters, numbers" in result.output


def test_restore_missing_tar_shows_friendly_error(monkeypatch, tmp_path: Path) -> None:
    store = cli.LcpStore(tmp_path / ".lcp")
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["profile", "restore", "project1", "--image-tar", str(tmp_path / "missing.tar")])

    assert result.exit_code == 1
    assert "error: snapshot tar not found" in result.output
    assert "--image-tar" in result.output
