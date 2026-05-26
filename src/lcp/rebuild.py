from pathlib import Path

from pydantic import BaseModel, Field

from .bridge import bridge_status
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
