UV ?= uv
PYTHON ?= python3
.DEFAULT_GOAL := test

.PHONY: baseline-test baseline-fixtures baseline-screenshots baseline-preserve migration-visual-check branding-visual-check images-smoke-test tournament-install tournament-backend-dev tournament-frontend-dev tournament-test tournament-build shifts-dev shifts-test shifts-build test

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

tournament-install:
	npm --prefix apps/tournament ci

tournament-backend-dev:
	npm --prefix apps/tournament run dev:server

tournament-frontend-dev:
	npm --prefix apps/tournament run dev:client

tournament-test:
	npm --prefix apps/tournament test
	npm --prefix apps/tournament run typecheck

tournament-build:
	npm --prefix apps/tournament run build

shifts-dev:
	mkdir -p apps/shifts/backend/data
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

shifts-test:
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked pytest

shifts-build:
	docker build -f apps/shifts/Dockerfile -t crr-shifts .

test: tournament-test shifts-test
