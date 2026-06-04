from .models import Profile
from .store import LcpStore


LARK_CLI_FILE_SEND_SKILL_NAME = "lark-cli-file-send"


def lark_cli_file_send_skill_dir(store: LcpStore, profile: Profile):
    return store.profile_dir(profile.name) / "skills" / LARK_CLI_FILE_SEND_SKILL_NAME


def ensure_core_profile_skills(store: LcpStore, profile: Profile) -> None:
    skill_dir = lark_cli_file_send_skill_dir(store, profile)
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(_lark_cli_file_send_skill_body(profile), encoding="utf-8")


def _lark_cli_file_send_skill_body(profile: Profile) -> str:
    return f"""---
name: {LARK_CLI_FILE_SEND_SKILL_NAME}
description: Send files to the current Feishu/Lark conversation from an LCP profile using profile-local bot identity.
---

# Lark CLI file sending in LCP

Use this skill when sending generated files or attachments from this LCP profile.

Rules:

1. Use plain `lark-cli`; LCP wraps it so it defaults to the profile-local Lark Channel bot identity.
2. Run file send commands from the directory that contains the file, or pass a path relative to the current working directory.
3. Do not use absolute host paths with `--file`; copy or create the file inside the profile workspace first.
4. Prefer paths under `{profile.workspace.defaultCwd}` for files created for this profile.
5. If authentication fails, run `lcp bridge {profile.name} bind-lark-cli` from the host admin context.

Example:

```bash
cd {profile.workspace.defaultCwd}
lark-cli im send --file ./report.pdf --chat-id <chat_id>
```
"""
