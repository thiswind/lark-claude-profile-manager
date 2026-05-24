# Changelog

## Unreleased

- Bind profile-local `lark-cli` automatically before managed bridge start/restart, fail fast when the bot is not configured, and add `lcp bridge <profile> bind-lark-cli` for manual retry.
- Mount host GitHub CLI config into profile containers so container `gh` can reuse the WSL host login.
- Install GitHub CLI in profile images.
- Persist profile container hostnames to keep upstream bridge encrypted secrets decryptable after container rebuilds.
- Enable passwordless sudo for the profile user inside containers so agents can install missing OS packages non-interactively.
- Move default profile workspaces from `Desktop/Projects/Active/<profile>` to `Desktop/Projects/lcp_profiles/<profile>` to avoid colliding with real projects.
- Speed up profile creation by skipping base image pulls when `ubuntu:24.04` already exists locally and making npm runtime installs explicitly use the shared `/cache/npm` cache.
- Replace common CLI tracebacks with friendly errors for missing profiles, missing containers, invalid profile names, and missing restore tar files.
- Set profile containers to Docker restart policy `always` by default so they come back after Docker/host restarts.
