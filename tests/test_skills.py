from lcp.models import default_profile
from lcp.skills import LARK_CLI_FILE_SEND_SKILL_NAME, lark_cli_file_send_skill_dir
from lcp.store import LcpStore


def test_save_profile_writes_lark_cli_file_send_skill(tmp_path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    store.save_profile(profile)

    skill = lark_cli_file_send_skill_dir(store, profile) / "SKILL.md"
    body = skill.read_text(encoding="utf-8")
    assert f"name: {LARK_CLI_FILE_SEND_SKILL_NAME}" in body
    assert "Use plain `lark-cli`" in body
    assert "relative to the current working directory" in body
    assert "Do not use absolute host paths with `--file`" in body
