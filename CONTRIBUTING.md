# Contributing

This project is source-available, not permissive open source.

By submitting a contribution to this repository, including code, documentation, configuration, tests, issues, pull requests, or patches, you agree that:

1. You have the right to submit the contribution.
2. Your contribution is provided under the project's current license.
3. You grant the project owner a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, copy, modify, distribute, sublicense, and relicense your contribution as part of this project or related versions of it.
4. The project owner may offer the project, including your contribution, under different license terms, including commercial or enterprise terms.

Do not submit contributions if you cannot grant these rights.

## Development expectations

- Keep runtime profile state, logs, snapshots, caches, credentials, and local machine configuration out of the repository.
- Do not make changes that require disrupting existing production LCP profile containers unless the maintenance task explicitly calls for it.
- Prefer focused tests that do not touch real `~/.lcp` state or running Docker containers.
- Follow `docs/agent-operations-runbook.md` for host-level agent operations.
