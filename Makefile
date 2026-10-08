UV ?= uv
PYTHON ?= python3
.DEFAULT_GOAL := test

.PHONY: images-smoke-test python-common-test tournament-install tournament-backend-dev tournament-frontend-dev tournament-test tournament-build shifts-dev shifts-test shifts-build test

images-smoke-test:
	$(PYTHON) tools/check_images.py

python-common-test:
	$(UV) run --directory packages/crr-python --package crr-python --locked python -m pytest

tournament-install:
	npm --prefix apps/tournament/frontend ci

tournament-backend-dev:
	DATABASE_PATH=$(abspath apps/tournament/tournament.sqlite) $(UV) run --directory apps/tournament/backend --package crr-tournament --locked python -m uvicorn app.main:create_app --factory --reload --host 127.0.0.1 --port 8080 --no-proxy-headers

tournament-frontend-dev:
	npm --prefix apps/tournament/frontend run dev:client

tournament-test:
	$(UV) run --directory apps/tournament/backend --package crr-tournament --locked python -m pytest
	npm --prefix apps/tournament/frontend test
	npm --prefix apps/tournament/frontend run typecheck

tournament-build:
	npm --prefix apps/tournament/frontend run build

shifts-dev:
	mkdir -p apps/shifts/backend/data
	cd apps/shifts/backend && "$(abspath .venv/bin/python)" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

shifts-test:
	$(UV) run --directory apps/shifts/backend --package crr-shifts --locked python -m pytest

shifts-build:
	docker build -f apps/shifts/Dockerfile -t crr-shifts .

test: python-common-test tournament-test shifts-test tooling-test

.PHONY: tooling-test release-plan
tooling-test:
	$(UV) run --no-project --python 3.13 python tools/test_automation.py

release-plan:
	$(UV) run --no-project --python 3.13 python tools/release.py "$(TAG)"
