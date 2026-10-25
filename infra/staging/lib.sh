# shellcheck shell=bash
# Staging skriptlari uchun umumiy funksiyalar (deploy.sh, backup.sh, restore.sh `source` qiladi).
# UP_ROOT — serverdagi papka (`infra/` va `.env` shu yerda); CI'da repozitoriy ildizi.
UP_ROOT=${UP_ROOT:-/srv/uzum-profit}
TAG_FILE="$UP_ROOT/.deployed-tag"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >&2; }
die() { log "XATO: $*"; exit 1; }

deployed_tag() { cat "$TAG_FILE" 2>/dev/null || true; }

# `.env` dan bitta qiymat (faylni `source` qilmasdan — sirlar shell muhitiga chiqmaydi).
env_get() { sed -n "s/^$1=//p" "$UP_ROOT/.env" | tail -n 1; }

# Compose `UP_TAG` siz ishlamaydi; berilmagan bo'lsa — hozir ishlab turgan versiya.
compose() {
	local tag=${UP_TAG:-$(deployed_tag)}
	UP_TAG=${tag:-none} docker compose -f "$UP_ROOT/infra/compose/staging.yml" --env-file "$UP_ROOT/.env" "$@"
}

# Caddy orqali haqiqiy HTTPS bilan (sertifikat ham tekshiriladi). CI'da `localhost` — ichki CA, shuning uchun -k.
health() {
	local domain _
	domain=$(env_get UP_DOMAIN)
	for _ in $(seq 1 "${UP_HEALTH_TRIES:-60}"); do
		if curl -fsS --max-time 5 ${UP_HEALTH_INSECURE:+-k} --resolve "$domain:443:127.0.0.1" \
			"https://$domain/health" 2>/dev/null | grep -q '"status":"ok"'; then
			return 0
		fi
		sleep "${UP_HEALTH_SLEEP:-2}"
	done
	return 1
}
