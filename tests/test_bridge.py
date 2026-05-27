from lcp.bridge import bridge_status, start_bridge, stop_bridge
from lcp.models import default_profile


class FakeAdapter:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.commands = []

    def exec(self, profile, command):
        self.commands.append(command)
        output = self.outputs.pop(0) if self.outputs else "stopped"
        if isinstance(output, tuple):
            return FakeResult(output[0], output[1])
        return FakeResult(0, output)


class FakeResult:
    def __init__(self, exit_code, output):
        self.exit_code = exit_code
        self.output = output


def make_profile(tmp_path):
    return default_profile("project1", tmp_path / "Desktop", [], "amd64", "thiswind", 1000, 1000)


def test_bridge_status_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["running:123"])

    status = bridge_status(adapter, profile)

    assert status.running
    assert status.pid == "123"


def test_bridge_status_unhealthy_supervisor_is_not_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["unhealthy:123:no bridge run process"])

    status = bridge_status(adapter, profile)

    assert not status.running
    assert status.pid is None
    assert "unhealthy" in status.detail


def test_start_bridge_skips_when_already_running(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["running:123"])

    status = start_bridge(adapter, profile)

    assert status.running
    assert status.pid == "123"
    assert len(adapter.commands) == 1


def test_start_bridge_launches_supervisor(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", "started:456", "running:456"])

    status = start_bridge(adapter, profile)

    assert status.running
    assert status.pid == "456"
    assert "if [ ! -s \"$HOME/.lark-channel/config.json\" ]" in adapter.commands[1]
    assert "nohup bash -lc" in adapter.commands[1]
    assert "lark-channel-bridge run" in adapter.commands[1]
    assert "for attempt in $(seq 1 15)" in adapter.commands[1]
    assert "no bridge run process" in adapter.commands[1]
    assert "lark-channel-bridge start" not in adapter.commands[1]


def test_start_bridge_fails_when_config_is_missing(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", (2, "missing-config: run 'lcp bridge project1 run' first")])

    status = start_bridge(adapter, profile)

    assert not status.running
    assert status.pid is None
    assert "missing-config" in status.detail


def test_stop_bridge_kills_supervisor_and_bridge(tmp_path) -> None:
    profile = make_profile(tmp_path)
    adapter = FakeAdapter(["stopped", "stopped"])

    status = stop_bridge(adapter, profile)

    assert not status.running
    assert "pkill -f '^node .*/lark-channel-bridge run($| )'" in adapter.commands[0]
