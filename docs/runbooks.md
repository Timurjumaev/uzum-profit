# Runbook'lar (B8.5a)

Qisqa, buyruqli yo'riqnomalar — hodisa bo'lganda o'ylab o'tirmaslik uchun. Hamma buyruq serverda, `deploy` foydalanuvchisi,
`/srv/uzum-profit` papkasida (tafsilot — `docs/staging.md`). `C` = `docker compose -f infra/compose/staging.yml --env-file .env`,
`T` = `UP_TAG=$(cat .deployed-tag)`.

## 1. Admin ogohlantirishlari (bot)

`UP_ADMIN_CHAT_ID` (`.env`, adminning shaxsiy Telegram chat id'si) berilsa, bot kuniga bitta jamlanma (Toshkent 09:00 dan
keyin: yiqilgan fon ishlari, qotib qolganlari, disk) va kritik xabar (ishlar 30 daqiqadan beri bajarilmayapti, disk > 80%;
har 6 soatda takrorlanadi) yuboradi. Chat id'ni bilish: botga `/start` yozib, `@userinfobot` dan; botga avval yozgan
bo'lish shart. O'zgartirgach: `infra/staging/deploy.sh $(cat .deployed-tag)`.

## 2. Ishchi ishlamayapti ("qotib qolgan ishlar")

```bash
$C ps                                   # worker holati
T=... ; $T $C logs --tail 100 worker    # sabab (UP_TAG bilan)
$C restart worker                       # odatda yetadi; ishlar navbatda saqlanadi (yo'qolmaydi)
```

Ishlar `procrastinate_jobs` da; ishchi qaytgach o'zi davom etadi. Yiqilgan ishlar: `psql` da
`SELECT task_name, count(*) FROM procrastinate_jobs WHERE status='failed' GROUP BY 1;` — sabab loglarda
(`error_code`); sotuvchi ma'lumoti logga yozilmaydi.

## 3. Deploy buzildi — qaytarish

`deploy.sh` sog'liq tekshiruvi o'tmasa o'zi oldingi image'ga qaytadi (migratsiyalar orqaga mos). Qo'lda: oldingi muvaffaqiyatli
sha'ni `git log` / GitHub Actions'dan topib `infra/staging/deploy.sh <sha>`. Migratsiyani orqaga qaytarish kerak bo'lsa —
avval zaxiradan tiklash (4-band), `alembic downgrade` ni faqat migratsiya muallifi bilan.

## 4. Zaxiradan tiklash

```bash
ls backups/                                   # tungi 03:30 (Toshkent) va deploy oldidan
infra/backup/backup.sh manual                 # avval joriy holatni saqlab qo'ying
infra/backup/restore.sh backups/<fayl>.dump   # tiklash
```

Tiklangach: `$C up -d --wait api worker`, `/health` va ilovada Bosh sahifani tekshiring, `/status` da sinxron holati.
Oylik mashq (06 §3): production nusxasi staging'ga tiklanadi; natija jurnalga (`docs/tasks/`) yoziladi.

## 5. Uzum kaliti sizib chiqdi (yoki sotuvchi so'radi)

1. Sotuvchi Uzum kabinetida kalitni **darhol bekor qiladi** (asosiy chora — bizda kalit shifrlangan, lekin kalit egasi Uzum).
2. Ilovada Sozlamalar → Akkaunt → yangi kalit kiritiladi (eski shifrlangan qiymat almashadi).
3. Bizning tomondan sabab izlanadi: `audit_log` (kim qachon akkauntga tegdi), loglarda kalit yo'qligini tekshirish
   (`grep -r` kalit parchasi bilan — logda bo'lmasligi kerak). `UP_TOKEN_KEYS` ga shubha bo'lsa — kalit versiyasini
   aylantirish (yangi versiya qo'shiladi, eski kalitlar qayta shifrlanadi) — kod egasi bilan.
4. Hodisa 24 soat ichida sotuvchiga yoziladi (nima bo'ldi, nima qilindi) — oferta va 06 §6 bo'yicha.

## 6. Uzum API ishlamayapti yoki 429/401 qaytaryapti

Ilovada "Yangilanmayapti" holati o'zi chiqadi (M3); sotuvchilarga bildirishnoma — faqat kalit yaroqsiz bo'lsa. Tekshirish:
`$T $C logs --tail 200 worker | grep sync` — `http_status` 401 (kalit), 429 (so'rov chegarasi — keyingi aylanishda o'zi),
5xx/timeout (Uzum uzilishi — kuting, ma'lumot yo'qolmaydi, sinxron keyin to'ldiradi). Uzum IP/WAF bloklasa — to'xtating:
`$C stop worker`, Uzum bilan bog'laning (B8.6a yozishmasi), qayta ishga tushirishdan oldin so'rov tezligini kamaytiring
(`UP_UZUM_MIN_INTERVAL_SECONDS`).

## 7. Kirish kodi kelmayapti (Telegram Gateway)

`$C logs api | grep otp_delivery_failed` — `502 otp_delivery_failed` ko'p bo'lsa Gateway balansi tugagan yoki token
yaroqsiz (Telegram Gateway kabinetida balansni tekshiring, to'ldiring). Vaqtincha: mavjud sessiyalar ishlaydi, faqat yangi
kirish to'xtaydi. Admin uchun dev-token (`infra/staging/devtoken.sh`) faqat staging.

## 8. Disk to'ldi

`df -h /`, `docker system df`. Tozalash tartibi: `docker image prune -af` (eski image'lar) → `backups/` dan 14 kundan
eskisini o'chirish (`backup.sh` o'zi qiladi) → `docker builder prune`. Postgres hajmi o'ssa — `SELECT pg_size_pretty(
pg_database_size('uzum'))`; navbat jadvallari (`procrastinate_*`) va `notifications` o'z-o'zidan tozalanadi (90 kun).

## 9. Admin ko'rinishi (tashkilotlar va sinxron holati)

Faqat o'qish; sotuvchi biznes ma'lumoti (sotuv, narx, tannarx) yo'q. Funksiya (`admin_overview()`, egasi `up_admin`) ilova
roliga berilmagan — migratsiya egasi ulanishi bilan chaqiriladi (`migrate` servisida shu URL bor):

```bash
$T $C --profile tools run --rm migrate python -m upapi.admin overview
$T $C --profile tools run --rm migrate python -m upapi.signup list    # ro'yxatdan o'tishga ruxsat berilganlar (B8.11)
```

Aktivatsiya voronkasi (B9.4): har tashkilot bo'yicha bosqichlarning birinchi vaqti va kunlik kirishlar soni:

```bash
$T $C --profile tools run --rm migrate python -m upapi.admin funnel
```
