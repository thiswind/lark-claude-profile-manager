from pathlib import Path
import json
import os
import subprocess

import typer
from docker.errors import APIError
from pydantic import ValidationError
from rich.table import Table

from .bridge import bridge_status, start_bridge, stop_bridge, BRIDGE_LOG
from .docker_adapter import DockerAdapter
from .installer import install_runtime
from .lark_cli import bind_lark_cli
from .models import Profile, container_name, default_profile
from .selfcheck import collect_init_report
from .store import LcpStore
from .ui import console, print_banner, print_checks
from .verify import verify_profile

app = typer.Typer(help="Manage Lark Claude profile containers", context_settings={"help_option_names": ["-h", "--help"]})
profile_app = typer.Typer(help="Manage profiles", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
rm_app = typer.Typer(help="Debug removal commands", context_settings={"help_option_names": ["-h", "--help"]})
app.add_typer(profile_app, name="profile")
app.add_typer(rm_app, name="rm", hidden=True)


def _fail(message: str, hint: str | None = None) -> None:
    typer.echo(f"error: {message}")
    if hint:
        typer.echo(f"hint: {hint}")
    raise typer.Exit(1)


def _load_profile_or_exit(store: LcpStore, name: str) -> Profile:
    try:
        return store.load_profile(name)
    except FileNotFoundError:
        _fail(f"profile not found: {name}", "run `lcp profile list` to see existing profiles, or `lcp profile create <name>` to create one")
    except (json.JSONDecodeError, ValidationError) as exc:
        _fail(f"profile state is invalid: {store.profile_dir(name) / 'profile.json'}", str(exc))


def _profile_from_name_or_exit(name: str) -> str:
    try:
        return container_name(name)
    except ValueError as exc:
        _fail(str(exc), "profile names must use letters, numbers, dot, underscore, or dash")


def _get_container_or_exit(adapter: DockerAdapter, profile: Profile):
    container = adapter.get_container_or_none(profile)
    if container is None:
        _fail(f"container not found: {profile.container.name}", f"run `lcp profile rm {profile.name}` to remove stale profile state, or recreate the profile")
    return container


def _bind_lark_cli_or_exit(adapter: DockerAdapter, profile: Profile) -> None:
    result = bind_lark_cli(adapter, profile)
    if result.exit_code != 0:
        output = result.output.strip()
        if output:
            typer.echo(output)
        _fail(
            f"lark-cli bind failed for profile: {profile.name}",
            f"run `lcp bridge {profile.name} run` first if the bot has not been configured, or `lcp bridge {profile.name} bind-lark-cli` to retry",
        )
    output = result.output.strip()
    typer.echo(output or "lark-cli bound")


def _create_profile(name: str, desktop: str | None, install: bool) -> None:
    _profile_from_name_or_exit(name)
    store = LcpStore()
    store.init_dirs()
    profile_file = store.profile_dir(name) / "profile.json"
    if profile_file.exists():
        typer.echo(f"profile already exists: {profile_file}")
        typer.echo(f"use `lcp profile status {name}` to inspect it, or `lcp profile rm {name}` before recreating")
        raise typer.Exit(1)
    if store.config_file.exists() and desktop is None:
        config = store.load_config()
        desktop_host_path = Path(config.desktop.hostPath)
        compat_symlinks = [config.desktop.hostPath] if config.platform.environment == "wsl" else []
        user_name = config.hostUser.name
        uid = config.hostUser.uid
        gid = config.hostUser.gid
        display_name = config.hostUser.displayName
        arch = config.platform.arch
    else:
        report = collect_init_report(desktop)
        if report.has_required_failures:
            print_checks(report.checks)
            raise typer.Exit(1)
        config = report.config
        desktop_host_path = Path(config.desktop.hostPath)
        compat_symlinks = [config.desktop.hostPath] if config.platform.environment == "wsl" else []
        user_name = config.hostUser.name
        uid = config.hostUser.uid
        gid = config.hostUser.gid
        display_name = config.hostUser.displayName
        arch = config.platform.arch
    profile = default_profile(name, desktop_host_path, compat_symlinks, arch, user_name, uid, gid, display_name)
    adapter = DockerAdapter(store)
    if adapter.get_container_or_none(profile):
        typer.echo(f"container already exists: {profile.container.name}")
        typer.echo(f"use `lcp profile rm {name}` before recreating this profile")
        raise typer.Exit(1)
    try:
        container = adapter.create_profile_container(profile)
    except APIError as exc:
        if getattr(exc.response, "status_code", None) == 409:
            typer.echo(f"container already exists: {profile.container.name}")
            typer.echo(f"use `lcp profile rm {name}` before recreating this profile")
            raise typer.Exit(1) from exc
        raise
    store.save_profile(profile)
    adapter.start(profile)
    typer.echo(f"created: {profile.container.name}")
    if install:
        for result in install_runtime(adapter, profile):
            status = "ok" if result.exit_code == 0 else "failed"
            typer.echo(f"install step: {status}")
            if result.exit_code != 0:
                typer.echo(result.output)
                raise typer.Exit(result.exit_code)


def _list_profiles() -> None:
    store = LcpStore()
    adapter = DockerAdapter(store)
    table = Table(show_header=True)
    table.add_column("name")
    table.add_column("container")
    table.add_column("status")
    table.add_column("bridge")
    for name in store.list_profiles():
        profile = _load_profile_or_exit(store, name)
        container = adapter.get_container_or_none(profile)
        container_status = container.status if container else "missing"
        bridge = "-"
        if container:
            status = bridge_status(adapter, profile)
            bridge = "running" if status.running else "stopped"
        table.add_row(name, profile.container.name, container_status, bridge)
    console.print(table)


def _show_profile_status(name: str) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    container = _get_container_or_exit(adapter, profile)
    status = bridge_status(adapter, profile)
    typer.echo(f"name: {profile.name}")
    typer.echo(f"container: {container.name}")
    typer.echo(f"status: {container.status}")
    typer.echo(f"bridge: {'running' if status.running else 'stopped'}")
    if status.pid:
        typer.echo(f"bridge pid: {status.pid}")


def _open_profile_shell(name: str) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    _get_container_or_exit(DockerAdapter(store), profile)
    os.execvp("docker", ["docker", "exec", "-it", profile.container.name, "bash"])


def _verify_profile_command(name: str, run_claude: bool) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    failures = 0
    for check in verify_profile(adapter, profile, run_claude=run_claude):
        mark = "ok" if check.ok else "failed"
        typer.echo(f"{mark}: {check.name}")
        if not check.ok:
            failures += 1
            typer.echo(check.detail)
    if failures:
        raise typer.Exit(1)


def _snapshot_profile(name: str, output: str | None) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    tar_path = adapter.snapshot(profile, Path(output) if output else None)
    typer.echo(f"snapshot: {tar_path}")


def _restore_profile(name: str, image_tar: str) -> None:
    tar = Path(image_tar)
    if not tar.exists():
        _fail(f"snapshot tar not found: {image_tar}", "check the path passed to `--image-tar`")
    store = LcpStore()
    DockerAdapter(store).load_image(tar)
    typer.echo(f"loaded snapshot for {name}: {image_tar}")


def _start_bridge_runtime(name: str, start_container: bool = True) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    if start_container:
        adapter.start(profile)
        typer.echo(f"started: {profile.container.name}")
    _bind_lark_cli_or_exit(adapter, profile)
    status = start_bridge(adapter, profile)
    if not status.running:
        typer.echo(status.detail)
        raise typer.Exit(1)
    typer.echo(f"bridge started: {status.pid}")


def _stop_bridge_runtime(name: str, stop_container: bool = False) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    stop_bridge(adapter, profile)
    typer.echo("bridge stopped")
    if stop_container:
        adapter.stop(profile)
        typer.echo(f"stopped: {profile.container.name}")


def _restart_bridge_runtime(name: str) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    stop_bridge(adapter, profile)
    adapter.stop(profile)
    adapter.start(profile)
    _bind_lark_cli_or_exit(adapter, profile)
    status = start_bridge(adapter, profile)
    if not status.running:
        typer.echo(status.detail)
        raise typer.Exit(1)
    typer.echo(f"restarted: {profile.container.name}")
    typer.echo(f"bridge started: {status.pid}")


def _bind_lark_cli_runtime(name: str) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    _bind_lark_cli_or_exit(adapter, profile)


def _show_profile_logs(name: str, bridge: bool) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    if bridge:
        result = adapter.exec(profile, f"test -f {BRIDGE_LOG} && tail -n 200 {BRIDGE_LOG} || true")
        typer.echo(result.output)
    else:
        typer.echo(adapter.logs(profile))


def _remove_container_only(name: str, yes: bool) -> None:
    if not yes and not typer.confirm(f"Remove container for profile {name}? Profile state will be kept."):
        raise typer.Exit(1)
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    removed = DockerAdapter(store).remove_container(profile)
    if removed:
        typer.echo(f"removed container: {profile.container.name}")
    else:
        typer.echo(f"container already absent: {profile.container.name}")
    typer.echo(f"profile state kept at: {store.profile_dir(name)}")


def _remove_profile_state_only(name: str, yes: bool) -> None:
    store = LcpStore()
    profile_dir = store.profile_dir(name)
    if not profile_dir.exists():
        typer.echo(f"profile already absent: {profile_dir}")
        return
    if not yes and not typer.confirm(f"Remove profile state {name}? Container will not be removed."):
        raise typer.Exit(1)
    removed = store.remove_profile(name)
    typer.echo(f"removed profile state: {removed}")


def _remove_profile_runtime(name: str, yes: bool) -> None:
    store = LcpStore()
    profile_dir = store.profile_dir(name)
    if not profile_dir.exists():
        typer.echo(f"profile already absent: {profile_dir}")
        return
    profile = _load_profile_or_exit(store, name)
    if not yes and not typer.confirm(
        f"Remove profile {name}? This will stop bridge, remove container {profile.container.name}, and delete profile state at {profile_dir}."
    ):
        raise typer.Exit(1)
    adapter = DockerAdapter(store)
    stop_bridge(adapter, profile)
    removed_container = adapter.remove_container(profile)
    if removed_container:
        typer.echo(f"removed container: {profile.container.name}")
    else:
        typer.echo(f"container already absent: {profile.container.name}")
    removed_profile = store.remove_profile(name)
    typer.echo(f"removed profile state: {removed_profile}")


@app.command()
def init(
    desktop: str | None = typer.Option(None, help="Explicit host Desktop path"),
    container_user: str | None = typer.Option(None, help="Explicit container user name"),
) -> None:
    store = LcpStore()
    store.init_dirs()
    report = collect_init_report(desktop, container_user)
    print_banner()
    console.print("[bold]Configuring local environment[/bold]\n")
    print_checks(report.checks)
    if report.has_required_failures:
        console.print("\n[red]Required checks failed. Configuration was not written.[/red]")
        raise typer.Exit(1)
    store.save_config(report.config)
    console.print(f"\n[green]Configuration written:[/green] {store.config_file}")


@app.command()
def doctor() -> None:
    store = LcpStore()
    report = collect_init_report()
    print_banner()
    console.print("[bold]Checking local environment[/bold]\n")
    print_checks(report.checks)
    if store.config_file.exists():
        config = store.load_config()
        user_label = f"{config.hostUser.displayName} → {config.hostUser.name}" if config.hostUser.displayName and config.hostUser.displayName != config.hostUser.name else config.hostUser.name
        console.print(f"\n[green]Config:[/green] {store.config_file}")
        console.print(f"Desktop: {config.desktop.hostPath}")
        console.print(f"User: {user_label} ({config.hostUser.uid}:{config.hostUser.gid})")
    else:
        console.print(f"\n[yellow]Config not found:[/yellow] {store.config_file}")
    if report.has_required_failures:
        raise typer.Exit(1)


@profile_app.command("create")
def profile_create(
    name: str,
    desktop: str | None = typer.Option(None, help="Explicit host Desktop path"),
    install: bool = typer.Option(True, help="Install Claude Code, lark-cli, and bridge"),
) -> None:
    _create_profile(name, desktop, install)


@profile_app.command("list")
def profile_list() -> None:
    _list_profiles()


@profile_app.command("status")
def profile_status(name: str) -> None:
    _show_profile_status(name)


@profile_app.command("shell")
def profile_shell(name: str) -> None:
    _open_profile_shell(name)


@profile_app.command("verify")
def profile_verify(name: str, run_claude: bool = typer.Option(True, help="Run Claude non-interactive check")) -> None:
    _verify_profile_command(name, run_claude)


@profile_app.command("snapshot")
def profile_snapshot(name: str, output: str | None = typer.Option(None, help="Output backup directory")) -> None:
    _snapshot_profile(name, output)


@profile_app.command("restore")
def profile_restore(name: str, image_tar: str = typer.Option(..., help="Snapshot tar path")) -> None:
    _restore_profile(name, image_tar)


@profile_app.command("rm")
def profile_rm(name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Confirm removal")) -> None:
    _remove_profile_runtime(name, yes)


@app.command(hidden=True)
def create(
    name: str,
    desktop: str | None = typer.Option(None, help="Explicit host Desktop path"),
    install: bool = typer.Option(True, help="Install Claude Code, lark-cli, and bridge"),
) -> None:
    _create_profile(name, desktop, install)


@app.command("list", hidden=True)
def list_profiles() -> None:
    _list_profiles()


@app.command(hidden=True)
def status(name: str) -> None:
    _show_profile_status(name)


@app.command(hidden=True)
def shell(name: str) -> None:
    _open_profile_shell(name)


@app.command(hidden=True)
def verify(name: str, run_claude: bool = typer.Option(True, help="Run Claude non-interactive check")) -> None:
    _verify_profile_command(name, run_claude)


@app.command(hidden=True)
def snapshot(name: str, output: str | None = typer.Option(None, help="Output backup directory")) -> None:
    _snapshot_profile(name, output)


@app.command(hidden=True)
def restore(name: str, image_tar: str = typer.Option(..., help="Snapshot tar path")) -> None:
    _restore_profile(name, image_tar)


@app.command(hidden=True)
def start(name: str, bridge: bool = typer.Option(True, help="Start lark-channel-bridge in the background")) -> None:
    if bridge:
        _start_bridge_runtime(name)
        return
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    adapter.start(profile)
    typer.echo(f"started: {profile.container.name}")


@app.command(hidden=True)
def stop(name: str, container: bool = typer.Option(True, help="Stop the profile container after stopping bridge")) -> None:
    _stop_bridge_runtime(name, stop_container=container)


@app.command(hidden=True)
def restart(name: str) -> None:
    _restart_bridge_runtime(name)


@app.command(
    help="""Manage bridge lifecycle and proxy lark-channel-bridge commands.

\b
Common actions:
  lcp bridge <profile> run            Foreground QR/debug
  lcp bridge <profile> start          Background run
  lcp bridge <profile> status         Show status
  lcp bridge <profile> logs           Show logs
  lcp bridge <profile> stop           Stop bridge
  lcp bridge <profile> restart        Restart bridge
  lcp bridge <profile> bind-lark-cli  Bind lark-cli to this profile's bot

Other arguments are proxied to lark-channel-bridge inside the container.
""",
    context_settings={"allow_extra_args": True, "ignore_unknown_options": True},
)
def bridge(ctx: typer.Context, name: str) -> None:
    args = list(ctx.args)
    action = args[0] if args else "status"
    if action == "start":
        _start_bridge_runtime(name)
        return
    if action == "stop":
        _stop_bridge_runtime(name)
        return
    if action == "restart":
        _restart_bridge_runtime(name)
        return
    if action == "bind-lark-cli":
        _bind_lark_cli_runtime(name)
        return
    if action == "status":
        _show_profile_status(name)
        return
    if action == "logs":
        _show_profile_logs(name, bridge=True)
        return

    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    _get_container_or_exit(DockerAdapter(store), profile)
    command = ["docker", "exec", "-it", profile.container.name, "lark-channel-bridge", *args]
    raise typer.Exit(subprocess.call(command))


@app.command(hidden=True)
def remove(name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Confirm removal")) -> None:
    _remove_profile_runtime(name, yes)


@rm_app.command("container")
def rm_container(name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Confirm removal")) -> None:
    _remove_container_only(name, yes)


@rm_app.command("profile")
def rm_profile(name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Confirm removal")) -> None:
    _remove_profile_state_only(name, yes)


@app.command(hidden=True)
def logs(name: str, bridge: bool = typer.Option(True, help="Show bridge log instead of container logs")) -> None:
    _show_profile_logs(name, bridge)


if __name__ == "__main__":
    app()
