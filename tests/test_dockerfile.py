from lcp.dockerfile import render_base_dockerfile, render_profile_dockerfile, render_runtime_dockerfile
from lcp.host_user import HostUser
from lcp.runtime import default_runtime_manifest


def test_base_dockerfile_installs_node_24_and_excludes_authorized_tools() -> None:
    text = render_base_dockerfile()
    assert "FROM ubuntu:24.04" in text
    assert "setup_24.x" in text
    assert " tree " in f" {text} "
    assert " gh " not in f" {text} "


def test_runtime_dockerfile_installs_lcp_runtime_tools() -> None:
    text = render_runtime_dockerfile(default_runtime_manifest())
    assert "FROM lcp/base:latest" in text
    assert "@anthropic-ai/claude-code" in text
    assert "@larksuite/cli" in text
    assert "lark-channel-bridge" in text


def test_profile_dockerfile_creates_non_root_user_from_runtime_image() -> None:
    text = render_profile_dockerfile(HostUser(name="thiswind", uid=1000, gid=1000, home="/home/thiswind"), "lcp/runtime:test")
    assert "FROM lcp/runtime:test" in text
    assert "useradd --uid 1000 --gid 1000" in text
    assert "ENV HOME=/home/thiswind" in text
    assert "USER 1000:1000" in text
    assert "WORKDIR /home/thiswind" in text
