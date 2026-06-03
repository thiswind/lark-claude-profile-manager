from pathlib import Path

from lcp.models import default_profile
from lcp.store import LcpStore


def test_save_profile_writes_lark_cli_file_send_skill(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    store.save_profile(profile)

    skill = store.profile_dir("project1") / "skills" / "lark-cli-file-send" / "SKILL.md"
    assert skill.is_file()
    text = skill.read_text(encoding="utf-8")
    assert "lark-cli-file-send" in text
    assert "--file ./filename.zip" in text
    assert "Do not start user OAuth from a group chat" in text
