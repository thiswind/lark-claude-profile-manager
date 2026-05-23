from dataclasses import dataclass
from pathlib import Path
import os
import platform
import re
import shutil
import subprocess

from .platforms import is_wsl


@dataclass(frozen=True)
class DesktopInfo:
    host_path: Path
    container_path: str = "/home/thiswind/Desktop"
    compat_symlinks: tuple[str, ...] = ()


def _run_text(args: list[str]) -> str:
    result = subprocess.run(args, capture_output=True, text=True, check=True)
    return result.stdout.strip().replace("\r", "")


class DesktopResolver:
    def resolve(self, explicit: str | None = None) -> DesktopInfo:
        if explicit:
            return self._from_path(Path(explicit).expanduser())
        if is_wsl():
            return self._resolve_wsl()
        current = platform.system().lower()
        if current == "windows":
            return self._resolve_windows()
        if current == "darwin":
            return self._from_path(Path.home() / "Desktop", create=True)
        return self._resolve_linux()

    def _from_path(self, path: Path, create: bool = False) -> DesktopInfo:
        if create:
            path.mkdir(parents=True, exist_ok=True)
        return DesktopInfo(host_path=path)

    def _resolve_linux(self) -> DesktopInfo:
        xdg = shutil.which("xdg-user-dir")
        if xdg:
            try:
                path = Path(_run_text([xdg, "DESKTOP"])).expanduser()
                if path:
                    path.mkdir(parents=True, exist_ok=True)
                    return self._from_path(path)
            except (subprocess.CalledProcessError, OSError):
                pass
        return self._from_path(Path.home() / "Desktop", create=True)

    def _resolve_windows(self) -> DesktopInfo:
        userprofile = os.environ.get("USERPROFILE")
        if userprofile:
            return self._from_path(Path(userprofile) / "Desktop")
        return self._from_path(Path.home() / "Desktop")

    def _resolve_wsl(self) -> DesktopInfo:
        desktop_path = self._wsl_desktop_from_powershell()
        if desktop_path is None:
            desktop_path = self._wsl_desktop_from_wslvar()
        if desktop_path is None:
            raise RuntimeError("Could not detect Windows Desktop from WSL. Pass --desktop explicitly.")
        compat = (str(desktop_path),)
        return DesktopInfo(host_path=desktop_path, compat_symlinks=compat)

    def _wsl_desktop_from_powershell(self) -> Path | None:
        if not shutil.which("powershell.exe"):
            return None
        try:
            win_desktop = _run_text([
                "powershell.exe",
                "-NoProfile",
                "-Command",
                '[Environment]::GetFolderPath("Desktop")',
            ])
            return self._wslpath(win_desktop)
        except (subprocess.CalledProcessError, OSError):
            return None

    def _wsl_desktop_from_wslvar(self) -> Path | None:
        if not shutil.which("wslvar"):
            return None
        try:
            userprofile = _run_text(["wslvar", "-s", "USERPROFILE"])
            return self._wslpath(userprofile + "\\Desktop")
        except (subprocess.CalledProcessError, OSError):
            return None

    def _wslpath(self, windows_path: str) -> Path | None:
        manual = self._manual_wsl_path(windows_path)
        if manual and manual.exists():
            return manual
        if not shutil.which("wslpath"):
            return None
        converted = Path(_run_text(["wslpath", windows_path]))
        if converted.exists():
            return converted
        return None

    def _manual_wsl_path(self, windows_path: str) -> Path | None:
        match = re.fullmatch(r"([A-Za-z]):\\(.*)", windows_path.strip())
        if not match:
            return None
        drive = match.group(1).lower()
        rest = match.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{rest}")
