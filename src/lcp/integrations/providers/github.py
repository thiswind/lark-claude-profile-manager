from pathlib import Path
import re
import subprocess

from lcp.models import Profile
from lcp.store import LcpStore

from ..base import IntegrationProvider
from ..models import HostCheck, IntegrationCapabilities, IntegrationMount


class GitHubProvider(IntegrationProvider):
    name = "github"
    description = "Share host GitHub CLI authentication with a profile container"

    def capabilities(self) -> IntegrationCapabilities:
        return IntegrationCapabilities(
            requiresHostTool=True,
            requiresHostAuth=True,
            supportsSnapshot=True,
            requiresMount=True,
            requiresContainerInstall=False,
            canVerifyContainer=True,
        )

    def check_host(self) -> HostCheck:
        version = subprocess.run(["gh", "--version"], capture_output=True, text=True)
        if version.returncode != 0:
            return HostCheck(provider=self.name, ok=False, message=(version.stderr or version.stdout).strip() or "gh not found")
        status = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        auth_dir = Path.home() / ".config" / "gh"
        if status.returncode != 0:
            return HostCheck(provider=self.name, ok=False, version=version.stdout.splitlines()[0] if version.stdout else None, authPath=str(auth_dir), message=(status.stderr or status.stdout).strip() or "gh auth status failed")
        if not auth_dir.exists():
            return HostCheck(provider=self.name, ok=False, version=version.stdout.splitlines()[0] if version.stdout else None, authPath=str(auth_dir), message="gh config directory not found")
        output = f"{status.stdout}\n{status.stderr}"
        account = ""
        match = re.search(r"account\s+([^\s]+)", output)
        if match:
            account = match.group(1)
        return HostCheck(
            provider=self.name,
            ok=True,
            version=version.stdout.splitlines()[0] if version.stdout else None,
            authPath=str(auth_dir),
            message="gh authenticated",
            details={"account": account} if account else {},
        )

    def mounts(self, store: LcpStore, profile: Profile) -> list[IntegrationMount]:
        state = profile.integrations.providers.get(self.name)
        if not state or not state.desired.enabled or not state.desired.snapshotPath:
            return []
        snapshot = Path(state.desired.snapshotPath)
        if not snapshot.exists():
            return []
        return [IntegrationMount(hostPath=str(snapshot), containerPath=f"{profile.container.user.home}/.config/gh", mode="ro")]

    def verify_commands(self, profile: Profile) -> list[str]:
        return ["gh auth status"]
