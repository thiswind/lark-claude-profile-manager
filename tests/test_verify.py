from lcp.integrations.models import ProfileIntegrationState
from lcp.models import default_profile
from lcp.verify import _git_identity_check


def test_git_identity_check_uses_git_integration_desired_config_when_profile_identity_empty(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("git", ProfileIntegrationState())
    state.desired.enabled = True
    state.desired.config = {"user.name": "thiswind", "user.email": "thiswind@gmail.com"}

    command = _git_identity_check(profile)

    assert 'test "$name" = thiswind' in command
    assert 'test "$email" = thiswind@gmail.com' in command
    assert "missing git user.name" not in command


def test_git_identity_check_reports_missing_identity_when_no_expected_identity(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    command = _git_identity_check(profile)

    assert "missing git user.name" in command
    assert "missing git user.email" in command
