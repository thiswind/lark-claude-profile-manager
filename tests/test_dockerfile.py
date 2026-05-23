from lcp.dockerfile import render_profile_dockerfile
from lcp.host_user import HostUser


def test_dockerfile_creates_non_root_user_and_node_24() -> None:
    text = render_profile_dockerfile(HostUser(name="thiswind", uid=1000, gid=1000, home="/home/thiswind"))
    assert "FROM ubuntu:24.04" in text
    assert "setup_24.x" in text
    assert "useradd --uid 1000 --gid 1000" in text
    assert "ENV HOME=/home/thiswind" in text
    assert "USER 1000:1000" in text
    assert "WORKDIR /home/thiswind" in text
