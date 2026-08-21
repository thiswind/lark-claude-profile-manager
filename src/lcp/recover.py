from pydantic import BaseModel, Field

from .docker_adapter import DockerAdapter
from .models import Profile
from .store import LcpStore


class ProfileRecoverPlan(BaseModel):
    profile: str
    container: str
    currentStatus: str
    image: str
    preservedHostPaths: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)


class ProfileRecoverResult(BaseModel):
    container: str
    started: bool
    actions: list[str] = Field(default_factory=list)


class RecoverError(RuntimeError):
    pass


def plan_profile_recover(store: LcpStore, adapter: DockerAdapter, profile: Profile) -> ProfileRecoverPlan:
    container = adapter.get_container_or_none(profile)
    status = container.status if container else "missing"
    profile_dir = store.profile_dir(profile.name)
    host_paths = [
        profile.mounts.desktop.hostPath,
        str(profile_dir / "lark-channel"),
        str(profile_dir / "lark-cli"),
        str(profile_dir / "logs"),
        str(store.cache_dir / "npm"),
        str(store.cache_dir / "pnpm"),
        str(store.cache_dir / "pip"),
        str(store.cache_dir / "tmp"),
    ]
    actions = []
    if container:
        actions.append(f"snapshot container writable layer to {store.snapshots_dir / profile.name}")
        actions.append(f"remove stale container: {profile.container.name}")
    actions.append(f"create replacement container from existing image: {profile.container.image}")
    actions.append("start replacement container without running in-container verification")
    return ProfileRecoverPlan(
        profile=profile.name,
        container=profile.container.name,
        currentStatus=status,
        image=profile.container.image,
        preservedHostPaths=host_paths,
        actions=actions,
    )


def recover_profile_container(store: LcpStore, adapter: DockerAdapter, profile: Profile, *, start: bool = True) -> ProfileRecoverResult:
    actions = []
    with store.profile_lock(profile.name):
        container = adapter.get_container_or_none(profile)
        if container is not None:
            try:
                snapshot_path = adapter.snapshot(profile)
                actions.append(f"snapshot saved: {snapshot_path}")
            except Exception as exc:
                actions.append(f"snapshot skipped: {exc}")
            container.remove(force=True)
            actions.append(f"removed stale container: {profile.container.name}")
        store.ensure_profile_dirs(profile.name)
        try:
            adapter.create_profile_container(profile, build_image=False)
            actions.append(f"created replacement container: {profile.container.name}")
            if start:
                adapter.start(profile)
                actions.append(f"started replacement container: {profile.container.name}")
        except Exception as exc:
            raise RecoverError(str(exc)) from exc
    return ProfileRecoverResult(container=profile.container.name, started=start, actions=actions)
