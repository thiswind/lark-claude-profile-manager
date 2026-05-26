from pathlib import Path

from lcp.models import default_profile
from lcp.runtime import DEFAULT_BASE_IMAGE, DEFAULT_RUNTIME_IMAGE
from lcp.store import LcpStore


def test_store_initializes_directories(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    store.init_dirs()
    assert store.profiles_dir.is_dir()
    assert (store.cache_dir / "npm").is_dir()
    assert store.snapshots_dir.is_dir()
    assert store.runtime_dir.is_dir()


def test_store_saves_and_loads_profile(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    assert (store.profile_dir("project1") / "profile.json").is_file()
    assert (store.profile_dir("project1") / "lark-channel").is_dir()
    loaded = store.load_profile("project1")
    assert loaded == profile


def test_store_lists_profiles(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    store.save_profile(default_profile("b", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000))
    store.save_profile(default_profile("a", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000))
    assert store.list_profiles() == ["a", "b"]


def test_store_loads_default_runtime_manifest(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    manifest = store.load_runtime_manifest()
    assert manifest.baseImage == DEFAULT_BASE_IMAGE
    assert manifest.runtimeImage == DEFAULT_RUNTIME_IMAGE
    assert "claude-code" in manifest.tools
