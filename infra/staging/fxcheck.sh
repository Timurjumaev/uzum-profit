#!/usr/bin/env bash
# CBU kurslari diagnostikasi: ishlab turgan api konteynerida `python -m upapi.fxcheck` (JSON → stdout). Sirlar chiqmaydi.
#
# Mac'dan (bitta buyruq, natija ekranda):
#   ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179 'sudo -u deploy /srv/uzum-profit/infra/staging/fxcheck.sh'
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=SCRIPTDIR/lib.sh
. "$here/lib.sh"

[ -n "$(deployed_tag)" ] || die "staging hali deploy qilinmagan (.deployed-tag yo'q)"
cd "$UP_ROOT"
compose exec -T api python -m upapi.fxcheck "$@"
