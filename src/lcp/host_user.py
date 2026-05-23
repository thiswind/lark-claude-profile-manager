from dataclasses import dataclass
import getpass
import os
from pathlib import Path
import platform
import re


WINDOWS_UID = 1000
WINDOWS_GID = 1000
FALLBACK_WINDOWS_USER = "lcpuser"


@dataclass(frozen=True)
class HostUser:
    name: str
    uid: int
    gid: int
    home: str
    display_name: str | None = None
    source: str | None = None


def current_host_user(container_user: str | None = None) -> HostUser:
    if platform.system().lower() == "windows":
        return _windows_host_user(container_user)
    return _posix_host_user(container_user)


def _posix_host_user(container_user: str | None = None) -> HostUser:
    import pwd

    uid = os.getuid()
    entry = pwd.getpwuid(uid)
    name = _normalize_linux_username(container_user) if container_user else entry.pw_name
    source = "explicit" if container_user else "posix-direct"
    return HostUser(name=name, uid=uid, gid=entry.pw_gid, home=entry.pw_dir, source=source)


def _windows_host_user(container_user: str | None = None) -> HostUser:
    raw_name = _windows_raw_user_name()
    name = _normalize_linux_username(container_user or raw_name)
    source = "explicit" if container_user else "windows-normalized"
    return HostUser(
        name=name,
        uid=WINDOWS_UID,
        gid=WINDOWS_GID,
        home=str(Path.home()),
        display_name=raw_name,
        source=source,
    )


def _windows_raw_user_name() -> str:
    candidates = [
        Path.home().name,
        _safe_getpass_user(),
        os.environ.get("USERNAME"),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    return FALLBACK_WINDOWS_USER


def _safe_getpass_user() -> str | None:
    try:
        return getpass.getuser()
    except Exception:
        return None


def _normalize_linux_username(value: str | None) -> str:
    if not value:
        return FALLBACK_WINDOWS_USER
    normalized = value.lower().replace(" ", "_").replace(".", "_")[:32]
    if re.fullmatch(r"[a-z_][a-z0-9_-]*", normalized):
        return normalized
    return FALLBACK_WINDOWS_USER
