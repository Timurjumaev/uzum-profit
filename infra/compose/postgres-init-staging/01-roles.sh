#!/bin/sh
# Staging/prod (B2.10): birinchi ishga tushishda (bo'sh volume'da). Ilova roli `up_app` — superuser emas, BYPASSRLS
# yo'q, jadvallar egasi emas (03 §10). Parol `.env` dan (`UP_APP_DB_PASSWORD`), repozitoriyda yo'q. Migratsiya —
# POSTGRES_USER (superuser, jadvallar egasi): `up_auth` (0002) va `up_sync` (0004) funksiyalari egasini o'zgartira oladi.
set -eu
psql -v ON_ERROR_STOP=1 -v pw="$UP_APP_DB_PASSWORD" --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<'SQL'
CREATE ROLE up_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD :'pw';
SQL
