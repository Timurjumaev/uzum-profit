# Staging server (B2.10)

Bitta VPS'da Docker Compose: `postgres`, `api`, `worker`, `caddy` (HTTPS + web). Fayllar: `infra/compose/staging.yml`,
`infra/caddy/`, `infra/staging/` (bootstrap, sirlar, deploy), `infra/backup/` (zaxira, tiklash).
`main`'ga har merge → `deploy-staging.yml`: image'lar GHCR'ga → serverda `deploy.sh` (zaxira → migratsiya → yangi
konteynerlar → sog'liq tekshiruvi → ishlamasa oldingi versiyaga qaytish).

## Server talablari

- **Ubuntu 24.04 yoki 26.04 LTS** (yoki 22.04). 20.04 ning rasmiy qo'llab-quvvatlashi 2025-05 da tugagan, Docker uni endi
  qo'llab-quvvatlamaydi, shuning uchun `bootstrap.sh` 20.04 da ishlamaydi.
- RAM ≥ 2 GB (4 GB tavsiya), disk ≥ 15 GB (tavsiya 30–40 GB). Hamma servislar birga ~250 MB RAM ishlatadi, image'lar
  ~2 GB, zaxiralar 14 kun saqlanadi.
- Provayder panelida (firewall / xavfsizlik guruhi) kiruvchi 22, 80, 443 portlari ochiq.
- Domen: `<ip, nuqtalar o'rniga chiziqcha>.sslip.io`, masalan `89-126-221-34.sslip.io`. Sertifikatni Caddy
  Let's Encrypt'dan o'zi oladi.

## Bir martalik sozlash (Temur, Mac'da, repozitoriy papkasida)

```bash
# 1. GitHub Actions uchun alohida SSH kalit (parolsiz, faqat deploy uchun)
ssh-keygen -t ed25519 -N "" -C uzum-staging-deploy -f ~/.ssh/uzum_staging_deploy

# 2. Serverni tayyorlash (Docker, deploy foydalanuvchisi, firewall, swap, tungi zaxira taymeri)
git pull
ssh root@89.126.221.34 'bash -s' -- "$(cat ~/.ssh/uzum_staging_deploy.pub)" < infra/staging/bootstrap.sh
#    Oxirida "Server SSH kaliti" ostida chiqqan qatorni (ssh-ed25519 AAAA...) saqlab qo'ying — 4-qadamda kerak.

# 3. Sirlar fayli (/srv/uzum-profit/.env). Telegram Gateway tokeni so'raladi, ekranga chiqmaydi.
scp infra/staging/gen-env.sh root@89.126.221.34:/tmp/
ssh -t root@89.126.221.34 'sudo -u deploy bash /tmp/gen-env.sh 89-126-221-34.sslip.io && rm /tmp/gen-env.sh'
```

4. GitHub → repozitoriy → Settings → Secrets and variables → Actions:
   - **Variables** → `STAGING_HOST` = `89.126.221.34`
   - **Secrets** → `STAGING_SSH_KEY` = `cat ~/.ssh/uzum_staging_deploy` chiqargan matn (to'liq, BEGIN/END qatorlari
     bilan); `STAGING_HOST_KEY` = 2-qadam oxirida chiqqan `ssh-ed25519 AAAA...` qatori.
5. GitHub → Actions → **Deploy staging** → Run workflow. Yashil bo'lsa: <https://89-126-221-34.sslip.io/health>.

## Kundalik ishlar (serverda, `deploy` foydalanuvchisi)

```bash
cd /srv/uzum-profit
infra/backup/backup.sh manual                    # qo'lda zaxira → backups/
infra/backup/restore.sh backups/<fayl>.dump      # tiklash (oylik mashq, 06 §3)
UP_TAG=$(cat .deployed-tag) docker compose -f infra/compose/staging.yml --env-file .env logs -f api worker
systemctl list-timers uzum-backup.timer          # keyingi tungi zaxira (03:30 Toshkent)
```

Qo'lda deploy yoki qaytish: `infra/staging/deploy.sh <git sha>` (image'lar GHCR'da yoki serverda bo'lishi kerak).

## Xavfsizlik

- Sirlar faqat serverdagi `.env` da (600, `gen-env.sh` tasodifiy yaratadi); repozitoriyda, CI loglarida va zaxira
  nusxalarida yo'q. Uzum kalitlari bazada AES-GCM bilan shifrlangan, shifrlash kaliti (`UP_TOKEN_KEYS`) `.env` da —
  zaxira nusxadan kalitlarni o'qib bo'lmaydi.
- API va ishchi `UP_ENV=staging` da xavfsizlik shartlarisiz ishga tushmaydi (dev kalitlari, `console` OTP, superuser
  yoki RLS'ni chetlab o'tadigan DB roli — `upapi.startup`).
- Postgres tashqariga ochilmagan; API faqat Caddy orqali. Kirish kodi so'rovi IP bo'yicha soatiga 20 ta
  (`UP_OTP_PER_IP_HOUR`), raqam bo'yicha 5 ta.
- GHCR tokeni deploy vaqtida stdin orqali beriladi va oxirida `docker logout`.

## Keyin (B8, production)

Zaxira: pgBackRest + WAL (7 kun istalgan nuqta), shifrlangan nusxa boshqa provayderdagi S3 ga; ogohlantirishlar admin
Telegram'iga (bot); bir nechta API jarayoni bo'lsa IP cheklovi bazaga yoki Caddy'ga ko'chadi.
