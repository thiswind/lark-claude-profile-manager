from pathlib import Path

from pydantic import BaseModel, Field


class RuntimeTool(BaseModel):
    package: str
    version: str = "latest"


class RuntimeManifest(BaseModel):
    schemaVersion: int = 1
    baseImage: str = "lcp/base:latest"
    runtimeImage: str = "lcp/runtime:latest"
    tools: dict[str, RuntimeTool] = Field(default_factory=dict)


def default_runtime_manifest() -> RuntimeManifest:
    return RuntimeManifest(
        tools={
            "claude-code": RuntimeTool(package="@anthropic-ai/claude-code"),
            "lark-cli": RuntimeTool(package="@larksuite/cli"),
            "lark-channel-bridge": RuntimeTool(package="lark-channel-bridge"),
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
