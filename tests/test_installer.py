import shlex

from lcp.installer import CLAUDE_NATIVE_FIXUP, NPM_CACHE_ARG, controlled_dependency_pack_install_command, git_identity_setup_command, install_runtime
from lcp.lark_cli_wrapper import LARK_CLI_WRAPPER_INSTALL
from lcp.version_lock import dependency_npm_install_spec
from lcp.models import default_profile


class FakeAdapter:
    def __init__(self):
        self.root_commands = []
        self.user_commands = []

    def exec_root(self, profile, command):
        self.root_commands.append(command)
        return FakeResult(0)

    def exec(self, profile, command):
        self.user_commands.append(command)
        return FakeResult(0)


class FakeResult:
    def __init__(self, exit_code):
        self.exit_code = exit_code
        self.output = ""


def test_install_runtime_runs_claude_native_fixup(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    adapter = FakeAdapter()

    results = install_runtime(adapter, profile)

    assert len(results) == 8
    assert not any("git config --global user.name" in command for command in adapter.user_commands)
    claude_install = f"npm install -g {dependency_npm_install_spec('@anthropic-ai/claude-code')} --include=optional {NPM_CACHE_ARG}"
    assert claude_install in adapter.user_commands
    assert CLAUDE_NATIVE_FIXUP in adapter.user_commands
    assert adapter.user_commands.index(CLAUDE_NATIVE_FIXUP) == adapter.user_commands.index(claude_install) + 1
    lark_cli_install = f"npm install -g {dependency_npm_install_spec('@larksuite/cli')} {NPM_CACHE_ARG}"
    assert lark_cli_install in adapter.user_commands
    assert LARK_CLI_WRAPPER_INSTALL in adapter.user_commands
    assert adapter.user_commands.index(LARK_CLI_WRAPPER_INSTALL) == adapter.user_commands.index(lark_cli_install) + 1
    bridge_install = controlled_dependency_pack_install_command("lark-channel-bridge", "/cache/tmp/lark-channel-bridge.tgz")
    assert bridge_install in adapter.user_commands
    assert not any("npm install -g git+https://github.com/thiswind/feishu-claude-code-bridge-lcp-0.2" in command for command in adapter.user_commands)
    assert "npm install --include=dev --cache /cache/npm" in bridge_install
    assert "npm pack --pack-destination /cache/tmp" in bridge_install


def test_install_runtime_configures_profile_git_identity(tmp_path) -> None:
    profile = default_profile(
        "project1",
        tmp_path / "Desktop",
        [],
        "amd64",
        "thiswind",
        1000,
        1000,
        git_name="thiswind",
        git_email="thiswind@gmail.com",
    )
    adapter = FakeAdapter()

    results = install_runtime(adapter, profile)

    assert len(results) == 9
    assert git_identity_setup_command(profile) in adapter.user_commands
