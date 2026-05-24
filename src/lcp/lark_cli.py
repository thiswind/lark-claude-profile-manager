from .docker_adapter import DockerAdapter, ExecResult
from .models import Profile


LARK_CLI_BOUND_CHECK = r"""
test -s "$HOME/.lark-channel/config.json" && \
test -s "$HOME/.lark-cli/lark-channel/config.json" && \
node -e '
const fs = require("fs");
const home = process.env.HOME;
const bridge = JSON.parse(fs.readFileSync(`${home}/.lark-channel/config.json`, "utf8"));
const cli = JSON.parse(fs.readFileSync(`${home}/.lark-cli/lark-channel/config.json`, "utf8"));
const app = Object.values(cli.apps || {})[0] || {};
if (bridge.accounts?.app?.id !== app.appId) {
  console.error(`app mismatch: bridge=${bridge.accounts?.app?.id || "missing"} lark-cli=${app.appId || "missing"}`);
  process.exit(1);
}
if (app.defaultAs !== "bot") {
  console.error(`identity mismatch: defaultAs=${app.defaultAs || "missing"}`);
  process.exit(1);
}
console.log(`bound: ${app.appId}`);
'
""".strip()


def bind_lark_cli(adapter: DockerAdapter, profile: Profile) -> ExecResult:
    command = f"""
if [ ! -s "$HOME/.lark-channel/config.json" ]; then
  echo "missing-config: run 'lcp bridge {profile.name} run' first to complete the QR-code setup"
  exit 2
fi
lark-cli config bind --source lark-channel --identity bot-only
""".strip()
    return adapter.exec(profile, command)
