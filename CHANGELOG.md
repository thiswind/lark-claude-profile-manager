# Changelog

## Unreleased

## 0.1.0 - 2026-05-25

- Prepare package metadata and installation docs for pip, uv, and pipx Git-based installs.
- Add `lcp --version` for installed package verification.
- Add PolyForm Noncommercial 1.0.0 licensing, commercial-use guidance, contributor relicensing terms, and explicit README restrictions against unauthorized commercial development or future-commercialization claims.
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
