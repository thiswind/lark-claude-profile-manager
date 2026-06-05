from lcp.lark_cli import LARK_CLI_BOT_IDENTITY_CHECK, bind_lark_cli
from lcp.lark_cli_wrapper import LARK_CLI_WRAPPER_INSTALL
from lcp.models import default_profile


class FakeAdapter:
    def __init__(self):
        self.command = ""

    def exec(self, profile, command):
        self.command = command
        return type("Result", (), {"exit_code": 0, "output": "ok"})()


def test_lark_cli_wrapper_defaults_plain_cli_to_lark_channel() -> None:
    assert "LCP managed lark-cli wrapper" in LARK_CLI_WRAPPER_INSTALL
    assert "export LARK_CHANNEL=1" in LARK_CLI_WRAPPER_INSTALL
    assert "lark-cli.upstream" in LARK_CLI_WRAPPER_INSTALL


def test_lark_cli_bot_identity_check_uses_plain_wrapped_lark_cli() -> None:
    assert "grep -q 'LCP managed lark-cli wrapper'" in LARK_CLI_BOT_IDENTITY_CHECK
    json_status = "lark-cli auth status --json >/tmp/lcp-lark-cli-auth-status.out"
    plain_status = "lark-cli auth status >/tmp/lcp-lark-cli-auth-status.out"
    assert json_status in LARK_CLI_BOT_IDENTITY_CHECK
    assert plain_status in LARK_CLI_BOT_IDENTITY_CHECK
    assert LARK_CLI_BOT_IDENTITY_CHECK.index(json_status) < LARK_CLI_BOT_IDENTITY_CHECK.index(plain_status)
    assert "LARK_CHANNEL=1 lark-cli auth status" not in LARK_CLI_BOT_IDENTITY_CHECK


def test_bind_lark_cli_repairs_wrapper_and_strict_bot_mode(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    adapter = FakeAdapter()

    bind_lark_cli(adapter, profile)

    assert "LCP managed lark-cli wrapper" in adapter.command
    assert "lark-cli config bind --source lark-channel --identity bot-only --force" in adapter.command
    assert "lark-cli config default-as bot" in adapter.command
    assert "lark-cli config strict-mode bot" in adapter.command
