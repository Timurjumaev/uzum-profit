COMPOSE_DEV = docker compose -f infra/compose/dev.yml

.PHONY: dev down logs migrate seed db-check db-reset check

## Lokal muhit: postgres + api (http://localhost:8000/health) + worker (sinxron navbati) + web (http://localhost:5173)
dev:
	$(COMPOSE_DEV) up --build

down:
	$(COMPOSE_DEV) down

logs:
	$(COMPOSE_DEV) logs -f

## Migratsiyalar va sintetik demo ma'lumot (`make dev` ishlab turganda)
migrate:
	$(COMPOSE_DEV) exec -T api alembic -c apps/api/alembic.ini upgrade head

seed: migrate
	$(COMPOSE_DEV) exec -T api python -m upapi.db.seed

## API ulanishi RLS'ga bo'ysunadimi (superuser/ega emas)
db-check:
	$(COMPOSE_DEV) exec -T api python -m upapi.db.guard

## Dev bazani o'chirib qayta yaratish (eski volume'da up_app roli yo'q bo'lsa)
db-reset:
	$(COMPOSE_DEV) down --volumes

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
