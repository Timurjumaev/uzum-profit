#!/usr/bin/env bash
# Bir marta (serverda): staging sirlari bilan `$UP_ROOT/.env` yaratadi (03 §10). Sirlar tasodifiy, faqat shu faylda
# (600); repozitoriyga, loglarga va chatga chiqmaydi. Mavjud fayl o'zgartirilmaydi.
#
# Ishlatish: infra/staging/gen-env.sh <domen>      (masalan: 89-126-221-34.sslip.io)
#   Telegram Gateway tokeni so'raladi (ekranga chiqmaydi) yoki UP_TELEGRAM_GATEWAY_TOKEN muhitidan olinadi.
set -euo pipefail
domain=${1:?domen kerak: gen-env.sh <domen>}
UP_ROOT=${UP_ROOT:-/srv/uzum-profit}
env_file="$UP_ROOT/.env"
[ -e "$env_file" ] && { echo "$env_file allaqachon bor — o'zgartirilmadi" >&2; exit 1; }

token=${UP_TELEGRAM_GATEWAY_TOKEN:-}
if [ -z "$token" ]; then
	read -rsp "Telegram Gateway API tokeni (gateway.telegram.org → API): " token </dev/tty
	echo >&2
fi
[ -n "$token" ] || { echo "token bo'sh" >&2; exit 1; }

hex() { openssl rand -hex 32; }
pg=$(hex)
app=$(hex)

umask 077
mkdir -p "$UP_ROOT"
cat >"$env_file.part" <<ENV
# Staging sirlari ($(date -u +%Y-%m-%d), gen-env.sh). Hech kimga bermang; zaxira nusxalarga kirmaydi.
UP_ENV=staging
UP_DOMAIN=$domain
POSTGRES_PASSWORD=$pg
UP_APP_DB_PASSWORD=$app
UP_DATABASE_URL=postgresql://up_app:$app@postgres:5432/uzum
UP_OTP_SENDER=telegram_gateway
UP_OTP_SECRET=$(hex)
UP_TELEGRAM_GATEWAY_TOKEN=$token
UP_TOKEN_KEYS={"1":"$(openssl rand -base64 32)"}
UP_TOKEN_KEY_VERSION=1
UP_ALLOWED_ORIGINS=["https://$domain"]
UP_WEB_URL=https://$domain
ENV
mv "$env_file.part" "$env_file"
echo "$env_file yaratildi" >&2
