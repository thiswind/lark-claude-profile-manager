import shlex

from .docker_adapter import DockerAdapter, ExecResult
from .models import Profile
from .version_lock import dependency_npm_install_spec


NPM_CACHE_ARG = "--cache /cache/npm"
CLAUDE_NATIVE_FIXUP = "cd $(npm root -g)/@anthropic-ai/claude-code && pkg=$(case $(node -p 'process.arch') in x64) echo @anthropic-ai/claude-code-linux-x64 ;; arm64) echo @anthropic-ai/claude-code-linux-arm64 ;; esac) && if [ -n \"$pkg\" ]; then npm install \"$pkg\" --cache /cache/npm; fi && node install.cjs"


def git_identity_setup_command(profile: Profile) -> str | None:
    identity = profile.gitIdentity
    if not identity.name or not identity.email:
        return None
    return f"git config --global user.name {shlex.quote(identity.name)} && git config --global user.email {shlex.quote(identity.email)}"


def install_runtime(adapter: DockerAdapter, profile: Profile) -> list[ExecResult]:
    user = profile.container.user
    setup_commands = [
        f"mkdir -p /cache/npm /cache/tmp /cache/pnpm /cache/pip /logs {user.home}/.npm-global {user.home}/.local/share {user.home}/.config {user.home}/.cache && chown -R {user.uid}:{user.gid} /cache /logs {user.home}/.npm-global {user.home}/.cache && chown {user.uid}:{user.gid} {user.home} {user.home}/.local {user.home}/.local/share {user.home}/.config",
    ]
    user_commands = [
        "mkdir -p ~/.npm-global /cache/npm /cache/tmp",
        "npm config set cache /cache/npm --global",
        f"npm install -g {shlex.quote(dependency_npm_install_spec('@anthropic-ai/claude-code'))} --include=optional {NPM_CACHE_ARG}",
        CLAUDE_NATIVE_FIXUP,
        f"npm install -g {shlex.quote(dependency_npm_install_spec('@larksuite/cli'))} {NPM_CACHE_ARG}",
        f"npm install -g {shlex.quote(dependency_npm_install_spec('lark-channel-bridge'))} {NPM_CACHE_ARG}",
    ]
    git_identity_command = git_identity_setup_command(profile)
    if git_identity_command:
        user_commands.insert(1, git_identity_command)
    results: list[ExecResult] = []
    for command in setup_commands:
        result = adapter.exec_root(profile, command)
        results.append(result)
        if result.exit_code != 0:
            return results
    for command in user_commands:
        result = adapter.exec(profile, command)
        results.append(result)
        if result.exit_code != 0:
            break
    return results
