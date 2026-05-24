# LCP Agent Operations Runbook

This document is for a host-level Claude Code agent operating Lark Claude Profile Manager.

Audience:

- You are Claude Code running on the host machine.
- You are not running inside an LCP profile container.
- You are expected to manage LCP profiles, containers, bridge processes, verification, logs, snapshots, documentation, tests, commits, and GitHub synchronization.

Primary rule:

- Use `lcp` as the source of truth for LCP operations.
- Do not bypass LCP by manually editing profile state or Docker containers unless a specific recovery step requires it and the user has approved the risk.

Repository command context:

```bash
cd /mnt/c/Users/Administrator/Desktop/Projects/Active/lark-claude-profile-manager
```

Runtime command context:

- `lcp` is installed as a host command.
- Daily LCP operations can run from any directory.
- Development operations should run from the repository root.

Core model:

```text
one profile = one long-running Docker container = one Feishu/Lark bot = one bridge state = one lark-cli state
```

Profile state lives outside the repository:

```text
~/.lcp/config.json
~/.lcp/profiles/<profile>/profile.json
~/.lcp/profiles/<profile>/lark-channel/
~/.lcp/profiles/<profile>/lark-cli/
~/.lcp/profiles/<profile>/logs/
~/.lcp/cache/
~/.lcp/snapshots/
```

Do not commit runtime state.

## Safety rules

Before destructive operations:

- Ask the user before deleting profiles, removing containers, force-pushing, resetting branches, or discarding local changes.
- Prefer `lcp profile rm <name>` for normal profile deletion because it stops the bridge, removes the container, and removes profile state together.
- Do not use `docker rm`, `docker stop`, or manual `rm -rf ~/.lcp/...` unless LCP cannot perform the operation and the user approves the recovery plan.

Before starting bridge:

- `lcp bridge <name> start` now treats bot configuration and profile-local `lark-cli` binding as preconditions.
- If the bot is not configured or `lark-cli` cannot bind, start must fail. Do not try to hide this failure by starting upstream commands manually.

Before GitHub operations:

- Prefer `gh` for GitHub platform operations.
- Use `git` for local version control and normal commit/push mechanics.
- GitHub authentication is expected to come from `gh auth git-credential`.
- Do not update git config unless the user explicitly asks.

## Host readiness checks

Run these before creating or repairing profiles:

```bash
lcp doctor
```

Expected result:

- Required checks pass.
- If checks fail, read the failing check output before proposing a fix.
- Do not create profiles while required checks fail.

Confirm `lcp` is available:

```bash
command -v lcp
lcp --help
```

Confirm Docker is available if profile/container operations fail:

```bash
docker version
```

Use Docker CLI only for inspection unless explicitly recovering a failure.

## Initialize host LCP configuration

Use this when `~/.lcp/config.json` is missing or the user asks to initialize a host:

```bash
lcp init
```

Then verify:

```bash
lcp doctor
```

Expected state:

- `~/.lcp/config.json` exists.
- Desktop path is detected.
- Host user identity is detected.
- Docker is reachable.

If `lcp init` reports required failures:

1. Stop.
2. Report the exact failed checks.
3. Do not create profiles until the user fixes the host or approves a targeted workaround.

## Create a new profile

Use this for normal profile creation:

```bash
lcp profile create <name>
```

Profile name constraints:

- Use letters, numbers, dot, underscore, or dash.
- Do not use slash or path-like names.

Expected creation result:

- Profile state is written under `~/.lcp/profiles/<name>/`.
- A Docker image is built.
- A long-running container named `lcp-<name>` is created.
- The container has Docker restart policy `always`.
- Runtime tools are installed unless `--no-install` is used.

Use `--no-install` only for development or targeted debugging:

```bash
lcp profile create <name> --no-install
```

After creation, verify the profile exists:

```bash
lcp profile status <name>
lcp profile verify <name> --no-run-claude
```

If creation says profile already exists:

1. Inspect first:

   ```bash
   lcp profile status <name>
   ```

2. If the user wants to recreate it, ask before deletion.
3. Use:

   ```bash
   lcp profile rm <name>
   lcp profile create <name>
   ```

If creation says container already exists:

1. Inspect current profiles:

   ```bash
   lcp profile list
   ```

2. Do not overwrite profile state manually.
3. If it is stale state, ask before using debug removal commands or Docker recovery.

## First-time Feishu/Lark bot configuration

Use foreground bridge mode:

```bash
lcp bridge <name> run
```

Purpose:

- Run upstream `lark-channel-bridge` in the container foreground.
- Let the user complete QR-code or link-based bot setup.
- Produce profile-local bridge config under:

  ```text
  ~/.lcp/profiles/<name>/lark-channel/
  ```

Operational behavior:

- This command is interactive.
- It may display QR codes or login/setup URLs.
- The user may need to act in Feishu/Lark or a browser.
- Watch the foreground output immediately after starting `run`.
- If operating through a chat or remote agent session, promptly forward the QR code and setup URL to the user before they expire.
- Keep it in foreground for initial setup and debugging.
- After setup is confirmed, the user can stop it with `Ctrl+C`.

Do not run this as a background detached process for initial setup unless you have an explicit way to stream or inspect its output and stop it after setup.

After foreground setup, bind `lark-cli` manually or let `start` do it automatically.

Manual bind command:

```bash
lcp bridge <name> bind-lark-cli
```

Expected result:

- Profile-local `lark-cli` config is written under:

  ```text
  ~/.lcp/profiles/<name>/lark-cli/
  ```

- The bound app id matches the bridge app id.
- The default identity is bot.

If manual bind fails with missing config:

```text
missing-config
```

Then run foreground setup first:

```bash
lcp bridge <name> run
```

Then retry:

```bash
lcp bridge <name> bind-lark-cli
```

## Start managed bridge

Use this for daily background operation:

```bash
lcp bridge <name> start
```

What LCP does:

1. Ensures the profile container exists.
2. Starts the container if needed.
3. Runs profile-local `lark-cli` bind:

   ```bash
   lark-cli config bind --source lark-channel --identity bot-only
   ```

4. Fails fast if bridge config is missing or `lark-cli` bind fails.
5. Starts a supervisor loop inside the container.
6. The supervisor loop runs:

   ```bash
   lark-channel-bridge run
   ```

7. Bridge logs go to:

   ```text
   /logs/bridge.log
   ```

Host-side log access:

```bash
lcp bridge <name> logs
```

If start fails:

- Do not manually start `lark-channel-bridge start` inside the container.
- Read the error.
- If config is missing, run:

  ```bash
  lcp bridge <name> run
  ```

- If bind fails, run:

  ```bash
  lcp bridge <name> bind-lark-cli
  lcp profile verify <name> --no-run-claude
  ```

## Stop managed bridge

Stop bridge only:

```bash
lcp bridge <name> stop
```

Behavior:

- Stops the managed bridge process.
- Does not remove the profile.

Legacy top-level stop may stop the container depending on options, but prefer the grouped bridge command for daily operations.

## Restart managed bridge and container

Use when the bridge process or container runtime environment needs a reset:

```bash
lcp bridge <name> restart
```

What restart does:

1. Stops bridge.
2. Stops the container.
3. Starts the container.
4. Rebinds profile-local `lark-cli`.
5. Starts managed bridge again.

Use restart for:

- Runtime process reset.
- Container environment reset.
- Applying changes that are effective when the existing container restarts.

Do not assume restart applies Docker create-time changes such as mounts, hostname, user, labels, or image build changes. Those require container recreation through the appropriate profile workflow.

## Check status

Profile status:

```bash
lcp profile status <name>
```

Bridge status:

```bash
lcp bridge <name> status
```

Profile list:

```bash
lcp profile list
```

Expected bridge status behavior:

- A valid running bridge status must identify the real `lark-channel-bridge run` child process.
- Do not treat the supervisor shell alone as proof that the bridge is healthy.

## Verify a profile

Full verification:

```bash
lcp profile verify <name>
```

Faster verification without Claude non-interactive call:

```bash
lcp profile verify <name> --no-run-claude
```

Important checks:

- Ubuntu version.
- Non-root user identity.
- HOME path.
- Desktop mount.
- Claude config mount.
- Node and npm.
- Claude Code availability.
- `lark-cli` availability.
- `lark_cli_bound`.
- `lark-channel-bridge` availability.

If `lark_cli_bound` fails:

1. Run:

   ```bash
   lcp bridge <name> bind-lark-cli
   ```

2. Run verify again:

   ```bash
   lcp profile verify <name> --no-run-claude
   ```

3. If it still fails, inspect the output. It should indicate missing config, app mismatch, or identity mismatch.

## Logs

Bridge logs:

```bash
lcp bridge <name> logs
```

Container logs through legacy command:

```bash
lcp logs <name> --no-bridge
```

Prefer bridge logs for message-flow issues.

Use container logs for container-level failures only.

## Enter a profile shell

Use only for debugging or direct inspection:

```bash
lcp profile shell <name>
```

Inside the shell:

- You are inside the profile container.
- The user is the profile non-root user.
- HOME points to the profile user home.
- `.lark-channel` and `.lark-cli` are profile-local mounted directories.

Do not make long-term manual changes inside the shell unless the user asked for an emergency repair. Prefer changing LCP code or using LCP commands.

## Proxy upstream bridge commands

LCP intercepts these bridge actions:

```text
start
stop
restart
status
logs
bind-lark-cli
```

Other arguments are proxied into the container as:

```bash
lark-channel-bridge <args...>
```

Examples:

```bash
lcp bridge <name> --help
lcp bridge <name> ps
lcp bridge <name> secrets list
```

Use proxied commands for upstream diagnostics.

Do not use proxied upstream `start` for managed background operation. LCP owns background bridge lifecycle.

## Snapshot and restore

Create a snapshot:

```bash
lcp profile snapshot <name>
```

Create a snapshot in a chosen directory:

```bash
lcp profile snapshot <name> --output /path/to/backup-dir
```

Load a snapshot image tar:

```bash
lcp profile restore <name> --image-tar /path/to/snapshot.tar
```

Current restore limitation:

- Restore loads the Docker image tar.
- Full recreation of profile/container from snapshot is not complete.
- Do not promise full disaster recovery from `restore` alone.

## Remove a profile

Normal removal:

```bash
lcp profile rm <name>
```

Non-interactive removal only when user explicitly approved:

```bash
lcp profile rm <name> --yes
```

Removal behavior:

- Stops bridge.
- Removes container.
- Removes profile state.

Before removal:

1. Confirm the target name.
2. Check status:

   ```bash
   lcp profile status <name>
   ```

3. Ask the user unless they already explicitly requested deletion.

Debug removal commands exist:

```bash
lcp rm container <name>
lcp rm profile <name>
```

Use debug removal only for recovery and only after explaining what will be kept or removed.

## Common failure handling

Failure: profile not found.

Action:

```bash
lcp profile list
```

Then ask whether to create the profile or use a different name.

Failure: container not found for existing profile state.

Action:

1. Report stale profile state.
2. Do not delete immediately.
3. Ask whether to remove stale state or recreate the profile.

Failure: invalid profile name.

Action:

- Rename using letters, numbers, dot, underscore, or dash.
- Do not try to force path-like names.

Failure: `lcp bridge <name> start` says missing config.

Action:

```bash
lcp bridge <name> run
```

Then:

```bash
lcp bridge <name> start
```

Failure: background bridge receives no messages.

Action sequence:

```bash
lcp bridge <name> status
lcp bridge <name> logs
lcp profile verify <name> --no-run-claude
```

Then inspect:

- Is bridge running?
- Does `lark_cli_bound` pass?
- Do logs show event subscription, permission, app credential, or network errors?
- Was the bot added to the correct chat?
- Is this the correct profile for the target bot?

Failure: `lark_cli_bound` app mismatch.

Interpretation:

- The profile-local bridge config and profile-local lark-cli config point to different app ids.

Action:

1. Do not copy config from another profile.
2. Re-run:

   ```bash
   lcp bridge <name> bind-lark-cli
   ```

3. If still mismatched, inspect profile-local state and report before modifying files.

Failure: GitHub push rejected as non-fast-forward.

Action:

1. Check whether local and remote content differ:

   ```bash
   git diff HEAD origin/main
   git log --oneline --decorate -5 --all
   ```

2. If the divergence is only duplicate-content commits with different SHA, rebase the latest valid local work onto `origin/main`.
3. Do not force-push unless the user explicitly requests it and the target is not protected/shared.

## Development workflow for LCP code changes

Before editing code:

```bash
git status --short --branch
```

Read files before editing them.

After code changes, run focused tests first:

```bash
pytest tests/test_cli.py tests/test_bridge.py
```

If model or Docker adapter behavior changed, also run relevant tests:

```bash
pytest tests/test_models.py tests/test_docker_adapter.py
```

Before committing:

```bash
git status --short --branch
git diff
```

Commit only when the user asks or the current task explicitly includes committing and pushing.

Use one-shot identity if git author identity is missing. Do not modify git config automatically.

```bash
GIT_AUTHOR_NAME='thiswind' \
GIT_AUTHOR_EMAIL='thiswind@users.noreply.github.com' \
GIT_COMMITTER_NAME='thiswind' \
GIT_COMMITTER_EMAIL='thiswind@users.noreply.github.com' \
git commit -m "$(cat <<'EOF'
Commit title.

Commit body explaining why.

Co-Authored-By: Claude Opus 4.6 <noreply@anthropic.com>
EOF
)"
```

Push:

```bash
git push origin main
```

If GitHub API is needed, use `gh api`. Prefer normal `git push` when git transport is working.

## Standard new-profile procedure

Use this exact sequence for a normal new profile:

```bash
lcp doctor
lcp profile create <name>
lcp profile status <name>
lcp bridge <name> run
```

Wait for the user to complete QR-code or setup flow.

Then:

```bash
lcp bridge <name> bind-lark-cli
lcp profile verify <name> --no-run-claude
lcp bridge <name> start
lcp bridge <name> status
```

If all checks pass, report:

- Profile name.
- Container name.
- Bridge status.
- Whether `lark_cli_bound` passed.
- How to view logs.

Do not claim the Feishu/Lark client works unless the user confirms a message round trip or logs prove it.

## Standard daily health check

For one profile:

```bash
lcp profile status <name>
lcp bridge <name> status
lcp profile verify <name> --no-run-claude
```

For all profiles:

```bash
lcp profile list
```

Then inspect individual profiles that show missing containers or stopped bridges.

## Standard bridge repair sequence

Use when the bridge is stopped, unhealthy, or not receiving messages:

```bash
lcp bridge <name> logs
lcp profile verify <name> --no-run-claude
lcp bridge <name> restart
lcp bridge <name> status
```

If restart fails on missing config:

```bash
lcp bridge <name> run
```

If restart fails on lark-cli binding:

```bash
lcp bridge <name> bind-lark-cli
lcp profile verify <name> --no-run-claude
```

If logs show upstream bridge configuration or Feishu app permission problems, report exact log lines and ask the user to confirm app setup.

## Agent output expectations

When reporting results to the user:

- Be concise.
- Include commands run only when useful.
- Include exact failing check names and relevant output.
- Include next action, not a vague diagnosis.
- Do not paste long logs unless the user asks.
- Do not claim success beyond what was actually verified.

When blocked:

- State the blocker.
- State what has been verified.
- State the safest next command or decision.
- Ask only the minimum necessary question.
