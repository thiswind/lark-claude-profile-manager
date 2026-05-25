from lcp.installer import CLAUDE_NATIVE_FIXUP, NPM_CACHE_ARG, git_identity_setup_command, install_runtime
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

    assert len(results) == 7
    assert not any("git config --global user.name" in command for command in adapter.user_commands)
    claude_install = f"npm install -g @anthropic-ai/claude-code --include=optional {NPM_CACHE_ARG}"
    assert claude_install in adapter.user_commands
    assert CLAUDE_NATIVE_FIXUP in adapter.user_commands
    assert adapter.user_commands.index(CLAUDE_NATIVE_FIXUP) == adapter.user_commands.index(claude_install) + 1
    assert f"npm install -g @larksuite/cli {NPM_CACHE_ARG}" in adapter.user_commands
    assert f"npm install -g lark-channel-bridge {NPM_CACHE_ARG}" in adapter.user_commands


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

    assert len(results) == 8
    assert git_identity_setup_command(profile) in adapter.user_commands
