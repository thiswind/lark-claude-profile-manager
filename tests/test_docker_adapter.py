from pathlib import Path

from lcp.docker_adapter import DockerAdapter
from lcp.models import default_profile
from lcp.store import LcpStore


class FakeImage:
    def save(self, named=True):
        yield b"snapshot-data"


class FakeContainer:
    name = "lcp-project1"
    status = "running"

    def commit(self, repository, tag):
        self.repository = repository
        self.tag = tag
        return FakeImage()


class FakeContainers:
    def __init__(self, container):
        self.container = container

    def get(self, name):
        return self.container


class FakeImages:
    def load(self, data):
        self.loaded = data


class FakeClient:
    def __init__(self):
        self.container = FakeContainer()
        self.containers = FakeContainers(self.container)
        self.images = FakeImages()

    def ping(self):
        return True


def test_snapshot_writes_tar(tmp_path: Path) -> None:
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    adapter = DockerAdapter(store, FakeClient())

    tar_path = adapter.snapshot(profile)

    assert tar_path == store.snapshots_dir / "project1" / "project1-snapshot.tar"
    assert tar_path.read_bytes() == b"snapshot-data"


def test_load_image_reads_tar(tmp_path: Path) -> None:
    client = FakeClient()
    store = LcpStore(tmp_path / ".lcp")
    adapter = DockerAdapter(store, client)
    tar_path = tmp_path / "image.tar"
    tar_path.write_bytes(b"image-data")

    adapter.load_image(tar_path)

    assert client.images.loaded == b"image-data"
