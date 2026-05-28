from lcp.bridge import bridge_status, start_bridge, stop_bridge
from lcp.cli import _bind_lark_cli_or_exit
from lcp.lark_cli import LARK_CLI_BOT_IDENTITY_CHECK
from lcp.models import default_profile


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.commands = []

    def exec(self, profile, command):
        self.commands.append(command)
        output = self.outputs.pop(0) if self.outputs else "stopped"
        if isinstance(output, tuple):
            return FakeResult(output[0], output[1])
        return FakeResult(0, output)


class FakeResult:
    def __init__(self, exit_code, output):
        self.exit_code = exit_code
        self.output = output


def make_profile(tmp_path):
    return default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)


def test_bridge_status_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["running:123"])

    status = bridge_status(adapter, profile)

    assert status.running
    assert status.pid == "123"


def test_bridge_status_unhealthy_supervisor_is_not_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["unhealthy:123:no bridge run process"])

    status = bridge_status(adapter, profile)

    assert not status.running
    assert status.pid is None
    assert "unhealthy" in status.detail


def test_start_bridge_skips_when_already_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["running:123"])

    status = start_bridge(adapter, profile)

    assert status.running
    assert status.pid == "123"
    assert len(adapter.commands) == 1


def test_start_bridge_launches_supervisor(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", "started:456", "running:456"])

    status = start_bridge(adapter, profile)

    assert status.running
    assert status.pid == "456"
    assert "if [ ! -s \"$HOME/.lark-channel/config.json\" ]" in adapter.commands[1]
    assert "nohup bash -lc" in adapter.commands[1]
    assert "lark-channel-bridge run" in adapter.commands[1]
    assert "for attempt in $(seq 1 60)" in adapter.commands[1]
    assert "no bridge run process" in adapter.commands[1]
    assert "lark-channel-bridge start" not in adapter.commands[1]


def test_lark_cli_bot_identity_check_enforces_bot_defaults() -> None:
    assert "lark-cli auth status --json" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "identity mismatch: defaultAs" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "identity mismatch: identity" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "bot identity not ready" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "user" not in LARK_CLI_BOT_IDENTITY_CHECK


def test_bind_lark_cli_skips_when_already_bound(tmp_path, capsys) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["bot-bound: cli_123"])

    _bind_lark_cli_or_exit(adapter, profile)

    assert "bot-bound: cli_123" in capsys.readouterr().out
    assert len(adapter.commands) == 1
    assert "lark-cli config bind" not in adapter.commands[0]


def test_bind_lark_cli_repairs_to_bot_only(tmp_path, capsys) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter([(1, "identity mismatch: defaultAs=user"), "bound: cli_123"])

    _bind_lark_cli_or_exit(adapter, profile)

    assert "bound: cli_123" in capsys.readouterr().out
    assert len(adapter.commands) == 2
    assert "LARK_CHANNEL=1 lark-cli config bind --source lark-channel --identity bot-only --force" in adapter.commands[1]
    assert "LARK_CHANNEL=1 lark-cli config default-as bot" in adapter.commands[1]


def test_start_bridge_fails_when_config_is_missing(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", (2, "missing-config: run 'lcp bridge project1 run' first")])

    status = start_bridge(adapter, profile)

    assert not status.running
    assert status.pid is None
    assert "missing-config" in status.detail


def test_stop_bridge_kills_supervisor_and_bridge(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", "stopped"])

    status = stop_bridge(adapter, profile)

    assert not status.running
    assert "pkill -f '^node .*/lark-channel-bridge run($| )'" in adapter.commands[0]
