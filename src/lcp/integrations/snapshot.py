from datetime import UTC, datetime
from pathlib import Path
import hashlib
import json
import shutil
import stat
import uuid

from .models import SnapshotFile, SnapshotMetadata


SECRET_KEYS = ("token", "secret", "password", "key", "credential", "auth")


def redact_secret(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def _chmod_secure(path: Path) -> None:
    if path.is_dir():
        path.chmod(0o700)
        for child in path.iterdir():
            _chmod_secure(child)
    else:
        path.chmod(0o600)


def _hash_file(path: Path, root: Path) -> SnapshotFile:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return SnapshotFile(path=str(path.relative_to(root)), sha256=digest.hexdigest(), size=path.stat().st_size)


def _metadata_files(snapshot: Path) -> list[SnapshotFile]:
    if snapshot.is_file():
        return [_hash_file(snapshot, snapshot.parent)]
    return [_hash_file(path, snapshot) for path in sorted(snapshot.rglob("*")) if path.is_file()]


def write_metadata(path: Path, metadata: SnapshotMetadata) -> None:
    path.write_text(json.dumps(metadata.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path.chmod(0o600)


def load_metadata(path: Path) -> SnapshotMetadata:
    return SnapshotMetadata.model_validate_json(path.read_text(encoding="utf-8"))


def capture_snapshot(provider: str, source: Path, destination: Path, host_version: str | None = None) -> SnapshotMetadata:
    if not source.exists():
        raise FileNotFoundError(source)
    if destination.exists():
        shutil.rmtree(destination) if destination.is_dir() else destination.unlink()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        shutil.copytree(source, destination, symlinks=True)
    else:
        destination.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination / source.name)
    _chmod_secure(destination)
    snapshot_id = uuid.uuid4().hex
    metadata = SnapshotMetadata(
        provider=provider,
        snapshotId=snapshot_id,
        capturedAt=datetime.now(UTC).isoformat(),
        hostVersion=host_version,
        sourcePath=str(source),
        files=_metadata_files(destination),
    )
    write_metadata(destination / "metadata.json", metadata)
    return metadata


def move_snapshot_to_trash(snapshot_dir: Path, trash_root: Path, snapshot_id: str | None = None) -> Path | None:
    if not snapshot_dir.exists():
        return None
    trash_root.mkdir(parents=True, exist_ok=True)
    trash_root.chmod(0o700)
    target = trash_root / (snapshot_id or datetime.now(UTC).strftime("%Y%m%d%H%M%S"))
    if target.exists():
        target = trash_root / f"{target.name}-{uuid.uuid4().hex[:8]}"
    shutil.move(str(snapshot_dir), str(target))
    _chmod_secure(target)
    return target
