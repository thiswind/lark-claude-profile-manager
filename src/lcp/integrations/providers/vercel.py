from pathlib import Path
import json
import re
import shlex
import subprocess

from lcp.models import Profile
from lcp.store import LcpStore

from ..base import IntegrationProvider
from ..models import HostCheck, IntegrationCapabilities, IntegrationMount


class VercelProvider(IntegrationProvider):
    name = "vercel"
    description = "Install Vercel CLI and share host Vercel authentication with a profile container"

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
        version_result = subprocess.run(["vercel", "--version"], capture_output=True, text=True)
        if version_result.returncode != 0:
            return HostCheck(provider=self.name, ok=False, message=(version_result.stderr or version_result.stdout).strip() or "vercel not found")
        token = self._token()
        if token:
            whoami = subprocess.run(["vercel", "whoami", "--token", token], capture_output=True, text=True)
            if whoami.returncode != 0:
                return HostCheck(provider=self.name, ok=False, version=self._parse_version(version_result.stdout), message=(whoami.stderr or whoami.stdout).strip() or "vercel token is not valid")
            auth_path = self._token_auth_path()
            self._write_token_auth_snapshot(auth_path, token)
            return HostCheck(provider=self.name, ok=True, version=self._parse_version(version_result.stdout), authPath=str(auth_path), message="vercel token authenticated", details={"account": whoami.stdout.strip(), "auth": "token"})
        whoami = subprocess.run(["vercel", "whoami"], capture_output=True, text=True)
        if whoami.returncode != 0:
            return HostCheck(provider=self.name, ok=False, version=self._parse_version(version_result.stdout), message=(whoami.stderr or whoami.stdout).strip() or "vercel is not authenticated")
        auth_path = self._auth_path()
        if auth_path is None:
            return HostCheck(provider=self.name, ok=False, version=self._parse_version(version_result.stdout), message="vercel auth directory not found")
        return HostCheck(
            provider=self.name,
            ok=True,
            version=self._parse_version(version_result.stdout),
            authPath=str(auth_path),
            message="vercel authenticated",
            details={"account": whoami.stdout.strip()},
        )

    def mounts(self, store: LcpStore, profile: Profile) -> list[IntegrationMount]:
        state = profile.integrations.providers.get(self.name)
        if not state or not state.desired.enabled or not state.desired.snapshotPath:
            return []
        snapshot = Path(state.desired.snapshotPath)
        if not snapshot.exists():
            return []
        return [IntegrationMount(hostPath=str(snapshot), containerPath=f"{profile.container.user.home}/.local/share/com.vercel.cli", mode="ro")]

    def install_commands(self, profile: Profile, reuse_matching: bool = False) -> list[str]:
        state = profile.integrations.providers.get(self.name)
        version = state.desired.hostVersion if state else None
        if not version:
            return []
        install = f"npm uninstall -g vercel || true && npm install -g vercel@{shlex.quote(version)} --cache /cache/npm"
        if not reuse_matching:
            return [install]
        pattern = re.escape(version)
        return [
            f"if command -v vercel >/dev/null 2>&1 && vercel --version | grep -Eq {shlex.quote(pattern)}; then echo 'vercel {version} already installed'; else {install}; fi"
        ]

    def verify_commands(self, profile: Profile, external: bool = False) -> list[str]:
        home = shlex.quote(profile.container.user.home)
        token_file = shlex.quote(f"{profile.container.user.home}/.local/share/com.vercel.cli/lcp-token.json")
        return [
            f"tmp=$(mktemp -d); if [ -s {token_file} ]; then token=$(node -e 'process.stdout.write(JSON.parse(require(\"fs\").readFileSync(process.argv[1], \"utf8\")).token)' {token_file}) && HOME=\"$tmp\" vercel whoami --token \"$token\"; code=$?; rm -rf \"$tmp\"; exit $code; else mkdir -p \"$tmp/.local/share\" && cp -a {home}/.local/share/com.vercel.cli \"$tmp/.local/share/\" && chmod -R u+w \"$tmp/.local/share/com.vercel.cli\" && HOME=\"$tmp\" vercel whoami; code=$?; rm -rf \"$tmp\"; exit $code; fi"
        ]

    def _auth_path(self) -> Path | None:
        for path in [Path.home() / ".local" / "share" / "com.vercel.cli", Path.home() / ".config" / "com.vercel.cli"]:
            if path.exists():
                return path
        return None

    def _token_path(self) -> Path:
        return Path.home() / ".lcp" / "secrets" / "vercel_token"

    def _token(self) -> str | None:
        path = self._token_path()
        if not path.exists():
            return None
        token = path.read_text(encoding="utf-8").strip()
        return token or None

    def _token_auth_path(self) -> Path:
        return Path.home() / ".lcp" / "secrets" / "vercel-auth"

    def _write_token_auth_snapshot(self, path: Path, token: str) -> None:
        path.mkdir(parents=True, exist_ok=True)
        path.chmod(0o700)
        token_file = path / "lcp-token.json"
        token_file.write_text(json.dumps({"token": token}) + "\n", encoding="utf-8")
        token_file.chmod(0o600)

    def _parse_version(self, text: str) -> str | None:
        match = re.search(r"\d+(?:\.\d+)+(?:[-+][0-9A-Za-z.-]+)?", text)
        return match.group(0) if match else text.strip() or None
