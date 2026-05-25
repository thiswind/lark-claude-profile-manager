from pathlib import Path

import pytest
from pydantic import ValidationError

from lcp.models import Profile, container_desktop, container_name, default_profile


def test_container_name() -> None:
    assert container_name("project1") == "lcp-project1"


@pytest.mark.parametrize("name", ["", "bad/name", " bad", "x" * 64])
def test_invalid_profile_name(name: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        default_profile(name, Path("/tmp/Desktop"), [], "amd64", "thiswind", 1000, 1000)


def test_default_profile_uses_desktop_workspace() -> None:
    profile = default_profile(
        "project1",
        Path("/mnt/c/Users/Administrator/Desktop"),
        ["/mnt/c/Users/Administrator/Desktop"],
        "amd64",
        "thiswind",
        1000,
        1000,
        git_name="thiswind",
        git_email="thiswind@gmail.com",
    )
    assert profile.container.image == "lcp/project1:base"
    assert profile.container.baseImage == "ubuntu:24.04"
    assert profile.container.user.name == "thiswind"
    assert profile.workspace.defaultCwd == f"{container_desktop('thiswind')}/Projects/lcp_profiles/project1"
    assert profile.runtime.autoStart is True
    assert profile.runtime.restartPolicy == "always"
    assert profile.mounts.desktop.hostPath == "/mnt/c/Users/Administrator/Desktop"
    assert profile.mounts.desktop.compatSymlinks == ["/mnt/c/Users/Administrator/Desktop"]
    assert profile.gitIdentity.name == "thiswind"
    assert profile.gitIdentity.email == "thiswind@gmail.com"


def test_profile_round_trip() -> None:
    profile = default_profile("notes", Path("/tmp/Desktop"), [], "amd64", "thiswind", 1000, 1000)
    loaded = Profile.model_validate(profile.model_dump(mode="json"))
    assert loaded == profile


def test_default_profile_preserves_display_name() -> None:
    profile = default_profile("win", Path("C:/Users/Administrator/Desktop"), [], "amd64", "administrator", 1000, 1000, "Administrator")
    assert profile.container.user.name == "administrator"
    assert profile.container.user.displayName == "Administrator"
    assert profile.container.user.home == "/home/administrator"
