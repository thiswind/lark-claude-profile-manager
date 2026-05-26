from pathlib import Path

from lcp.docker_adapter import ExecResult
from lcp.integrations.providers.proxy import ProxyProvider
from lcp.integrations.service import IntegrationService
from lcp.models import default_profile
from lcp.store import LcpStore


class FakeAdapter:
    def __init__(self):
        self.commands = []

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
    assert "/home/thiswind/.claude/skills/lcp-proxy-project1" in joined
    assert results[0].provider == "proxy"


def test_proxy_revoke_removes_lcp_owned_config(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("LCP_PROXY_HTTP", "http://proxy.example:8080")
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    service = IntegrationService(store)
    adapter = FakeAdapter()

    profile = service.grant(profile, "proxy")
    profile, _ = service.apply(adapter, profile)
    profile = service.revoke(profile, "proxy")
    profile, _ = service.apply(adapter, profile)

    assert profile.integrations.providers["proxy"].effective.status == "disabled"
    joined = "\n".join(adapter.commands)
    assert "rm -f /etc/profile.d/lcp-proxy.sh" in joined
    assert "npm config delete proxy" in joined
    assert "rm -rf /home/thiswind/.claude/skills/lcp-proxy-project1" in joined
