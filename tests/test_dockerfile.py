from lcp.dockerfile import render_base_dockerfile, render_profile_dockerfile, render_runtime_dockerfile
from lcp.host_user import HostUser
from lcp.runtime import DEFAULT_BASE_IMAGE, default_runtime_manifest


def test_base_dockerfile_installs_node_24_and_excludes_authorized_tools() -> None:
    text = render_base_dockerfile()
    assert "FROM ubuntu:24.04" in text
    assert "setup_24.x" in text
    for package in ["dnsutils", "file", "iproute2", "netcat-openbsd", "traceroute", "tree"]:
        assert f" {package} " in f" {text} "
    assert " gh " not in f" {text} "


def test_runtime_dockerfile_installs_lcp_runtime_tools() -> None:
    text = render_runtime_dockerfile(default_runtime_manifest())
    assert f"FROM {DEFAULT_BASE_IMAGE}" in text
    assert "@anthropic-ai/claude-code@2.1.150" in text
    assert "@larksuite/cli@1.0.46" in text
    assert "LCP managed lark-cli wrapper" in text
    assert "git clone https://github.com/thiswind/feishu-claude-code-bridge-lcp-0.2.git" in text
    assert "git checkout 4c9c47c5b32f6353bc9d86fcfc45813cdcdf96cc" in text
    assert "npm install --include=dev" in text
    assert "npm run build" in text
    assert "npm pack --pack-destination /cache/tmp" in text
    assert "/cache/tmp/lark-channel-bridge.pack.out" in text
    assert "lastIndexOf" in text
    assert "text.indexOf" in text
    assert "missing npm pack JSON array" in text
    assert "/cache/tmp/lark-channel-bridge.tgz" in text
    assert 'RUN ["bash", "-lc", "set -eu\\n' in text
    assert 'prefix=\\"${NPM_CONFIG_PREFIX:-$HOME/.npm-global}\\"' in text
    assert '\nprefix="${NPM_CONFIG_PREFIX:-$HOME/.npm-global}"' not in text


def test_profile_dockerfile_creates_non_root_user_from_runtime_image() -> None:
    text = render_profile_dockerfile(HostUser(name="thiswind", uid=1000, gid=1000, home="/home/thiswind"), "lcp/runtime:test")
    assert "FROM lcp/runtime:test" in text
    assert "useradd --uid 1000 --gid 1000" in text
    assert "ENV HOME=/home/thiswind" in text
    assert "USER 1000:1000" in text
    assert "WORKDIR /home/thiswind" in text
