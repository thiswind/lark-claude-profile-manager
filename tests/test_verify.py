from lcp.integrations.models import ProfileIntegrationState
from lcp.models import default_profile
from lcp.verify import _git_identity_check, verify_profile


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


class _RecordingAdapter:
    """Minimal adapter that records all exec commands and returns success."""

    def __init__(self, store) -> None:
        self.store = store
        self.commands = []

    def exec(self, profile, command):
        self.commands.append(command)
        return type("R", (), {"exit_code": 0, "output": "ok"})()

    def exec_root(self, profile, command):
        return type("R", (), {"exit_code": 0, "output": "ok"})()


def test_verify_profile_includes_integration_checks(tmp_path) -> None:
    """Gap 1: verify_profile must run provider verify_commands for enabled
    integrations, not just the base container checks."""
    from lcp.store import LcpStore

    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("git", ProfileIntegrationState())
    state.desired.enabled = True
    state.desired.config = {"user.name": "thiswind", "user.email": "thiswind@example.com"}
    store.save_profile(profile)
    adapter = _RecordingAdapter(store)

    checks = verify_profile(adapter, profile, run_claude=False)

    integration_checks = [c for c in checks if c.name.startswith("integration:")]
    assert len(integration_checks) == 1
    assert integration_checks[0].name == "integration:git"
    assert integration_checks[0].ok is True
    # git verify_commands are "git config --global user.name" and "git config --global user.email"
    assert any("git config --global user.name" in cmd for cmd in adapter.commands)
    assert any("git config --global user.email" in cmd for cmd in adapter.commands)


def test_verify_profile_skips_disabled_integrations(tmp_path) -> None:
    """Disabled integrations should not produce checks or run commands."""
    from lcp.store import LcpStore

    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    state = profile.integrations.providers.setdefault("github", ProfileIntegrationState())
    state.desired.enabled = False
    store.save_profile(profile)
    adapter = _RecordingAdapter(store)

    checks = verify_profile(adapter, profile, run_claude=False)

    integration_checks = [c for c in checks if c.name.startswith("integration:")]
    assert len(integration_checks) == 0
    assert not any("gh auth" in cmd for cmd in adapter.commands)
