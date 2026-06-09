import json
import shlex

from .docker_adapter import DockerAdapter, ExecResult
from .lark_cli_wrapper import LARK_CLI_WRAPPER_INSTALL
from .models import Profile
from .version_lock import dependency_npm_install_spec, find_dependency


NPM_CACHE_ARG = "--cache /cache/npm"
CLAUDE_NATIVE_FIXUP = "cd $(npm root -g)/@anthropic-ai/claude-code && pkg=$(case $(node -p 'process.arch') in x64) echo @anthropic-ai/claude-code-linux-x64 ;; arm64) echo @anthropic-ai/claude-code-linux-arm64 ;; esac) && if [ -n \"$pkg\" ]; then npm install \"$pkg\" --cache /cache/npm; fi && node install.cjs"


def controlled_dependency_pack_install_command(identifier: str, package_file: str) -> str | None:
    dependency = find_dependency(identifier)
    if not dependency.controlled:
        return None
    if not dependency.package:
        raise ValueError(f"{dependency.name}: controlled dependency has no npm package")
    source_dir = f"/cache/tmp/{dependency.package}-src"
    repo = str(dependency.controlled.repo).rstrip("/")
    package_name = json.dumps(dependency.package)
    pack_output = f"/cache/tmp/{dependency.package}.pack.out"
    pack_parser = "".join([
        "const fs=require('fs');",
        "const text=fs.readFileSync(process.argv[1],'utf8');",
        "const start=text.lastIndexOf('\\n[')>=0?text.lastIndexOf('\\n[')+1:text.indexOf('[');",
        "if(start<0){throw new Error('missing npm pack JSON array');}",
        "const p=JSON.parse(text.slice(start).trim())[0];",
        f"if(!p||p.name!=={package_name}){{process.exit(1);}}",
        "process.stdout.write(p.filename);",
    ])
    return " && ".join([
        f"rm -rf {shlex.quote(source_dir)} {shlex.quote(package_file)} {shlex.quote(pack_output)}",
        f"git clone {shlex.quote(repo + '.git')} {shlex.quote(source_dir)}",
        f"cd {shlex.quote(source_dir)}",
        f"git checkout {shlex.quote(dependency.controlled.commit)}",
        "npm install --include=dev --cache /cache/npm",
        "npm run build",
        f"npm pack --pack-destination /cache/tmp --cache /cache/npm --json > {shlex.quote(pack_output)}",
        f"node -e {shlex.quote(pack_parser)} {shlex.quote(pack_output)} > /cache/tmp/{dependency.package}.pack",
        f"mv /cache/tmp/$(cat /cache/tmp/{dependency.package}.pack) {shlex.quote(package_file)}",
        f"npm install -g {shlex.quote(package_file)} {NPM_CACHE_ARG}",
    ])


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
    bridge_package_file = "/cache/tmp/lark-channel-bridge.tgz"
    bridge_install = controlled_dependency_pack_install_command("lark-channel-bridge", bridge_package_file)
    if bridge_install is None:
        bridge_install = f"npm install -g {shlex.quote(dependency_npm_install_spec('lark-channel-bridge'))} {NPM_CACHE_ARG}"
    user_commands = [
        "mkdir -p ~/.npm-global /cache/npm /cache/tmp",
        "npm config set cache /cache/npm --global",
        f"npm install -g {shlex.quote(dependency_npm_install_spec('@anthropic-ai/claude-code'))} --include=optional {NPM_CACHE_ARG}",
        CLAUDE_NATIVE_FIXUP,
        f"npm install -g {shlex.quote(dependency_npm_install_spec('@larksuite/cli'))} {NPM_CACHE_ARG}",
        LARK_CLI_WRAPPER_INSTALL,
        bridge_install,
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
