#!/usr/bin/env bash
# Zaxira (06 §3, staging): pg_dump (custom format) → $UP_BACKUP_DIR, `pg_restore --list` bilan tekshiriladi,
# UP_BACKUP_KEEP_DAYS kundan eskilari o'chadi. Tungi — systemd `uzum-backup.timer` (bootstrap.sh), deploy oldidan —
# deploy.sh. Production (B8): pgBackRest + WAL, shifrlangan nusxa boshqa provayderdagi S3 ga.
#
# Ishlatish: infra/backup/backup.sh [belgi]   (masalan: nightly, pre-deploy)
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/../staging/lib.sh
. "$here/../staging/lib.sh"

label=${1:-nightly}
case $label in *[!a-z0-9-]*) die "belgi faqat a-z, 0-9, -" ;; esac
dir=${UP_BACKUP_DIR:-$UP_ROOT/backups}
keep=${UP_BACKUP_KEEP_DAYS:-14}

umask 077
mkdir -p "$dir"
file="$dir/uzum-$(date -u +%Y%m%dT%H%M%SZ)-$label.dump"
trap 'rm -f "$file.part"' EXIT

# shellcheck disable=SC2016 # konteyner ichida ochiladi
compose exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' >"$file.part"
[ -s "$file.part" ] || die "zaxira bo'sh"
compose exec -T postgres pg_restore --list <"$file.part" >/dev/null || die "zaxira o'qilmadi (pg_restore --list)"
mv "$file.part" "$file"

find "$dir" -maxdepth 1 -name 'uzum-*.dump' -mtime +"$keep" -delete
log "zaxira: $file ($(du -h "$file" | cut -f1))"
