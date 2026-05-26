import os
import shlex
from urllib.parse import urlparse

from lcp.models import Profile

from ..base import IntegrationProvider
from ..models import HostCheck, IntegrationCapabilities


class ProxyProvider(IntegrationProvider):
    name = "proxy"
    description = "Configure profile container HTTP, HTTPS, and SOCKS proxy access"

    def capabilities(self) -> IntegrationCapabilities:
        return IntegrationCapabilities(
            requiresHostTool=False,
            requiresHostAuth=False,
            supportsSnapshot=False,
            requiresMount=False,
            requiresContainerInstall=False,
            canVerifyContainer=True,
        )

    def check_host(self) -> HostCheck:
        details = self._proxy_config_from_env()
        if not details:
            return HostCheck(
                provider=self.name,
                ok=False,
                message="proxy config not found; set LCP_PROXY_HTTP, LCP_PROXY_HTTPS, or LCP_PROXY_SOCKS5 before granting",
            )
        invalid = [f"{key}={value}" for key, value in details.items() if key != "noProxy" and not self._valid_proxy_url(value)]
        if invalid:
            return HostCheck(provider=self.name, ok=False, message="invalid proxy URL: " + ", ".join(invalid), details=details)
        return HostCheck(provider=self.name, ok=True, message="proxy config detected", details=details)

    def configure_commands(self, profile: Profile) -> list[str]:
        state = profile.integrations.providers.get(self.name)
        config = state.desired.config if state else {}
        if not config:
            return []
        http = config.get("http", "")
        https = config.get("https", "") or http
        socks5 = config.get("socks5", "")
        all_proxy = socks5 or https or http
        no_proxy = config.get("noProxy", "")
        exports = {
            "http_proxy": http,
            "https_proxy": https,
            "all_proxy": all_proxy,
            "no_proxy": no_proxy,
            "HTTP_PROXY": http,
            "HTTPS_PROXY": https,
            "ALL_PROXY": all_proxy,
            "NO_PROXY": no_proxy,
        }
        profile_lines = [f"export {key}={shlex.quote(value)}" for key, value in exports.items() if value]
        profile_body = "\n".join(["# Managed by LCP proxy integration", *profile_lines, ""])
        commands = [
            f"printf %s {shlex.quote(profile_body)} | sudo tee /etc/profile.d/lcp-proxy.sh >/dev/null",
            "sudo chmod 0644 /etc/profile.d/lcp-proxy.sh",
        ]
        if http or https:
            apt_lines = []
            if http:
                apt_lines.append(f'Acquire::http::Proxy "{http}";')
            if https:
                apt_lines.append(f'Acquire::https::Proxy "{https}";')
            apt_body = "\n".join(apt_lines) + "\n"
            commands.append(f"printf %s {shlex.quote(apt_body)} | sudo tee /etc/apt/apt.conf.d/90lcp-proxy >/dev/null")
        npm_proxy = https or http
        if npm_proxy:
            npm_proxy_arg = shlex.quote(npm_proxy)
            commands.append(f"npm config set proxy {npm_proxy_arg} --global && npm config set https-proxy {npm_proxy_arg} --global")
        commands.append("mkdir -p ~/.config/pip")
        if http or https:
            pip_proxy = https or http
            pip_body = f"[global]\nproxy = {pip_proxy}\n"
            commands.append(f"printf %s {shlex.quote(pip_body)} > ~/.config/pip/pip.conf")
        skill_dir = shlex.quote(f"{profile.container.user.home}/.claude/skills/lcp-proxy-{profile.name}")
        commands.append(f"mkdir -p {skill_dir} && printf %s {shlex.quote(self._skill_body(profile))} > {skill_dir}/SKILL.md")
        return commands

    def revoke_commands(self, profile: Profile) -> list[str]:
        skill_dir = shlex.quote(f"{profile.container.user.home}/.claude/skills/lcp-proxy-{profile.name}")
        return [
            "sudo rm -f /etc/profile.d/lcp-proxy.sh /etc/apt/apt.conf.d/90lcp-proxy",
            "npm config delete proxy --global >/dev/null 2>&1 || true; npm config delete https-proxy --global >/dev/null 2>&1 || true",
            f"rm -f ~/.config/pip/pip.conf && rm -rf {skill_dir}",
        ]

    def verify_commands(self, profile: Profile) -> list[str]:
        return ["bash -lc 'source /etc/profile.d/lcp-proxy.sh && env | grep -E \"^(http_proxy|https_proxy|all_proxy)=\"'"]

    def _skill_body(self, profile: Profile) -> str:
        return f"""---
name: lcp-proxy-{profile.name}
description: Use the LCP-managed proxy configured for this profile when network access fails.
---

# LCP proxy

This profile has proxy variables managed by LCP in `/etc/profile.d/lcp-proxy.sh`.

Run these checks before network-heavy commands:

1. Load the proxy variables:
   `source /etc/profile.d/lcp-proxy.sh`
2. Inspect available proxy modes:
   `env | grep -E '^(http_proxy|https_proxy|all_proxy|no_proxy)='`
3. For HTTP/HTTPS tools, use the exported `http_proxy` and `https_proxy` variables.
4. For SOCKS-capable tools, use `all_proxy` when present.
5. For apt, npm, and pip, LCP also writes tool-specific proxy config during integration apply.

If this file exists but `/etc/profile.d/lcp-proxy.sh` is missing, ask the user to run:
`lcp integration apply {profile.name} --dry-run`
then inspect the plan before real apply.
"""

    def _proxy_config_from_env(self) -> dict[str, str]:
        config = {
            "http": self._env("LCP_PROXY_HTTP", "HTTP_PROXY", "http_proxy"),
            "https": self._env("LCP_PROXY_HTTPS", "HTTPS_PROXY", "https_proxy"),
            "socks5": self._env("LCP_PROXY_SOCKS5", "ALL_PROXY", "all_proxy"),
            "noProxy": self._env("LCP_PROXY_NO_PROXY", "NO_PROXY", "no_proxy"),
        }
        return {key: value for key, value in config.items() if value}

    def _env(self, *names: str) -> str:
        for name in names:
            value = os.environ.get(name)
            if value:
                return value
        return ""

    def _valid_proxy_url(self, value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https", "socks5", "socks5h"} and bool(parsed.hostname) and bool(parsed.port)
