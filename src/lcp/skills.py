from pathlib import Path

from .models import Profile
from .paths import ensure_dir


LARK_CLI_FILE_SEND_SKILL = """---
name: lark-cli-file-send
description: Use when sending files, images, documents, zips, or attachments through Feishu/Lark from an LCP container with lark-cli.
---

# Lark CLI file sending from LCP

Use the profile bot identity by default. Do not start user OAuth from a group chat; if user OAuth is truly required, ask the user to start it in private chat.

Check identity first:

```bash
lark-cli config show
lark-cli config strict-mode
```

Expected result:

- workspace/profile is the Lark Channel profile
- `strict-mode: bot`
- no user login is required

If identity is missing, rebind the profile bot:

```bash
LARK_CHANNEL=1 lark-cli config bind --source lark-channel --identity bot-only --force
LARK_CHANNEL=1 lark-cli config default-as bot
LARK_CHANNEL=1 lark-cli config strict-mode bot
```

## Sending files

`--file` must be a cwd-relative path. Absolute paths and `..` are rejected.

Correct pattern:

```bash
cd /path/to/directory-containing-file
lark-cli im +messages-send --chat-id <oc_chat_id> --file ./filename.zip
```
"""


def ensure_core_skills(profile_dir: Path, profile: Profile) -> None:
    skill_dir = profile_dir / "skills" / "lark-cli-file-send"
    ensure_dir(skill_dir)
    (skill_dir / "SKILL.md").write_text(LARK_CLI_FILE_SEND_SKILL, encoding="utf-8")
