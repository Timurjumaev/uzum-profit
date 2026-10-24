COMPOSE_DEV = docker compose -f infra/compose/dev.yml

.PHONY: dev down logs check

## Lokal muhit: postgres + api (http://localhost:8000/health) + web (http://localhost:5173)
dev:
	$(COMPOSE_DEV) up --build

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f

## CI bilan bir xil tekshiruvlar
check:
	uv run ruff check
	uv run ruff format --check
	uv run mypy
	uv run pytest
	uv run pytest -m benchmark
	python3 -m unittest tests.test_all
	pnpm --filter web lint
	pnpm --filter web typecheck
	pnpm --filter web test
	pnpm --filter web build
