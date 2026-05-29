from pathlib import Path
import json
import os
import subprocess

import typer
from docker.errors import APIError
from pydantic import ValidationError
from rich.table import Table

from . import __version__
from .bridge import bridge_status, start_bridge, stop_bridge, BRIDGE_LOG
from .docker_adapter import DockerAdapter
from .installer import install_runtime
from .integrations.service import IntegrationService
from .lark_cli import LARK_CLI_BOT_IDENTITY_CHECK, bind_lark_cli
from .models import Profile, container_name, default_profile
from .rebuild import RebuildError, cleanup_rollback_containers, list_rollback_containers, plan_profile_rebuild, rebuild_profile
from .selfcheck import collect_init_report
from .store import LcpStore
from .ui import console, print_banner, print_checks
from .verify import verify_profile
from .version_lock import load_version_lock, verify_version_lock

app = typer.Typer(help="Manage Lark Claude profile containers", context_settings={"help_option_names": ["-h", "--help"]})
profile_app = typer.Typer(help="Manage profiles", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
rm_app = typer.Typer(help="Debug removal commands", context_settings={"help_option_names": ["-h", "--help"]})
integration_app = typer.Typer(help="Manage profile host integrations", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
image_app = typer.Typer(help="Manage LCP shared images", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
runtime_app = typer.Typer(help="Manage LCP runtime tools", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
version_lock_app = typer.Typer(help="Inspect the LCP release dependency lock", no_args_is_help=True, context_settings={"help_option_names": ["-h", "--help"]})
app.add_typer(profile_app, name="profile")
app.add_typer(integration_app, name="integration")
app.add_typer(image_app, name="image")
app.add_typer(runtime_app, name="runtime")
app.add_typer(version_lock_app, name="version-lock")
app.add_typer(rm_app, name="rm", hidden=True)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"lcp {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version_callback, is_eager=True, help="Show version and exit"),
) -> None:
    pass


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


def _is_ai_contributor_identity(name: str | None, email: str | None) -> bool:
    value = f"{name or ''} {email or ''}".lower()
    return "claude" in value or "anthropic" in value


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
    bound = adapter.exec(profile, LARK_CLI_BOT_IDENTITY_CHECK)
    if bound.exit_code == 0:
        output = bound.output.strip()
        typer.echo(output or "lark-cli bound")
        return
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
        if not config.gitIdentity.name or not config.gitIdentity.email or _is_ai_contributor_identity(config.gitIdentity.name, config.gitIdentity.email):
            report = collect_init_report(desktop)
            if report.has_required_failures:
                print_checks(report.checks)
                raise typer.Exit(1)
            config = report.config
            store.save_config(config)
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
    profile = default_profile(
        name,
        desktop_host_path,
        compat_symlinks,
        arch,
        user_name,
        uid,
        gid,
        display_name,
        config.gitIdentity.name,
        config.gitIdentity.email,
    )
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


def _print_rebuild_plan(plan) -> None:
    typer.echo(f"profile: {plan.profile}")
    typer.echo(f"container: {plan.container} ({plan.currentStatus})")
    typer.echo(f"bridge: {'running' if plan.bridgeRunning else 'stopped'}")
    typer.echo(f"current image: {plan.currentImage}")
    typer.echo(f"runtime image: {plan.runtimeImage}")
    typer.echo(f"Claude Code continuity: {'safe' if plan.claudeContinuity.safe else 'unsafe'}")
    for reason in plan.claudeContinuity.reasons:
        typer.echo(f"  reason: {reason}")
    typer.echo("preserved mounts:")
    for mount in plan.preservedMounts:
        typer.echo(f"  {mount}")
    typer.echo("active integrations:")
    if plan.activeIntegrations:
        for provider in plan.activeIntegrations:
            typer.echo(f"  {provider}: will be reapplied after rebuild")
    else:
        typer.echo("  none")
    typer.echo("verification:")
    for command in plan.verification:
        typer.echo(f"  {command}")


def _print_rebuild_result(profile: Profile, result) -> None:
    typer.echo(f"rebuilt: {profile.container.name}")
    typer.echo(f"rollback kept: {result.rollbackContainer}")
    for line in result.verification:
        typer.echo(f"verified: {line}")
    for integration in result.integrations:
        mark = "ok" if integration.ok else "failed"
        command = f" command={integration.command}" if integration.command else ""
        typer.echo(f"integration {mark}: {integration.provider}{command}")
    if result.bridgeRestored:
        typer.echo("bridge restored: running")


def _rebuild_one(store: LcpStore, adapter: DockerAdapter, name: str, dry_run: bool) -> Profile:
    profile = _load_profile_or_exit(store, name)
    plan = plan_profile_rebuild(store, adapter, profile)
    _print_rebuild_plan(plan)
    if dry_run:
        typer.echo("dry-run: would rebuild the profile image and safely replace the container with rollback")
    return profile


def _profile_names_or_exit(store: LcpStore, name: str | None, all_profiles: bool, command_hint: str) -> list[str]:
    if all_profiles and name:
        _fail("choose either a profile name or --all, not both")
    if not all_profiles and not name:
        _fail("profile name required", command_hint)
    names = store.list_profiles() if all_profiles else [name]
    if not names:
        _fail("no profiles found")
    return names


def _rebuild_profile(name: str | None, all_profiles: bool, dry_run: bool, yes: bool) -> None:
    store = LcpStore()
    adapter = DockerAdapter(store)
    names = _profile_names_or_exit(store, name, all_profiles, "use `lcp profile rebuild <name> --dry-run` or `lcp profile rebuild --all --dry-run`")
    profiles = []
    for index, profile_name in enumerate(names):
        if index:
            typer.echo("---")
        profiles.append(_rebuild_one(store, adapter, profile_name, dry_run))
    if dry_run:
        return
    if not yes:
        hint = "run `lcp profile rebuild --all --dry-run` first, then rerun with `--yes`" if all_profiles else "run `lcp profile rebuild <name> --dry-run` first, then rerun with `--yes`"
        _fail("profile rebuild requires explicit confirmation", hint)
    for index, profile in enumerate(profiles):
        if index:
            typer.echo("---")
        try:
            result = rebuild_profile(store, adapter, profile)
        except RebuildError as exc:
            typer.echo(f"error: {profile.name}: {exc}")
            for line in exc.recovery:
                if line:
                    typer.echo(f"recovery: {line}")
            raise typer.Exit(1) from exc
        _print_rebuild_result(profile, result)


def _cleanup_rollbacks(name: str | None, all_profiles: bool, dry_run: bool, yes: bool) -> None:
    store = LcpStore()
    adapter = DockerAdapter(store)
    names = _profile_names_or_exit(store, name, all_profiles, "use `lcp profile cleanup-rollbacks <name> --dry-run` or `lcp profile cleanup-rollbacks --all --dry-run`")
    profiles = [_load_profile_or_exit(store, profile_name) for profile_name in names]
    plans = [(profile, list_rollback_containers(adapter, profile)) for profile in profiles]
    for index, (profile, rollbacks) in enumerate(plans):
        if index:
            typer.echo("---")
        typer.echo(f"profile: {profile.name}")
        if rollbacks:
            for rollback in rollbacks:
                typer.echo(f"rollback: {rollback.name} ({rollback.status})")
        else:
            typer.echo("rollback: none")
        if dry_run:
            typer.echo(f"dry-run: would remove {len(rollbacks)} rollback container(s)")
    if dry_run:
        return
    if not yes:
        hint = "run `lcp profile cleanup-rollbacks --all --dry-run` first, then rerun with `--yes`" if all_profiles else "run `lcp profile cleanup-rollbacks <name> --dry-run` first, then rerun with `--yes`"
        _fail("rollback cleanup requires explicit confirmation", hint)
    for index, profile in enumerate(profiles):
        if index:
            typer.echo("---")
        result = cleanup_rollback_containers(adapter, profile)
        typer.echo(f"profile: {profile.name}")
        if result.removed:
            for name in result.removed:
                typer.echo(f"removed rollback: {name}")
        else:
            typer.echo("removed rollback: none")


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


def _image_status() -> None:
    store = LcpStore()
    manifest = store.load_runtime_manifest()
    typer.echo(f"base image: {manifest.baseImage}")
    typer.echo(f"runtime image: {manifest.runtimeImage}")
    typer.echo(f"runtime manifest: {store.runtime_manifest_file}")


def _build_base_image(dry_run: bool, yes: bool) -> None:
    store = LcpStore()
    store.init_dirs()
    manifest = store.load_runtime_manifest()
    typer.echo(f"base image: {manifest.baseImage}")
    typer.echo(f"dockerfile: {store.runtime_dir / 'Dockerfile.base'}")
    if dry_run:
        typer.echo("dry-run: would render Dockerfile.base and build the base image")
        return
    if not yes and not typer.confirm(f"Build base image {manifest.baseImage}?"):
        raise typer.Exit(1)
    DockerAdapter(store).build_base_image()
    typer.echo(f"built: {manifest.baseImage}")


def _runtime_list() -> None:
    store = LcpStore()
    manifest = store.load_runtime_manifest()
    typer.echo(f"base image: {manifest.baseImage}")
    typer.echo(f"runtime image: {manifest.runtimeImage}")
    for name, tool in sorted(manifest.tools.items()):
        typer.echo(f"{name}: {tool.package}@{tool.version}")


def _version_lock_show() -> None:
    lock = load_version_lock()
    typer.echo(f"LCP: {lock.lcpVersion}")
    typer.echo(f"generated: {lock.generatedAt}")
    for dependency in lock.dependencies:
        typer.echo(f"{dependency.name}:")
        typer.echo(f"  policy: {dependency.policy}")
        typer.echo(f"  risk: {dependency.risk}")
        if dependency.package:
            typer.echo(f"  package: {dependency.package}")
        if dependency.version:
            typer.echo(f"  version: {dependency.version}")
        if dependency.controlled:
            typer.echo(f"  repo: {dependency.controlled.repo}")
            typer.echo(f"  tag: {dependency.controlled.tag}")
            typer.echo(f"  commit: {dependency.controlled.commit}")
        if dependency.upstream:
            upstream_ref = dependency.upstream.tag or dependency.upstream.branch or "unknown"
            typer.echo(f"  upstream: {dependency.upstream.repo}@{upstream_ref}")
            typer.echo(f"  upstream commit: {dependency.upstream.commit}")
        typer.echo(f"  patches: {len(dependency.patches)}")


def _version_lock_verify() -> None:
    try:
        lock = load_version_lock()
        failures = verify_version_lock(lock)
    except (OSError, ValueError, ValidationError) as exc:
        _fail("version lock is invalid", str(exc))
    if failures:
        for failure in failures:
            typer.echo(f"failed: {failure}")
        raise typer.Exit(1)
    typer.echo("ok: version_lock")


def _runtime_apply(dry_run: bool, yes: bool) -> None:
    store = LcpStore()
    store.init_dirs()
    manifest = store.load_runtime_manifest()
    profiles = store.list_profiles()
    typer.echo(f"runtime image: {manifest.runtimeImage}")
    typer.echo(f"dockerfile: {store.runtime_dir / 'Dockerfile.runtime'}")
    typer.echo("tools:")
    for name, tool in sorted(manifest.tools.items()):
        typer.echo(f"  {name}: {tool.package}@{tool.version}")
    typer.echo("affected profiles:")
    if profiles:
        for profile_name in profiles:
            typer.echo(f"  {profile_name}: requires explicit `lcp profile rebuild {profile_name} --dry-run` before container changes")
    else:
        typer.echo("  none")
    if dry_run:
        typer.echo("dry-run: would render Dockerfile.runtime and build the runtime image; no containers would be recreated")
        return
    if not yes and not typer.confirm(f"Build runtime image {manifest.runtimeImage}?"):
        raise typer.Exit(1)
    DockerAdapter(store).build_runtime_image()
    typer.echo(f"built: {manifest.runtimeImage}")


def _list_integrations() -> None:
    service = IntegrationService(LcpStore())
    table = Table(show_header=True)
    table.add_column("provider")
    table.add_column("host")
    table.add_column("version")
    table.add_column("description")
    for info in service.list_providers():
        table.add_row(info.name, "ok" if info.host.ok else "missing", info.host.version or "-", info.description)
    console.print(table)


def _doctor_integration(provider: str) -> None:
    try:
        check = IntegrationService(LcpStore()).doctor(provider)
    except ValueError as exc:
        _fail(str(exc), "run `lcp integration list` to see available providers")
    typer.echo(f"provider: {check.provider}")
    typer.echo(f"status: {'ok' if check.ok else 'failed'}")
    if check.version:
        typer.echo(f"version: {check.version}")
    if check.authPath:
        typer.echo(f"auth path: {check.authPath}")
    if check.message:
        typer.echo(check.message)
    if not check.ok:
        raise typer.Exit(1)


def _show_integration_status(name: str) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    if not profile.integrations.providers:
        typer.echo("no integrations configured")
        return
    for provider, state in sorted(profile.integrations.providers.items()):
        typer.echo(f"{provider}: {state.effective.status}")
        typer.echo(f"  enabled: {state.desired.enabled}")
        if state.desired.hostVersion:
            typer.echo(f"  host version: {state.desired.hostVersion}")
        if state.desired.config.get("account"):
            typer.echo(f"  account: {state.desired.config['account']}")
        if state.desired.snapshotId:
            typer.echo(f"  snapshot: {state.desired.snapshotId}")
        if state.effective.reason:
            typer.echo(f"  reason: {state.effective.reason}")
        if state.effective.lastError:
            typer.echo(f"  error: {state.effective.lastError}")


def _parse_integration_config(items: list[str]) -> dict[str, str]:
    config: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            _fail(f"invalid --config value: {item}", "use --config key=value")
        key, value = item.split("=", 1)
        if not key or not value:
            _fail(f"invalid --config value: {item}", "use --config key=value")
        config[key] = value
    return config


def _grant_integration(name: str, provider: str, from_env: bool, config_items: list[str]) -> None:
    store = LcpStore()
    config = _parse_integration_config(config_items)
    if provider == "proxy" and not from_env and not config:
        _fail("proxy grant requires explicit configuration", "use `--from-env` or one or more `--config key=value` options")
    if provider != "proxy" and (from_env or config):
        _fail(f"provider does not accept grant config: {provider}")
    try:
        with store.profile_lock(name):
            profile = _load_profile_or_exit(store, name)
            service = IntegrationService(store)
            if from_env:
                env_check = service.doctor(provider)
                if not env_check.ok:
                    raise RuntimeError(env_check.message or f"{provider} is not ready on host")
                config = {**env_check.details, **config}
            updated = service.grant(profile, provider, config if config else None)
            store.save_profile(updated)
    except RuntimeError as exc:
        _fail(str(exc))
    except ValueError as exc:
        _fail(str(exc), "run `lcp integration list` to see available providers")
    typer.echo(f"granted: {provider}")
    typer.echo(f"run `lcp integration apply {name} --dry-run` to preview container changes")


def _revoke_integration(name: str, provider: str) -> None:
    store = LcpStore()
    try:
        with store.profile_lock(name):
            profile = _load_profile_or_exit(store, name)
            updated = IntegrationService(store).revoke(profile, provider)
            store.save_profile(updated)
    except RuntimeError as exc:
        _fail(str(exc))
    except ValueError as exc:
        _fail(str(exc), "run `lcp integration list` to see available providers")
    typer.echo(f"revoked: {provider}")
    typer.echo(f"run `lcp integration apply {name} --dry-run` to preview container changes")


def _verify_integration(name: str, provider: str | None, external: bool) -> None:
    store = LcpStore()
    profile = _load_profile_or_exit(store, name)
    adapter = DockerAdapter(store)
    _get_container_or_exit(adapter, profile)
    if external and provider != "proxy":
        _fail("external verification is only supported for proxy", "use `lcp integration verify <profile> proxy --external`")
    try:
        results = IntegrationService(store).verify(adapter, profile, provider, external=external)
    except (RuntimeError, ValueError) as exc:
        _fail(str(exc))
    failures = 0
    for result in results:
        mark = "ok" if result.ok else "failed"
        command = f" command={result.command}" if result.command else ""
        typer.echo(f"{mark}: {result.provider}{command}")
        if result.output:
            typer.echo(result.output)
        if not result.ok:
            failures += 1
    if failures:
        raise typer.Exit(1)


def _apply_integration(name: str, dry_run: bool, yes: bool, verbose: bool, reuse_matching: bool) -> None:
    store = LcpStore()
    service = IntegrationService(store)
    try:
        with store.profile_lock(name):
            profile = _load_profile_or_exit(store, name)
            plan = service.plan(profile)
            if dry_run:
                if not plan.steps:
                    typer.echo("no integration changes")
                    return
                for step in plan.steps:
                    typer.echo(f"{step.provider}: {step.action} - {step.reason}")
                return
            if not yes and not typer.confirm(f"Apply integrations for {name}? This may recreate container {profile.container.name}."):
                raise typer.Exit(1)
            adapter = DockerAdapter(store)
            container = _get_container_or_exit(adapter, profile)
            if container.status != "running":
                adapter.start(profile)
                typer.echo(f"started: {profile.container.name}")
            if any(step.action == "recreate" for step in plan.steps):
                stop_bridge(adapter, profile)
                adapter.recreate_container(profile)
                typer.echo(f"recreated: {profile.container.name}")
                for result in install_runtime(adapter, profile):
                    if result.exit_code != 0:
                        raise RuntimeError(result.output.strip() or "runtime install failed after recreate")
            def progress(message: str) -> None:
                if verbose:
                    typer.echo(message)
            updated, results = service.apply(adapter, profile, reuse_matching=reuse_matching, progress=progress)
            store.save_profile(updated)
    except RuntimeError as exc:
        try:
            store.save_profile(profile)
        except Exception:
            pass
        _fail(str(exc))
    except ValueError as exc:
        _fail(str(exc), "run `lcp integration list` to see available providers")
    for result in results:
        mark = "ok" if result.ok else "failed"
        typer.echo(f"{mark}: {result.provider} command={result.command}")
        if result.output:
            typer.echo(result.output)
    if any(not result.ok for result in results):
        raise typer.Exit(1)
    typer.echo("integrations applied")


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


@profile_app.command("rebuild")
def profile_rebuild(
    name: str | None = typer.Argument(None, help="Profile name to rebuild"),
    all_profiles: bool = typer.Option(False, "--all", help="Rebuild all profiles sequentially"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview safe profile rebuild without changing containers"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm real rebuild"),
) -> None:
    _rebuild_profile(name, all_profiles, dry_run, yes)


@profile_app.command("cleanup-rollbacks")
def profile_cleanup_rollbacks(
    name: str | None = typer.Argument(None, help="Profile name whose rollback containers should be removed"),
    all_profiles: bool = typer.Option(False, "--all", help="Remove rollback containers for all profiles"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview rollback cleanup without removing containers"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm rollback cleanup"),
) -> None:
    _cleanup_rollbacks(name, all_profiles, dry_run, yes)


@profile_app.command("snapshot")
def profile_snapshot(name: str, output: str | None = typer.Option(None, help="Output backup directory")) -> None:
    _snapshot_profile(name, output)


@profile_app.command("restore")
def profile_restore(name: str, image_tar: str = typer.Option(..., help="Snapshot tar path")) -> None:
    _restore_profile(name, image_tar)


@profile_app.command("rm")
def profile_rm(name: str, yes: bool = typer.Option(False, "--yes", "-y", help="Confirm removal")) -> None:
    _remove_profile_runtime(name, yes)


@image_app.command("status")
def image_status() -> None:
    _image_status()


@image_app.command("build-base")
def image_build_base(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview base image build without running Docker build"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm real build"),
) -> None:
    _build_base_image(dry_run, yes)


@runtime_app.command("list")
def runtime_list() -> None:
    _runtime_list()


@runtime_app.command("status")
def runtime_status() -> None:
    _runtime_list()


@runtime_app.command("apply")
def runtime_apply(
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview runtime image build without changing containers"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm real build"),
) -> None:
    _runtime_apply(dry_run, yes)


@version_lock_app.command("show")
def version_lock_show() -> None:
    _version_lock_show()


@version_lock_app.command("verify")
def version_lock_verify() -> None:
    _version_lock_verify()


@integration_app.command("list")
def integration_list() -> None:
    _list_integrations()


@integration_app.command("doctor")
def integration_doctor(provider: str) -> None:
    _doctor_integration(provider)


@integration_app.command("status")
def integration_status(name: str) -> None:
    _show_integration_status(name)


@integration_app.command("grant")
def integration_grant(
    name: str,
    provider: str,
    from_env: bool = typer.Option(False, "--from-env", help="Read provider configuration from environment variables"),
    config: list[str] = typer.Option([], "--config", help="Provider config as key=value; may be repeated"),
) -> None:
    _grant_integration(name, provider, from_env, config)


@integration_app.command("revoke")
def integration_revoke(name: str, provider: str) -> None:
    _revoke_integration(name, provider)


@integration_app.command("verify")
def integration_verify(
    name: str,
    provider: str | None = typer.Argument(None, help="Provider name to verify"),
    external: bool = typer.Option(False, "--external", help="Run opt-in external network verification for proxy"),
) -> None:
    _verify_integration(name, provider, external)


@integration_app.command("apply")
def integration_apply(
    name: str,
    dry_run: bool = typer.Option(False, "--dry-run", help="Preview changes without touching the container"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Confirm real apply"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show install/configure commands"),
    reuse_matching: bool = typer.Option(False, "--reuse-matching", help="Reuse matching container CLI versions when supported"),
) -> None:
    _apply_integration(name, dry_run, yes, verbose, reuse_matching)


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
