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

    def start(self):
        self.status = "running"

    def commit(self, repository, tag):
        self.repository = repository
        self.tag = tag
        return FakeImage()

    def exec_run(self, command, stdout=True, stderr=True, environment=None, workdir=None, user=None):
        self.exec_command = command
        self.exec_user = user
        return type("ExecRunResult", (), {"exit_code": 0, "output": b""})()


class FakeContainers:
    def __init__(self, container):
        self.container = container
        self.created = None

    def get(self, name):
        return self.container

    def create(self, **kwargs):
        self.created = kwargs
        return self.container


class FakeImages:
    def get(self, image):
        self.local_image = image
        return object()

    def pull(self, image):
        self.pulled = image

    def build(self, path, tag, rm, dockerfile=None):
        self.built = {"path": path, "tag": tag, "rm": rm, "dockerfile": dockerfile}

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


def test_start_creates_compat_symlinks(tmp_path: Path) -> None:
    client = FakeClient()
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", ["/mnt/c/Users/Administrator/Desktop"], "amd64", "thiswind", 1000, 1000)
    store.save_profile(profile)
    adapter = DockerAdapter(store, client)

    adapter.start(profile)

    assert client.container.exec_user == "0:0"
    command = client.container.exec_command
    assert command == ["bash", "-lc", "mkdir -p /mnt/c/Users/Administrator && ln -sfn /home/thiswind/Desktop /mnt/c/Users/Administrator/Desktop"]


def test_create_mounts_github_cli_config_when_present(tmp_path: Path) -> None:
    client = FakeClient()
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    gh_dir = tmp_path / "gh"
    gh_dir.mkdir()
    profile.mounts.githubCli.hostConfigDir = str(gh_dir)
    adapter = DockerAdapter(store, client)

    adapter.create_profile_container(profile)

    assert client.containers.created["volumes"][str(gh_dir)] == {"bind": "/home/thiswind/.config/gh", "mode": "rw"}


def test_create_sets_restart_policy(tmp_path: Path) -> None:
    client = FakeClient()
    store = LcpStore(tmp_path / ".lcp")
    profile = default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)
    adapter = DockerAdapter(store, client)

    adapter.create_profile_container(profile)

    assert client.containers.created["restart_policy"] == {"Name": "always"}
