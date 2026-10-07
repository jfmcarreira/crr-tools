UV ?= uv
PYTHON ?= python3
.DEFAULT_GOAL := test

.PHONY: baseline-test baseline-fixtures baseline-screenshots baseline-preserve migration-visual-check branding-visual-check images-smoke-test python-common-test tournament-install tournament-backend-dev tournament-frontend-dev tournament-test tournament-compat-test tournament-build shifts-dev shifts-test shifts-compat-test shifts-build test

baseline-test:
	$(PYTHON) tools/migration_baseline.py all

baseline-fixtures:
	node --import ./.migration/tournament/node_modules/tsx/dist/loader.mjs migration/capture_tournament.mjs

baseline-screenshots:
	$(UV) pip install --python .migration/shifts/.venv/bin/python playwright
	.migration/shifts/.venv/bin/python -m playwright install chromium
	.migration/shifts/.venv/bin/python migration/capture_screenshots.py

baseline-preserve:
	$(PYTHON) tools/preserve_baseline.py

migration-visual-check:
	.migration/shifts/.venv/bin/python migration/capture_screenshots.py --migrated --reference migration/phase2/screenshots

branding-visual-check:
	.migration/shifts/.venv/bin/python migration/capture_screenshots.py --branding
	.migration/shifts/.venv/bin/python migration/capture_screenshots.py --migrated --branding

images-smoke-test:
	$(PYTHON) tools/check_images.py

python-common-test:
	$(UV) run --directory packages/crr-python --package crr-python --locked pytest

tournament-install:
	npm --prefix apps/tournament ci

tournament-backend-dev:
	DATABASE_PATH=$(abspath apps/tournament/tournament.sqlite) $(UV) run --directory apps/tournament/backend --package crr-tournament --locked uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8080 --no-proxy-headers

tournament-frontend-dev:
	npm --prefix apps/tournament run dev:client

tournament-test:
	$(UV) run --directory apps/tournament/backend --package crr-tournament --locked pytest
	npm --prefix apps/tournament test
	npm --prefix apps/tournament run typecheck
	$(PYTHON) tools/check_tournament_compat.py

tournament-compat-test:
	$(UV) sync --package crr-tournament --locked
	$(PYTHON) tools/check_tournament_compat.py

tournament-build:
	npm --prefix apps/tournament run build

shifts-dev:
	mkdir -p apps/shifts/backend/data
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

shifts-test:
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked pytest
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked python $(abspath migration/check_shifts_structure.py)

shifts-compat-test:
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked python $(abspath migration/check_shifts_structure.py)

shifts-build:
	docker build -f apps/shifts/Dockerfile -t crr-shifts .

test: python-common-test tournament-test shifts-test
