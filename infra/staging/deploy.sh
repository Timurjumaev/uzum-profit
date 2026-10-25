#!/usr/bin/env bash
# Staging deploy (06 §2, 03 §13): zaxira → migratsiya → yangi konteynerlar → sog'liq tekshiruvi → muvaffaqiyatsiz
# bo'lsa oldingi image'ga qaytish. Migratsiyalar orqaga mos ("kengaytir → ko'chir → toraytir"), shuning uchun eski
# image yangi sxema bilan ishlaydi.
#
# Ishlatish (serverda): infra/staging/deploy.sh <tag>
#   UP_REGISTRY_TOKEN — GHCR'dan tortish uchun (deploy-staging.yml beradi; faqat shu deploy davomida saqlanadi)
#   UP_SKIP_PULL=1    — image'lar lokal (CI)
set -euo pipefail
tag=${1:?tag kerak: deploy.sh <tag>}
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/lib.sh
. "$here/lib.sh"

prev=$(deployed_tag)
log "deploy: $tag (oldingi: ${prev:--})"

if [ -n "${UP_REGISTRY_TOKEN:-}" ]; then
	printf '%s' "$UP_REGISTRY_TOKEN" |
		docker login ghcr.io -u "${UP_REGISTRY_USER:-github}" --password-stdin >/dev/null
	trap 'docker logout ghcr.io >/dev/null 2>&1 || true' EXIT
fi
if [ "${UP_SKIP_PULL:-0}" != 1 ]; then
	UP_TAG=$tag compose pull --quiet api caddy
fi

# Image'lar serverda bo'lishi shart: aks holda compose ularni bu yerda (manba kodsiz) yig'ishga urinadi.
for image in $(UP_TAG=$tag compose config --images api caddy); do
	docker image inspect "$image" >/dev/null 2>&1 || die "image yo'q: $image"
done

UP_TAG=$tag compose up -d --wait postgres
"$here/../backup/backup.sh" "pre-deploy" || die "zaxira olinmadi — deploy to'xtatildi"
UP_TAG=$tag compose run --rm --pull never migrate || die "migratsiya muvaffaqiyatsiz — eski versiya ishlashda davom etadi"

started() {
	UP_TAG=$1 compose up -d --no-build --wait --wait-timeout 180 api worker caddy &&
		health &&
		sleep "${UP_WORKER_SETTLE:-5}" &&
		compose ps --status running --services | grep -qx worker
}

if UP_TAG=$tag started "$tag"; then
	echo "$tag" >"$TAG_FILE"
	# Disk kichik: faqat joriy va oldingi versiya image'lari qoladi (qaytish uchun).
	docker image ls --format '{{.Repository}}:{{.Tag}}' | grep -E -- '-(api|web):' |
		grep -v -e ":$tag\$" ${prev:+-e ":$prev\$"} | xargs -r docker image rm >/dev/null 2>&1 || true
	log "deploy: $tag tayyor"
	exit 0
fi

log "deploy: $tag sog'liq tekshiruvidan o'tmadi"
compose logs --tail 100 api worker caddy >&2 || true
if [ -n "$prev" ] && [ "$prev" != "$tag" ]; then
	log "deploy: $prev ga qaytilmoqda"
	if UP_TAG=$prev started "$prev"; then
		die "$tag ishlamadi; $prev qaytarildi"
	fi
	die "$tag ishlamadi va $prev ham ko'tarilmadi — qo'lda tekshirish kerak"
fi
die "$tag ishlamadi; qaytadigan oldingi versiya yo'q"
