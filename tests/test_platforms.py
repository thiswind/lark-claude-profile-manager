from pathlib import Path

from lcp.platforms import is_wsl


def test_is_wsl_detects_microsoft_kernel(tmp_path: Path) -> None:
    version = tmp_path / "version"
    version.write_text("Linux version microsoft-standard-WSL2", encoding="utf-8")
    assert is_wsl(version)


def test_is_wsl_false_for_regular_kernel(tmp_path: Path) -> None:
    version = tmp_path / "version"
    version.write_text("Linux version generic", encoding="utf-8")
    assert not is_wsl(version)


def test_is_wsl_false_for_missing_file(tmp_path: Path) -> None:
    assert not is_wsl(tmp_path / "missing")
