# Dependency Updates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply all six open Dependabot recommendations in one verified branch.

**Architecture:** Change only existing dependency pins and the checkout action version. Rebuild the local environment, test the previously ignored advisory without suppression, and retain or remove the exception based on evidence.

**Tech Stack:** Python 3.13, pip, Ruff, Bandit, pip-audit, pytest, GitHub Actions, MCP stdio.

---

### Task 1: Update dependency and workflow pins

**Files:**
- Modify: `requirements.txt`
- Modify: `requirements-dev.txt`
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/release.yml`

- [ ] Replace `fastmcp==3.3.1` with `fastmcp==3.4.3` and `thrift==0.22.0` with `thrift==0.23.0`; adapt byte strings emitted by the legacy generated Evernote client at the shared protocol construction point.
- [ ] Replace `pytest==9.0.3`, `ruff==0.15.12`, and `pip-audit==2.10.0` with `9.1.1`, `0.15.20`, and `2.10.1` respectively.
- [ ] Replace both `actions/checkout@v6` references with `actions/checkout@v7`.
- [ ] Confirm `git diff --check` exits successfully.

### Task 2: Resolve and audit the updated environment

**Files:**
- Modify if justified: `Makefile`

- [ ] Run `.venv\Scripts\python.exe -m pip install -r requirements-dev.txt` and require successful resolution.
- [ ] Run `.venv\Scripts\python.exe -m pip_audit -r requirements.txt` without an ignore.
- [ ] If the audit passes, remove `--ignore-vuln PYSEC-2025-183` and its temporary explanatory comments from `Makefile`; otherwise retain them and record the advisory output.

### Task 3: Verify the consolidated update

**Files:**
- Verify: all changed files

- [ ] Run `.venv\Scripts\python.exe -m ruff check .` and require exit 0.
- [ ] Run `.venv\Scripts\python.exe -m bandit -q -r src` and require exit 0.
- [ ] Run `.venv\Scripts\python.exe -m pip_audit -r requirements.txt` with the resulting policy and require exit 0.
- [ ] Run `.venv\Scripts\python.exe -m pytest -q` and require zero failures.
- [ ] Run `.venv\Scripts\python.exe scripts\smoke_mcp_stdio.py` and require successful initialization.
- [ ] Confirm `git status --short` and `git diff --stat origin/main...HEAD` contain only scoped files.
- [ ] Commit the verified dependency update.
