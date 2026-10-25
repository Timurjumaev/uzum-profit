#!/usr/bin/env bash
# Staging serverni bir marta tayyorlash (B2.10): Ubuntu 22.04/24.04/26.04 LTS, root sifatida. Takror ishga tushirsa bo'ladi.
# Docker (rasmiy repo), `deploy` foydalanuvchisi (GitHub Actions shu bilan kiradi), /srv/uzum-profit, ufw (22, 80,
# 443), fail2ban, avtomatik xavfsizlik yangilanishlari, swap, Toshkent vaqti, tungi zaxira taymeri (03:30).
#
# Ishlatish (Mac'dan, repozitoriy papkasida):
#   ssh root@<ip> 'bash -s' -- "$(cat ~/.ssh/uzum_staging_deploy.pub)" < infra/staging/bootstrap.sh
set -euo pipefail
deploy_key=${1:-}
root=/srv/uzum-profit

[ "$(id -u)" -eq 0 ] || { echo "root sifatida ishga tushiring" >&2; exit 1; }
# shellcheck source=/dev/null
. /etc/os-release
case "${ID}:${VERSION_ID}" in
ubuntu:22.04 | ubuntu:24.04 | ubuntu:26.04) ;;
*) echo "Ubuntu 22.04, 24.04 yoki 26.04 kerak (hozir: $PRETTY_NAME)" >&2; exit 1 ;;
esac

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get upgrade -yq
apt-get install -yq ca-certificates curl ufw fail2ban unattended-upgrades

if ! command -v docker >/dev/null; then
	install -m 0755 -d /etc/apt/keyrings
	curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
	chmod a+r /etc/apt/keyrings/docker.asc
	echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc]" \
		"https://download.docker.com/linux/ubuntu $VERSION_CODENAME stable" >/etc/apt/sources.list.d/docker.list
	apt-get update -q
	apt-get install -yq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker

timedatectl set-timezone Asia/Tashkent
dpkg-reconfigure -f noninteractive unattended-upgrades

# Kichik serverda xotira tugab, Postgres o'chib qolmasligi uchun.
if ! swapon --show | grep -q .; then
	fallocate -l 2G /swapfile
	chmod 600 /swapfile
	mkswap /swapfile
	swapon /swapfile
	echo '/swapfile none swap sw 0 0' >>/etc/fstab
fi

id deploy >/dev/null 2>&1 || useradd --create-home --shell /bin/bash deploy
usermod -aG docker deploy
if [ -n "$deploy_key" ]; then
	install -d -m 700 -o deploy -g deploy /home/deploy/.ssh
	touch /home/deploy/.ssh/authorized_keys
	grep -qxF "$deploy_key" /home/deploy/.ssh/authorized_keys || echo "$deploy_key" >>/home/deploy/.ssh/authorized_keys
	chown deploy:deploy /home/deploy/.ssh/authorized_keys
	chmod 600 /home/deploy/.ssh/authorized_keys
fi
install -d -m 750 -o deploy -g deploy "$root"

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp
ufw --force enable
systemctl enable --now fail2ban

cat >/etc/systemd/system/uzum-backup.service <<UNIT
[Unit]
Description=Uzum Profit: tungi zaxira (pg_dump)
After=docker.service

[Service]
Type=oneshot
User=deploy
ExecStart=$root/infra/backup/backup.sh nightly
UNIT
cat >/etc/systemd/system/uzum-backup.timer <<UNIT
[Unit]
Description=Uzum Profit: tungi zaxira, 03:30 Toshkent

[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Tashkent
Persistent=true

[Install]
WantedBy=timers.target
UNIT
systemctl daemon-reload
systemctl enable --now uzum-backup.timer

echo "tayyor: docker $(docker --version | cut -d' ' -f3 | tr -d ,), deploy foydalanuvchisi, $root, ufw, zaxira taymeri"
echo "Server SSH kaliti (GitHub → Settings → Secrets → STAGING_HOST_KEY):"
cut -d' ' -f1,2 /etc/ssh/ssh_host_ed25519_key.pub
