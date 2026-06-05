# Changelog

## Unreleased

## 0.2.4 - 2026-06-05

- Fix profile bot metadata parsing for real profile-local `lark-cli` configs where `apps` is stored as a list, preventing `lcp profile list/status` crashes after upgrading existing profiles.
- Migrate legacy sample `lark-cli` wrapper layouts safely by routing managed wrappers to the preserved real `lark-cli.bin` target.
- Make `profile verify` use enabled git integration desired identity as the expected git identity and print a targeted reapply hint when container git config drifts.
- Render the runtime Dockerfile `lark-cli` wrapper installer in Docker exec form so multiline shell scripts do not become invalid Dockerfile instructions.
- Parse noisy `npm pack --json` output from controlled dependency builds by extracting the actual JSON array after lifecycle/build logs.

## 0.2.3 - 2026-06-02

- Build controlled runtime npm dependencies by cloning the pinned repo, installing development dependencies, running the package build, packing a local tarball, and installing that tarball into the runtime image.
- Let GitHub integration installs fall back to the repository default `gh` package when the previously recorded exact host version is no longer available from apt.
- Support host-local Vercel token snapshots and verify Vercel auth snapshots with a temporary writable `HOME`.
- Show resolved runtime install specs in `lcp runtime apply --dry-run` and add a remediation hint when `lark_cli_bot_identity` profile verification fails.
- Add the first built-in Python `lcp host-admin` commands for host-level admin agent bootstrap, status/doctor, lark-cli binding, and bridge start.
- Pin `@larksuite/cli` to `1.0.46`, wrap plain `lark-cli` so it defaults to profile-local Lark Channel bot identity, enforce strict bot mode, and mount a profile-local `lark-cli-file-send` skill.
- Add `lcp profile recover` for stale Docker Desktop bind-mount recovery by recreating the container from the existing image without relying on `docker exec`.
- Show bound bot identity in `lcp profile list/status` and add dry-run-first `profile rename` / `sync-name-from-bot` state rename workflows.
- Add an opt-in `ssh` host integration for read-only least-privilege SSH/SOFIA access snapshots.

## 0.2.2 - 2026-05-30

- Add LCP Version Lock file, model, and `lcp version-lock show` / `lcp version-lock verify` commands to record external dependency policy, versions, controlled repo anchors, and release validation state per LCP release.
- Lock the bridge-class dependency to `thiswind/feishu-claude-code-bridge-lcp-0.2@lcp-0.2.2`, anchored at commit `4c9c47c5b32f6353bc9d86fcfc45813cdcdf96cc`.
- Install runtime bridge dependencies from the Version Lock controlled repo/tag instead of resolving `lark-channel-bridge` from a floating npm package source.
- Reject `latest` for critical dependencies and floating tags for controlled fork dependencies during lock verification.

## 0.2.1 - 2026-05-28

- Verify and repair profile-local `lark-cli` as bot-only/default-bot by default, so managed bridge start/restart and attachment sending use the profile's own Feishu/Lark bot without requiring user OAuth.
- Rename the profile verification check from `lark_cli_bound` to `lark_cli_bot_identity` and allow `user: missing` while still rejecting app mismatches, non-bot defaults, and non-ready bot identity.

## 0.2.0 - 2026-05-27

- Add shared base/runtime image management commands and profile rebuild dry-run planning with versioned default shared image tags.
- Implement confirmed `lcp profile rebuild <profile> --yes` and `lcp profile rebuild --all --yes` with rollback container preservation, Claude Code continuity checks, bridge restoration, and active integration reapply.
- Add dry-run-first rollback cleanup commands for single-profile and all-profile rebuild rollback containers.
- Add grantable `proxy` integration for HTTP, HTTPS, and SOCKS proxy configuration using explicit `--from-env` or `--config key=value` endpoints, without hardcoded host proxy addresses.
- Generate a profile-local Claude Code proxy skill and mount it read-only into profile containers during proxy integration apply.
- Redact proxy URL credentials from provider errors and verbose integration apply output.
- Add opt-in `lcp integration verify <profile> proxy --external` network probing while keeping default proxy verification local-only.

## 0.1.2 - 2026-05-25

- Clarify that the default install path is `pip` from the GitHub source/tag, with `uv` and `pipx` as secondary options.
- Add profile-level host integrations for `git`, `github`, and `vercel` with `list`, `doctor`, `grant`, `revoke`, `status`, `apply`, and `verify` commands.
- Store integration auth as profile-local snapshots and mount them read-only into profile containers instead of directly mounting mutable host credentials.
- Add real integration apply orchestration with dry-run previews, confirmation gating, container recreation for mount changes, runtime reinstall after recreate, provider install/configure commands, and container verification.
- Install or upgrade container GitHub CLI to the authorized host `gh` version during GitHub integration apply.
- Preserve legacy GitHub CLI config mounting for profiles that have not moved to the new GitHub integration state.
- Harden runtime installation so read-only credential mounts are not recursively chowned while required profile-local directories remain writable.
- Validate the new integration flow on a real `solid` profile with Git identity, GitHub CLI authentication, Vercel authentication, and bridge recovery.

## 0.1.1 - 2026-05-25

- Publish a corrected package/release version so GitHub, pip, and uv users see the updated package metadata and license posture without relying on a moved `0.1.0` tag.
- Add explicit README restrictions against unauthorized commercial development and reserve future commercialization rights.

## 0.1.0 - 2026-05-24

- Prepare package metadata and installation docs for pip, uv, and pipx Git-based installs.
- Add `lcp --version` for installed package verification.
- Add PolyForm Noncommercial 1.0.0 licensing, commercial-use guidance, and contributor relicensing terms.
- Make the agent operations runbook portable by removing host-specific repository paths, Git identity, and branch/remote assumptions.
- Fix generated profile Dockerfiles so sudoers newline escaping remains valid Dockerfile syntax.
- Add a host-level Claude Code agent operations runbook and link it from README.
- Bind profile-local `lark-cli` automatically before managed bridge start/restart, fail fast when the bot is not configured, and add `lcp bridge <profile> bind-lark-cli` for manual retry.
- Mount host GitHub CLI config into profile containers so container `gh` can reuse the WSL host login.
- Install GitHub CLI in profile images.
- Persist profile container hostnames to keep upstream bridge encrypted secrets decryptable after container rebuilds.
- Enable passwordless sudo for the profile user inside containers so agents can install missing OS packages non-interactively.
- Move default profile workspaces from `Desktop/Projects/Active/<profile>` to `Desktop/Projects/lcp_profiles/<profile>` to avoid colliding with real projects.
- Speed up profile creation by skipping base image pulls when `ubuntu:24.04` already exists locally and making npm runtime installs explicitly use the shared `/cache/npm` cache.
- Replace common CLI tracebacks with friendly errors for missing profiles, missing containers, invalid profile names, and missing restore tar files.
- Set profile containers to Docker restart policy `always` by default so they come back after Docker/host restarts.
