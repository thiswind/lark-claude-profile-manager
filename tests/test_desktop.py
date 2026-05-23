from pathlib import Path
import subprocess

from lcp.desktop import DesktopResolver


def test_explicit_desktop_path(tmp_path: Path) -> None:
    desktop = tmp_path / "Desktop"
    info = DesktopResolver().resolve(str(desktop))
    assert info.host_path == desktop
    assert info.container_path == "/home/thiswind/Desktop"


def test_wsl_powershell_desktop_resolution(monkeypatch, tmp_path: Path) -> None:
    desktop = tmp_path / "Users" / "Administrator" / "Desktop"
    desktop.mkdir(parents=True)

    monkeypatch.setattr("lcp.desktop.is_wsl", lambda: True)
    monkeypatch.setattr("lcp.desktop.shutil.which", lambda cmd: f"/usr/bin/{cmd}")

    def fake_run(args, capture_output, text, check):
        if args[0] == "powershell.exe":
            return subprocess.CompletedProcess(args, 0, "C:\\Users\\Administrator\\Desktop\r\n", "")
        if args[0] == "wslpath":
            return subprocess.CompletedProcess(args, 0, str(desktop) + "\n", "")
        raise AssertionError(args)

    monkeypatch.setattr("lcp.desktop.subprocess.run", fake_run)
    monkeypatch.setattr("lcp.desktop.DesktopResolver._manual_wsl_path", lambda self, path: None)

    info = DesktopResolver().resolve()
    assert info.host_path == desktop
    assert info.compat_symlinks == (str(desktop),)


def test_manual_windows_to_wsl_path() -> None:
    resolver = DesktopResolver()
    assert resolver._manual_wsl_path("C:\\Users\\Administrator\\Desktop") == Path("/mnt/c/Users/Administrator/Desktop")


def test_wsl_requires_explicit_when_detection_fails(monkeypatch) -> None:
    monkeypatch.setattr("lcp.desktop.is_wsl", lambda: True)
    monkeypatch.setattr("lcp.desktop.shutil.which", lambda cmd: None)

    try:
        DesktopResolver().resolve()
    except RuntimeError as exc:
        assert "--desktop" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
