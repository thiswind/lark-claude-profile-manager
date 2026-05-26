from pathlib import Path
import json
import shutil
from contextlib import contextmanager

from .config import MachineConfig
from .models import Profile
from .paths import default_lcp_home, ensure_dir
from .runtime import RuntimeManifest, load_runtime_manifest, save_runtime_manifest


class LcpStore:
    def __init__(self, root: Path | None = None):
        self.root = root or default_lcp_home()

    @property
    def profiles_dir(self) -> Path:
        return self.root / "profiles"

    @property
    def cache_dir(self) -> Path:
        return self.root / "cache"

    @property
    def snapshots_dir(self) -> Path:
        return self.root / "snapshots"

    @property
    def config_file(self) -> Path:
        return self.root / "config.json"

    @property
    def runtime_dir(self) -> Path:
        return self.root / "runtime"

    @property
    def runtime_manifest_file(self) -> Path:
        return self.runtime_dir / "manifest.json"

    def init_dirs(self) -> None:
        ensure_dir(self.root)
        ensure_dir(self.profiles_dir)
        ensure_dir(self.snapshots_dir)
        ensure_dir(self.runtime_dir)
        for name in ["apt", "npm", "pip", "pnpm", "tmp"]:
            ensure_dir(self.cache_dir / name)

    def profile_dir(self, name: str) -> Path:
        return self.profiles_dir / name

    def ensure_profile_dirs(self, name: str) -> Path:
        profile_dir = self.profile_dir(name)
        ensure_dir(profile_dir)
        ensure_dir(profile_dir / "lark-channel")
        ensure_dir(profile_dir / "lark-cli")
        ensure_dir(profile_dir / "logs")
        return profile_dir

    def save_config(self, config: MachineConfig) -> None:
        config.save(self.config_file)

    def load_config(self) -> MachineConfig:
        return MachineConfig.load(self.config_file)

    def load_runtime_manifest(self) -> RuntimeManifest:
        return load_runtime_manifest(self.runtime_manifest_file)

    def save_runtime_manifest(self, manifest: RuntimeManifest) -> None:
        save_runtime_manifest(self.runtime_manifest_file, manifest)

    def save_profile(self, profile: Profile) -> None:
        profile_dir = self.ensure_profile_dirs(profile.name)
        data = profile.model_dump(mode="json")
        target = profile_dir / "profile.json"
        tmp = profile_dir / "profile.json.tmp"
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(target)

    def load_profile(self, name: str) -> Profile:
        data = json.loads((self.profile_dir(name) / "profile.json").read_text(encoding="utf-8"))
        return Profile.model_validate(data)

    def remove_profile(self, name: str) -> Path:
        profile_dir = self.profile_dir(name)
        shutil.rmtree(profile_dir)
        return profile_dir

    def list_profiles(self) -> list[str]:
        if not self.profiles_dir.exists():
            return []
        return sorted(path.name for path in self.profiles_dir.iterdir() if (path / "profile.json").exists())

    def integration_dir(self, profile_name: str, provider: str) -> Path:
        return self.profile_dir(profile_name) / "integrations" / provider

    def integration_snapshot_dir(self, profile_name: str, provider: str) -> Path:
        return self.integration_dir(profile_name, provider) / "snapshot"

    def ensure_integration_dir(self, profile_name: str, provider: str) -> Path:
        integration_dir = self.integration_dir(profile_name, provider)
        ensure_dir(integration_dir)
        ensure_dir(integration_dir / "snapshot")
        ensure_dir(integration_dir / "trash")
        integration_dir.chmod(0o700)
        (integration_dir / "snapshot").chmod(0o700)
        (integration_dir / "trash").chmod(0o700)
        return integration_dir

    @contextmanager
    def profile_lock(self, name: str):
        lock_dir = self.profile_dir(name) / ".lock"
        try:
            lock_dir.mkdir(parents=True)
        except FileExistsError as exc:
            raise RuntimeError(f"profile is locked: {name}") from exc
        try:
            yield
        finally:
            lock_dir.rmdir()
