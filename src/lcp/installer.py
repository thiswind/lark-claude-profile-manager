from .docker_adapter import DockerAdapter, ExecResult
from .models import Profile


CLAUDE_NATIVE_FIXUP = "cd $(npm root -g)/@anthropic-ai/claude-code && pkg=$(case $(node -p 'process.arch') in x64) echo @anthropic-ai/claude-code-linux-x64 ;; arm64) echo @anthropic-ai/claude-code-linux-arm64 ;; esac) && if [ -n \"$pkg\" ]; then npm install \"$pkg\"; fi && node install.cjs"


def install_runtime(adapter: DockerAdapter, profile: Profile) -> list[ExecResult]:
    user = profile.container.user
    setup_commands = [
        f"mkdir -p /cache/npm /cache/tmp /cache/pnpm /cache/pip && chown -R {user.uid}:{user.gid} /cache /logs {user.home}",
    ]
    user_commands = [
        "mkdir -p ~/.npm-global /cache/npm /cache/tmp",
        "npm config set cache /cache/npm --global",
        "npm install -g @anthropic-ai/claude-code --include=optional",
        CLAUDE_NATIVE_FIXUP,
        "npm install -g @larksuite/cli",
        "npm install -g lark-channel-bridge",
    ]
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
