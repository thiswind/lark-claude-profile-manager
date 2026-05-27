# Changelog

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
