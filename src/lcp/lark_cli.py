import shlex

from .docker_adapter import DockerAdapter, ExecResult
from .lark_cli_wrapper import LARK_CLI_WRAPPER_INSTALL
from .models import Profile


LARK_CLI_BOT_IDENTITY_CHECK = r"""
test -s "$HOME/.lark-channel/config.json" && \
test -s "$HOME/.lark-cli/lark-channel/config.json" && \
grep -q 'LCP managed lark-cli wrapper' "$(command -v lark-cli)" && \
(lark-cli auth status --json >/tmp/lcp-lark-cli-auth-status.out 2>/tmp/lcp-lark-cli-auth-status.err || \
 lark-cli auth status >/tmp/lcp-lark-cli-auth-status.out 2>/tmp/lcp-lark-cli-auth-status.err) && \
(lark-cli auth status --verify >/tmp/lcp-lark-cli-auth-verify.out 2>/tmp/lcp-lark-cli-auth-verify.err || \
 { cat /tmp/lcp-lark-cli-auth-verify.out; cat /tmp/lcp-lark-cli-auth-verify.err >&2; exit 1; }) && \
(lark-cli im +chat-list --page-size 1 >/tmp/lcp-lark-cli-api-probe.out 2>/tmp/lcp-lark-cli-api-probe.err || \
 { cat /tmp/lcp-lark-cli-api-probe.out; cat /tmp/lcp-lark-cli-api-probe.err >&2; exit 1; }) && \
(grep -q '"ok"[[:space:]]*:[[:space:]]*true' /tmp/lcp-lark-cli-api-probe.out || \
 { echo "api probe: bot credentials not usable for API calls"; cat /tmp/lcp-lark-cli-api-probe.out; exit 1; }) && \
node -e '
const fs = require("fs");
const home = process.env.HOME;
const bridge = JSON.parse(fs.readFileSync(`${home}/.lark-channel/config.json`, "utf8"));
const cli = JSON.parse(fs.readFileSync(`${home}/.lark-cli/lark-channel/config.json`, "utf8"));
const rawStatus = fs.readFileSync("/tmp/lcp-lark-cli-auth-status.out", "utf8");
let status = {};
try {
  status = JSON.parse(rawStatus);
} catch {
  const defaultAs = rawStatus.match(/defaultAs\s*[:=]\s*([^\s,]+)/i)?.[1];
  const identity = rawStatus.match(/identity\s*[:=]\s*([^\s,]+)/i)?.[1];
  const botStatus = rawStatus.match(/bot[^\n]*(ready|missing|error|expired)/i)?.[1];
  status = { defaultAs, identity, identities: { bot: { status: botStatus } } };
}
const app = Object.values(cli.apps || {})[0] || {};
const activeProfile = bridge.activeProfile;
const bridgeProfile = activeProfile ? bridge.profiles?.[activeProfile] : undefined;
const bridgeAppId = bridge.accounts?.app?.id || bridgeProfile?.accounts?.app?.id;
const cliAppId = app.appId || status.appId || status.app?.appId || status.app?.id;
const defaultAs = app.defaultAs || status.defaultAs;
const identity = status.identity || defaultAs;
const bot = status.identities?.bot || status.bot || {};
if (bridgeAppId !== cliAppId) {
  console.error(`app mismatch: bridge=${bridgeAppId || "missing"} lark-cli=${cliAppId || "missing"}`);
  process.exit(1);
}
if (defaultAs !== "bot") {
  console.error(`identity mismatch: defaultAs=${defaultAs || "missing"}`);
  process.exit(1);
}
if (identity && identity !== "bot" && identity !== "bot-only") {
  console.error(`identity mismatch: identity=${identity}`);
  process.exit(1);
}
if (bot.status && bot.status !== "ready") {
  console.error(`bot identity not ready: ${bot.status}`);
  process.exit(1);
}
console.log(`bot-bound: ${bridgeAppId}`);
'
""".strip()

LARK_CLI_BOUND_CHECK = LARK_CLI_BOT_IDENTITY_CHECK


def bind_lark_cli(adapter: DockerAdapter, profile: Profile) -> ExecResult:
    schema_sync = "node -e " + shlex.quote(r"""
const fs = require("fs");
const path = process.env.HOME + "/.lark-channel/config.json";
const config = JSON.parse(fs.readFileSync(path, "utf8"));
const activeProfile = config.activeProfile;
const app = activeProfile ? config.profiles?.[activeProfile]?.accounts?.app : undefined;
if (!config.accounts?.app && app) {
  config.accounts = Object.assign({}, config.accounts || {}, { app });
  fs.writeFileSync(path, JSON.stringify(config, null, 2) + "\n");
}
""".strip())
    command = f"""
if [ ! -s "$HOME/.lark-channel/config.json" ]; then
  echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
  exit 2
fi
bash -lc {shlex.quote(LARK_CLI_WRAPPER_INSTALL)} &&
{schema_sync} &&
lark-cli config bind --source lark-channel --identity bot-only --force &&
lark-cli config default-as bot &&
lark-cli config strict-mode bot
""".strip()
    return adapter.exec(profile, command)
