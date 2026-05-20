VENV_PYTHON := .venv/bin/python
SYSTEM_PYTHON := python3
PYTHON ?= $(if $(wildcard $(VENV_PYTHON)),$(VENV_PYTHON),$(SYSTEM_PYTHON))
LOCAL_IMAGE_NAME := evernote-mcp-server:local
TRIVY_SEVERITY_LEVELS := HIGH,CRITICAL

.PHONY: lint security test container-security check

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check .

security:
	PYTHONPATH=src $(PYTHON) -m bandit -q -r src
	# Temporary: pyjwt is transitive via fastmcp -> fastmcp-slim -> mcp.
	# pip-audit reports PYSEC-2025-183 with no fix version available yet.
	# Dependabot is configured for weekly pip updates; remove this after #25 is fixed.
	PYTHONPATH=src $(PYTHON) -m pip_audit -r requirements.txt --ignore-vuln PYSEC-2025-183

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

container-security:
	docker build -t $(LOCAL_IMAGE_NAME) .
	trivy image --severity $(TRIVY_SEVERITY_LEVELS) --exit-code 1 $(LOCAL_IMAGE_NAME)

check: lint security test
