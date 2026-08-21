from pathlib import Path

from lcp.docker_adapter import ExecResult
from lcp.models import default_profile
from lcp.recover import plan_profile_recover, recover_profile_container
from lcp.store import LcpStore


class FakeContainer:
    def __init__(self, name="lcp-project1", status="running") -> None:
        self.name = name
        self.status = status
        self.removed = False

    def remove(self, force=False) -> None:
        self.removed = True


class FakeSnapshotAdapter:
    def __init__(self, store) -> None:
        self.store = store
        self.container = FakeContainer()
        self.snapshotted = False
        self.created = False
        self.started = False

    def get_container_or_none(self, profile):
        return self.container

    def snapshot(self, profile, output_dir=None):
        self.snapshotted = True
        return Path(f"/tmp/{profile.name}-snapshot.tar")

    def create_profile_container(self, profile, build_image=True):
        self.created = True
        return self.container

    def start(self, profile):
        self.started = True

    def exec(self, profile, command):
        return ExecResult(0, "ok")

    def exec_root(self, profile, command):
        return ExecResult(0, "ok")

    def ensure_home_parent_dirs(self, profile):
        pass

    def ensure_compat_symlinks(self, profile):
        pass


class FakeNoSnapshotAdapter(FakeSnapshotAdapter):
    """Adapter where snapshot raises, simulating a broken Docker commit."""

    def snapshot(self, profile, output_dir=None):
        raise RuntimeError("docker commit failed")


def make_profile(tmp_path: Path):
    return default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)


def test_recover_snapshots_before_removing_container(tmp_path: Path) -> None:
    """Gap 3: recover must snapshot the writable layer before destroying the
    old container so that manual in-container changes are not lost."""
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    store.save_profile(profile)
    adapter = FakeSnapshotAdapter(store)

    result = recover_profile_container(store, adapter, profile)

    assert adapter.snapshotted is True
    assert adapter.container.removed is True
    assert any("snapshot saved" in a for a in result.actions)
    assert any("removed stale container" in a for a in result.actions)
    # snapshot must happen before remove
    snapshot_idx = next(i for i, a in enumerate(result.actions) if "snapshot saved" in a)
    remove_idx = next(i for i, a in enumerate(result.actions) if "removed stale" in a)
    assert snapshot_idx < remove_idx


def test_recover_proceeds_when_snapshot_fails(tmp_path: Path) -> None:
    """Snapshot is best-effort: if it fails, recover still removes and recreates."""
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    store.save_profile(profile)
    adapter = FakeNoSnapshotAdapter(store)

    result = recover_profile_container(store, adapter, profile)

    assert adapter.container.removed is True
    assert adapter.created is True
    assert any("snapshot skipped" in a for a in result.actions)


def test_plan_recover_includes_snapshot_action(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = make_profile(tmp_path)
    store.save_profile(profile)
    adapter = FakeSnapshotAdapter(store)

    plan = plan_profile_recover(store, adapter, profile)

    assert any("snapshot" in a for a in plan.actions)
    assert any("remove stale container" in a for a in plan.actions)
