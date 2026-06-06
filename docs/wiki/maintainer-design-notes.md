# Maintainer Design Notes

This page is a durable design and maintenance brief for future LCP developers and operators. It summarizes the decisions that are easy to miss if someone only reads the source code.

For day-to-day commands, use the README and `docs/agent-operations-runbook.md`. This page explains why the system is shaped the way it is and what must not be accidentally changed.

## 1. Core product model

LCP is not just a Docker wrapper. It is a local profile manager for long-running Claude Code workspaces that are reachable through Feishu/Lark.

The core invariant is:

```text
one task domain = one profile = one long-running Docker container = one Feishu/Lark bot = one bridge state = one lark-cli state
```

A profile owns its own runtime state:

```text
~/.lcp/profiles/<profile>/profile.json
~/.lcp/profiles/<profile>/lark-channel/
~/.lcp/profiles/<profile>/lark-cli/
~/.lcp/profiles/<profile>/logs/
~/.lcp/profiles/<profile>/integrations/<provider>/snapshot/
```

Do not commit runtime state. Do not paste integration snapshots into issues or docs. They may contain credentials or service-specific auth material.

Profile containers should be long-lived, but they must also be rebuildable. Persistent state belongs in host-mounted profile directories, integration snapshots, caches, and the user workspace, not inside throwaway image layers.

## 2. Runtime directory and repository boundary

The source repository is only for source code, tests, documentation, and local uncommitted planning notes.

Runtime state belongs under `~/.lcp`:

```text
~/.lcp/config.json
~/.lcp/profiles/<profile>/...
~/.lcp/cache/...
~/.lcp/snapshots/...
```

A developer should be able to run `lcp` from any directory once installed. Development work should happen from the repository root, but daily LCP operations must not depend on activating a repository-local virtual environment.

The repository may contain `.local-plan/` design notes, but those are local planning artifacts. Only durable user-facing or maintainer-facing conclusions should be promoted to README, runbook, changelog, release notes, or this wiki.

## 3. Bridge-first recovery is the current stable model

The 0.2.6 release changed the bridge runtime model. The goal is not to make the current Claude Agent turn impossible to kill. That is unrealistic in an interactive container where the Agent can run broad process-management commands.

The product goal is narrower and more useful:

```text
The Feishu/Lark entry point should recover so the next user message can start a new Agent turn.
```

The expected failure model is:

1. The user sends a task through Feishu/Lark.
2. The bridge receives the message and starts Claude Code Agent work.
3. The Agent runs a broad process kill command such as `pkill -f` or a node-child kill.
4. The current Agent turn may die.
5. The managed bridge supervisor survives or recovers the bridge child.
6. The user sends a follow-up such as `继续`.
7. A new Agent turn can proceed.

The managed bridge supervisor is now root-owned:

```text
/bin/bash /usr/local/bin/lcp-bridge-sv
```

The bridge child still runs as the profile user through `sudo -u`:

```text
sudo -H -u <profile-user> env ... lark-channel-bridge run
node /usr/bin/lark-channel-bridge run
```

This separation matters:

- The supervisor command line does not contain `lark-channel-bridge`.
- The bridge child stays in the normal profile user environment.
- Killing the node child should trigger supervisor restart.
- `profile verify` includes `bridge_runtime` so stopped or degraded bridge runtime is part of profile health.

Known non-goals:

- Do not promise that the current Agent turn survives a broad kill.
- Do not promise protection from a user with root/sudo who intentionally kills all relevant processes.
- Do not treat project service processes as protected by the bridge supervisor.

Maintenance rule:

If future changes touch `src/lcp/bridge.py`, preserve the distinction between control plane and child process. Status must prove the real bridge child exists; supervisor-only liveness is not enough.

## 4. Bridge state semantics

Bridge status is intentionally more precise than a boolean.

Use these meanings:

- `running`: the supervisor and the real `lark-channel-bridge run` child are both alive.
- `degraded`: the supervisor exists, but the bridge child is not healthy or the supervisor model is old/wrong.
- `stopped`: the managed supervisor is not alive.

Do not hide a degraded bridge by reporting it as running. A degraded bridge can make the profile look alive while the Feishu/Lark entry point is unavailable.

Standard repair path:

```bash
lcp bridge <profile> logs
lcp profile verify <profile> --no-run-claude
lcp bridge <profile> restart
lcp bridge <profile> status
```

If config is missing, run the foreground setup flow:

```bash
lcp bridge <profile> run
```

## 5. lark-cli must default to the profile bot

Each profile has two related but separate pieces of state:

- `lark-channel-bridge` config, used for chat message ingress/egress.
- `lark-cli` config, used by the Agent for CLI actions such as sending files.

A working bridge does not automatically mean `lark-cli` is ready.

The intended default is bot-only:

```text
identity: bot-only
defaultAs: bot
bot: ready
user: missing is acceptable
```

The profile should not require user OAuth for ordinary bridge messaging or bot attachment sending. User OAuth is only for operations that truly need access to user resources.

Managed bridge start/restart should bind or verify profile-local `lark-cli` before starting the background bridge. If `lark_cli_bot_identity` fails during verification, repair with:

```bash
lcp bridge <profile> bind-lark-cli
lcp profile verify <profile> --no-run-claude
```

Do not switch profiles to `user-default` as a general fix for attachment sending. That reintroduces user OAuth dependency and breaks the profile-bot isolation model.

## 6. Version Lock and controlled dependencies

LCP depends on external moving parts: bridge runtime, `lark-cli`, Claude Code, Docker, Node.js, Feishu/Lark platform behavior, GitHub CLI, Vercel CLI, and more.

For release stability, LCP uses Version Lock. The release chain should be reproducible:

```text
LCP release -> controlled dependency repo/tag -> exact commit SHA -> upstream source reference
```

Rules for maintainers:

1. Critical dependencies must not resolve from `latest` in a stable release.
2. Controlled fork dependencies need a controlled repo, tag, and exact commit SHA.
3. Version Lock must match the package version for the release.
4. Runtime installation should use the locked dependency spec, not a floating upstream source.
5. Release validation commands belong in Version Lock when they are part of the release evidence.

For the bridge-class dependency, the controlled repository pattern is:

```text
repo: <project>-lcp-<major.minor>
tag:  lcp-<full-lcp-version or compatibility line>
```

The controlled repo is a compatibility anchor, not a license to fork permanently without reason. Upstream remains important for attribution, license review, and future sync.

## 7. Image layering and rebuild model

LCP uses a layered runtime model:

```text
ubuntu:24.04
  -> lcp/base:<version>-ubuntu24.04
  -> lcp/runtime:<version>-ubuntu24.04
  -> lcp/<profile>:base
  -> container lcp-<profile>
```

Design rules:

1. Shared OS packages belong in `lcp/base`.
2. Shared LCP runtime tools belong in `lcp/runtime`.
3. Profile-specific state belongs in profile mounts, not image layers.
4. Credentials and host-specific endpoints must never be baked into image layers.
5. Building a new base/runtime image must not automatically recreate existing containers.
6. Real container rebuilds must be explicit and dry-run-first.

Dry-run output should show:

- images that would be built or used;
- containers that would be stopped or recreated;
- whether bridge is currently running;
- whether Claude Code continuity is safe;
- preserved mounts;
- integration apply steps;
- rollback container/image behavior;
- verification steps.

Real rebuild should require explicit confirmation:

```bash
lcp profile rebuild <profile> --dry-run
lcp profile rebuild <profile> --yes
```

For all profiles:

```bash
lcp profile rebuild --all --dry-run
lcp profile rebuild --all --yes
```

Rollback containers should be preserved during validation. Cleanup should be a separate explicit operation after the maintainer confirms the new containers are healthy.

## 8. Host integrations are grants, not image features

Host integrations follow this principle:

```text
Image layers provide generic tools.
Integrations grant profile-specific access.
```

The integration framework exists because tools such as GitHub CLI, Vercel CLI, SSH, Git identity, and proxy settings combine host readiness, credential capture, profile-local state, container configuration, and verification.

Provider behavior should be explicit:

- check host readiness;
- capture or clear profile-local snapshot;
- define read-only mounts when needed;
- install or reuse container tools;
- configure the profile container;
- verify container state.

Credentials should be copied into profile-local snapshots and mounted read-only where possible. Do not directly mount mutable host auth directories unless maintaining legacy compatibility.

Provider apply flows should be dry-run capable and auditable. They should not automatically log into third-party services, print tokens, or silently rebuild production containers without confirmation.

## 9. Proxy and credential hygiene

Proxy endpoints and credentials are runtime configuration, not defaults.

Do not hardcode local proxy endpoints in code, tests, docs, image layers, or committed config. A proxy endpoint may be known to a specific host, but it should enter LCP only through explicit profile integration grant/apply.

Never bake these into images:

- GitHub auth;
- Vercel auth;
- SSH private keys;
- Feishu/Lark secrets;
- Claude user config;
- proxy endpoints or proxy credentials.

When errors or verbose logs mention proxy URLs, redact credentials.

## 10. Platform compatibility notes

Supported target platforms are:

1. WSL Ubuntu + Docker Desktop.
2. Windows + Docker Desktop.
3. macOS + Docker Desktop.
4. Native Linux + Docker.

Windows has one important difference: Docker Desktop bind mounts do not preserve POSIX uid/gid semantics. Therefore Windows does not try to map host uid/gid into the container. The Windows container user name is normalized from the Windows home directory name, and uid/gid use conventional `1000:1000`.

Do not run profile containers as root for normal use. Root-owned user files break future migration and create cache/permission problems. The profile user may have passwordless sudo for controlled repair/install operations, but daily Agent work should run as the profile user.

Windows console output should be UTF-8 safe. Do not regress GBK/PowerShell support when changing CLI output.

## 11. Safety and operations rules

Destructive operations should be explicit.

Ask before:

- deleting profiles;
- removing containers;
- cleaning rollback containers;
- force-pushing;
- resetting branches;
- discarding local changes;
- removing runtime state manually.

Prefer LCP commands over raw Docker commands for normal operations:

```bash
lcp profile rm <profile>
lcp profile recover <profile> --dry-run
lcp profile recover <profile> --yes
lcp profile cleanup-rollbacks <profile> --dry-run
lcp profile cleanup-rollbacks <profile> --yes
```

Use raw Docker CLI mainly for inspection or when LCP cannot execute because the container is in a stale bind-mount or non-execable state.

If Docker Desktop/WSL bind mounts become stale and `docker exec` cannot run, use host-side recovery:

```bash
lcp profile recover <profile> --dry-run
lcp profile recover <profile> --yes
lcp profile verify <profile> --no-run-claude
```

## 12. Release checklist

Before publishing a stable release:

1. Confirm the issue/test feedback that justifies the release.
2. Update package version and `src/lcp/__init__.py`.
3. Update `src/lcp/version_lock.json` so it matches the package version.
4. Update tests that assert version output or Version Lock version.
5. Update `CHANGELOG.md`.
6. Update README install examples and runtime image tag examples.
7. Update `docs/agent-operations-runbook.md` when operational behavior changes.
8. Run full tests:

```bash
PYTHONPATH=src pytest -q
```

9. Verify Version Lock:

```bash
PYTHONPATH=src python -m lcp.cli version-lock verify
```

10. Verify CLI version:

```bash
PYTHONPATH=src python -m lcp.cli --version
```

11. Run at least one real profile verification when the change affects runtime behavior:

```bash
PYTHONPATH=src python -m lcp.cli profile verify <profile> --no-run-claude
```

12. Build and check package artifacts:

```bash
python -m build --outdir /tmp/lcp-build-<version>
python -m twine check /tmp/lcp-build-<version>/*
```

13. Commit without AI co-author trailers unless the maintainer explicitly asks otherwise.
14. Tag the release.
15. Push branch and tag.
16. Create a GitHub release with validation and upgrade notes.
17. Reply to the relevant issue with release details.
18. Close the issue only after maintainer or tester acceptance.

## 13. What to document where

Use README for user-facing install, quick start, and common commands.

Use `docs/agent-operations-runbook.md` for step-by-step operational procedures that host-side Claude Code agents should follow.

Use CHANGELOG for release-scoped behavior changes.

Use GitHub issues for bug reports, validation evidence, and acceptance records.

Use this wiki page for durable design decisions that help future maintainers avoid repeating old debates.

Use `.local-plan/` for temporary design work and implementation notes. Promote only stable conclusions from `.local-plan/` into public docs or wiki.
