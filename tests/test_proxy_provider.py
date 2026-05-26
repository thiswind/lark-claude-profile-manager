from pathlib import Path

from typer.testing import CliRunner

from lcp import cli
from lcp.docker_adapter import ExecResult
from lcp.integrations.providers.proxy import ProxyProvider
from lcp.integrations.registry import IntegrationRegistry
from lcp.integrations.service import IntegrationService
from lcp.models import default_profile
from lcp.store import LcpStore


runner = CliRunner()


class FakeAdapter:
    def __init__(self, store=None):
        self.store = store
        self.commands = []

    def get_container_or_none(self, profile):
        return object()

    def exec(self, profile, command):
        self.commands.append(command)
        return ExecResult(0, "ok")


def test_proxy_provider_reads_explicit_env_without_hardcoded_defaults(monkeypatch) -> None:
    monkeypatch.delenv("HTTP_PROXY", raising=False)
    monkeypatch.delenv("HTTPS_PROXY", raising=False)
    monkeypatch.delenv("ALL_PROXY", raising=False)
    monkeypatch.delenv("http_proxy", raising=False)
    monkeypatch.delenv("https_proxy", raising=False)
    monkeypatch.delenv("all_proxy", raising=False)
    monkeypatch.setenv("LCP_PROXY_HTTP", "http://proxy.example:8080")
    monkeypatch.setenv("LCP_PROXY_SOCKS5", "socks5h://proxy.example:1080")

    check = ProxyProvider().check_host()

    assert check.ok is True
    assert check.details["http"] == "http://proxy.example:8080"
    assert check.details["socks5"] == "socks5h://proxy.example:1080"


def test_proxy_provider_requires_explicit_proxy_config(monkeypatch) -> None:
    for name in ["LCP_PROXY_HTTP", "LCP_PROXY_HTTPS", "LCP_PROXY_SOCKS5", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "http_proxy", "https_proxy", "all_proxy"]:
        monkeypatch.delenv(name, raising=False)

    check = ProxyProvider().check_host()

    assert check.ok is False
    assert "proxy config not found" in check.message


def test_proxy_provider_redacts_credentials() -> None:
    provider = ProxyProvider()

    text = provider.redact("curl http://user:secret@proxy.example:8080 && curl socks5h://u:p@proxy.example:1080")

    assert "secret" not in text
    assert "u:p" not in text
    assert "http://***:***@proxy.example:8080" in text
    assert "socks5h://***:***@proxy.example:1080" in text


def test_proxy_provider_redacts_invalid_url_message() -> None:
    check = ProxyProvider().check_config({"http": "http://user:secret@"})

    assert check.ok is False
    assert "secret" not in check.message


def test_proxy_apply_writes_profile_and_tool_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LCP_PROXY_HTTP", "http://proxy.example:8080")
    monkeypatch.setenv("LCP_PROXY_SOCKS5", "socks5h://proxy.example:1080")
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store)

    profile = service.grant(profile, "proxy")
    adapter = FakeAdapter()
    profile, results = service.apply(adapter, profile)

    assert profile.integrations.providers["proxy"].effective.status == "active"
    joined = "\n".join(adapter.commands)
    assert "/etc/profile.d/lcp-proxy.sh" in joined
    assert "/etc/apt/apt.conf.d/90lcp-proxy" in joined
    assert "npm config set proxy" in joined
    assert "/home/thiswind/.claude/skills" not in joined
    assert (store.profile_dir("project1") / "skills" / "lcp-proxy-networking" / "SKILL.md").is_file()
    mounts = service.mounts(profile)
    assert mounts[0].hostPath == str(store.profile_dir("project1") / "skills" / "lcp-proxy-networking")
    assert mounts[0].containerPath == "/home/thiswind/.claude/skills/lcp-proxy-networking"
    assert mounts[0].mode == "ro"
    assert results[0].provider == "proxy"


def test_proxy_verify_external_is_opt_in(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store)
    profile = service.grant(profile, "proxy", {"http": "http://proxy.example:8080"})
    adapter = FakeAdapter()

    service.verify(adapter, profile, "proxy")
    normal_commands = list(adapter.commands)
    service.verify(adapter, profile, "proxy", external=True)

    assert not any("api.github.com" in command for command in normal_commands)
    assert any("api.github.com" in command for command in adapter.commands)


def test_proxy_cli_verify_external_requires_proxy_provider(monkeypatch, tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)
    monkeypatch.setattr(cli, "DockerAdapter", FakeAdapter)

    result = runner.invoke(cli.app, ["integration", "verify", "project1", "git", "--external"])

    assert result.exit_code == 1
    assert "external verification is only supported for proxy" in result.output


def test_proxy_apply_progress_redacts_credentials(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store)
    profile = service.grant(profile, "proxy", {"http": "http://user:secret@proxy.example:8080"})
    messages = []

    service.apply(FakeAdapter(), profile, progress=messages.append)

    joined = "\n".join(messages)
    assert "secret" not in joined
    assert "http://***:***@proxy.example:8080" in joined


def test_proxy_revoke_removes_lcp_owned_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LCP_PROXY_HTTP", "http://proxy.example:8080")
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store)
    adapter = FakeAdapter()

    profile = service.grant(profile, "proxy")
    profile, _ = service.apply(adapter, profile)
    profile = service.revoke(profile, "proxy")
    plan = service.plan(profile)
    profile, _ = service.apply(adapter, profile)

    assert [step.action for step in plan.steps] == ["recreate"]
    assert "remove mounts" in plan.steps[0].reason
    assert profile.integrations.providers["proxy"].effective.status == "disabled"
    joined = "\n".join(adapter.commands)
    assert "rm -f /etc/profile.d/lcp-proxy.sh" in joined
    assert "npm config delete proxy" in joined
    assert not (store.profile_dir("project1") / "skills" / "lcp-proxy-networking").exists()


def test_default_registry_includes_proxy_provider() -> None:
    registry = IntegrationRegistry()

    assert registry.get("proxy").name == "proxy"


def test_proxy_cli_grant_then_dry_run(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LCP_PROXY_HTTP", "http://proxy.example:8080")
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    grant = runner.invoke(cli.app, ["integration", "grant", "project1", "proxy", "--from-env"])
    dry_run = runner.invoke(cli.app, ["integration", "apply", "project1", "--dry-run"])

    assert grant.exit_code == 0
    assert "granted: proxy" in grant.output
    assert dry_run.exit_code == 0
    assert "proxy: configure" in dry_run.output
    assert "proxy: recreate" in dry_run.output
    assert "proxy: verify" in dry_run.output


def test_proxy_cli_grant_accepts_explicit_config(monkeypatch, tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["integration", "grant", "project1", "proxy", "--config", "http=http://proxy.example:8080", "--config", "socks5=socks5h://proxy.example:1080"])

    assert result.exit_code == 0
    profile = store.load_profile("project1")
    config = profile.integrations.providers["proxy"].desired.config
    assert config["http"] == "http://proxy.example:8080"
    assert config["socks5"] == "socks5h://proxy.example:1080"


def test_proxy_cli_grant_requires_explicit_config(monkeypatch, tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    monkeypatch.setattr(cli, "LcpStore", lambda: store)

    result = runner.invoke(cli.app, ["integration", "grant", "project1", "proxy"])

    assert result.exit_code == 1
    assert "proxy grant requires explicit configuration" in result.output
