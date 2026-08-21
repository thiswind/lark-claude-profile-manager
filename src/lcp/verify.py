from dataclasses import dataclass
import shlex

from .bridge import bridge_status
from .docker_adapter import DockerAdapter
from .integrations.service import IntegrationService
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
    runtime_status = bridge_status(adapter, profile)
    checks.append(CheckResult("bridge_runtime", runtime_status.running, runtime_status.detail))

    integration_service = IntegrationService(adapter.store)
    for name in sorted(profile.integrations.providers):
        state = profile.integrations.providers[name]
        if not state.desired.enabled:
            continue
        commands = integration_service.verify_commands(profile, name)
        if not commands:
            checks.append(CheckResult(f"integration:{name}", True, "no verification command"))
            continue
        outputs = []
        all_ok = True
        for command in commands:
            result = adapter.exec(profile, command)
            if result.exit_code != 0:
                all_ok = False
            outputs.append(result.output.strip())
        checks.append(CheckResult(f"integration:{name}", all_ok, "; ".join(outputs)))

    return checks


def _expected_git_identity(profile: Profile) -> tuple[str | None, str | None]:
    state = profile.integrations.providers.get("git")
    if state and state.desired.enabled:
        user_name = state.desired.config.get("user.name")
        user_email = state.desired.config.get("user.email")
        if user_name or user_email:
            return user_name, user_email
    return profile.gitIdentity.name, profile.gitIdentity.email


def _git_identity_check(profile: Profile) -> str:
    expected_name, expected_email = _expected_git_identity(profile)
    name_check = 'test -n "$name" || { echo "missing git user.name"; exit 1; }'
    email_check = 'test -n "$email" || { echo "missing git user.email"; exit 1; }'
    if expected_name:
        name_check = f"test \"$name\" = {shlex.quote(expected_name)} || {{ echo \"git user.name mismatch: expected {shlex.quote(expected_name)} got $name\"; exit 1; }}"
    if expected_email:
        email_check = f"test \"$email\" = {shlex.quote(expected_email)} || {{ echo \"git user.email mismatch: expected {shlex.quote(expected_email)} got $email\"; exit 1; }}"
    return f"""
name=$(git config --global --get user.name || true)
email=$(git config --global --get user.email || true)
case "$name $email" in
  *[Cc]laude*|*[Aa]nthropic*) echo "forbidden AI contributor identity: $name <$email>"; exit 1 ;;
esac
{name_check} && {email_check}
""".strip()
