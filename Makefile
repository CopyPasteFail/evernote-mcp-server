PYTHON ?= python3

.PHONY: lint security test check

lint:
	PYTHONPATH=src $(PYTHON) -m ruff check .

security:
	PYTHONPATH=src $(PYTHON) -m bandit -q -r src
	PYTHONPATH=src $(PYTHON) -m pip_audit -r requirements.txt

test:
	PYTHONPATH=src $(PYTHON) -m pytest -q

check: lint security test
