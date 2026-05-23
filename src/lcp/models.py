from pathlib import Path
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

UBUNTU_LTS_IMAGE = "ubuntu:24.04"


def container_home(user_name: str) -> str:
    return f"/home/{user_name}"


def container_desktop(user_name: str) -> str:
    return f"{container_home(user_name)}/Desktop"


class GpuConfig(BaseModel):
    strategy: Literal["auto", "cpu"] = "auto"
    enabled: bool = False
    vendor: str | None = None


class InstallConfig(BaseModel):
    claudeCode: str = "latest-at-create-time"
    larkCli: str = "latest-at-create-time"
    larkChannelBridge: str = "latest-at-create-time"


class BackupConfig(BaseModel):
    lastSnapshotAt: str | None = None
    lastImageTag: str | None = None
    lastTarPath: str | None = None


class UserConfig(BaseModel):
    name: str
    uid: int
    gid: int
    home: str
    displayName: str | None = None


class ContainerConfig(BaseModel):
    name: str
    image: str
    baseImage: str = UBUNTU_LTS_IMAGE
    ubuntuLts: str = "24.04"
    arch: str = "amd64"
    user: UserConfig
    gpu: GpuConfig = Field(default_factory=GpuConfig)
    install: InstallConfig = Field(default_factory=InstallConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)


class WorkspaceConfig(BaseModel):
    defaultCwd: str


class DesktopMount(BaseModel):
    hostPath: str
    containerPath: str
    compatSymlinks: list[str] = Field(default_factory=list)


class ClaudeMount(BaseModel):
    shareConfig: bool = True
    hostClaudeDir: str
    hostClaudeJson: str


class MountConfig(BaseModel):
    desktop: DesktopMount
    claude: ClaudeMount


class RuntimeConfig(BaseModel):
    autoStart: bool = False
    restartPolicy: str = "unless-stopped"


class VerificationConfig(BaseModel):
    lastRunAt: str | None = None
    lastStatus: str | None = None


class Profile(BaseModel):
    name: str
    description: str = ""
    container: ContainerConfig
    workspace: WorkspaceConfig
    mounts: MountConfig
    runtime: RuntimeConfig = Field(default_factory=RuntimeConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", value):
            raise ValueError("profile name must be 1-63 chars: letters, numbers, dot, underscore, dash")
        return value


def container_name(profile_name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", profile_name):
        raise ValueError("invalid profile name")
    return f"lcp-{profile_name}"


def profile_image_name(profile_name: str) -> str:
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}", profile_name):
        raise ValueError("invalid profile name")
    return f"lcp/{profile_name}:base"


def default_profile(
    name: str,
    desktop_host_path: Path,
    compat_symlinks: list[str],
    arch: str,
    user_name: str,
    uid: int,
    gid: int,
    display_name: str | None = None,
) -> Profile:
    container = container_name(name)
    user_home = container_home(user_name)
    desktop = container_desktop(user_name)
    cwd = f"{desktop}/Projects/Active/{name}"
    return Profile(
        name=name,
        description=f"LCP profile {name}",
        container=ContainerConfig(
            name=container,
            image=profile_image_name(name),
            arch=arch,
            user=UserConfig(name=user_name, uid=uid, gid=gid, home=user_home, displayName=display_name),
        ),
        workspace=WorkspaceConfig(defaultCwd=cwd),
        mounts=MountConfig(
            desktop=DesktopMount(
                hostPath=str(desktop_host_path),
                containerPath=desktop,
                compatSymlinks=compat_symlinks,
            ),
            claude=ClaudeMount(
                hostClaudeDir=str(Path.home() / ".claude"),
                hostClaudeJson=str(Path.home() / ".claude.json"),
            ),
        ),
    )
