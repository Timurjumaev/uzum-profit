#!/usr/bin/env bash
# Zaxiradan tiklash (06 §3; oylik mashq). API va ishchi to'xtaydi, baza nusxadan to'liq almashtiriladi.
# Avval `pg_restore --list` bilan nusxa tekshiriladi — buzuq faylga almashtirib, bazani yo'qotib qo'ymaslik uchun.
#
# Ishlatish: infra/backup/restore.sh <fayl.dump>
set -euo pipefail
dump=${1:?fayl kerak: restore.sh <fayl.dump>}
[ -s "$dump" ] || { echo "fayl topilmadi: $dump" >&2; exit 1; }
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/../staging/lib.sh
. "$here/../staging/lib.sh"

log "tiklash: $dump"
compose exec -T postgres pg_restore --list <"$dump" >/dev/null || die "nusxa o'qilmadi: $dump"
compose stop api worker
# Baza to'liq qayta yaratiladi (`--clean` nusxada yo'q obyektlarni qoldirib ketardi); rollar (up_app va h.k.) umumiy.
# shellcheck disable=SC2016 # konteyner ichida ochiladi
compose exec -T postgres sh -c 'set -e
	psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d postgres \
		-c "DROP DATABASE IF EXISTS \"$POSTGRES_DB\" WITH (FORCE)" -c "CREATE DATABASE \"$POSTGRES_DB\""
	pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --exit-on-error --single-transaction' <"$dump"
compose up -d --wait api worker
log "tiklash: tayyor"
