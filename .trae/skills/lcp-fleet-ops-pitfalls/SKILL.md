---
name: "lcp-fleet-ops-pitfalls"
description: "Operational pitfall playbook for the remote LCP container fleet (Windows+WSL host, GLM/Zhipu backend, lark-channel-bridge). Invoke when running lcp/claude/bridge health checks, model-endpoint migrations, fleet audits, or Feishu bridge repairs on that host."
---

# LCP Fleet Ops Pitfalls

Symptom-first playbook for maintaining the LCP fleet on the remote Windows+WSL host
(SSH alias `SOLID-TITAN-SOFIA`, WSL distro `Ubuntu-22.04`, remote docker context).
Each entry: SYMPTOM -> ROOT CAUSE -> FIX -> VERIFY. Check the quick table first,
then jump to the matching section.

## Quick symptom table

| Symptom | Likely pitfall | Section |
|---|---|---|
| All containers 429 on `claude -p` | Zhipu plan quota window, not config | P1 |
| `claude -p` 400 InvalidSubscription from ONE cwd only | Windows-side settings.json leak | P2 |
| Bridge spawns claude, exit code 1, `costUsd:0` | Stale session ID resume | P3 |
| Bridge can't spawn claude at all (PATH falls to Windows shim) | WSL/Windows PATH shadowing | P4 |
| Audit says process "running" but it is dead | pgrep self-match via bash -lc wrapper | P5 |
| Remote file read shows mojibake (`??`) | cmd default codepage vs UTF-8 | P6 |
| `scp` to host fails with "Connection closed" | SFTP subsystem disabled | P7 |
| `docker: command not found` on Mac | PATH loses /usr/local/bin | P8 |
| Zhipu endpoint 404 | Retired `/api/coding/anthropic` path | P9 |

## P1 — Plan quota before config

When every container suddenly returns 429 on `claude -p`, suspect the Coding Plan
5h-window/weekly quota FIRST. Do not re-debug config that worked yesterday.
Confirm by a single direct API call from any machine; if the API itself returns
429, wait for the window. Only if a single container differs from the fleet is it
a config problem.

Two independent subscription keys exist (aliases recorded in the Mac-side `~/.env`
`GLM_CODE_PLAN_*` / `ZHIPU_CODE_PLAN_*` blocks). The fleet uses exactly one of
them. NEVER silently swap keys between purposes; ask the user first.

## P2 — cwd-dependent settings leak (project-level override)

Claude Code merges project-level `.claude/settings.json` based on cwd. On the
Windows+WSL host, cwd `/mnt/c/Users/<win-user>` makes the WINDOWS user-level
`C:\Users\<win-user>\claude\settings.json`... precisely
`C:\Users\<win-user>\.claude\settings.json` act as PROJECT settings, and its
`env` block overrides the WSL user-level GLM config.

- SYMPTOM: `claude -p hi` works from WSL `$HOME` but returns
  `400 InvalidSubscription` (or hits the WRONG provider endpoint) only when cwd
  is the Windows home dir.
- FIX: rename the stale Windows-side file:
  `Move-Item C:\Users\<win-user>\.claude\settings.json C:\Users\<win-user>\.claude\settings.json.<provider>-legacy`
  (keep `settings.local.json` if it only holds permission allowlists).
- VERIFY: re-run `claude -p hi` with `wsl -d <distro> --cd /mnt/c/Users/<win-user>`.
- RULE: after any provider migration, sweep BOTH sides for leftover settings.json
  (WSL `$HOME/.claude/`, Windows `%USERPROFILE%\.claude\`, plus
  `settings.local.json` / `.claude.json` / `.credentials.json`) and confirm which
  one is the single source of truth.

## P3 — Stale bridge session IDs ("no content" from Feishu)

`lark-channel-bridge` resumes chats via `claude -p --resume <sessionId>` using
`~/.lark-channel/sessions.json`. Claude Code prunes session files under
`~/.claude/projects/<encoded-cwd>/` after its retention window (default 30d).
Idle chats therefore accumulate DEAD ids: resume fails, exit code 1, `costUsd:0`,
user sees "no content".

- Signature in structured log: `"phase":"agent","event":"exit","code":1` plus
  `costUsd:0`, while plain `claude -p` in the same cwd works.
- FIX: verify the id has no `<sessionId>.jsonl` on disk, then back up and clear
  `~/.lark-channel/sessions.json` (`echo '{}' >`), restart the systemd user unit.
- MITIGATION: raise `cleanupPeriodDays` in the shared `settings.json` (currently
  180) so retention outlives bridge-side memory.
- This WILL recur for any chat idle longer than retention. Check it before
  blaming model config.

## P4 — WSL/Windows claude PATH shadowing

Windows npm dir sits on the WSL PATH tail. If the Windows-side claude shim is
broken (`Error: claude native binary not installed`), any PATH lookup that
misses earlier entries resolves to it and every spawned claude dies instantly.

- FIX (already applied, re-apply if it regresses):
  1. `sudo ln -sf /home/<wsl-user>/.npm-global/bin/claude /usr/local/bin/claude`
     (WSL-native binary, shadows everything Windows-side)
  2. `npm uninstall -g @anthropic-ai/claude-code` on the WINDOWS side
  3. `systemctl --user restart lark-channel-bridge.bot.service`
- NOTE: the bridge systemd unit PATH contains a literal dead `~/.npm-global/bin`
  entry. Harmless once `/usr/local/bin/claude` exists. Do NOT rewrite the unit
  for cosmetics; if it is ever regenerated, do it from a shell whose rc files
  are already fixed.

## P5 — pgrep self-match false positive in docker exec

`docker exec <c> bash -lc 'pgrep -f <pattern>'` reports the WRAPPER shell as a
match (the pattern string is in the wrapper's own argv). Audits built on this
report dead services as running.

- Use instead:
  `ps -ef | awk '/node/ && /bridge/ && !/awk/'`
- Or count real connections:
  `awk 'NR>1 && $4=="01"' /proc/net/tcp /proc/net/tcp6 | wc -l` (state 01 = ESTABLISHED)
- RULE: any "is it running" verdict needs a ps-based check PLUS an established
  :443 socket count, not pgrep -f.

## P6 — UTF-8 mojibake when reading remote files

`ssh <host> "type file.md"` runs cmd with its legacy codepage and mangles UTF-8
Chinese into `??`. Re-read with PowerShell forcing UTF-8:

```bash
ssh <host> "powershell -NoProfile -Command \"[Console]::OutputEncoding=[Text.Encoding]::UTF8; Get-Content -Encoding UTF8 '<file>'\""
```

Also remember the remote default shell is PowerShell: `if exist ...`
cmd syntax fails; use `Test-Path`.

## P7 — scp disabled; feed scripts via ssh stdin

If `scp` fails with `Connection closed` (SFTP subsystem disabled on the host),
pipe scripts instead of copying them:

```bash
ssh <host> "wsl -d <distro> -- python3 -" < local_script.py
```

Prefer script-piped edits over long inline `ssh ... sed/jq` one-liners: quoting
across ssh -> PowerShell -> wsl -> bash is fragile and silently mangles.

## P8 — Mac docker PATH gotcha

The Mac is a frontend only; the docker engine is remote (context via ssh).
Non-interactive shells may lose `/usr/local/bin` (docker symlink). If
`docker: command not found`, invoke `/usr/local/bin/docker` explicitly.
ControlMaster on the client side is intentionally off; the LaunchAgent owns the
master connection.

## P9 — Zhipu endpoint lifecycle

`https://open.bigmodel.cn/api/coding/anthropic` was RETIRED (404). The working
Anthropic-protocol path is `https://open.bigmodel.cn/api/anthropic`. Model name
accepts uppercase (`GLM-5.3`); the response echoes lowercase. After any provider
change, pre-flight with a direct `POST <base>/v1/messages` (x-api-key +
anthropic-version headers, expect HTTP 200) BEFORE touching fleet config.

## General workflow rules

1. Pre-flight the API directly before changing any shared config.
2. Always timestamped-backup before overwriting (`settings.json.bak.YYYYmmdd_HHMMSS`).
3. Shared WSL `~/.claude/settings.json` is a DIRECTORY bind-mount: edits are
   visible to new claude processes immediately, no container restart, no
   `lcp profile recover`. Single-FILE mounts (`.claude.json`) DO require recover.
4. After edits, smoke-test from BOTH a normal cwd and the trap cwd (P2).
5. The WSL entry path is `ssh <host> "wsl -d <distro> --cd <path> -- <cmd>"`;
   always pin `--cd` so cwd-dependent behavior is deterministic.
