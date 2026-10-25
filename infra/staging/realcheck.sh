#!/usr/bin/env bash
# B2.11 real sinov hisoboti: ishlab turgan api konteynerida `python -m upapi.realcheck` (JSON → stdout, xulosa →
# stderr). Kalit va sirlar hisobotga chiqmaydi. Solishtirish — Temurning Mac'ida `scripts/compare_staging.py`.
#
# Mac'dan (bitta buyruq, natija Mac'dagi faylga):
#   ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179 \
#     'sudo -u deploy /srv/uzum-profit/infra/staging/realcheck.sh' > ~/realcheck.json
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/lib.sh
. "$here/lib.sh"

[ -n "$(deployed_tag)" ] || die "staging hali deploy qilinmagan (.deployed-tag yo'q)"
# `sudo -u deploy` chaqiruvchining papkasida (masalan, /home/ubuntu) qoladi — deploy uni o'qiy olmaydi, compose yiqiladi.
cd "$UP_ROOT"
compose exec -T api python -m upapi.realcheck "$@"
