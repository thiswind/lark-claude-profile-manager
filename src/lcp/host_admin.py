from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import shlex
import subprocess

from pydantic import BaseModel

from .store import LcpStore
from .version_lock import dependency_npm_install_spec

HOST_ADMIN_DIR_NAME = "LCP_HOST_ADMIN"
ARK_HELPER_INSTALL_URL = "https://lf3-static.bytednsdoc.com/obj/eden-cn/ylwslo-yrh/ljhwZthlaukjlkulzlp/install.sh"


class HostAdminState(BaseModel):
    schemaVersion: int = 1
    path: str
    home: str
    workspace: str
    logs: str
    state: str
    createdAt: str
    botAppId: str | None = None
    bridgeConfigured: bool = False
    larkCliBound: bool = False


@dataclass(frozen=True)
class HostAdminPaths:
    root: Path
    home: Path
    workspace: Path
    logs: Path
    state: Path
    bin: Path

    @property
    def state_file(self) -> Path:
        return self.state / "host-admin.json"


@dataclass(frozen=True)
class CommandResult:
    command: str
    exit_code: int
    output: str


class HostAdminCommandRunner:
    def run(self, command: list[str], *, env: dict[str, str] | None = None, cwd: Path | None = None) -> CommandResult:
        completed = subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return CommandResult(" ".join(shlex.quote(part) for part in command), completed.returncode, completed.stdout)

    def run_shell(self, command: str, *, env: dict[str, str] | None = None, cwd: Path | None = None) -> CommandResult:
        completed = subprocess.run(command, shell=True, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return CommandResult(command, completed.returncode, completed.stdout)


def default_host_admin_path(store: LcpStore | None = None) -> Path:
    store = store or LcpStore()
    if store.config_file.exists():
        desktop = Path(store.load_config().desktop.hostPath)
    else:
        desktop = Path.home() / "Desktop"
    return desktop / "Projects" / HOST_ADMIN_DIR_NAME


def host_admin_paths(path: Path | None = None, store: LcpStore | None = None) -> HostAdminPaths:
    root = path or default_host_admin_path(store)
    return HostAdminPaths(
        root=root,
        home=root / "home",
        workspace=root / "workspace",
        logs=root / "logs",
        state=root / "state",
        bin=root / "bin",
    )


def ensure_host_admin_dirs(paths: HostAdminPaths) -> None:
    for path in [paths.root, paths.home, paths.workspace, paths.logs, paths.state, paths.bin]:
        path.mkdir(parents=True, exist_ok=True)


def load_host_admin_state(paths: HostAdminPaths) -> HostAdminState | None:
    if not paths.state_file.exists():
        return None
    return HostAdminState.model_validate_json(paths.state_file.read_text(encoding="utf-8"))


def save_host_admin_state(paths: HostAdminPaths, state: HostAdminState) -> None:
    paths.state_file.write_text(json.dumps(state.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def initial_host_admin_state(paths: HostAdminPaths) -> HostAdminState:
    return HostAdminState(
        path=str(paths.root),
        home=str(paths.home),
        workspace=str(paths.workspace),
        logs=str(paths.logs),
        state=str(paths.state),
        createdAt=datetime.now(timezone.utc).isoformat(),
    )


def host_admin_env(paths: HostAdminPaths) -> dict[str, str]:
    env = os.environ.copy()
    env["HOME"] = str(paths.home)
    env["LCP_HOST_ADMIN"] = "1"
    env["PATH"] = f"{paths.bin}:{env.get('PATH', '')}"
    return env


def bootstrap_commands() -> list[str]:
    return [
        "npm install -g @anthropic-ai/claude-code",
        f"curl -fsSL {ARK_HELPER_INSTALL_URL} | sh",
        f"npm install -g {shlex.quote(dependency_npm_install_spec('@larksuite/cli'))}",
        f"npm install -g {shlex.quote(dependency_npm_install_spec('lark-channel-bridge'))}",
    ]


def bootstrap_host_admin(paths: HostAdminPaths, *, dry_run: bool, yes: bool, runner: HostAdminCommandRunner | None = None) -> list[CommandResult]:
    commands = bootstrap_commands()
    if dry_run:
        return [CommandResult(command, 0, "dry-run") for command in commands]
    ensure_host_admin_dirs(paths)
    state = load_host_admin_state(paths) or initial_host_admin_state(paths)
    save_host_admin_state(paths, state)
    if not yes:
        raise RuntimeError("host-admin bootstrap requires --yes")
    runner = runner or HostAdminCommandRunner()
    results: list[CommandResult] = []
    for command in commands:
        result = runner.run_shell(command, env=host_admin_env(paths), cwd=paths.workspace)
        results.append(result)
        if result.exit_code != 0:
            break
    return results


def tool_status(tool: str, runner: HostAdminCommandRunner | None = None, paths: HostAdminPaths | None = None) -> CommandResult:
    runner = runner or HostAdminCommandRunner()
    env = host_admin_env(paths) if paths else None
    return runner.run([tool, "--version"], env=env)


def bind_host_admin_lark_cli(paths: HostAdminPaths, app_id: str | None = None, *, runner: HostAdminCommandRunner | None = None) -> list[CommandResult]:
    ensure_host_admin_dirs(paths)
    state = load_host_admin_state(paths) or initial_host_admin_state(paths)
    state.botAppId = app_id or os.environ.get("LARK_APP_ID") or state.botAppId
    save_host_admin_state(paths, state)
    runner = runner or HostAdminCommandRunner()
    env = host_admin_env(paths)
    commands = [
        ["lark-cli", "config", "bind", "--source", "lark-channel", "--identity", "bot-only", "--force"],
        ["lark-cli", "config", "default-as", "bot"],
    ]
    results: list[CommandResult] = []
    for command in commands:
        result = runner.run(command, env=env, cwd=paths.workspace)
        results.append(result)
        if result.exit_code != 0:
            return results
    state.larkCliBound = True
    save_host_admin_state(paths, state)
    return results


def start_host_admin_bridge(paths: HostAdminPaths, *, runner: HostAdminCommandRunner | None = None) -> CommandResult:
    ensure_host_admin_dirs(paths)
    runner = runner or HostAdminCommandRunner()
    log_file = paths.logs / "bridge.log"
    command = f"nohup lark-channel-bridge run >> {shlex.quote(str(log_file))} 2>&1 & echo $!"
    return runner.run_shell(command, env=host_admin_env(paths), cwd=paths.workspace)
