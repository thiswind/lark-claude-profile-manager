from pathlib import Path
import re
import shlex
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
            requiresContainerInstall=True,
            supportsExactVersionInstall=True,
            supportsReuseMatching=True,
            canVerifyContainer=True,
        )

    def check_host(self) -> HostCheck:
        version = subprocess.run(["gh", "--version"], capture_output=True, text=True)
        if version.returncode != 0:
            return HostCheck(provider=self.name, ok=False, message=(version.stderr or version.stdout).strip() or "gh not found")
        status = subprocess.run(["gh", "auth", "status"], capture_output=True, text=True)
        auth_dir = Path.home() / ".config" / "gh"
        if status.returncode != 0:
            return HostCheck(provider=self.name, ok=False, version=self._parse_version(version.stdout), authPath=str(auth_dir), message=(status.stderr or status.stdout).strip() or "gh auth status failed")
        if not auth_dir.exists():
            return HostCheck(provider=self.name, ok=False, version=self._parse_version(version.stdout), authPath=str(auth_dir), message="gh config directory not found")
        output = f"{status.stdout}\n{status.stderr}"
        account = ""
        match = re.search(r"account\s+([^\s]+)", output)
        if match:
            account = match.group(1)
        return HostCheck(
            provider=self.name,
            ok=True,
            version=self._parse_version(version.stdout),
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

    def install_commands(self, profile: Profile, reuse_matching: bool = False) -> list[str]:
        state = profile.integrations.providers.get(self.name)
        version = state.desired.hostVersion if state else None
        if not version:
            return []
        version_arg = shlex.quote(version)
        install = " && ".join([
            "sudo mkdir -p -m 755 /etc/apt/keyrings",
            "curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | sudo tee /etc/apt/keyrings/githubcli-archive-keyring.gpg >/dev/null",
            "sudo chmod go+r /etc/apt/keyrings/githubcli-archive-keyring.gpg",
            "echo \"deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main\" | sudo tee /etc/apt/sources.list.d/github-cli.list >/dev/null",
            "sudo apt-get -o Acquire::Retries=3 update",
            f"sudo apt-get -o Acquire::Retries=3 install -y gh={version_arg}",
        ])
        if not reuse_matching:
            return [install]
        return [
            f"if command -v gh >/dev/null 2>&1 && gh --version | grep -Eq {shlex.quote(re.escape(version))}; then echo 'gh {version} already installed'; else {install}; fi"
        ]

    def verify_commands(self, profile: Profile, external: bool = False) -> list[str]:
        return ["gh --version", "gh auth status"]

    def _parse_version(self, text: str) -> str | None:
        match = re.search(r"gh version\s+([^\s]+)", text)
        return match.group(1) if match else None
