#!/usr/bin/env bash
# ADR-072 dev-token boshqaruvi (faqat staging, faqat o'qish): ishlab turgan api konteynerida
# `python -m upapi.devtokens create|list|revoke`. Token faqat `create` da, stdout'ga bir marta chiqadi.
#
# Mac'dan (token Mac'dagi faylga tushadi, chatga yozilmaydi):
#   ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179 \
#     'sudo -u deploy /srv/uzum-profit/infra/staging/devtoken.sh create --phone +998XXXXXXXXX --label claude' > ~/devtoken.txt
#   ssh ... 'sudo -u deploy /srv/uzum-profit/infra/staging/devtoken.sh list'
#   ssh ... 'sudo -u deploy /srv/uzum-profit/infra/staging/devtoken.sh revoke --all'
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/lib.sh
. "$here/lib.sh"

[ -n "$(deployed_tag)" ] || die "staging hali deploy qilinmagan (.deployed-tag yo'q)"
cd "$UP_ROOT"
compose exec -T api python -m upapi.devtokens "$@"
