from dataclasses import dataclass

from .docker_adapter import DockerAdapter
from .lark_cli import LARK_CLI_BOUND_CHECK
from .models import Profile


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str


def verify_profile(adapter: DockerAdapter, profile: Profile, run_claude: bool = True) -> list[CheckResult]:
    checks: list[CheckResult] = []
    user = profile.container.user
    desktop = profile.mounts.desktop.containerPath

    def run(name: str, command: str) -> None:
        result = adapter.exec(profile, command)
        checks.append(CheckResult(name, result.exit_code == 0, result.output.strip()))

    run("ubuntu", "grep -E 'NAME=\"Ubuntu\"|VERSION_ID=\"24.04\"' /etc/os-release")
    run("non_root_user", f"test \"$(id -u)\" = \"{user.uid}\" && test \"$(id -g)\" = \"{user.gid}\" && test \"$(whoami)\" = \"{user.name}\"")
    run("home", f"test \"$HOME\" = \"{user.home}\"")
    run("desktop_mount", f"test -d {desktop} && touch {desktop}/lcp-mount-test.txt")
    run("claude_config", f"test -d {user.home}/.claude || test -f {user.home}/.claude.json")
    run("node", "node --version | grep '^v24\\.'")
    run("npm", "npm --version")
    run("claude_version", "claude --version")
    if run_claude:
        run("claude_non_interactive", "claude -p 'reply ok' --output-format stream-json --verbose")
    run("lark_cli", "lark-cli --version")
    run("lark_cli_bound", LARK_CLI_BOUND_CHECK)
    run("bridge_version", "lark-channel-bridge --version")
    run("bridge_help", "lark-channel-bridge --help >/tmp/lcp-bridge-help.txt && test -s /tmp/lcp-bridge-help.txt")

    return checks
