# Dependency Updates Design

## Scope

Consolidate the six open Dependabot recommendations into one branch:

- `fastmcp` 3.4.3
- `thrift` 0.23.0
- `pytest` 9.1.1
- `ruff` 0.15.20
- `pip-audit` 2.10.1
- `actions/checkout` 7

No application behavior or unrelated dependencies will change.

## Implementation

Update the existing pins in `requirements.txt`, `requirements-dev.txt`, and both
GitHub Actions workflows. Reinstall the development environment from the updated
requirements. If an unignored audit confirms `PYSEC-2025-183` is resolved, remove
the temporary ignore from `Makefile`; otherwise retain it and leave issue #25 open.

## Verification

Run Ruff, Bandit, pip-audit, pytest, and the MCP stdio initialization smoke test.
The branch is complete only when every check passes and the working diff contains
only the dependency, workflow, audit-exception, and design files described here.
