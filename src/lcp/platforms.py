from pathlib import Path
import platform


def is_wsl(proc_version_path: Path = Path("/proc/version")) -> bool:
    try:
        text = proc_version_path.read_text(encoding="utf-8", errors="ignore").lower()
    except FileNotFoundError:
        return False
    return "microsoft" in text or "wsl" in text


def system_name() -> str:
    return platform.system().lower()


def machine_arch() -> str:
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        return "amd64"
    if machine in {"aarch64", "arm64"}:
        return "arm64"
    return machine
