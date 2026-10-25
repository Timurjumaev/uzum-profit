# infra

Docker Compose fayllari, Caddy, zaxira va kuzatuv sozlamalari (03-arxitektura.md §1, §13–§15).

- `compose/dev.yml` — lokal muhit (B0.5): postgres, api, worker (B2.6 sinxron navbati), web
- `compose/staging.yml` (B2.10) — staging: postgres, migrate, api, worker, caddy; `compose/postgres-init-staging/`
  — `up_app` roli (parol `.env` dan)
- `caddy/` — web image: React build + Caddy (HTTPS, xavfsizlik sarlavhalari, `/api` → api)
- `staging/` — `bootstrap.sh` (server), `gen-env.sh` (sirlar), `deploy.sh` (zaxira → migratsiya → sog'liq → qaytish)
- `backup/` — `backup.sh` (tungi `pg_dump`), `restore.sh`
- `tests/` — skriptlar testi (soxta docker/curl bilan); to'liq oqim — CI `staging` ishi
- Yo'riqnoma: `docs/staging.md`. Production (`compose/prod.yml`) — B8
