from pathlib import Path
import json
from typing import Literal

from pydantic import BaseModel


class PlatformConfig(BaseModel):
    system: str
    environment: Literal["wsl", "linux", "windows", "macos"]
    arch: str


class HostUserConfig(BaseModel):
    name: str
    uid: int
    gid: int
    home: str
    displayName: str | None = None
    source: str | None = None


class DesktopConfig(BaseModel):
    hostPath: str
    containerPath: str
    source: str


class DockerConfig(BaseModel):
    available: bool
    serverVersion: str | None = None


class GpuMachineConfig(BaseModel):
    available: bool = False
    vendor: str | None = None
    model: str | None = None
    dockerGpuAvailable: bool = False


class ImagesConfig(BaseModel):
    ubuntuLts: str = "ubuntu:24.04"
    nodeMajor: int = 24


class ClaudeConfig(BaseModel):
    configDir: str
    configFile: str


class MachineConfig(BaseModel):
    version: int = 1
    platform: PlatformConfig
    hostUser: HostUserConfig
    desktop: DesktopConfig
    docker: DockerConfig
    gpu: GpuMachineConfig
    images: ImagesConfig
    claude: ClaudeConfig

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "MachineConfig":
        return cls.model_validate_json(path.read_text(encoding="utf-8"))
