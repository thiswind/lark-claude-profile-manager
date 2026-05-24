# Changelog

## Unreleased

- Mount host GitHub CLI config into profile containers so container `gh` can reuse the WSL host login.
- Install GitHub CLI in profile images.
- Persist profile container hostnames to keep upstream bridge encrypted secrets decryptable after container rebuilds.
