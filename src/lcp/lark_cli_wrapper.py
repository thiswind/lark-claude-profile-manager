LARK_CLI_WRAPPER_MARKER = "LCP managed lark-cli wrapper"

LARK_CLI_WRAPPER_INSTALL = r"""
set -eu
prefix="${NPM_CONFIG_PREFIX:-$HOME/.npm-global}"
bin_dir="$prefix/bin"
cli="$bin_dir/lark-cli"
upstream="$bin_dir/lark-cli.upstream"
mkdir -p "$bin_dir"
if [ -e "$cli" ] && ! grep -q 'LCP managed lark-cli wrapper' "$cli" 2>/dev/null; then
  rm -f "$upstream"
  mv "$cli" "$upstream"
fi
if [ ! -e "$upstream" ]; then
  found="$(command -v lark-cli || true)"
  if [ -z "$found" ] || [ "$found" = "$cli" ]; then
    echo "missing upstream lark-cli binary"
    exit 1
  fi
  ln -s "$found" "$upstream"
fi
cat > "$cli" <<'EOF'
#!/usr/bin/env bash
# LCP managed lark-cli wrapper
set -euo pipefail
if [ -z "${LARK_CHANNEL+x}" ]; then
  export LARK_CHANNEL=1
fi
exec "$(dirname "$0")/lark-cli.upstream" "$@"
EOF
chmod +x "$cli"
""".strip()
