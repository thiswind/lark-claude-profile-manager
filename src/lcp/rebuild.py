from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from .bridge import bridge_status, start_bridge, stop_bridge
from .docker_adapter import DockerAdapter
from .models import Profile
from .store import LcpStore


class ClaudeContinuityCheck(BaseModel):
    safe: bool
    hostClaudeDir: str | None = None
    hostClaudeJson: str | None = None
    reasons: list[str] = Field(default_factory=list)


class ProfileRebuildPlan(BaseModel):
    profile: str
    container: str
    currentStatus: str
    bridgeRunning: bool
    currentImage: str
    runtimeImage: str
    claudeContinuity: ClaudeContinuityCheck
    preservedMounts: list[str] = Field(default_factory=list)
    verification: list[str] = Field(default_factory=list)


class ProfileRebuildResult(BaseModel):
    rollbackContainer: str
    bridgeRestored: bool
    verification: list[str] = Field(default_factory=list)


class RebuildError(RuntimeError):
    def __init__(self, message: str, recovery: list[str] | None = None):
        super().__init__(message)
        self.recovery = recovery or []


def check_claude_continuity(profile: Profile) -> ClaudeContinuityCheck:
    claude = profile.mounts.claude
    reasons: list[str] = []
    if not claude.shareConfig:
        reasons.append("Claude config sharing is disabled")
        return ClaudeContinuityCheck(safe=False, reasons=reasons)
    if not claude.hostClaudeDir:
        reasons.append("hostClaudeDir is not configured")
    elif not Path(claude.hostClaudeDir).is_dir():
        reasons.append(f"hostClaudeDir not found: {claude.hostClaudeDir}")
    elif not (Path(claude.hostClaudeDir) / "projects").is_dir():
        reasons.append(f"Claude projects directory not found: {Path(claude.hostClaudeDir) / 'projects'}")
    if not claude.hostClaudeJson:
        reasons.append("hostClaudeJson is not configured")
    elif not Path(claude.hostClaudeJson).is_file():
        reasons.append(f"hostClaudeJson not found: {claude.hostClaudeJson}")
    return ClaudeContinuityCheck(
        safe=not reasons,
        hostClaudeDir=claude.hostClaudeDir,
        hostClaudeJson=claude.hostClaudeJson,
        reasons=reasons,
    )


def plan_profile_rebuild(store: LcpStore, adapter: DockerAdapter, profile: Profile) -> ProfileRebuildPlan:
    container = adapter.get_container_or_none(profile)
    status = container.status if container else "missing"
    bridge = bridge_status(adapter, profile).running if container else False
    user_home = profile.container.user.home
    preserved = [
        f"{profile.mounts.desktop.hostPath} -> {profile.mounts.desktop.containerPath}",
        f"{store.profile_dir(profile.name) / 'lark-channel'} -> {user_home}/.lark-channel",
        f"{store.profile_dir(profile.name) / 'lark-cli'} -> {user_home}/.lark-cli",
        f"{store.profile_dir(profile.name) / 'logs'} -> /logs",
    ]
    claude = profile.mounts.claude
    if claude.shareConfig:
        preserved.append(f"{claude.hostClaudeDir} -> {user_home}/.claude")
        preserved.append(f"{claude.hostClaudeJson} -> {user_home}/.claude.json")
    return ProfileRebuildPlan(
        profile=profile.name,
        container=profile.container.name,
        currentStatus=status,
        bridgeRunning=bridge,
        currentImage=profile.container.image,
        runtimeImage=store.load_runtime_manifest().runtimeImage,
        claudeContinuity=check_claude_continuity(profile),
        preservedMounts=preserved,
        verification=[
            "test -d ~/.claude/projects",
            "claude --version",
            "lark-cli --version",
            "lark-channel-bridge --version",
        ],
    )


def _rollback_name(profile: Profile) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"{profile.container.name}-rollback-{stamp}"


def _verification_commands() -> list[str]:
    return [
        "test -d ~/.claude/projects",
        "claude --version",
        "lark-cli --version",
        "lark-channel-bridge --version",
    ]


def _run_verification(adapter: DockerAdapter, profile: Profile) -> list[str]:
    outputs = []
    for command in _verification_commands():
        result = adapter.exec(profile, command)
        detail = result.output.strip()
        if result.exit_code != 0:
            raise RebuildError(f"verification failed: {command}", [detail] if detail else [])
        outputs.append(f"{command}: {detail or 'ok'}")
    return outputs


def _restore_rollback(adapter: DockerAdapter, profile: Profile, rollback_name: str, bridge_was_running: bool) -> list[str]:
    recovery = []
    current = adapter.get_container_or_none(profile)
    if current is not None:
        try:
            current.remove(force=True)
            recovery.append(f"removed failed container: {profile.container.name}")
        except Exception as exc:  # pragma: no cover - defensive recovery detail
            recovery.append(f"failed to remove new container: {exc}")
    try:
        rollback = adapter.client.containers.get(rollback_name)
        rollback.rename(profile.container.name)
        rollback.start()
        recovery.append(f"restored rollback container: {profile.container.name}")
        if bridge_was_running:
            start_bridge(adapter, profile)
            recovery.append("bridge restart attempted on rollback container")
    except Exception as exc:  # pragma: no cover - defensive recovery detail
        recovery.append(f"automatic rollback failed: {exc}")
    return recovery


def rebuild_profile(store: LcpStore, adapter: DockerAdapter, profile: Profile) -> ProfileRebuildResult:
    plan = plan_profile_rebuild(store, adapter, profile)
    if plan.currentStatus == "missing":
        raise RebuildError(f"container not found: {profile.container.name}")
    if not plan.claudeContinuity.safe:
        raise RebuildError("Claude Code continuity is unsafe", plan.claudeContinuity.reasons)

    rollback_name = _rollback_name(profile)
    bridge_was_running = plan.bridgeRunning
    with store.profile_lock(profile.name):
        old_container = adapter.get_container(profile)
        if bridge_was_running:
            stop_bridge(adapter, profile)
        old_container.stop()
        old_container.rename(rollback_name)
        try:
            adapter.build_profile_image(profile)
            adapter.create_profile_container(profile, build_image=False)
            adapter.start(profile)
            verification = _run_verification(adapter, profile)
            bridge_restored = False
            if bridge_was_running:
                status = start_bridge(adapter, profile)
                if not status.running:
                    raise RebuildError("bridge restart failed", [status.detail])
                bridge_restored = True
            return ProfileRebuildResult(
                rollbackContainer=rollback_name,
                bridgeRestored=bridge_restored,
                verification=verification,
            )
        except Exception as exc:
            recovery = _restore_rollback(adapter, profile, rollback_name, bridge_was_running)
            if isinstance(exc, RebuildError):
                recovery = exc.recovery + recovery
                raise RebuildError(str(exc), recovery) from exc
            raise RebuildError(str(exc), recovery) from exc
