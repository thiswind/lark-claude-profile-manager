import json
import re
import shutil
from pathlib import Path

from pydantic import BaseModel

from .models import LCP_PROFILE_WORKSPACES_DIR, Profile, container_name, profile_image_name
from .store import LcpStore


class BotIdentity(BaseModel):
    appId: str | None = None
    name: str | None = None

    @property
    def label(self) -> str:
        if self.name and self.appId:
            return f"{self.name} ({self.appId})"
        return self.name or self.appId or "-"


def _first_app(data) -> dict:
    if not isinstance(data, dict):
        return {}
    app = data.get("accounts", {}).get("app", {})
    if isinstance(app, dict) and app:
        return app
    apps = data.get("apps")
    if isinstance(apps, dict):
        first = next(iter(apps.values()), {})
        return first if isinstance(first, dict) else {}
    if isinstance(apps, list) and apps:
        first = apps[0]
        return first if isinstance(first, dict) else {}
    return {}


def profile_bot_identity(store: LcpStore, profile: Profile) -> BotIdentity:
    bridge_config = store.profile_dir(profile.name) / "lark-channel" / "config.json"
    cli_config = store.profile_dir(profile.name) / "lark-cli" / "lark-channel" / "config.json"
    app_id = None
    name = None
    for path in [bridge_config, cli_config]:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        app = _first_app(data)
        app_id = app_id or app.get("id") or app.get("appId")
        name = name or app.get("name") or app.get("appName") or app.get("botName")
    return BotIdentity(appId=app_id, name=name)


def profile_name_from_bot(identity: BotIdentity) -> str | None:
    source = identity.name or identity.appId
    if not source:
        return None
    value = re.sub(r"[^a-zA-Z0-9_.-]+", "-", source).strip("-._").lower()
    if not value:
        return None
    if not re.match(r"[a-zA-Z0-9]", value):
        value = f"p-{value}"
    return value[:63]


def renamed_profile(profile: Profile, new_name: str) -> Profile:
    updated = profile.model_copy(deep=True)
    updated.name = new_name
    updated.description = f"LCP profile {new_name}"
    updated.container.name = container_name(new_name)
    updated.container.image = profile_image_name(new_name)
    updated.container.hostname = updated.container.name
    desktop = updated.mounts.desktop.containerPath.rstrip("/")
    updated.workspace.defaultCwd = f"{desktop}/Projects/{LCP_PROFILE_WORKSPACES_DIR}/{new_name}"
    return updated


def rename_profile_state(store: LcpStore, old_name: str, new_profile: Profile) -> None:
    old_dir = store.profile_dir(old_name)
    new_dir = store.profile_dir(new_profile.name)
    if new_dir.exists():
        raise FileExistsError(f"profile already exists: {new_profile.name}")
    new_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(old_dir), str(new_dir))
    store.save_profile(new_profile)
