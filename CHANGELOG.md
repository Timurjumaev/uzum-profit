# O'zgarishlar jurnali

Format: [Keep a Changelog](https://keepachangelog.com/), versiyalar: [SemVer](https://semver.org/).
Yangi tizim (`packages/`, `apps/`) uchun; legacy ilova o'zgarishlari git tarixida.

## [Chiqarilmagan]

### Qo'shildi

- B0.1 Production rejasi (`docs/plan`), `CLAUDE.md`.
- B0.2 Monorepo skeleti: `packages/core` (upcore), `apps/api` (upapi, `/health`), `apps/bot` (upbot),
  `apps/web` (Vite + React + TS), `infra/`; uv va pnpm workspace'lari.
- B0.3 CI: ruff, mypy, pytest (core, api, bot), legacy testlari (Python 3.8 va 3.13), web
  lint/typecheck/test/build.
- B0.4 Kod tartibi: pre-commit (ruff, taqiqlangan fayllar, Conventional Commits), PR shabloni, Dependabot,
  `CONTRIBUTING.md`, `.python-version`, `.nvmrc`.
- B0.5 Dev muhit: `infra/compose/dev.yml` (PostgreSQL 18, api, web), `make dev`, API Dockerfile; CI'da
  compose smoke testi.
- B0.6 Legacy siyosati README'da.
- B1.1 `upcore.money` (Decimal, valyutalar, ROUND_HALF_UP, aniq taqsimot — qoldiq eng katta qatorga) va
  `upcore.fx` (CBU qatorini o'qish, dam olish kunida oxirgi ish kuni kursi, so'mga o'tkazish, qo'lda va
  kartadan yechilgan summadan effektiv kurs); hypothesis testlari, CI'da core qamrovi ≥ 95%.
- B1.2 `upcore.metrics`: F1 (Toshkent sanasi, davr), F2 (holat guruhlari), F3–F8, F6 `sellerProfit` tekshiruvi,
  F9 yig'indi, F10 amortizatsiya (ketma-ket davrlar yig'indisi aniq), F12 sof foyda va F15 tannarx qamrovi
  ("tannarxsiz qism" alohida), F13 marja — maxraj tannarxi ma'lum tushum, yonida tannarxsiz qism ulushi
  (ADR-024), F14, F16 realizatsiya va kutilayotgan foyda, F17–F18, F19 DRR va SKU ACOS
  (bog'lanmagan reklama tushum ulushi bo'yicha), F35–F36; `tzdata` bog'liqligi.
- B1.3 `upcore.expenses`: xarajat kodini normallashtirish (kirill → lotin, U/У/Y → Y), toifalar va P&L'ga
  kirishi, lug'at `CodeBook` (bazadan; `SEED_CODEBOOK` — boshlang'ich yozuvlar), CANCELED/REFUNDED va
  `BALANCE_CORRECTION` chiqarib tashlanadi (sababi bilan), dublikatlar, reklama matnidan aniq summa, buyurtma va
  tovar bog'lanishi, F9 yig'indisi.
- B1.4 `upcore.purchasing` (F20, F22): xarid qatorlari va komponentlar (tovar, kargo, bojxona, qadoq ...),
  5 taqsimot usuli (dona, vazn, hajm, qiymat, qo'lda; ma'lumot yo'q bo'lsa dona + belgi), 3 kurs rejimi
  (`upcore.fx` orqali), aniq taqsimot (qoldiq eng katta qatorga), qabul qilinmagan / kargo yo'q / CBU kursi
  belgilari, lot tayyor sanasi; legacy partiya tannarxi bilan solishtirish testi.
- B1.5 `upcore.costing` (F21–F22): lot dvigateli — FIFO (standart, Temur tashkiloti uchun ham: ADR-025) va
  harakatlanuvchi o'rtacha; tayyor lot yetmasa erta sotuv / yo'ldagi lot, hamma lot tugasa oxirgi narx +
  "lot yetmadi", lot yo'q bo'lsa tannarx yo'q; sotuvga yaroqli qaytish asl lotga o'sha narxda; brak/yo'qotish;
  lot belgilari sotuvga o'tadi; deterministik qayta hisob; 10 000 sotuv < 1 s benchmark testi.
- B1.6 `upcore.pnl` (F12–F16, M5): hisob (kun × do'kon × SKU) kataklarida, har kesim — kataklar yig'indisi
  (ADR-026): davr, oy, kun, do'kon, SKU; F9 turlari va F10 toifalari alohida, F11 (a) aylanmadan foiz,
  F15 qamrovi va "tannarxsiz qism", hisob varag'i qatorlari, oldingi davr bilan solishtirish, F16 bloki.
  `Money` va `to_decimal` tez yo'li; tezlik testlari `-m benchmark` (CI'da coverage'siz).
- ADR-026 to'ldirildi: P&L'da taqsimlangan va to'g'ridan-to'g'ri xarajatlar alohida (`Statement.uzum_allocated`,
  `own_allocated`, `allocated_total`, `direct_total`); 02 (M5) va B4.2, B4.3 vazifalariga yozildi.
- B1.7 `upcore.inventory` (F23–F34): sof sotuv tezligi (vazn, stockout kunlarisiz, yangi tovar, qaytish,
  trend), zaxira kunlari, to'liq muddat (oxirgi 5 xarid medianasi), holat (mahsulot darajasi bilan),
  tavsiya miqdor va byudjet, ABC/XYZ, muzlagan pul, o'rtacha sotilish muddati, nelikvid/sekin, yo'qolgan tovar,
  kompensatsiya taxmini, qabul kamomadi, tugab qolishdan yo'qotilgan foyda; parametrlar `InventorySettings` da.
- B1.8 `upcore.tariffs` (F37 logistika tarifi sana bo'yicha, F40 standart tarif bo'yicha foyda va bepul kunlarni
  aniqlash), `upcore.tax` (F11 profillari sana bo'yicha: aylanmadan foiz P&L kataklarida, agent, QQS + foyda
  solig'i oylik taxmini; stavkalar ma'lumotnomasi), `upcore.cash` (F38 to'lov jadvallari va prognozi, ish
  kunlari va bayramlar, kechikish chegarasi; F39 90 kunlik kassa prognozi va uzilish kuni). Hamma tarif va
  stavkalar ma'lumot (ADR-015), seed qiymatlari 02/08 dan.
- B1.9 vositasi: `scripts/compare_legacy.py` (faqat stdlib, Python 3.12+; 3.15 da tekshirilgan) — legacy va
  yangi yadro natijalarini Temurning `uzum.db` / `uzum_history.json` da solishtiradi: partiyalar tannarxi, oylar
  bo'yicha tushum/komissiya/logistika/dona (majburiy), xarajat toifalari, tannarx (legacy / o'rtacha / FIFO) va
  foyda farqlari sababi bilan. `docs/legacy-farqlari.md` — farqlar ro'yxati. CI: legacy 3.15 da, yangi
  "Core (Python 3.15)" job. QQS 12% (2026) manba bilan tasdiqlandi.
- B1.9 skripti: `--history` fayli topilmasa yiqilmaydi — ogohlantirish beradi va `uzum.db` bilan davom etadi.
- B1.9 skripti: xarajatlar qatorlar bo'yicha legacy ↔ yangi toifalash farqi jadvali (sabab, kod, tur, status).
  Real natija `docs/legacy-farqlari.md` ga yozildi: majburiy tekshiruvlar ✓.
- B1.9 skripti: "Xarajat manbalari" jadvali — `uzum.db` va `uzum_history.json` dagi xarajat qatorlari farqi
  (faqat bazada, faqat JSON'da, summasi boshqa) legacy toifalari bo'yicha.
- B1.9 yakunlandi: Temurning real ma'lumotida majburiy tekshiruvlar ✓, reklama farqi manba farqi ekani
  tasdiqlandi (`uzum.db` JSON'dan keyin sinxronlangan). **B1 bosqichi tugadi.**
- ADR-027: kirish kodi Telegram orqali (Q3), SMS — keyinroq zaxira.
- B2.1 FastAPI skeleti (`apps/api`): `create_app` fabrikasi, sozlamalar (`UP_*`, pydantic-settings), structlog
  (JSON / dev'da konsol, so'rov id konteksti, maxfiy maydonlar filtri — token, kod, kalit, Authorization),
  RFC 9457 `application/problem+json` xatolar `code` bilan (404, 405, 422, `AppError`, 500 — prod'da tafsilotsiz),
  `X-Request-ID`, kirish logi, `/health` va `/api/v1/health`, OpenAPI `/api/v1/openapi.json`. CI: API qamrovi ≥ 80%.
- B2.2 DB sxemasi (03 §5): 50 jadval (SQLAlchemy Core), Alembic `0001_initial_schema`, PostgreSQL RLS —
  `up_app` roli (superuser/BYPASSRLS/ega emas), `FORCE`, kompozit FK'lar, `org_id` li unikal kalitlar, global
  jadvallar faqat o'qish, kirish jadvallari yopiq, `audit_log`/`events` faqat qo'shish. Har jadvalda boshqa
  tashkilot qatorini o'qish, o'zgartirish, boshqa tashkilotga ko'chirish, o'chirish, qo'shish va unga havola
  qilish testlari; `org_transaction` (`SET LOCAL`), migratsiya upgrade ↔ downgrade va model ↔ migratsiya
  mosligi testlari. Sintetik seed `python -m upapi.db.seed` (`make seed`). CI'da PostgreSQL 18 servisi; CI'da DB
  bo'lmasa DB testlari o'tkazib yuborilmaydi, xato beradi.
- B2.3 Kirish (M1): telefon + 6 xonali kod (Telegram Gateway, ADR-028; dev'da terminalga), HMAC xesh, 5 daqiqa,
  raqam bo'yicha 5 ta/soat, 5 xato → 15 daqiqa blok; sessiya cookie (`HttpOnly`, `SameSite=Lax`, prod'da `Secure`,
  30 kun, har 24 soatda yangi token, eskisi 60 s), "qurilmalarim", qurilmadan va hamma qurilmalardan chiqish; profil.
  Tashkilot yaratish, xodimlar (rol o'zgartirish, o'chirish, oxirgi egasi himoyasi), telefon raqamga bog'langan
  taklif havolasi (7 kun, bir marta), audit jurnali; rollar matritsasi (03 §10) va `require(Permission)` —
  omborchi foyda endpoint'iga kira olmaydi (test). CSRF: `X-Requested-With` + `Origin`. Migratsiya `0002`:
  `auth_*` `SECURITY DEFINER` funksiyalari (`up_auth` roli; kod yoki sessiya tokenisiz hech narsa qilmaydi),
  ilova roli foydalanuvchi telefonini o'zgartira olmaydi.
- DB roli himoyasi: staging/prod'da API superuser, `BYPASSRLS`, jadval egasi yoki boshqa rol a'zosi bo'lgan rol
  bilan yoki xavfli sozlama bilan ishga tushmaydi; dev'da ogohlantirish. Dev compose API'si `up_app` bilan
  ulanadi (migratsiya — `UP_MIGRATION_DATABASE_URL`), `make db-check` / `python -m upapi.db.guard`, CI'da tekshiriladi.
- B2.4 Marketplace ulanishi (M2 1–2-qadam): `POST /orgs/{id}/accounts` — kalit Uzum'da tekshiriladi
  (`/v1/shops`), AES-256-GCM bilan shifrlanadi (kalit versiyasi, AAD = tashkilot + akkaunt id; `upapi.crypto`,
  `python -m upapi.crypto keygen`), do'konlar faol holda qo'shiladi; tekshirish (holat: faol / yaroqsiz / kvota /
  WAF, yangi do'konlar, eski versiyali shifrni joriy kalitga o'tkazish), kalitni almashtirish (faqat shu sotuvchi
  kaliti), uzish (shifrlangan kalit bazadan o'chadi, do'konlar va ma'lumot qoladi), do'konlarni tanlash (faollik,
  taxallus, rang). Faqat egasi; do'konlar ro'yxati — har a'zo. Yaroqsiz kalit urinishlari tashkilot bo'yicha
  soatiga 10 ta. Uzum mijozi boshlang'ichi (`upapi.uzum.client`): `Authorization` "Bearer"siz, xato turlari
  (03 §6), xato matnida kalit va javob tanasi yo'q. Migratsiya `0003`: uzilgan akkaunt (`token_state` cheklovi),
  `audit_log` indeksi. Staging/prod dev shifrlash kaliti bilan ishga tushmaydi. `test_token_secrecy.py` — kalit
  log, javob, sarlavha, xato matni va bazaning hech qayerida yo'qligi (ataylab kiritilgan sizishlarni ushlashi
  tekshirilgan).
- `CLAUDE.md`: real Uzum API, Temurning kompyuteridagi ma'lumot yoki `.env` kerak bo'lsa — ish to'xtatiladi va
  Temurga aniq buyruq + natijani qayerga yuborish yoziladi (kalit so'ralmaydi).
- B2.5 Uzum mijozi (`upapi.uzum.client`): hamma o'qish endpointlari (sotuvlar, xarajatlar, mahsulotlar, postavkalar va
  tarkibi, qaytarishlar) sahifalab, xom JSON bilan (`Page.raw`, qatorlar takrorsiz); qayta urinish (5xx/tarmoq
  0,8 → 1,6 → 3,2 s, sekundlik 429 — kutib), kunlik kvota kuzatuvi va fon uchun zaxira (`QuotaReserved`), kalit
  bo'yicha tezlik navbati foydalanuvchi ustuvorligi bilan (`upapi.uzum.limiter`), 400 da kichikroq sahifa, jimgina
  kesilgan sahifa hajmini aniqlash; `MarketplaceProvider` interfeysi (`upapi.marketplace`). Yozib olingan javoblar:
  `scripts/record_uzum.py` (Temurning Mac'ida, anonimlashtirilgan kasseta) va kasseta testlari
  (`apps/api/tests/fixtures/uzum`).
- B2.5 haqiqiy kasseta (`fixtures/uzum/recorded.json`, Temurning yozuvi): sotuvlar sahifasi 5000 (kesilmasligi
  tasdiqlandi), xarajatlar 2000; qaytarishlar `/v1/return` — butun akkaunt, tarkibi bilan (`returns()`), do'kon
  ro'yxati — `shop_returns()`; kontrakt maydonlari (postavka tarkibi, qaytarishlar) va "haqiqiy Uzum faktlari"
  testi. `record_uzum.py`: sizish tekshiruvi faqat saqlangan qiymatlarda (kalit nomlarida yolg'on xato yo'q),
  kichik harfli xarajat kodlari, nuqtali sanalar va so'rov parametrlari saqlanadi.
- B2.6 Sinxron ishlari (M3, `upapi.sync`): Procrastinate navbati (`sync.tick` har daqiqa, `sync.account` —
  `lock = account:<id>`, navbat qulfi, ustuvorlik), ishchi `python -m upapi.worker` (dev compose'da `worker`,
  migratsiyagacha kutadi, xavfli sozlama/DB rolida ishga tushmaydi). Turlar: do'konlar, sotuvlar, xarajatlar
  (lug'at — `expense_codes` + `upcore` boshlang'ichi), mahsulot/SKU/qoldiq, kunlik snapshot (Toshkent 23:50,
  `sku_daily`), postavkalar va tarkibi (yangi yoki holati o'zgarganda bir marta), qaytarishlar (butun akkaunt,
  `shopId` bo'yicha). Sotuv/xarajat usullari: tarix (2020-01-01 dan, rad etilsa qisqaroq oyna, "full"/"limited:N",
  kursordan davom), inkremental, kuniga bir marta 45 kunlik chuqur, uzilish davrini to'ldirish. Upsert: tabiiy kalit,
  partiyadagi dublikatlar birlashadi, `NULL` bilan ustidan yozilmaydi, o'zgarmagan qator yozilmaydi, sotuvchi
  kiritgani tegilmaydi; bog'lanishlar (sotuv → SKU `skuTitle`, logistika xarajati → sotuv, tarkiblar → SKU).
  `sync_runs` (progress, so'rovlar, kim boshlagan, usul) va `sync_state` (oxirgi urinish/muvaffaqiyat, kursor);
  0 ta obyekt — ogohlantirish. Xatolar: 3 ta ketma-ket kalit xatosi → "yaroqsiz" (audit), WAF/kvota → holat va
  30 daqiqada sinov, kvota zaxirasi → fon to'xtaydi, tarmoq/5xx → uzilish signali. Uzilish rejimi
  (`provider_health`): 2 do'kon / 5 daqiqa → 15 daqiqa pauza, bitta sinov, tiklangach to'ldirish.
  "Ma'lumotlar holati" `GET /orgs/{id}/sync`, "Hozir yangilash" `POST /orgs/{id}/sync/refresh` (60 s da bir marta);
  kalit ulanganda (va almashtirilganda) tarix navbatga qo'yiladi; kalit tekshiruvi sinxron xatolar hisobini
  tozalaydi. Uzum mijozi: `start_page`/`size` (davom ettirish). Migratsiya `0004`: Procrastinate sxemasi, sinxron
  ustunlari va indekslar, `provider_health`, `sync_accounts()` (`up_sync` roli). Testlar: soxta sotuvchi
  (`tests/sellerfake.py`), xaritalash (haqiqiy kasseta), engine, navbat, API, kalit maxfiyligi (sinxron yo'li).
  `psycopg[binary,pool]` — API'ning asosiy bog'liqligi (image'da `--no-dev` bilan ham libpq kerak emas).
- B2.7 CBU kurslari ishi (F20, `upapi.fx`): `fx.cbu` kuniga 2 marta (Toshkent 09:05 va 16:05), USD/CNY/RUB/EUR
  (`UP_FX_CURRENCIES`), `Nominal` ga bo'lish `upcore.fx.parse_cbu_row` da; arxiv bazadagi eng eski kundan orqaga
  `UP_FX_BACKFILL_DAYS` (730) gacha, har ishda ≤ `UP_FX_BACKFILL_PER_RUN` (30) kun; CBU bermagan kun uchun qator
  o'ylab topilmaydi (dam olish kuni — `rate_on`). Qayta urinish (5xx/tarmoq) va 3 urinishli ish; tushunarsiz javob
  hech narsa yozmaydi. Yozuv — `fx_upsert()` (migratsiya `0005`, `up_sync` egasi, manba doim `cbu`): `up_app`
  `fx_rates` ga to'g'ridan-to'g'ri yoza olmaydi, qo'lda kurslarga tegilmaydi. `UP_CBU_URL` staging/prod'da faqat https.
  Testlar: `tests/test_fx.py`.
- B2.8 Hisob ishlari (`upapi.calc`, migratsiya `0006`): qayta hisob navbati `recalc_queue` (xarid / tovar / do'kon
  sotuvlari / faqat agregat; manba bilan bitta tranzaksiyada yoziladi, takrori bitta qatorga birlashadi — eng erta
  kun). `calc.org` ishi (tashkilotga bitta, `FOR UPDATE` bilan — hisob paytidagi so'rov yo'qolmaydi): lotlar (F20:
  CBU / qo'lda / effektiv kurs, `targets` — qatorlar va qo'lda ulushlar; hisoblab bo'lmaydigan xarid lotsiz va
  xato bilan), faqat o'zgargan tovarlar uchun `sale_costs` (F21, FIFO / o'rtacha; faqat farqlar yoziladi, COGS
  o'zgarsa `changed_at` + `previous_cogs` — "qayta hisoblandi"; bekor sotuv qatori o'chadi; SKU tovarga
  bog'lanmagan — `no_item`, lot yo'q — `no_lots`), o'zgargan kunlardan `daily_sku_metrics` (`upcore.metrics.sale_totals`:
  F3–F8, F15 tannarxi ma'lum qism, F17, F18, F22 taxminiy COGS; reklama `AD#` orqali SKU'ga, bog'lanmagani do'kon
  qatorida). Sinxron sotuv/xarajat yozganda so'rov qo'yadi, akkaunt ishi `calc.org` ni navbatga qo'yadi; `calc.nightly`
  (Toshkent 03:40) — to'liq qayta qurish. Ishchi `sync` va `calc` navbatlarini oladi. Inkremental natija = to'liq
  qayta qurish (test); 10 000 sotuvli tovar bazasi bilan < 3 s (benchmark). Testlar: `tests/test_calc.py`.
- B2.9 O'qish API'lari (`upapi.reports`, `upapi.routes`, migratsiya `0007`): `GET /orgs/{id}/dashboard` (M4: hisob
  varag'i oldingi davr bilan, bugun/kecha/shu oy/o'tgan oy, oy prognozi, kunlik grafik, TOP-5 va zarar-5 SKU, F13–F19,
  F16, F29, "Diqqat talab qiladi" sanoqlari), `/pnl` (M5: qatorlar va solishtirish, oylar/kunlar/do'konlar/SKU
  ustunlari, F16 do'konlar bo'yicha, "qayta hisoblandi" soni), `/skus` (M6: unit-iqtisod, holat belgisi, F17, F18,
  qoldiq, F24, ABC; lotin/kirill va tutuqdan qat'i nazar qidiruv, saralash, kursor; bog'lanmagan va taqsimlanmagan
  alohida), `/sales` (M7: qatorlar F6–F8, tannarx belgilari, kursor, F17/F18 xulosasi), `/expenses` (M8: F9 toifalar,
  oylar, eng katta jarimalar, chiqarilganlar sababi bilan; F10 davr qismi), `/inventory` (M10 asos: F23–F30, mahsulot
  holati, muzlagan pul joylar bo'yicha; omborchiga summasiz). Davr va do'kon filtri, `meta.freshness`. P&L kataklari
  `daily_sku_metrics` dan (`lines`, `lines_uncosted`, `units_costed` ustunlari qo'shildi). `upcore`:
  `build_cells(totals=CellSales)`, `Cells.within / statements / by_and_total`, `unit_economics` (M6),
  `profit_label`, `run_rate` (M4), `statuses`, `cancel_rate`, `realization_rate_units`, `SaleLine.gross_profit`,
  `money.split`; P&L kataklari xom `Decimal` da (`Cell`) — 50 000 katakli yil 3,4 s → 0,5 s. OpenAPI:
  `apps/api/openapi.json` (`python -m upapi.openapi`) → `apps/web/src/lib/api/schema.d.ts` (`pnpm --filter web
  api:types`, openapi-typescript), CI'da ikkalasining sinxronligi. Testlar: `tests/test_reports.py` (P&L = qatorlardan
  qurilgan `upcore` P&L, bosh sahifa = P&L = SKU yig'indisi, ustunlar va drill-down yig'indilari, rollar, tashkilotlar
  ajratilgani, benchmark).
- B2.10 Staging (https://16-170-178-179.sslip.io, AWS eu-north-1 vaqtincha — ADR-029; `docs/staging.md`): `infra/compose/staging.yml` (postgres, migrate, api,
  worker, caddy; image'lar GHCR'dan), `infra/caddy/` (web build + Caddy: HTTPS, HSTS, CSP, SPA marshrutlari),
  `infra/staging/bootstrap.sh` (Ubuntu 22.04/24.04: Docker, ufw, fail2ban, swap, `deploy` foydalanuvchisi, tungi
  zaxira taymeri), `gen-env.sh` (tasodifiy sirlar, `.env` 600), `deploy.sh` (zaxira → migratsiya → konteynerlar →
  HTTPS orqali sog'liq → ishlamasa oldingi image; disk uchun eski image'lar tozalanadi), `infra/backup/` (`pg_dump`,
  `pg_restore --list` tekshiruvi, 14 kun; to'liq tiklash), `.github/workflows/deploy-staging.yml`. API: kirish kodi
  IP bo'yicha soatiga 20 ta (`UP_OTP_PER_IP_HOUR`, `upapi.ratelimit`, `otp_ip_rate_limited`), uvicorn
  `--proxy-headers`. CI: `staging` ishi (shu oqim real konteynerlarda), `infra/tests/` (skriptlar: qaytish, migratsiya
  xatosi, image yo'qligi, zaxira aylanishi, sirlar staging tekshiruvlaridan o'tadi).
- B2.11 real sinov vositalari (`docs/staging.md` "Real sinov"): `scripts/staging_connect.py` (stdlib, Mac'da — telefon +
  Telegram kodi, tashkilot, Uzum kaliti `getpass` bilan, yaroqsiz kalitni almashtirish, sinxron holati `status --watch`;
  sessiya `~/.uzum-profit/staging-session.json` 600, kalit hech qayerga yozilmaydi); `python -m upapi.realcheck` +
  `infra/staging/realcheck.sh` (serverda, `up_app`/RLS bilan JSON: do'kon × oy × holat bo'yicha F3–F6 yig'indilari va
  qatorlar, taxminlar — postavka `skuForInvoiceDtoList[].id`, faktura `dateCreated` ko'rinishlari, `/v1/return`
  ishi, logistika `externalId` (buyurtma id'siga mosligi ham), `sellerProfit` bo'yicha `amount`/`amountReturns` va
  `PARTIALLY_CANCELLED` semantikasi, "boshqa" xarajat kodlari; 24 soatlik sinxron xatolari); `scripts/compare_staging.py`
  (legacy `uzum.db` bilan oylar bo'yicha 1 so'mgacha, qator farqlari, taxminlar hukmi ✓/✗/≈). CI `staging` ishida
  realcheck image ichida. Testlar: `test_realcheck.py`, `test_compare_staging.py` (sinxron → realcheck → legacy import
  bilan solishtirish), `test_staging_connect.py` (haqiqiy API bilan), `infra/tests`.
- B2.11 tuzatish: `realcheck.sh` `sudo -u deploy` bilan chaqirilganda `UP_ROOT` ga o'tadi (oldin `/home/ubuntu` da
  qolib, compose "stat .: permission denied" bilan yiqilardi); `compare_staging.py` bo'sh yoki buzuq JSON'da traceback
  o'rniga tushunarli xabar; `staging_connect.py` tarix yuklanayotganda (xatosiz) "⏳ tarix yuklanmoqda" ko'rsatadi.
- B2.11 real natija (Temurning ikkala do'koni, staging): legacy bilan har oy TO_WITHDRAW dona/tushum/komissiya/logistika
  0 so'm farq; postavka SKU id, faktura sanasi, `/v1/return`, logistika `externalId` taxminlari tasdiqlandi (08 §4).
  **Tuzatildi** (`upcore.metrics`): Uzum Bekor qatorda `amount` = 0 beradi, bekor dona `amountReturns` da — F17 bekor
  ulushi va F16 realizatsiya darajasi bekor donani 0 deb olardi (R = 100%), F18 qaytish ulushi va ombor tezligi
  (`daily_sku_metrics.returns`) bekor qilinganni qaytish deb sanardi. Endi Bekor dona = `amount` + `amountReturns`,
  F18 — faqat Yakunlangan qatorlardan. Mavjud agregatlar tungi `calc.nightly` da qayta quriladi. Testlar: haqiqiy
  shakldagi Bekor qator (`test_metrics.py`, `test_calc.py`).
- B2.11 yakuni (2026-10-27, Temurning qayta tekshiruvi): 24 soatda xato ishlar 0, iyul–oktabr har oy 0 so'm farq,
  taxminlar ✓ — **B2 yopildi**. `docs/staging.md`: qator darajasidagi holat farqlari (sinxron vaqti) qanday o'qiladi.
- B3.1 Web karkasi (`apps/web`): `lib/api/client.ts` — openapi-fetch (generatsiya qilingan sxema), cookie bilan,
  `X-Requested-With` (CSRF), RFC 9457 → `ApiError` (`code`, `detail`, so'rov ID, `retryable`), 204 va tarmoq xatosi;
  `app/query.ts` — TanStack Query (staleTime 60 s, 4xx qayta so'ralmaydi, tarmoq/5xx/429 — 2 marta, 401 → kesh
  tozalanadi va `/login?redirect=`), `meQuery`; `app/router.tsx` — TanStack Router (kontekstda Query, kirish talab
  qiladigan `app` tartibi, `/`, `/status`, `/login` — lazy bo'laklar; qaytish manzili faqat ichki yo'l); xato
  chegaralari `app/errors.tsx` (marshrut xatosi — matn, so'rov ID, "Qayta urinish"; 404; yuklanmoqda; ildiz
  `AppErrorBoundary`). Sahifalar — B3.5–B4 da. Tezlik byudjeti: `pnpm --filter web size` (boshlang'ich JS ≤ 250 KB
  gzip; hozir ~103 KB), CI'da. Testlar: `App.test.tsx`, `lib/api/client.test.ts`.
- B3.2 Tillar va formatlash (`apps/web`): `lib/i18n` — i18next, uz-Latn (asosiy; testda oddiy apostrof yo'qligi va
  oʻ/gʻ U+02BB), uz-Cyrl uz-Latn'dan avtomatik (`translit.ts`: oʻ/gʻ/sh/ch/yo/yu/ya, e/э, tutuq → ъ, katta harf,
  `{{...}}` va teglar o'zgarmaydi, nomlar — Uzum, Telegram, ROI ...; so'z istisnolari — sentabr → сентябр,
  kompensatsiya; kalit tuzatishlari `uz-Cyrl.fixes.ts`), ru qo'lda (`Messages` tipi — kalit yetishmasa typecheck
  xatosi); tanlov `localStorage` (yopiq bo'lsa ham ishlaydi) → brauzer tili → uz-Latn, `<html lang>`, `setLanguage`,
  `useFormat()`; atamalar lug'ati (04 §8.2) `terms` + `glossary.ts`; API xato `code` lari matni (04 §8.1 ovozida).
  `searchKey` — kirill/lotin va apostrof turlaridan qat'i nazar qidiruv kaliti (04 §8.3). `lib/format` (04 §8.4):
  guruh U+00A0, kasr vergul, manfiy U+2212, pul (soʻm / сўм / сум, jadvalda valyutasiz), valyuta ($ ¥ € ₽), ixcham
  (ming/mln/mlrd, тыс./млн/млрд), foiz va o'zgarish (▲/▼), sana, kun (`23-oktabr`, `23 октября`), davr, hafta kuni,
  nisbiy vaqt (rus ko'plik shakli) — Toshkent sanasi bo'yicha; API satrlari float'siz, ROUND_HALF_UP. B3.1 matnlari
  i18n'ga ko'chdi. eslint: `toLocaleString`/`Intl` faqat `lib/format` da. Testlar: `format.test.ts`, `i18n.test.tsx`,
  `App.test.tsx` (ruscha va kirillcha karkas, xato matni).
- B3.3 Dizayn tokenlari va mavzu (`apps/web`): `src/styles/tokens.ts` — yagona manba (ranglar 04 §4.2 ikkala
  rejimda, grafik slotlari 1–8, holat, ketma-ket va ikki qutbli ranglar, rollar §4.3, tipografik shkala §2.1, oraliq,
  radius, breakpointlar, soya, shrift steklari); `tokens.css` — CSS o'zgaruvchilari (tizim sozlamasi
  `prefers-color-scheme` yoki `data-theme`), test bilan `tokens.ts` ga teng. WCAG kontrasti testi (matn ≥ 4,5,
  muted/input/fokus ≥ 3, holat matni o'z fonida ≥ 4,5) — `border-input` yorug' rejimda `#858A96` ga o'zgardi (eskisi
  qog'oz/hover fonida 2,9; 04 §4.4 yangilandi). Inter variable (wght + opsz, `@fontsource-variable/inter`) o'zimizda:
  lotin, lotin-ext, kirill, kirill-ext subsetlari `unicode-range` bilan, `font-display: swap`, lotin fayli preload
  (vite plagini); belgilar qamrovi testda. `base.css` — shkala, `.num` (tabular-nums), `.mono`, `.hero`, fokus halqasi,
  mobil o'lchamlar, `prefers-reduced-motion`. `lib/theme.ts` — `applyTheme` / `useTheme` (tizim / yorug' / qorong'i,
  `localStorage`, `theme-color`), `public/theme-init.js` — React'dan oldin (CSP `script-src 'self'`, inline yo'q).
- B3.4 Komponentlar katalogi (`apps/web/src/components/ui`, 04 §5–6) va `/ui-kit` sahifasi (kirishsiz, sintetik
  namunalar, mavzu va til tanlash): Button (4 tur, 3 o'lcham, yuklanish), Field + TextInput / NumberInput /
  MoneyInput (`lib/format.parseNumber` — "1 234,5", "1234.5", "1.234.567,50"; API uchun nuqtali satr, valyuta
  qo'shimchasi), Select, Combobox (`searchKey` + apostrofsiz, ↑ ↓ Enter Esc, ARIA combobox/listbox, rasm bilan),
  DateRangePicker (`lib/dates`: Toshkent bugungi kuni, 8 tayyor davr, oldingi davr / o'tgan yil, oy kalendari;
  kalendar bilan ikki bosishda), CompareToggle, KPI (o'zgarish rangi = yo'nalish × yaxshimi, sparkline), FormulaPopover
  (F-raqam, manba, taxminiy sababi), LedgerTable (operator ustuni, oraliq summa `rule`, yakun `rule-double`,
  drill-down), DataTable (asos), Badge / StatusPill, Banner, Dialog / Drawer (fokus tuzog'i, Esc, fon, fokus qaytadi;
  drawer mobilda pastdan), Popover, Tooltip, Toast (`ToastProvider`, 5 s), Stepper, Timeline (Partiya yo'li),
  EmptyState, Skeleton (300 ms kechikish), ProgressBar, ProductThumb (lazy, harf-belgi), FileDrop. Lucide ikonlar.
  `formatMonth`. Testlar: `ui.test.tsx` (xatti-harakat), `ui-kit.test.tsx` (axe-core: jiddiy xato 0, ochiq
  qatlamlar va ruscha bilan). Boshlang'ich JS 135 KB gzip.
- B3.5 Sahifa karkasi (`apps/web/src/components/shell`, 04 §7.1): `AppShell` kirish talab qiladigan sahifalar uchun;
  Sidebar (232/64 px, tanlov saqlanadi), TopBar — do'kon (bir nechta), davr, solishtirish, SyncIndicator va uzilish
  banneri (M3), mobil tab bar ("Yana" paneli bilan), Ctrl/⌘ + K palitrasi (sahifalar, mavzu, til; lotin/kirill
  qidiruvi), foydalanuvchi menyusi (mavzu, til, chiqish). Umumiy filtrlar URL'da (`shop`, `from`, `to`, `cmp`;
  `app/filters`) va bo'limdan bo'limga o'tganda saqlanadi. Sahifalari yo'q bo'limlar "qurilmoqda" sahifasida.
  Testlar: karkas (axe-core bilan), filtrlar, sinxron holati; soxta API `src/test/api.ts`. Boshlang'ich JS 146,8 KB gzip.
- B3.6 Grafik komponentlari (`apps/web/src/components/charts`, 04 §5.1): LineBarChart, StackedBarChart, WaterfallChart,
  HeatmapChart, CalendarHeatmap — Apache ECharts 6 (SVG, alohida bo'lak ~84 KB gzip), ranglar tokenlardan, tooltip,
  "Grafik | Jadval" ko'rinishi, legenda, matnli tavsif, bo'sh holat, annotatsiyalar (bepul logistika, uzilgan kunlar),
  qorong'i rejim va `prefers-reduced-motion`. `/ui-kit` da "Grafiklar". Testlar: sof quruvchilar, ramka va hayot sikli,
  axe-core, haqiqiy ECharts jsdom'da. Boshlang'ich JS 147,8 KB gzip.
- B3.7 Kirish, onboarding, "Ma'lumotlar holati" (`apps/web/src/features/{auth,onboarding,status}`): `/login` (telefon +
  Telegram kodi, 6 raqamda avtoyuborish, qayta yuborish 30 s), `/invite`, profil tili bilan bog'lash; `/onboarding`
  (tashkilot → Uzum kaliti → do'konlar: nom va rang → tarix yuklanishi progressi; serverdan holat, istalgan joydan
  davom etish); "Ma'lumotlar holati" (do'kon × ma'lumot turi, akkaunt va kvota, "Hozir yangilash"). Tashkilotsiz
  foydalanuvchi onboarding'ga yo'naltiriladi. Xavfsizlik: xom URL qidiruvidagi qaytish manzili ishlatishdan oldin qayta
  tekshiriladi (ochiq qayta yo'naltirish). Testlar (axe-core bilan), `lib/phone`. Boshlang'ich JS 154 KB gzip.
- Q1 Brend nomi **SellerMax** (ADR-030, `sellermax.uz`): UI (`app.name`, hamma tillarda lotinda), sahifa sarlavhasi va
  API sarlavhasi ("SellerMax API", `openapi.json`) yangilandi; repo va paket nomlari o'zgarmaydi. Tovar belgisi
  tekshiruvi ochiq (06 §6).
- B3.8 Playwright (`apps/web/e2e`, `playwright.config.ts`, CI'da `E2E va vizual` job'i): production build brauzerda,
  holatli soxta API (`e2e/support/api.ts`, vaqt qotirilgan). E2E: kirish, to'liq onboarding, karkas; axe haqiqiy
  brauzerda **kontrast bilan** (9 sahifa × yorug'/qorong'i × 1440/390 px, ochiq qatlamlar); vizual regressiya — 40
  skrinshot asosi (`e2e/__screenshots__`, `pnpm --filter web e2e:update`). Topildi va tuzatildi: qidiruv tugmasining
  ko'rinadigan matni nomiga kirmagan (WCAG 2.5.3). B3 yopildi.
- B4.1 Bosh sahifa (M4, `apps/web/src/features/home`): hisob varag'i (hero sof foyda, tushumdan sof foydagacha qatorlar,
  har qatorda oldingi davrga nisbatan o'zgarish va FormulaPopover, mobilda 3 qatorli yig'ilgan ko'rinish),
  drill-down drawer (sotuv qatorlari, Uzum toifasi va o'z xarajatlari; kursor bilan "Yana yuklash"), davr chizig'i
  (Bugun, Kecha, Shu oy, Oy prognozi, O'tgan oy), kunlik tushum + sof foyda grafigi, "Diqqat talab qiladi", eng foydali
  5 / zarar 5 SKU, qo'shimcha ko'rsatkichlar (marja + tannarxsiz qism, ROI, bekor, qaytish, DRR, muzlagan pul, yo'ldagi
  tovar, kutilayotgan foyda). Davr, do'kon va solishtirish URL'da. API: `RowOut.change` (farq / |oldingi|, `upcore.pnl.compare`)
  — o'zgarish foizi UI'da hisoblanmaydi. `LedgerTable` ga `trailing` / `compactHidden`, `Kpi` ga `note`. Testlar: model,
  sahifa (jsdom + axe), e2e (drill-down, mobil, 360 px gorizontal skrollsiz), vizual asoslar (home, palette).
- B4.2 Foyda va zarar (M5, `apps/web/src/features/pnl`): to'liq hisob varag'i (yalpi foyda, Uzum xarajatlari turlari,
  o'z xarajatlari toifalari; tannarxsiz sotuvlar to'lovi yalpi foydadan oldin — har oraliq summa zanjirda to'g'ri) va
  ustunlar: joriy davr, tushumga nisbatan, oldingi davr, farq, o'zgarish (tor ekranda — joriy va o'zgarish);
  sharshara (tushumdan sof foydagacha); kutilayotgan blok (F16, R do'kon bo'yicha, R yo'q bo'lsa sababi); tannarx
  qamrovi sariq banneri (F15); "qayta hisoblandi" banneri; drill-down (bosh sahifa `Drill`); kesimlar — oylar,
  do'konlar, SKU (`?view=` URL'da), do'kon va SKU kesimida F9/F10 to'g'ridan-to'g'ri va taqsimlangan, "Taqsimlanmagan"
  (ADR-026). Bepul logistika kunlari (`upapi.reports.free`: ma'lumotdan, do'kon × kun ≥ 90%, + jadval) — `/pnl` va
  `/dashboard` `free_periods`, kunlik grafikda soya; haqiqiy hisobga ta'sir qilmaydi. `/pnl`: SKU ustuni nomi;
  `StatementOut`: `uzum_total`, `own_total`, F9/F10 to'g'ridan-to'g'ri va taqsimlangan jami. `upcore.tariffs`:
  `is_free_day`, `typical_fee`, `standard_fee_of` (me'yoriy tarif uchun, B4.3). ADR-031 (Temur tasdiqladi): Uzum
  bonuslari — vaqtinchalik ma'lumot; P&L'dagi "standart tarif bo'yicha foyda" qatori olib tashlandi, F40 — me'yoriy
  (bonussiz) foyda/dona, faqat SKU baholash va narx uchun (B4.2a, B4.3). Testlar: core, API (bonus kunlari haqiqiy
  P&L'ni o'zgartirmaydi, SKU nomlari, ADR-026 yig'indilari), model, sahifa (jsdom + axe), e2e (kesimlar URL'da,
  360 px), haqiqiy brauzerda axe, vizual asos.
- B4.2a Uzum bonuslari (ADR-031): vaqtinchalik bepul xarajat davrlari — ma'lumot, qoida emas. `upcore.waivers`
  (turlar: sotuv logistikasi + P&L'ga kiradigan Uzum toifalari; tekshiruv; `waiver_for`; takliflar — aniqlangan bepul
  kunlardan, mavjud yozuvlar qoplamaganlari). Migratsiya 0008: `fee_waivers` (do'kon yoki hammasi, sanalar, turlar,
  sabab, manba, `dismissed_at`; RLS) — `free_logistics_periods` o'rniga. API: `/fee-waivers` (GET — `view_finance`;
  POST/PATCH/DELETE — `manage_settings`, audit jurnali), `/pnl` `waivers` va `waiver_suggestions`, `/dashboard`
  `waivers`, `/sales` `waiver_id`; `upapi.reports.free` o'rniga `upapi.reports.waivers`. Web: P&L'da bonus banneri,
  taklifni belgilash yoki rad etish, qo'shish shakli (Dialog), drill-down'da "Bonus davri" belgisi, bosh sahifa
  grafigida bonus davri soyasi; mobilda P&L banner tugmalari matn ostida. Haqiqiy foyda o'zgarmaydi. Testlar: core
  (100%), API (CRUD, ruxsatlar, tekshiruvlar, audit, taklif → tasdiqlash/rad etish, sotuv belgisi, tashkilotlarni
  ajratish, RLS), sahifa (jsdom + axe), e2e, vizual asos.
- B4.3 Mahsulotlar (M6). Core: `upcore.unit.unit_calc` (narxdagi foyda/dona, zararsizlik narxi F35, maqsadli marja
  narxi F36 — bitta tenglamadan), `upcore.waivers.normative_profit` (F40: foyda/dona − bonus bilan tejalgan xarajatning
  me'yoriy qiymati; baho yo'q — taxmin qilinmaydi). API: `/skus` — yangi ustunlar (to'g'ridan-to'g'ri va taqsimlangan
  xarajat, me'yoriy foyda/dona va holati), filtrlar (`label`, `abc`), saralash kalitlari, `bonus` (davr bonuslari va
  baholanmaydigan turlar); `/skus/{id}` — SKU sahifasi (kunlik tarix, lotlar, qaytish sabablari, bog'langan tovar,
  kalkulyator boshlang'ich qiymatlari manbasi bilan, Uzum havolasi); `/unit-calc`; `/items`, `PUT /skus/{id}/item`
  (tovarga bog'lash / yangi tovar / ajratish; `manage_purchases`, audit, qayta hisob navbati). Me'yoriy logistika —
  SKU'ning bonusdan tashqari oxirgi pullik tarifi, bo'lmasa do'konning odatiy tarifi (oxirgi 90 kun); saqlash — SKU
  `storage_price` × bonus kunlaridagi qoldiq-kunlar. Web: `/products` (qidiruv, filtrlar, saralash URL'da, ustun
  tanlash va saqlangan ko'rinishlar brauzerda, har ustunda formula, virtual skroll, bonus banneri, jadvaldan tashqari
  qatorlar) va `/products/:skuId` (KPI, tarix grafiklari, lotlar, qaytishlar, tovarga bog'lash, unit kalkulyator);
  `DataTable` — saralanadigan sarlavha va virtual skroll. Testlar: core, API (haqiqiy PostgreSQL), sahifalar (jsdom + axe).
- B4.4 Buyurtmalar (M7). Core: `upcore.metrics.late_cancel_share` (F17 qismi — topshirilgandan keyin bekor ulushi).
  API: `/orders/analysis` — bekor (F17) va qaytish (F18) ulushi, topshirilgandan keyin bekor (`issued_at`), kunlik trend,
  bekor va qaytish sabablari (`returnCause`), SKU bo'yicha jadval, qaytim saqlash xarajati (C000004, kompensatsiya
  ayirilgan, chiqarilgani hisobga kirmaydi). Web: `/orders` — bo'limlar "Ro'yxat / Bekor bo'lish / Qaytarilish" va
  ro'yxat holati filtri URL'da; ro'yxat (`/sales`, kursor bilan): holat belgisi, "Bonus davri", "Taxminiy", tannarxsiz
  qator tire bilan; tahlil: KPI (formula "?" bilan), kunlik grafik, sabablar va SKU jadvali. Testlar: core, API
  (haqiqiy PostgreSQL: ulushlar, sabablar, do'kon va davr filtri, ruxsatlar, boshqa tashkilot), sahifalar (jsdom + axe).
- B4.5 Xarajatlar (M8). API: `POST/PATCH/DELETE /own-expenses` (o'z xarajatlari: bir martalik, davr — amortizatsiya,
  takroriy — `repeat_months`, har oy alohida yozuv; toifa nomi bilan, yo'q bo'lsa yaratiladi; do'kon yoki butun
  tashkilot; `manage_settings`, audit jurnali), `GET /own-expense-categories`. Web: `/expenses` — "Uzum xarajatlari"
  (toifalar F9, oylar grafigi, eng katta jarimalar, ro'yxat; P&L'ga kirmaganlari belgilanadi) va "O'z xarajatlarim"
  (F10 jami, toifalar, ro'yxat, qo'shish/tahrirlash/o'chirish — egasi va menejer, buxgalter ko'radi). Testlar: API
  (haqiqiy PostgreSQL: CRUD, takroriy qisqartirish, tekshiruvlar, ruxsatlar, audit, P&L bilan mosligi, boshqa tashkilot),
  sahifalar (jsdom + axe).
- B4.6 Xaridlar (M9). Core: `upcore.purchasing` — Partiya yo'li (`Stage`, `timeline`: joriy bosqich, o'tgan kunlar,
  keyingi bosqich kutilgan sanasi F25 medianasidan, kechikish), `stage_days` (F25 o'rganish — `reports.stock` ham shundan),
  komponent turi standart taqsimoti (kargo — vazn, tovar — qiymat). API: `GET/POST/PATCH/DELETE /purchases`, `POST
  /purchases/{id}/copy` ("qayta buyurtma"), qatorlar va xarajat komponentlari CRUD (kurs: CBU, qo'lda, kartadan
  yechilgan summa), `GET/POST /suppliers`, `/carriers`; birlik tannarx (F20) javobda jonli (`calc.lots.evaluate` —
  lotlar bilan bitta yo'l), har komponentda ishlatilgan kurs va sanasi; hisoblab bo'lmasa — sababi bilan, summasiz.
  Ruxsat: o'qish `view_purchases`, yozish `manage_purchases`; omborchi summalarni ko'rmaydi va o'zgartirmaydi; audit.
  Kech kiritilgan xarajat: yozuv bilan bir tranzaksiyada qayta hisob so'rovi, commitdan keyin `calc.org` navbatga
  (`JobQueue.defer_calc`) → o'tgan sotuvlar tannarxi va P&L "qayta hisoblandi". Web: `/purchases` (bosqich guruhlari
  URL'da, ixcham Partiya yo'li, "~" taxminiy), `/purchases/:id` (Partiya yo'li va bosqich sanalari, qatorlar — mavjud
  yoki yangi tovar, kamomad; xarajatlar; o'ngda tannarx tarkibi va F22 belgilari; qayta buyurtma, o'chirish). Testlar:
  core (Partiya yo'li), API (haqiqiy PostgreSQL: bosqichma-bosqich xarid, kech kargo → qayta hisob, kurs rejimlari,
  taqsimot va ulushlar, tekshiruvlar, ruxsatlar, F25 kutilgan sana, nusxa va o'chirish), sahifalar (jsdom + axe), e2e
  (haqiqiy brauzerda kontrast bilan axe, 360 px).
- B4.7 Ombor (M10 asos). Core: `upcore.inventory.order_by` — F27 buyurtma sanasi (bugun + zaxira kunlari − to'liq
  muddat; kechikkan — bugun va `overdue`; tezlik 0 yoki muddat noma'lum — sana yo'q), `own_warehouse_qty` — o'z omborim
  (qabul qilingan, Uzumga yuborilmagan + tuzatish − hisobdan chiqarish, manfiy emas). API: `/inventory` joylari
  (Xitoyda, yo'lda, o'z omborim — xarid bosqichidan; FBO, FBS, brak, kutilayotgan), `order_by`, jamlarda joylar bo'yicha
  dona; F27 endi o'z omborimdagi tovarni ham hisobga oladi (Uzumga yuborilishi kutilmoqda — ortiqcha tavsiya yo'q), F29
  muzlagan pulga o'z omborim qiymati qo'shildi (`frozen_money` kalitlari: china, road, own, fbo, fbs, defected;
  bosh sahifada "yo'lda" = Xitoyda + yo'lda). Yangi `POST /stock-moves`, `GET /items/{id}/stock-moves`, `DELETE
  /stock-moves/{id}`: hisobdan chiqarish (brak, yo'qotish, kamomad) va inventarizatsiya tuzatishi — tannarx dvigatelida
  lotdan chiqim (F21), tovar bo'yicha qayta hisob so'rovi (B4.6 qoldig'i); omborchi ham yozadi, buxgalter faqat
  o'qiydi; audit. Web: `/inventory` — KPI (muzlagan pul, yo'ldagi tovar, o'z omborim, o'rtacha sotilish muddati F29),
  holat guruhlari sonlari bilan (F26) va qidiruv URL'da, jadval (holat, Uzumda FBO/FBS, boshqa joylar, tezlik F23,
  zaxira kunlari F24, buyurtma sanasi va tavsiya miqdor F27, byudjet CNY va so'm, qiymat), "Xarid yaratish"
  (tavsiya miqdorli qoralama xarid), "Hisobdan chiqarish" oynasi (yozuv, oxirgi yozuvlar, o'chirib qaytarish);
  omborchi summasiz. Testlar: core (F27 sana, o'z omborim), API (haqiqiy PostgreSQL: joylar xarid bosqichidan, qiymat,
  hisobdan chiqarish va tuzatish qoldiqqa ta'siri, lotdan chiqim, tekshiruvlar, ruxsatlar, audit), sahifalar (jsdom +
  axe), e2e (kontrast bilan axe, 360 px).

### Tuzatildi

- Davr nomi: 30 kunlik oyning 30-kunida (va 1-yanvarda) standart "Shu oy" davri "30 kun" ("Bugun") deb ko'rinardi —
  bir xil kunlarga tushgan tayyor davrlarda taqvim nomi ustun (`matchPreset`).
