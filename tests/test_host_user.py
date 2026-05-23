from pathlib import Path

import lcp.host_user as host_user
from lcp.host_user import _normalize_linux_username, _windows_host_user


def test_normalize_linux_username() -> None:
    assert _normalize_linux_username("Administrator") == "administrator"
    assert _normalize_linux_username("John Smith") == "john_smith"
    assert _normalize_linux_username("zhang.001") == "zhang_001"
    assert _normalize_linux_username("A" * 40) == "a" * 32
    assert _normalize_linux_username("123bad") == "lcpuser"
    assert _normalize_linux_username("bad@name") == "lcpuser"
    assert _normalize_linux_username(None) == "lcpuser"


def test_windows_host_user_uses_home_basename(monkeypatch) -> None:
    monkeypatch.setattr(host_user.Path, "home", lambda: Path("C:/Users/Administrator"))
    monkeypatch.setattr(host_user, "_safe_getpass_user", lambda: "ignored")
    monkeypatch.setattr(host_user.os, "environ", {})

    user = _windows_host_user()

    assert user.name == "administrator"
    assert user.display_name == "Administrator"
    assert user.uid == 1000
    assert user.gid == 1000
    assert user.home == "C:/Users/Administrator"
    assert user.source == "windows-normalized"


def test_windows_host_user_accepts_explicit_container_user(monkeypatch) -> None:
    monkeypatch.setattr(host_user.Path, "home", lambda: Path("C:/Users/Administrator"))

    user = _windows_host_user("John Smith")

    assert user.name == "john_smith"
    assert user.display_name == "Administrator"
    assert user.source == "explicit"
