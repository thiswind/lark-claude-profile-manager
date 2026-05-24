# Changelog

## Unreleased

- Mount host GitHub CLI config into profile containers so container `gh` can reuse the WSL host login.
- Install GitHub CLI in profile images.
- Persist profile container hostnames to keep upstream bridge encrypted secrets decryptable after container rebuilds.
- Enable passwordless sudo for the profile user inside containers so agents can install missing OS packages non-interactively.
- Move default profile workspaces from `Desktop/Projects/Active/<profile>` to `Desktop/Projects/lcp_profiles/<profile>` to avoid colliding with real projects.
