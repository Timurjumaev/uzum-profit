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

## Hozirgi server (2026-10-25, ADR-029)

AWS EC2 eu-north-1, Ubuntu 26.04 LTS, 2 GB RAM; Elastic IP `16.170.178.179` (o'chirib-yoqilganda o'zgarmaydi);
<https://16-170-178-179.sslip.io>. Kirish: `ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179` (AWS'da `root` emas,
`ubuntu`); ilova fayllari — `sudo -u deploy -i`, keyin `cd /srv/uzum-profit`. AWS Security group: kiruvchi 22, 80, 443.

## Bir martalik sozlash (yangi server bo'lsa; Temur, Mac'da, repozitoriy papkasida, `main` branch'da)

`KEY` — provayder bergan kalit (`-i ~/Downloads/awskey.pem`), `USER@IP` — `ubuntu@<ip>` (yoki `root@<ip>`),
`DOMEN` — `<ip, nuqtalar o'rniga chiziqcha>.sslip.io`.

```bash
# 1. GitHub Actions uchun alohida SSH kalit (parolsiz, faqat deploy uchun)
ssh-keygen -t ed25519 -N "" -C uzum-staging-deploy -f ~/.ssh/uzum_staging_deploy

# 2. Serverni tayyorlash (Docker, deploy foydalanuvchisi, firewall, swap, tungi zaxira taymeri)
git checkout main && git pull
ssh KEY USER@IP "sudo bash -s -- '$(cat ~/.ssh/uzum_staging_deploy.pub)'" < infra/staging/bootstrap.sh
#    Oxirida chiqqan `ssh-ed25519 AAAA...` qatorini saqlang — 4-qadamda kerak.

# 3. Sirlar fayli (/srv/uzum-profit/.env). Telegram Gateway tokeni so'raladi, ekranga chiqmaydi.
scp KEY infra/staging/gen-env.sh USER@IP:/tmp/
ssh -t KEY USER@IP 'sudo -u deploy bash /tmp/gen-env.sh DOMEN && rm /tmp/gen-env.sh'
```

4. GitHub → repozitoriy → Settings → Secrets and variables → Actions:
   - **Variables** → `STAGING_HOST` = server IP
   - **Secrets** → `STAGING_SSH_KEY` = `cat ~/.ssh/uzum_staging_deploy` chiqargan matn (to'liq, BEGIN/END qatorlari
     bilan); `STAGING_HOST_KEY` = 2-qadam oxirida chiqqan `ssh-ed25519 AAAA...` qatori.
5. GitHub → Actions → **Deploy staging** → Run workflow. Yashil bo'lsa: `https://DOMEN/health`.

IP o'zgarsa: `.env` dagi domenni almashtirish (`sudo -u deploy sed -i 's/ESKI-IP/YANGI-IP/g' /srv/uzum-profit/.env`)
va GitHub'dagi `STAGING_HOST`.

## Kundalik ishlar (serverda, `deploy` foydalanuvchisi)

```bash
cd /srv/uzum-profit
infra/backup/backup.sh manual                    # qo'lda zaxira → backups/
infra/backup/restore.sh backups/<fayl>.dump      # tiklash (oylik mashq, 06 §3)
UP_TAG=$(cat .deployed-tag) docker compose -f infra/compose/staging.yml --env-file .env logs -f api worker
systemctl list-timers uzum-backup.timer          # keyingi tungi zaxira (03:30 Toshkent)
```

Qo'lda deploy yoki qaytish: `infra/staging/deploy.sh <git sha>` (image'lar GHCR'da yoki serverda bo'lishi kerak).

## Real sinov (B2.11)

Temurning Mac'ida, repozitoriy papkasida (`git checkout main && git pull`):

```bash
# 1. Kirish (kod Telegram'ga keladi) → tashkilot → Uzum kaliti (yashirin so'raladi) → sinxron holati
python3 scripts/staging_connect.py
python3 scripts/staging_connect.py status --watch   # tarix to'liq yuklanguncha (Ctrl+C — to'xtatish)

# 2. Tarix "full" bo'lgach: legacy'ni ham yangilash va serverdan hisobotni olish
python3 -m uzum_profit sync
ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179 \
  'sudo -u deploy /srv/uzum-profit/infra/staging/realcheck.sh' > ~/realcheck.json

# 3. Solishtirish → staging_farqlari.md (✓/✗, chiqish kodi 0 — hammasi mos)
python3 scripts/compare_staging.py --staging ~/realcheck.json --db uzum.db
```

- `staging_connect.py` — faqat stdlib; kalit faqat `getpass` bilan so'raladi, hech qayerga yozilmaydi; sessiya cookie'si
  `~/.uzum-profit/staging-session.json` (600).
- `realcheck.sh` → `python -m upapi.realcheck` (api konteynerida, `up_app` bilan): do'kon × oy × holat yig'indilari,
  sotuv qatorlari, B2.6/B2.8 taxminlari (postavka SKU id, faktura sanasi, `/v1/return`, logistika `externalId`,
  `amount`/`amountReturns`), oxirgi 24 soat sinxron xatolari. Kalit va sirlar o'qilmaydi.
- `compare_staging.py` — legacy `uzum.db` bilan har oy TO_WITHDRAW dona/tushum/komissiya/logistika (1 so'mgacha),
  qator darajasida farqlar, taxminlar hukmi (✓ / ✗ — kodni tuzatish kerak / ≈ — qo'lda ko'rish).

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
