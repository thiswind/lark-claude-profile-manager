from pathlib import Path

from pydantic import BaseModel, Field

from . import __version__

RUNTIME_OS_TAG = "ubuntu24.04"
DEFAULT_BASE_IMAGE = f"lcp/base:{__version__}-{RUNTIME_OS_TAG}"
DEFAULT_RUNTIME_IMAGE = f"lcp/runtime:{__version__}-{RUNTIME_OS_TAG}"


class RuntimeTool(BaseModel):
    package: str
    version: str = "latest"
    versionLockDependency: str | None = None


class RuntimeManifest(BaseModel):
    schemaVersion: int = 1
    baseImage: str = DEFAULT_BASE_IMAGE
    runtimeImage: str = DEFAULT_RUNTIME_IMAGE
    tools: dict[str, RuntimeTool] = Field(default_factory=dict)


def default_runtime_manifest() -> RuntimeManifest:
    return RuntimeManifest(
        tools={
            "claude-code": RuntimeTool(package="@anthropic-ai/claude-code", versionLockDependency="claude-code"),
            "lark-cli": RuntimeTool(package="@larksuite/cli", versionLockDependency="lark-cli"),
            "lark-channel-bridge": RuntimeTool(package="lark-channel-bridge", versionLockDependency="feishu-claude-code-bridge"),
        }
    )


def load_runtime_manifest(path: Path) -> RuntimeManifest:
    if not path.exists():
        return default_runtime_manifest()
    return RuntimeManifest.model_validate_json(path.read_text(encoding="utf-8"))


def save_runtime_manifest(path: Path, manifest: RuntimeManifest) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    tmp.replace(path)
