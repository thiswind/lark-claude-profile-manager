from pathlib import Path

from lcp.config import ClaudeConfig, DesktopConfig, DockerConfig, GpuMachineConfig, HostUserConfig, ImagesConfig, MachineConfig, PlatformConfig
from lcp.selfcheck import InitCheck, InitReport, _desktop_source


def make_config() -> MachineConfig:
    return MachineConfig(
        platform=PlatformConfig(system="linux", environment="wsl", arch="amd64"),
        hostUser=HostUserConfig(name="thiswind", uid=1000, gid=1000, home="/home/thiswind"),
        desktop=DesktopConfig(hostPath="/mnt/c/Users/Administrator/Desktop", containerPath="/home/thiswind/Desktop", source="test"),
        docker=DockerConfig(available=True, serverVersion="29.4.0"),
        gpu=GpuMachineConfig(),
        images=ImagesConfig(),
        claude=ClaudeConfig(configDir="/home/thiswind/.claude", configFile="/home/thiswind/.claude.json"),
    )


def test_machine_config_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    config = make_config()
    config.save(path)
    assert MachineConfig.load(path) == config


def test_init_report_required_failure_detection() -> None:
    config = make_config()
    report = InitReport(config=config, checks=[
        InitCheck("Docker", "fail", "unavailable", required=True),
        InitCheck("GPU", "warn", "not detected", required=False),
    ])
    assert report.has_required_failures


def test_init_report_allows_optional_warnings() -> None:
    config = make_config()
    report = InitReport(config=config, checks=[
        InitCheck("GPU", "warn", "not detected", required=False),
    ])
    assert not report.has_required_failures


def test_desktop_source_names_are_platform_specific() -> None:
    assert _desktop_source("wsl", None) == "wsl-detected"
    assert _desktop_source("windows", None) == "windows-userprofile"
    assert _desktop_source("macos", None) == "macos-default"
    assert _desktop_source("linux", None) == "linux-xdg-or-home"
    assert _desktop_source("windows", "C:/Users/Administrator/Desktop") == "explicit"


def test_machine_config_loads_legacy_host_user_without_optional_fields(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        """
{
  "version": 1,
  "platform": {"system": "linux", "environment": "wsl", "arch": "amd64"},
  "hostUser": {"name": "thiswind", "uid": 1000, "gid": 1000, "home": "/home/thiswind"},
  "desktop": {"hostPath": "/mnt/c/Users/Administrator/Desktop", "containerPath": "/home/thiswind/Desktop", "source": "test"},
  "docker": {"available": true, "serverVersion": "29.4.0"},
  "gpu": {"available": false, "vendor": null, "model": null, "dockerGpuAvailable": false},
  "images": {"ubuntuLts": "ubuntu:24.04", "nodeMajor": 24},
  "claude": {"configDir": "/home/thiswind/.claude", "configFile": "/home/thiswind/.claude.json"}
}
""".strip(),
        encoding="utf-8",
    )

    config = MachineConfig.load(path)

    assert config.hostUser.displayName is None
    assert config.hostUser.source is None
