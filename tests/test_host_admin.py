from pathlib import Path

from lcp.host_admin import (
    CommandResult,
    bind_host_admin_lark_cli,
    bootstrap_commands,
    bootstrap_host_admin,
    host_admin_paths,
    load_host_admin_state,
)


class FakeRunner:
    def __init__(self):
        self.commands = []
        self.shell_commands = []

    def run(self, command, *, env=None, cwd=None):
        self.commands.append((command, env, cwd))
        return CommandResult(" ".join(command), 0, "ok")

    def run_shell(self, command, *, env=None, cwd=None):
        self.shell_commands.append((command, env, cwd))
        return CommandResult(command, 0, "ok")


def test_bootstrap_commands_install_host_claude_ark_helper_and_bridge() -> None:
    commands = bootstrap_commands()

    assert "npm install -g @anthropic-ai/claude-code" in commands
    assert any("lf3-static.bytednsdoc.com" in command for command in commands)
    assert any("@larksuite/cli@1.0.46" in command for command in commands)
    assert any("feishu-claude-code-bridge-lcp-0.2.git#4c9c47c5b32f6353bc9d86fcfc45813cdcdf96cc" in command for command in commands)


def test_bootstrap_dry_run_does_not_create_workspace(tmp_path: Path) -> None:
    paths = host_admin_paths(tmp_path / "LCP_HOST_ADMIN")

    results = bootstrap_host_admin(paths, dry_run=True, yes=False)

    assert len(results) == 4
    assert all(result.output == "dry-run" for result in results)
    assert not paths.root.exists()


def test_bootstrap_yes_creates_state_and_runs_installers(tmp_path: Path) -> None:
    paths = host_admin_paths(tmp_path / "LCP_HOST_ADMIN")
    runner = FakeRunner()

    results = bootstrap_host_admin(paths, dry_run=False, yes=True, runner=runner)

    assert len(results) == 4
    assert paths.home.exists()
    assert paths.workspace.exists()
    assert paths.logs.exists()
    assert load_host_admin_state(paths).path == str(paths.root)
    assert runner.shell_commands[0][0] == "npm install -g @anthropic-ai/claude-code"
    assert runner.shell_commands[0][1]["HOME"] == str(paths.home)
    assert runner.shell_commands[0][2] == paths.workspace


def test_bind_records_app_id_and_sets_bot_default(tmp_path: Path, monkeypatch) -> None:
    paths = host_admin_paths(tmp_path / "LCP_HOST_ADMIN")
    runner = FakeRunner()
    monkeypatch.setenv("LARK_APP_ID", "cli_host_admin")

    results = bind_host_admin_lark_cli(paths, runner=runner)

    assert len(results) == 2
    assert runner.commands[0][0] == ["lark-cli", "config", "bind", "--source", "lark-channel", "--identity", "bot-only", "--force"]
    assert runner.commands[1][0] == ["lark-cli", "config", "default-as", "bot"]
    state = load_host_admin_state(paths)
    assert state.botAppId == "cli_host_admin"
    assert state.larkCliBound is True
