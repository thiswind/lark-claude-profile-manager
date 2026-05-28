from dataclasses import dataclass
import shlex

from .docker_adapter import DockerAdapter
from .lark_cli import LARK_CLI_BOT_IDENTITY_CHECK
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
    run("git_identity", _git_identity_check(profile))
    run("claude_version", "claude --version")
    if run_claude:
        run("claude_non_interactive", "claude -p 'reply ok' --output-format stream-json --verbose")
    run("lark_cli", "lark-cli --version")
    run("lark_cli_bot_identity", LARK_CLI_BOT_IDENTITY_CHECK)
    run("bridge_version", "lark-channel-bridge --version")
    run("bridge_help", "lark-channel-bridge --help >/tmp/lcp-bridge-help.txt && test -s /tmp/lcp-bridge-help.txt")

    return checks


def _git_identity_check(profile: Profile) -> str:
    expected = profile.gitIdentity
    name_check = 'test -n "$name"'
    email_check = 'test -n "$email"'
    if expected.name:
        name_check = f"test \"$name\" = {shlex.quote(expected.name)}"
    if expected.email:
        email_check = f"test \"$email\" = {shlex.quote(expected.email)}"
    return f"""
name=$(git config --global --get user.name || true)
email=$(git config --global --get user.email || true)
case "$name $email" in
  *[Cc]laude*|*[Aa]nthropic*) echo "forbidden AI contributor identity: $name <$email>"; exit 1 ;;
esac
{name_check} && {email_check}
""".strip()
