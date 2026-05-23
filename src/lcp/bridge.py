from dataclasses import dataclass

from .docker_adapter import DockerAdapter
from .models import Profile

BRIDGE_LOG = "/logs/bridge.log"
BRIDGE_PID = "/logs/bridge.pid"
BRIDGE_SUPERVISOR_PID = "/logs/bridge-supervisor.pid"


@dataclass(frozen=True)
class BridgeStatus:
    running: bool
    pid: str | None
    detail: str


def start_bridge(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    current = bridge_status(adapter, profile)
    if current.running:
        return current
    command = f"""
mkdir -p /logs
if [ ! -s "$HOME/.lark-channel/config.json" ]; then
  echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
  exit 2
fi
if [ -f {BRIDGE_SUPERVISOR_PID} ] && kill -0 $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null; then
  kill $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null || true
fi
pkill -f '^node .*/lark-channel-bridge run($| )' 2>/dev/null || true
rm -f {BRIDGE_SUPERVISOR_PID} {BRIDGE_PID}
: > {BRIDGE_LOG}
nohup bash -lc '
while true; do
  echo "[lcp] bridge run starting at $(date -Is)" >> {BRIDGE_LOG}
  lark-channel-bridge run >> {BRIDGE_LOG} 2>&1
  code=$?
  echo "[lcp] bridge run exited with code $code at $(date -Is); restarting in 5s" >> {BRIDGE_LOG}
  sleep 5
done
' >/logs/bridge-supervisor.out 2>&1 &
echo $! > {BRIDGE_SUPERVISOR_PID}
sleep 2
if ! kill -0 $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null; then
  echo failed
  exit 1
fi
if grep -E -q '未检测到飞书应用配置|进入扫码创建向导' {BRIDGE_LOG} 2>/dev/null; then
  echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
  exit 2
fi
echo started:$(cat {BRIDGE_SUPERVISOR_PID})
""".strip()
    result = adapter.exec(profile, command)
    if result.exit_code != 0:
        return BridgeStatus(False, None, result.output.strip())
    return bridge_status(adapter, profile)


def stop_bridge(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    command = f"""
if [ -f {BRIDGE_SUPERVISOR_PID} ] && kill -0 $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null; then
  kill $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null || true
fi
pkill -f '^node .*/lark-channel-bridge run($| )' 2>/dev/null || true
rm -f {BRIDGE_SUPERVISOR_PID} {BRIDGE_PID}
echo stopped
""".strip()
    adapter.exec(profile, command)
    return bridge_status(adapter, profile)


def bridge_status(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    command = f"""
if [ -f {BRIDGE_SUPERVISOR_PID} ] && kill -0 $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null; then
  supervisor=$(cat {BRIDGE_SUPERVISOR_PID})
  child=$(pgrep -f '^node .*/lark-channel-bridge run($| )' | head -n 1 || true)
  if [ -n "$child" ]; then
    echo running:$supervisor
  else
    echo unhealthy:$supervisor:no bridge run process
  fi
else
  echo stopped
fi
""".strip()
    result = adapter.exec(profile, command)
    output = result.output.strip()
    if result.exit_code == 0 and output.startswith("running:"):
        pid = output.split(":", 1)[1].strip() or None
        return BridgeStatus(True, pid, output)
    return BridgeStatus(False, None, output or "stopped")
