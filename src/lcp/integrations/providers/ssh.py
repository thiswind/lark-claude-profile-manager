from pathlib import Path
import shutil
import subprocess

from lcp.models import Profile
from lcp.store import LcpStore

from ..base import IntegrationProvider
from ..models import HostCheck, IntegrationCapabilities, IntegrationMount


class SshProvider(IntegrationProvider):
    name = "ssh"
    description = "Share a least-privilege read-only SSH snapshot with a profile container"

    def capabilities(self) -> IntegrationCapabilities:
        return IntegrationCapabilities(
            requiresHostTool=True,
            requiresHostAuth=True,
            supportsSnapshot=False,
            requiresMount=True,
            requiresContainerInstall=False,
            canVerifyContainer=True,
        )

    def check_host(self) -> HostCheck:
        version = subprocess.run(["ssh", "-V"], capture_output=True, text=True)
        if version.returncode != 0:
            return HostCheck(provider=self.name, ok=False, message=(version.stderr or version.stdout).strip() or "ssh not found")
        ssh_dir = Path.home() / ".ssh"
        if not ssh_dir.exists():
            return HostCheck(provider=self.name, ok=False, version=self._version(version), message="~/.ssh not found")
        config = ssh_dir / "config"
        known_hosts = ssh_dir / "known_hosts"
        if not config.exists() and not known_hosts.exists():
            return HostCheck(provider=self.name, ok=False, version=self._version(version), authPath=str(ssh_dir), message="~/.ssh has no config or known_hosts to share")
        return HostCheck(provider=self.name, ok=True, version=self._version(version), authPath=str(ssh_dir), message="ssh config available", details={"mode": "config-only"})

    def check_config(self, config: dict[str, str]) -> HostCheck:
        base = self.check_host()
        if not base.ok:
            return base
        ssh_dir = Path(config.get("sshDir") or Path.home() / ".ssh").expanduser()
        key = config.get("key")
        include_private_keys = config.get("includePrivateKeys", "false").lower() in {"1", "true", "yes"}
        if key:
            key_path = Path(key).expanduser()
            if not key_path.is_absolute():
                key_path = ssh_dir / key
            if not key_path.exists():
                return HostCheck(provider=self.name, ok=False, version=base.version, message=f"ssh key not found: {key_path}")
        elif include_private_keys:
            return HostCheck(provider=self.name, ok=False, version=base.version, message="includePrivateKeys requires explicit --config key=<path>")
        details = {"sshDir": str(ssh_dir), "mode": "key" if key else "config-only"}
        if key:
            details["key"] = str(key_path)
        if include_private_keys:
            details["includePrivateKeys"] = "true"
        return HostCheck(provider=self.name, ok=True, version=base.version, authPath=str(ssh_dir), message="ssh config available", details=details)

    def desired_config(self, check: HostCheck) -> dict[str, str]:
        return check.details

    def prepare(self, store: LcpStore, profile: Profile) -> None:
        state = profile.integrations.providers.get(self.name)
        if not state or not state.desired.enabled:
            return
        snapshot = store.ensure_integration_dir(profile.name, self.name) / "snapshot"
        snapshot.mkdir(parents=True, exist_ok=True)
        self._copy_snapshot(Path(state.desired.config.get("sshDir") or Path.home() / ".ssh"), snapshot, state.desired.config)
        state.desired.snapshotPath = str(snapshot)

    def cleanup(self, store: LcpStore, profile: Profile) -> None:
        shutil.rmtree(store.integration_snapshot_dir(profile.name, self.name), ignore_errors=True)

    def mounts(self, store: LcpStore, profile: Profile) -> list[IntegrationMount]:
        state = profile.integrations.providers.get(self.name)
        if not state or not state.desired.enabled or not state.desired.snapshotPath:
            return []
        snapshot = Path(state.desired.snapshotPath)
        if not snapshot.exists():
            return []
        return [IntegrationMount(hostPath=str(snapshot), containerPath=f"{profile.container.user.home}/.ssh", mode="ro")]

    def verify_commands(self, profile: Profile, external: bool = False) -> list[str]:
        return ["test -d ~/.ssh && test ! -w ~/.ssh && (test -f ~/.ssh/config || test -f ~/.ssh/known_hosts || ls ~/.ssh/id_* >/dev/null 2>&1)"]

    def _copy_snapshot(self, source: Path, target: Path, config: dict[str, str]) -> None:
        shutil.rmtree(target, ignore_errors=True)
        target.mkdir(parents=True, exist_ok=True)
        for name in ["config", "known_hosts", "known_hosts2"]:
            path = source / name
            if path.exists() and path.is_file():
                shutil.copy2(path, target / name)
        key = config.get("key")
        if key:
            key_path = Path(key).expanduser()
            if not key_path.is_absolute():
                key_path = source / key
            shutil.copy2(key_path, target / key_path.name)
            pub = key_path.with_suffix(key_path.suffix + ".pub") if key_path.suffix else Path(str(key_path) + ".pub")
            if pub.exists():
                shutil.copy2(pub, target / pub.name)
        for child in target.iterdir():
            if child.is_file():
                child.chmod(0o600 if not child.name.endswith(".pub") else 0o644)
        target.chmod(0o700)

    def _version(self, result) -> str | None:
        text = (result.stderr or result.stdout).strip()
        return text or None
