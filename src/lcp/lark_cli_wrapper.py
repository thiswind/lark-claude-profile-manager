import shlex


LARK_CLI_DEFAULT_CHANNEL_SCRIPT = """#!/usr/bin/env bash
# LCP default Lark Channel wrapper
set -euo pipefail
if [ -z "${LARK_CHANNEL:-}" ]; then
  export LARK_CHANNEL=1
fi
exec "${BASH_SOURCE[0]}.bin" "$@"
"""

LARK_CLI_DEFAULT_CHANNEL_WRAPPER = f"""
cli=$(command -v lark-cli)
if ! grep -q 'LCP default Lark Channel wrapper' "$cli" 2>/dev/null; then
  mv "$cli" "$cli.bin"
  printf %s {shlex.quote(LARK_CLI_DEFAULT_CHANNEL_SCRIPT)} > "$cli"
  chmod +x "$cli"
fi
""".strip()
