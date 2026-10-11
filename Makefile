# FROZEN. Only the owner edits this file.
FROZEN := contracts/data.md contracts/strategy.md swing/config.py swing/env.py \
          docs/PREREGISTRATION.md tests/conftest.py tests/test_frozen.py \
          $(wildcard tests/leakage/*.py) Makefile scripts/start-team.sh scripts/audit.py \
          .claude/settings.json $(wildcard .claude/hooks/*) $(wildcard .claude/agents/*.md) \
          .claude/kickoff-prompt.md

.PHONY: team test test-fast test-leakage audit freeze

team:
	./scripts/start-team.sh

test:
	STRICT_TESTS=1 python3 -m pytest -q

test-fast:
	python3 -m pytest -q -x -m "not slow"

test-leakage:
	STRICT_TESTS=1 python3 -m pytest -q tests/leakage

audit:
	python3 scripts/audit.py

freeze:
	sha256sum $(FROZEN) > FROZEN.sha256
	@echo "Recorded $(words $(FROZEN)) frozen files. Commit, then: git tag -f frozen"
