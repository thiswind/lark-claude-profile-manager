from dataclasses import dataclass
import shlex

from .docker_adapter import DockerAdapter
from .models import Profile

BRIDGE_LOG = "/logs/bridge.log"
BRIDGE_PID = "/logs/bridge.pid"
BRIDGE_SUPERVISOR_PID = "/logs/bridge-supervisor.pid"
BRIDGE_SUPERVISOR_BIN = "/usr/local/bin/lcp-bridge-sv"
BRIDGE_SUPERVISOR_PATTERN = r"^(/usr/bin/|/bin/)?bash /usr/local/bin/lcp-bridge-sv($| )"
BRIDGE_CHILD_PATTERN = r"^node .*/lark-channel-bridge run($| )"


@dataclass(frozen=True)
class BridgeStatus:
    running: bool
    pid: str | None
    detail: str
    state: str = "running"


def start_bridge(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    current = bridge_status(adapter, profile)
    if current.running:
        return current
    user = profile.container.user
    supervisor = _supervisor_script(user.name, user.home)
    command = f"""
mkdir -p /logs
if [ ! -s "$HOME/.lark-channel/config.json" ]; then
  echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
  exit 2
fi
if [ -f {BRIDGE_SUPERVISOR_PID} ] && ps -p $(cat {BRIDGE_SUPERVISOR_PID}) >/dev/null 2>&1; then
  sudo kill $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null || true
fi
sudo pkill -f {shlex.quote(BRIDGE_SUPERVISOR_PATTERN)} 2>/dev/null || true
pkill -f {shlex.quote(BRIDGE_CHILD_PATTERN)} 2>/dev/null || true
rm -f {BRIDGE_SUPERVISOR_PID} {BRIDGE_PID}
: > {BRIDGE_LOG}
sudo tee {BRIDGE_SUPERVISOR_BIN} >/dev/null <<'LCP_BRIDGE_SUPERVISOR'
{supervisor}
LCP_BRIDGE_SUPERVISOR
sudo chown root:root {BRIDGE_SUPERVISOR_BIN}
sudo chmod 0755 {BRIDGE_SUPERVISOR_BIN}
sudo bash -c 'nohup {BRIDGE_SUPERVISOR_BIN} >/logs/bridge-supervisor.out 2>&1 & echo $! > {BRIDGE_SUPERVISOR_PID}'
for attempt in $(seq 1 60); do
  if ! ps -p $(cat {BRIDGE_SUPERVISOR_PID}) >/dev/null 2>&1; then
    echo failed
    exit 1
  fi
  if grep -E -q '未检测到飞书应用配置|进入扫码创建向导' {BRIDGE_LOG} 2>/dev/null; then
    echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
    exit 2
  fi
  if pgrep -f {shlex.quote(BRIDGE_CHILD_PATTERN)} >/dev/null; then
    echo started:$(cat {BRIDGE_SUPERVISOR_PID})
    exit 0
  fi
  sleep 1
done
echo degraded:$(cat {BRIDGE_SUPERVISOR_PID}):no bridge run process
exit 1
""".strip()
    result = adapter.exec(profile, command)
    if result.exit_code != 0:
        return BridgeStatus(False, None, result.output.strip(), "stopped")
    return bridge_status(adapter, profile)


def stop_bridge(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    command = f"""
if [ -f {BRIDGE_SUPERVISOR_PID} ] && ps -p $(cat {BRIDGE_SUPERVISOR_PID}) >/dev/null 2>&1; then
  sudo kill $(cat {BRIDGE_SUPERVISOR_PID}) 2>/dev/null || true
fi
sudo pkill -f {shlex.quote(BRIDGE_SUPERVISOR_PATTERN)} 2>/dev/null || true
pkill -f {shlex.quote(BRIDGE_CHILD_PATTERN)} 2>/dev/null || true
rm -f {BRIDGE_SUPERVISOR_PID} {BRIDGE_PID}
echo stopped
""".strip()
    adapter.exec(profile, command)
    return bridge_status(adapter, profile)


def bridge_status(adapter: DockerAdapter, profile: Profile) -> BridgeStatus:
    command = f"""
if [ -f {BRIDGE_SUPERVISOR_PID} ] && ps -p $(cat {BRIDGE_SUPERVISOR_PID}) >/dev/null 2>&1; then
  supervisor=$(cat {BRIDGE_SUPERVISOR_PID})
  child=$(pgrep -f {shlex.quote(BRIDGE_CHILD_PATTERN)} | head -n 1 || true)
  owner=$(ps -o user= -p "$supervisor" 2>/dev/null | tr -d ' ' || true)
  if [ "$owner" != "root" ]; then
    echo degraded:$supervisor:supervisor not root-owned:$owner
  elif [ -n "$child" ]; then
    echo running:$supervisor:$child:$owner
  else
    echo degraded:$supervisor:no bridge run process:$owner
  fi
else
  echo stopped
fi
""".strip()
    result = adapter.exec(profile, command)
    output = result.output.strip()
    if result.exit_code == 0 and output.startswith("running:"):
        parts = output.split(":")
        pid = parts[1].strip() if len(parts) > 1 else None
        return BridgeStatus(True, pid or None, output, "running")
    if result.exit_code == 0 and output.startswith("degraded:"):
        parts = output.split(":")
        pid = parts[1].strip() if len(parts) > 1 else None
        return BridgeStatus(False, pid or None, output, "degraded")
    return BridgeStatus(False, None, output or "stopped", "stopped")


def _supervisor_script(user_name: str, home: str) -> str:
    return f"""#!/bin/bash
set -u
log={shlex.quote(BRIDGE_LOG)}
pidfile={shlex.quote(BRIDGE_PID)}
run_user={shlex.quote(user_name)}
run_home={shlex.quote(home)}
run_path={shlex.quote(f'{home}/.npm-global/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin')}
while true; do
  echo "[lcp] bridge run starting at $(date -Is)" >> "$log"
  sudo -H -u "$run_user" env HOME="$run_home" USER="$run_user" PATH="$run_path" lark-channel-bridge run >> "$log" 2>&1 &
  child=$!
  echo "$child" > "$pidfile"
  wait "$child"
  code=$?
  rm -f "$pidfile"
  echo "[lcp] bridge run exited with code $code at $(date -Is); restarting in 5s" >> "$log"
  sleep 5
done
""".strip()
