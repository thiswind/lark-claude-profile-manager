import json

from lcp.models import default_profile
from lcp.profile_meta import profile_bot_identity, profile_name_from_bot, rename_profile_state, renamed_profile
from lcp.store import LcpStore


def test_profile_bot_identity_reads_lark_channel_config(tmp_path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    config = store.profile_dir("project1") / "lark-channel" / "config.json"
    config.write_text(json.dumps({"accounts": {"app": {"id": "cli_123", "name": "Research Bot"}}}), encoding="utf-8")

    identity = profile_bot_identity(store, profile)

    assert identity.appId == "cli_123"
    assert identity.name == "Research Bot"
    assert identity.label == "Research Bot (cli_123)"
    assert profile_name_from_bot(identity) == "research-bot"


def test_renamed_profile_updates_names_and_workspace(tmp_path) -> None:
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)

    updated = renamed_profile(profile, "research-bot")

    assert updated.name == "research-bot"
    assert updated.container.name == "lcp-research-bot"
    assert updated.container.image == "lcp/research-bot:base"
    assert updated.container.hostname == "lcp-research-bot"
    assert updated.workspace.defaultCwd.endswith("/lcp_profiles/research-bot")


def test_rename_profile_state_moves_directory(tmp_path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    updated = renamed_profile(profile, "research-bot")

    rename_profile_state(store, "project1", updated)

    assert not store.profile_dir("project1").exists()
    assert store.load_profile("research-bot").name == "research-bot"
