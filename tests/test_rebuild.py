from pathlib import Path

from lcp.models import default_profile
from lcp.rebuild import check_claude_continuity


def test_claude_continuity_is_safe_when_host_state_is_mounted(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    (claude_dir / "projects").mkdir(parents=True)
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    profile.mounts.claude.hostClaudeDir = str(claude_dir)
    profile.mounts.claude.hostClaudeJson = str(claude_json)

    check = check_claude_continuity(profile)

    assert check.safe is True
    assert check.reasons == []


def test_claude_continuity_is_unsafe_when_projects_are_missing(tmp_path: Path) -> None:
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    claude_json = tmp_path / ".claude.json"
    claude_json.write_text("{}", encoding="utf-8")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    profile.mounts.claude.hostClaudeDir = str(claude_dir)
    profile.mounts.claude.hostClaudeJson = str(claude_json)

    check = check_claude_continuity(profile)

    assert check.safe is False
    assert "Claude projects directory not found" in check.reasons[0]
