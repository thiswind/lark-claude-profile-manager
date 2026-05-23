from pathlib import Path


def default_lcp_home() -> Path:
    return Path.home() / ".lcp"


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path
