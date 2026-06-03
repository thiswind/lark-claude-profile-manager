from lcp.lark_cli import LARK_CLI_BOT_IDENTITY_CHECK
from lcp.lark_cli_wrapper import LARK_CLI_DEFAULT_CHANNEL_WRAPPER


def test_lark_cli_wrapper_defaults_to_lark_channel() -> None:
    assert "LCP default Lark Channel wrapper" in LARK_CLI_DEFAULT_CHANNEL_WRAPPER
    assert "export LARK_CHANNEL=1" in LARK_CLI_DEFAULT_CHANNEL_WRAPPER
    assert 'exec "${BASH_SOURCE[0]}.bin" "$@"' in LARK_CLI_DEFAULT_CHANNEL_WRAPPER


def test_lark_cli_identity_check_uses_plain_agent_command() -> None:
    assert "lark-cli auth status --json" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "LARK_CHANNEL=1 lark-cli auth status" not in LARK_CLI_BOT_IDENTITY_CHECK
    assert "lark-cli config strict-mode | grep -q 'bot'" in LARK_CLI_BOT_IDENTITY_CHECK
