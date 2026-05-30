import pytest
from pydantic import ValidationError

from lcp.version_lock import VersionLock, VersionLockEntry, dependency_npm_install_spec, load_version_lock, verify_version_lock


def test_load_version_lock_matches_package_version() -> None:
    lock = load_version_lock()

    assert lock.lcpVersion == "0.2.1"
    assert any(dependency.name == "feishu-claude-code-bridge" for dependency in lock.dependencies)
    assert verify_version_lock(lock) == []


def test_dependency_npm_install_spec_uses_controlled_commit() -> None:
    assert dependency_npm_install_spec("feishu-claude-code-bridge") == "git+https://github.com/thiswind/feishu-claude-code-bridge-lcp-0.2.git#4c9c47c5b32f6353bc9d86fcfc45813cdcdf96cc"
    assert dependency_npm_install_spec("lark-channel-bridge") == "git+https://github.com/thiswind/feishu-claude-code-bridge-lcp-0.2.git#4c9c47c5b32f6353bc9d86fcfc45813cdcdf96cc"
    assert dependency_npm_install_spec("lark-cli") == "@larksuite/cli@1.0.41"


def test_controlled_dependency_requires_repo_tag_commit() -> None:
    with pytest.raises(ValidationError, match="controlled dependency requires repo, tag, and commit"):
        VersionLockEntry(
            name="bridge",
            role="Bridge",
            risk="critical",
            policy="controlled-fork",
            upstream={
                "repo": "https://github.com/example/upstream",
                "branch": "main",
                "commit": "abc123",
            },
        )


def test_controlled_dependency_rejects_floating_tag() -> None:
    with pytest.raises(ValidationError, match="controlled tag must not be floating"):
        VersionLockEntry(
            name="bridge",
            role="Bridge",
            risk="critical",
            policy="controlled-fork",
            controlled={
                "repo": "https://github.com/example/bridge-lcp-0.2",
                "tag": "main",
                "commit": "abc123",
            },
            upstream={
                "repo": "https://github.com/example/upstream",
                "branch": "main",
                "commit": "abc123",
            },
        )


def test_critical_dependency_rejects_latest_version() -> None:
    with pytest.raises(ValidationError, match="critical dependency must not use latest"):
        VersionLockEntry(
            name="lark-cli",
            role="CLI",
            risk="critical",
            policy="pin-first",
            package="@larksuite/cli",
            version="latest",
        )


def test_validation_record_must_match_lock_version() -> None:
    with pytest.raises(ValidationError, match="validation version does not match lock version"):
        VersionLock(
            lcpVersion="0.2.1",
            generatedAt="2026-05-28",
            dependencies=[
                {
                    "name": "lark-cli",
                    "role": "CLI",
                    "risk": "critical",
                    "policy": "pin-first",
                    "package": "@larksuite/cli",
                    "version": "1.0.41",
                    "validation": {
                        "lcpVersion": "0.2.0",
                        "validatedAt": "2026-05-28",
                        "profiles": [],
                        "commands": [],
                    },
                }
            ],
        )
