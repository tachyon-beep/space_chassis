# Space Aurora: the commands every stream shares. Each stream's own commands are in its README.

PYTEST ?= python3 -m pytest
WORKERS ?= 8
BASE ?= HEAD
RUFF ?= 0.17.0
# The vehicle stream pins its own (vehicle/requirements-dev.in).
VEHICLE_RUFF ?= 0.16.8

.PHONY: setup test test-aurora test-vehicle lint worktree

setup:
	python3 -m pip install -r requirements-dev.txt

test:
	$(PYTEST) -q -n $(WORKERS)

test-aurora:
	$(PYTEST) -q -n $(WORKERS) aurora/tests aurora/harness/tests aurora/recorder/tests aurora/pump/tests

test-vehicle:
	$(PYTEST) -q -n $(WORKERS) vehicle/tests

lint:
	uvx ruff@$(RUFF) check . --no-cache
	uvx ruff@$(RUFF) format --check . --no-cache
	cd vehicle && uvx ruff@$(VEHICLE_RUFF) check . --no-cache

# make worktree STREAM=vehicle|aurora|governance TOPIC=<short-name> [BASE=<ref>]
worktree:
	@case "$(STREAM)" in vehicle|aurora|governance) ;; *) echo "STREAM must be vehicle, aurora or governance" >&2; exit 2;; esac
	@test -n "$(TOPIC)" || { echo "TOPIC is required" >&2; exit 2; }
	git worktree add .claude/worktrees/$(STREAM)-$(TOPIC) -b $(STREAM)/$(TOPIC) $(BASE)
