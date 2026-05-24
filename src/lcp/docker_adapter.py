from dataclasses import dataclass
from pathlib import Path
import shlex
from typing import Any

import docker
from docker.errors import NotFound
from docker.models.containers import Container

from .dockerfile import render_profile_dockerfile
from .models import Profile, UBUNTU_LTS_IMAGE
from .store import LcpStore


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str


class DockerAdapter:
    def __init__(self, store: LcpStore, client: Any | None = None):
        self.store = store
        self.client = client or docker.from_env()

    def ping(self) -> bool:
        return bool(self.client.ping())

    def pull_base_image(self) -> None:
        self.client.images.pull(UBUNTU_LTS_IMAGE)

    def write_profile_dockerfile(self, profile: Profile) -> Path:
        profile_dir = self.store.ensure_profile_dirs(profile.name)
        dockerfile = profile_dir / "Dockerfile"
        dockerfile.write_text(render_profile_dockerfile(profile.container.user), encoding="utf-8")
        return dockerfile

    def build_profile_image(self, profile: Profile) -> None:
        self.pull_base_image()
        self.write_profile_dockerfile(profile)
        self.client.images.build(
            path=str(self.store.profile_dir(profile.name)),
            tag=profile.container.image,
            rm=True,
        )

    def create_profile_container(self, profile: Profile) -> Container:
        self.build_profile_image(profile)
        self._ensure_workspace_host_dir(profile)
        mounts = self._binds(profile)
        user = profile.container.user
        return self.client.containers.create(
            image=profile.container.image,
            name=profile.container.name,
            hostname=profile.container.hostname,
            detach=True,
            tty=True,
            labels={
                "lcp.profile": profile.name,
                "lcp.managed": "true",
            },
            volumes=mounts,
            working_dir=profile.workspace.defaultCwd,
            environment={
                "HOME": user.home,
                "USER": user.name,
            },
            user=f"{user.uid}:{user.gid}",
            restart_policy={"Name": profile.runtime.restartPolicy},
        )

    def get_container(self, profile: Profile) -> Container:
        return self.client.containers.get(profile.container.name)

    def get_container_or_none(self, profile: Profile) -> Container | None:
        try:
            return self.get_container(profile)
        except NotFound:
            return None

    def remove_container(self, profile: Profile) -> bool:
        container = self.get_container_or_none(profile)
        if container is None:
            return False
        container.remove(force=True)
        return True

    def start(self, profile: Profile) -> None:
        container = self.get_container(profile)
        container.start()
        self.ensure_compat_symlinks(profile)

    def ensure_compat_symlinks(self, profile: Profile) -> None:
        links = profile.mounts.desktop.compatSymlinks
        if not links:
            return
        commands = []
        target = shlex.quote(profile.mounts.desktop.containerPath)
        for link in links:
            link_path = shlex.quote(link)
            parent = shlex.quote(str(Path(link).parent))
            commands.append(f"mkdir -p {parent} && ln -sfn {target} {link_path}")
        result = self.exec_root(profile, " && ".join(commands))
        if result.exit_code != 0:
            raise RuntimeError(result.output)

    def stop(self, profile: Profile) -> None:
        container = self.get_container(profile)
        container.stop()

    def logs(self, profile: Profile) -> str:
        container = self.get_container(profile)
        output = container.logs(stdout=True, stderr=True)
        return output.decode("utf-8", errors="replace")

    def exec(self, profile: Profile, command: str) -> ExecResult:
        user = profile.container.user
        return self._exec(profile, command, user=f"{user.uid}:{user.gid}", home=user.home, user_name=user.name)

    def exec_root(self, profile: Profile, command: str) -> ExecResult:
        return self._exec(profile, command, user="0:0", home="/root", user_name="root", workdir="/")

    def _exec(self, profile: Profile, command: str, user: str, home: str, user_name: str, workdir: str | None = None) -> ExecResult:
        container = self.get_container(profile)
        result = container.exec_run(
            ["bash", "-lc", command],
            stdout=True,
            stderr=True,
            environment={"HOME": home, "USER": user_name},
            workdir=workdir or profile.workspace.defaultCwd,
            user=user,
        )
        output = result.output.decode("utf-8", errors="replace") if isinstance(result.output, bytes) else str(result.output)
        return ExecResult(exit_code=result.exit_code, output=output)

    def snapshot(self, profile: Profile, output_dir: Path | None = None) -> Path:
        container = self.get_container(profile)
        snapshot_dir = output_dir or (self.store.snapshots_dir / profile.name)
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        tag = f"lcp/{profile.name}:snapshot"
        image = container.commit(repository=f"lcp/{profile.name}", tag="snapshot")
        tar_path = snapshot_dir / f"{profile.name}-snapshot.tar"
        with tar_path.open("wb") as fh:
            for chunk in image.save(named=True):
                fh.write(chunk)
        return tar_path

    def load_image(self, image_tar: Path) -> None:
        with image_tar.open("rb") as fh:
            self.client.images.load(fh.read())

    def _ensure_workspace_host_dir(self, profile: Profile) -> None:
        desktop_container = profile.mounts.desktop.containerPath.rstrip("/")
        cwd = profile.workspace.defaultCwd
        if cwd.startswith(desktop_container + "/"):
            relative = cwd[len(desktop_container) + 1:]
            (Path(profile.mounts.desktop.hostPath) / relative).mkdir(parents=True, exist_ok=True)

    def _binds(self, profile: Profile) -> dict[str, dict[str, str]]:
        profile_dir = self.store.profile_dir(profile.name)
        user_home = profile.container.user.home
        binds = {
            profile.mounts.desktop.hostPath: {"bind": profile.mounts.desktop.containerPath, "mode": "rw"},
            str(profile_dir / "lark-channel"): {"bind": f"{user_home}/.lark-channel", "mode": "rw"},
            str(profile_dir / "lark-cli"): {"bind": f"{user_home}/.lark-cli", "mode": "rw"},
            str(profile_dir / "logs"): {"bind": "/logs", "mode": "rw"},
            str(self.store.cache_dir / "npm"): {"bind": "/cache/npm", "mode": "rw"},
            str(self.store.cache_dir / "pnpm"): {"bind": "/cache/pnpm", "mode": "rw"},
            str(self.store.cache_dir / "pip"): {"bind": "/cache/pip", "mode": "rw"},
            str(self.store.cache_dir / "tmp"): {"bind": "/cache/tmp", "mode": "rw"},
        }
        claude = profile.mounts.claude
        if claude.shareConfig:
            claude_dir = Path(claude.hostClaudeDir)
            claude_json = Path(claude.hostClaudeJson)
            if claude_dir.exists():
                binds[str(claude_dir)] = {"bind": f"{user_home}/.claude", "mode": "rw"}
            if claude_json.exists():
                binds[str(claude_json)] = {"bind": f"{user_home}/.claude.json", "mode": "rw"}
        github_cli = profile.mounts.githubCli
        if github_cli and github_cli.shareConfig:
            gh_dir = Path(github_cli.hostConfigDir)
            if gh_dir.exists():
                binds[str(gh_dir)] = {"bind": f"{user_home}/.config/gh", "mode": "rw"}
        return binds
