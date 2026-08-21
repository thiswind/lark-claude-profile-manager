import os
import subprocess

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
    assert "lark-cli auth status --verify" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "bridge.profiles?.[activeProfile]" in LARK_CLI_BOT_IDENTITY_CHECK
    assert LARK_CLI_BOT_IDENTITY_CHECK.index(json_status) < LARK_CLI_BOT_IDENTITY_CHECK.index(plain_status)
    assert LARK_CLI_BOT_IDENTITY_CHECK.index(plain_status) < LARK_CLI_BOT_IDENTITY_CHECK.index("lark-cli auth status --verify")
    assert "LARK_CHANNEL=1 lark-cli auth status" not in LARK_CLI_BOT_IDENTITY_CHECK


def test_lark_cli_bot_identity_check_includes_real_api_probe() -> None:
    """Issue #20: --verify checks the token, but a real API probe catches
    app-credential-level failures (invalid_client / code 10003) that --verify
    may miss when the bot token is still cached."""
    assert "lark-cli im +chat-list --page-size 1" in LARK_CLI_BOT_IDENTITY_CHECK
    assert "/tmp/lcp-lark-cli-api-probe.out" in LARK_CLI_BOT_IDENTITY_CHECK
    # the grep ensures the JSON output contains "ok": true, not just exit code
    assert '"ok"' in LARK_CLI_BOT_IDENTITY_CHECK
    # API probe must come after --verify and before the node config parser
    verify_idx = LARK_CLI_BOT_IDENTITY_CHECK.index("lark-cli auth status --verify")
    probe_idx = LARK_CLI_BOT_IDENTITY_CHECK.index("lark-cli im +chat-list")
    node_idx = LARK_CLI_BOT_IDENTITY_CHECK.index("node -e")
    assert verify_idx < probe_idx < node_idx


def test_lark_cli_wrapper_migrates_old_sample_wrapper_to_bin_target(tmp_path) -> None:
    bin_dir = tmp_path / "prefix" / "bin"
    bin_dir.mkdir(parents=True)
    cli = bin_dir / "lark-cli"
    cli_bin = bin_dir / "lark-cli.bin"
    cli.write_text(
        "#!/usr/bin/env bash\n# LCP default Lark Channel wrapper\nexec \"${BASH_SOURCE[0]}.bin\" \"$@\"\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)
    cli_bin.write_text("#!/usr/bin/env bash\necho real-lark-cli \"$@\"\n", encoding="utf-8")
    cli_bin.chmod(0o755)

    env = os.environ.copy()
    env["NPM_CONFIG_PREFIX"] = str(tmp_path / "prefix")
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    install = subprocess.run(["bash", "-lc", LARK_CLI_WRAPPER_INSTALL], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    run = subprocess.run(["bash", "-lc", "lark-cli --version"], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    assert install.returncode == 0, install.stdout
    assert run.returncode == 0, run.stdout
    assert run.stdout.strip() == "real-lark-cli --version"
    assert "LCP managed lark-cli wrapper" in cli.read_text(encoding="utf-8")
    assert (bin_dir / "lark-cli.upstream").is_symlink()
    assert (bin_dir / "lark-cli.upstream").resolve() == cli_bin


def test_lark_cli_wrapper_reports_old_sample_wrapper_missing_bin(tmp_path) -> None:
    bin_dir = tmp_path / "prefix" / "bin"
    bin_dir.mkdir(parents=True)
    cli = bin_dir / "lark-cli"
    cli.write_text(
        "#!/usr/bin/env bash\n# LCP default Lark Channel wrapper\nexec \"${BASH_SOURCE[0]}.bin\" \"$@\"\n",
        encoding="utf-8",
    )
    cli.chmod(0o755)

    env = os.environ.copy()
    env["NPM_CONFIG_PREFIX"] = str(tmp_path / "prefix")
    env["PATH"] = f"{bin_dir}:{env.get('PATH', '')}"
    result = subprocess.run(["bash", "-lc", LARK_CLI_WRAPPER_INSTALL], env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    assert result.returncode == 1
    assert "old lark-cli wrapper detected but lark-cli.bin is missing" in result.stdout
    assert not (bin_dir / "lark-cli.upstream").exists()


def test_bind_lark_cli_repairs_wrapper_and_strict_bot_mode(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    adapter = FakeAdapter()

    bind_lark_cli(adapter, profile)

    assert "LCP managed lark-cli wrapper" in adapter.command
    assert "config.profiles?.[activeProfile]?.accounts?.app" in adapter.command
    assert "lark-cli config bind --source lark-channel --identity bot-only --force" in adapter.command
    assert "lark-cli config default-as bot" in adapter.command
    assert "lark-cli config strict-mode bot" in adapter.command


def test_bind_lark_cli_schema_sync_js_survives_escaping(tmp_path) -> None:
    """Issue #26: the schema-sync node script must survive shlex quoting intact.

    The JS payload is embedded in a Python string; if it is not a raw string,
    the JS "\\n" literal becomes a real newline inside node -e, producing a
    SyntaxError before lark-cli binding ever runs.
    """
    import shlex

    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    adapter = FakeAdapter()

    bind_lark_cli(adapter, profile)

    marker = "node -e "
    segment = adapter.command[adapter.command.index(marker):]
    tokens = shlex.split(segment)
    assert tokens[0] == "node" and tokens[1] == "-e"
    js = tokens[2]

    assert '+ "\\n"' in js, "JS newline literal must remain escaped inside the node payload"
    assert 'writeFileSync(path, JSON.stringify(config, null, 2) + "\\n")' in js
    # the payload must not contain a bare real newline inside the string literal
    assert 'JSON.stringify(config, null, 2) + "\n"' not in js
