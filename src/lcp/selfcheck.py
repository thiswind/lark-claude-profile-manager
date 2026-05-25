from dataclasses import dataclass
from pathlib import Path
import shutil
import subprocess

import docker

from .config import ClaudeConfig, DesktopConfig, DockerConfig, GitIdentityConfig, GpuMachineConfig, HostUserConfig, ImagesConfig, MachineConfig, PlatformConfig
from .desktop import DesktopResolver
from .host_user import current_host_user
from .models import UBUNTU_LTS_IMAGE, container_desktop
from .platforms import is_wsl, machine_arch, system_name


@dataclass(frozen=True)
class InitCheck:
    name: str
    status: str
    value: str
    required: bool = True

    @property
    def ok(self) -> bool:
        return self.status == "ok" or (self.status == "warn" and not self.required)


@dataclass(frozen=True)
class InitReport:
    config: MachineConfig
    checks: list[InitCheck]

    @property
    def has_required_failures(self) -> bool:
        return any(check.required and check.status == "fail" for check in self.checks)


def collect_init_report(explicit_desktop: str | None = None, container_user: str | None = None) -> InitReport:
    checks: list[InitCheck] = []

    system = system_name()
    environment = _environment(system)
    arch = machine_arch()
    checks.append(InitCheck("Operating system", "ok", f"{environment} / {system} / {arch}"))

    user = current_host_user(container_user)
    user_label = f"{user.display_name} → {user.name}" if user.display_name and user.display_name != user.name else user.name
    checks.append(InitCheck("Host user", "ok", f"{user_label} ({user.uid}:{user.gid})"))

    desktop_info = DesktopResolver().resolve(explicit_desktop)
    desktop_source = _desktop_source(environment, explicit_desktop)
    checks.append(InitCheck("Desktop", "ok" if desktop_info.host_path.exists() else "fail", str(desktop_info.host_path)))

    docker_config = _docker_config()
    checks.append(InitCheck("Docker", "ok" if docker_config.available else "fail", docker_config.serverVersion or "unavailable"))

    gpu_config = _gpu_config()
    checks.append(InitCheck("GPU", "ok" if gpu_config.available else "warn", gpu_config.model or "not detected; CPU fallback", required=False))

    claude_dir = Path(user.home) / ".claude"
    claude_json = Path(user.home) / ".claude.json"
    claude_ok = claude_dir.exists() or claude_json.exists()
    checks.append(InitCheck("Claude config", "ok" if claude_ok else "warn", f"{claude_dir} / {claude_json}", required=False))

    git_identity = _git_identity_config()
    git_identity_ok = bool(git_identity.name and git_identity.email)
    git_identity_safe = git_identity_ok and not _is_ai_contributor_identity(git_identity.name, git_identity.email)
    git_identity_value = f"{git_identity.name or 'missing'} <{git_identity.email or 'missing'}>"
    checks.append(InitCheck("Git identity", "ok" if git_identity_safe else "fail", git_identity_value))

    checks.append(InitCheck("Ubuntu LTS image", "ok", UBUNTU_LTS_IMAGE))
    checks.append(InitCheck("Node.js policy", "ok", "24 LTS in profile image"))

    config = MachineConfig(
        platform=PlatformConfig(system=system, environment=environment, arch=arch),
        hostUser=HostUserConfig(
            name=user.name,
            displayName=user.display_name,
            uid=user.uid,
            gid=user.gid,
            home=user.home,
            source=user.source,
        ),
        desktop=DesktopConfig(
            hostPath=str(desktop_info.host_path),
            containerPath=container_desktop(user.name),
            source=desktop_source,
        ),
        docker=docker_config,
        gpu=gpu_config,
        images=ImagesConfig(),
        claude=ClaudeConfig(configDir=str(claude_dir), configFile=str(claude_json)),
        gitIdentity=git_identity,
    )
    return InitReport(config=config, checks=checks)


def _environment(system: str) -> str:
    if system == "darwin":
        return "macos"
    if system == "windows":
        return "windows"
    if is_wsl():
        return "wsl"
    return "linux"


def _desktop_source(environment: str, explicit_desktop: str | None) -> str:
    if explicit_desktop:
        return "explicit"
    if environment == "wsl":
        return "wsl-detected"
    if environment == "windows":
        return "windows-userprofile"
    if environment == "macos":
        return "macos-default"
    return "linux-xdg-or-home"


def _git_identity_config() -> GitIdentityConfig:
    return GitIdentityConfig(
        name=_git_config_value("user.name"),
        email=_git_config_value("user.email"),
    )


def _git_config_value(key: str) -> str | None:
    git = shutil.which("git")
    if not git:
        return None
    try:
        result = subprocess.run(
            [git, "config", "--global", "--get", key],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    value = result.stdout.strip()
    return value or None


def _is_ai_contributor_identity(name: str | None, email: str | None) -> bool:
    value = f"{name or ''} {email or ''}".lower()
    return "claude" in value or "anthropic" in value


def _docker_config() -> DockerConfig:
    try:
        client = docker.from_env()
        payload = client.version()
        version = payload.get("Version") or payload.get("Server", {}).get("Version")
        return DockerConfig(available=True, serverVersion=version)
    except Exception:
        return DockerConfig(available=False)


def _gpu_config() -> GpuMachineConfig:
    nvidia = shutil.which("nvidia-smi")
    if not nvidia:
        return GpuMachineConfig()
    try:
        result = subprocess.run(
            [nvidia, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            check=True,
        )
        model = result.stdout.strip().splitlines()[0] if result.stdout.strip() else None
        return GpuMachineConfig(available=bool(model), vendor="nvidia" if model else None, model=model, dockerGpuAvailable=False)
    except (subprocess.CalledProcessError, OSError, IndexError):
        return GpuMachineConfig()
