import shlex
import subprocess

from lcp.models import Profile

from ..base import IntegrationProvider
from ..models import HostCheck, IntegrationCapabilities


class GitProvider(IntegrationProvider):
    name = "git"
    description = "Share host Git identity with a profile container"

    def capabilities(self) -> IntegrationCapabilities:
        return IntegrationCapabilities(
            requiresHostTool=True,
            requiresHostAuth=False,
            supportsSnapshot=False,
            requiresMount=False,
            requiresContainerInstall=False,
            canVerifyContainer=True,
        )

    def check_host(self) -> HostCheck:
        version = subprocess.run(["git", "--version"], capture_output=True, text=True)
        if version.returncode != 0:
            return HostCheck(provider=self.name, ok=False, message=(version.stderr or version.stdout).strip() or "git not found")
        name = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True)
        email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True)
        user_name = name.stdout.strip()
        user_email = email.stdout.strip()
        if not user_name or not user_email:
            return HostCheck(provider=self.name, ok=False, version=version.stdout.strip(), message="global git user.name and user.email are required")
        return HostCheck(
            provider=self.name,
            ok=True,
            version=version.stdout.strip(),
            message="git identity found",
            details={"user.name": user_name, "user.email": user_email},
        )

    def configure_commands(self, profile: Profile) -> list[str]:
        state = profile.integrations.providers.get(self.name)
        if not state:
            return []
        user_name = state.desired.config.get("user.name")
        user_email = state.desired.config.get("user.email")
        if not user_name or not user_email:
            return []
        return [
            f"git config --global user.name {shlex.quote(user_name)}",
            f"git config --global user.email {shlex.quote(user_email)}",
        ]

    def verify_commands(self, profile: Profile, external: bool = False) -> list[str]:
        return ["git config --global user.name", "git config --global user.email"]
