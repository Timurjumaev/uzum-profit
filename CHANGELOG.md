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
- B4.8 Sozlamalar (M16). Migratsiya 0009: `orgs.settings` (JSONB) — standart yetkazish muddatlari (F25) va ABC qamrov
  kunlari (F27) bazada. API: `GET /settings` (tannarx usuli, soliq profillari va ma'lumotnoma stavkalari, to'lov
  jadvallari va shartlari, muddat va qamrov), `PUT /settings/cost-method` (almashsa hamma tovar/xarid/do'kon qayta
  hisob so'rovi, commitdan keyin `calc.org`), `POST/PATCH/DELETE /tax-profiles` (sana bo'yicha; rejimga mos maydonlar,
  bir sanada bitta profil — 409), `POST/DELETE /payout-schedules`, `PUT /settings/inventory`; o'qish `view_settings`,
  yozish `manage_settings`, audit. Standart muddatlar ombor (holat, buyurtma sanasi, tavsiya) va xarid sahifasidagi
  kutilgan sanaga ulangan, qamrov F27 va ABC ga. Web: `/settings` — tannarx usuli (tasdiq bilan), soliq profili,
  Uzum to'lov jadvali, muddatlar va qamrov, do'konlar (faqat egasi), Uzum bonuslari ro'yxati (qo'shish, tahrirlash,
  o'chirish; `WaiverForm` P&L bilan umumiy). Testlar: API (haqiqiy PostgreSQL: usul almashishi va qayta hisob, soliq
  profili CRUD va tekshiruvlar, to'lov jadvali, muddat/qamrovning hisobotlarga ta'siri, ruxsatlar, RLS, audit),
  sahifalar (jsdom + axe), e2e (kontrast bilan axe, 360 px).
- B4.10 Excel eksport: `upapi.reports.xlsx` (formatlangan ish daftari) va `/orgs/{id}/exports/{sales,skus,expenses,purchases,inventory}.xlsx`
  (ro'yxat endpoint'ini sahifalab chaqiradi; `export` / `export_inventory` ruxsati; omborchiga summasiz), web'da
  `ExportButton` (Buyurtmalar, Mahsulotlar, Xarajatlar, Xaridlar, Ombor). Testlar: fayl qatorlari va yig'indilari
  ro'yxat API'si bilan bir xil (haqiqiy PostgreSQL), rollar, boshqa tashkilot ma'lumoti yo'qligi, formula
  in'ektsiyasidan himoya, tugma (URL, yuklash, xato toast'i).
- B4.11 Yordam: `PageHelp` (8 asosiy sahifada "?" — qisqa tushuntirish, uz-Latn/uz-Cyrl/ru) va yetishmagan FormulaPopover'lar
  (Buyurtmalar qatorlari F4–F8, qaytim saqlash F9, Ombor F27/F29). Testlar: PageHelp, Buyurtmalar sahifasi, matnlar to'liqligi.
- B4.12 Boshlang'ich holat (ADR-033, F41): eski partiyalarni kiritmasdan boshlash. `upcore.costing.Opening` — boshlash
  sanasidan oldingi sotuvlar tarixiy narxda ("tarixiy" belgisi, lotlarga tegmaydi), boshlang'ich qoldiq — birinchi lot,
  oldingi partiyalar ishlatilmaydi; migratsiya 0010 (`orgs.cost_start_on`, `item_costs`, `opening_stock`); `GET/PUT
  /opening` (tushum tartibi, Uzum qoldig'i taklifi, qamrov, tovarsiz SKU uchun tovar yaratish, audit, qayta hisob); ombor
  qiymatida boshlang'ich narx; unit kalkulyator tannarxi — oxirgi partiya. Web: `/opening` sahifasi (Sozlamalar → Tannarx
  usulidan havola). Testlar: core (FIFO va o'rtacha, narx davrlari, qaytish, hypothesis), API (haqiqiy PostgreSQL: tarixiy
  sotuv, FIFO taqsimoti 120 + 30, takroriy saqlash, ruxsatlar, tekshiruvlar, o'chirish, RLS), web (model, sahifa, axe),
  e2e (kontrast bilan axe, 360 px).
- Boshlang'ich holat: Uzum kabinetidagi SKU jadvali ko'rinishi — har Uzum mahsuloti alohida karta va ixcham jadval (tur,
  tushum, tannarx, Uzumda, o'z omborimda); "Tannarx" ustuni sarlavhasidagi tugma — "Barcha turlar uchun qo'llash" (narx →
  ✓ → hamma turga), keyin istalgan turini alohida o'zgartirish mumkin (Temur taklifi). API qatorida `product_id`, `product`.

- B4.13 (ADR-034, tovar joylari 1-qadam): `realcheck` hisobotida "qoldiq joylari" — SKU `quantity*` maydonlari
  yig'indilari (SKU/mahsulot holati bo'yicha, munosabatlar, hujjatda yo'q maydonlar), postavka holatlari, qaytarish turi ×
  holati, 60 kunlik sotuv holatlari; faqat yig'indilar, nom va shaxsiy ma'lumotsiz.

- B4.14 (ADR-034): "Postavkada" joyi — qabul qilinmagan FBO postavkalar SKU bo'yicha (Ombor sahifasi, Excel, F29
  qiymati, F27 da yo'ldagi tovar); o'z omborimdan ayiriladi. Boshlang'ich holat qoldig'iga brak, kutilayotgan, fotostudiya
  va postavkadagi tovar ham qo'shildi ("shundan postavkada N"). B4.13 natijalari 08 §4 da.

- B4.20 (07 Q10): `realcheck` hisobotida xarajatlar vaqti va bog'lanishi — Uzum yechgan logistika ↔ sotuv qatoridagi
  logistika holat bo'yicha (bekor qatorda yechilgan yashirin logistika), reklama turlari (buyurtmaga bog'liq "xaridor
  olganida" turi, `AD#` → sotuv qatori, yechilgan kun buyurtma va topshirilgan kunga nisbatan), `dateService` ↔
  `dateCreated` farqi va saqlash yechiladigan kunlar; faqat yig'indilar, matnlar raqamsiz.

- B4.36 (ADR-048 davomi): **kartochkalar bir xil burchakda** — Asosiy, Foyda va Mahsulotlar sahifalaridagi kartochkalar ham 10 px (hisob
  varag'i burchaksiz); davr kartalaridagi sarlavhalar bir chiziqda; jadvallarda gorizontal skroll bo'lsa, chetida yengil soya. Faqat CSS.
- B4.35 (ADR-048 davomi): **dizayn jilosi — qolgan sahifalar.** KPI kartalarda raqamlar bir chiziqda; Ombor holat belgilari cho'zilmaydi;
  Buyurtmalarda filtr va Excel tugmasi bir chiziqda; Xarajatlarda Excel tugmasi cho'zilmaydi; Sozlamalarda sarlavha, izoh va forma
  sarlavhalari oralig'i tuzatildi. Faqat CSS.
- B4.34 (ADR-049, Temur topdi): **Kargo sahifasi tuzatishlari.** Kargo xarajati turlarida endi faqat kargoga tegishlilari (Kargo, Bojxona,
  Qadoqlash, Shtrix-kod / yorliq, Uzum omboriga yetkazish, Boshqa); Tovar, Xitoy ichki yetkazish va agent komissiyasi xaridniki — API ham rad
  etadi (`kind_not_for_shipment`). Oyna tugmalari to'g'ri yoziladi ("Xarajatni / Kargoni / Sanalarni saqlash"), kargodagi xaridni kargo
  sahifasidan ajratish mumkin, xaridsiz kargoda tushuntirish chiqadi.
- B4.33 (ADR-048, Temur talabi): **dizayn jilosi — Xaridlar va Kargolar** (yo'nalish A, "hisob daftari"). Standart mavzu endi yorug' (tizim
  sozlamasi emas; menyuda hamon tanlanadi). Iliq qog'oz tokenlari va yangi `border-strong`; jadval (sarlavha fon va siyoh chiziq, qator
  bo'shliqlari, burchak), mobilda Xaridlar va Kargolar ro'yxati ixcham (nom ostida meta qator), tovar nomlari bir qator; formadagi
  `submit` tugma va sahifaning asosiy amali — primary; yig'indi paneli hisob daftari qatorlari bilan; oynadagi radio/checkbox tanlov qatorlari
  va Summa/Valyuta qatori tuzatildi. Vizual testlarga xaridlar va kargolar sahifalari qo'shildi.
- B4.32 (ADR-047, Temur talabi): **xarid ↔ kargo biriktirish.** Xarid sahifasida "Yangi xarajat" → Turi = Kargo tanlansa, summa
  o'rniga kargolar ro'yxati chiqadi (holati va sanasi bilan, "Kargosiz", "Yangi kargo…") va xarid shu kargoga biriktiriladi —
  xarajat komponenti yaratilmaydi, kargo puli ikki marta hisoblanmaydi. Kargo sahifasida "Xarid biriktirish": kargosiz va boshqa
  kargodagi xaridlardan bir nechtasini belgilab biriktirish (biri xato bersa to'xtaydi, nechtasi biriktirilgani aytiladi).
- B4.31 (ADR-046, Temur taklifi): **Kargo — bitta kargo, ko'p xarid.** Yangi `shipments` (nomi, kargo kompaniyasi, Xitoy omborida /
  yo'lda / keldi sanalari), `purchases.shipment_id`, `cost_components.shipment_id` (migratsiya 0017). Kargo xarajatlari kargodagi
  hamma xaridlarning hamma tovarlariga bitta taqsimotda bo'linadi (yig'indi tiyinigacha); sanalar kargodan; `/shipments` API va
  ekranlar (ro'yxat, sahifa: xaridlar kargo ulushi bilan, xarajatlar, tovarlar), xarid shaklida kargo tanlovi.
- B4.30 (ADR-045, Temur tasdig'i): **zaxira kurs manbai — bozor kursi**. cbu.uz staging serverdan (AWS) ochilmaydi, shuning uchun
  CBU javob bermasa joriy kurs va arxiv `fx_market_urls` dan (jsDelivr, Cloudflare Pages) olinadi, `fx_rates.source = market`
  (`fx_upsert_market()`, migratsiya 0016). Bir kunda CBU ustun; lotda `market_rate` belgisi (taxminiy), xarajatda "bozor kursi,
  Markaziy bank emas" (`rate_source`). Qo'lda va "karta" kurslari o'zgarmadi.

- B4.28 (ADR-044, Temur talabi): xarid tovarini **hamma SKU'dan** tanlash — `GET /sku-picker` (do'kon, mahsulot, variant,
  qoldiq, Uzum holati; arxivlangan va bloklangan ham; avval qoldig'i yoki sotuvi borlari) va SKU'siz tovarlar;
  `LineIn.sku_id` (tovari yo'q SKU'ga tovar o'zi yaratiladi) va `POST /purchases/{id}/lines/bulk` (bir nechta tovar
  bitta tranzaksiyada); shaklda bir nechta SKU tanlash va takror belgisi.

- B4.26 (ADR-043, Temur talabi — Robohub tahlili): bosh sahifada **KPI sarhisob** — "Buyurtmadan sof foydagacha" yo'li
  va 4 guruh × 24 kartochka (buyurtmalar va tushum; Uzum ushlab qolgani va foyda; qaytarilgan va bekor qilingan;
  o'rtacha), har birida oldingi davr qiymati, o'zgarish (ulushda — punkt), trend chizig'i va formula. Yangi formulalar
  F44–F48 (`upcore.metrics.OrderFlow`, `Statement.uzum_costs` / `after_uzum`), `/dashboard` → `summary`, sozlamalarda
  bekor va qaytarish ulushi ogohlantirish chegaralari (`PUT /settings/alerts`), realcheck `cancel_split`.
- B4.62 Tanqidiy tahlil hisoboti `docs/plan/09-audit.md` (faqat hujjat, kod o'zgarmadi): hisob va ma'lumotdagi 15 ta
  topilma (F23 tezlik tugab qolishdan keyin 3,5 barobar kam; F26/F27 o'z ombori va yo'ldagi tovarni ko'rmaydi; ADR-051
  "postavka kuni" ADR-055 fakti bilan yangilanmagan; oy prognozi 1-sanada −60%; QQS rejimida soliq 0), xavfsizlik va
  test qamrovi, reja (B4 yopilmayapti, rejada yo'q PWA / jamoa ekrani / hodisalar), dizayn o'lchovlari (360 / 1000 /
  1440 px: bosish maydoni, jadval kengligi, bosh sahifa ierarxiyasi), raqobatchilar jadvali (2026-11-11 holati) va
  Temurning qarori kerak bo'lgan 14 ta savol (Q1–Q14).

### O'zgartirildi

- TM0 (faqat hujjat, ADR-061) Ta'minot qayta loyihasi rejasi: 9 bosqich o'rniga uch avtomatik holat (Yo'lda → Omborimda →
  Uzumda), tez xarid oynasi (jami to'landi, CNY / USD / UZS, kurs tanlovi, ixtiyoriy trek), kargo puli jadvali (trekli
  xarid / kodli quti, dona bo'yicha), sanash (kelgan son, brak, sotuvchi qaytargan summa), tovarning qadoq qo'shimchasi,
  "Boshqa SKU'ga o'tkazish", Uzumga jo'natish (Excel, band qilish, postavka bilan bog'lash), qabul farqi (kamomad ro'yxati);
  yangi formulalar F51 (brak zarari) va F52 (Uzum qabulida yo'qotish); 05 da TM1–TM8 — B5 ning boshida.

- B4.80 F50 yillik tushum chegarasi (ADR-058): soliq profilida soliq to'lovchi turi (YaTT / MChJ / o'zini o'zi band qilgan;
  migratsiya 0022, shablon to'ldiradi), chegaralar `ref_amounts` da (1 mlrd / 12 000 BHM / 100 mln so'm, sana bo'yicha);
  yil boshidan tushum chegaraning 80% iga yetsa — bosh sahifada ogohlantirish (100% — qizil), Sozlamalarda doim holat.
  `/dashboard` va `/settings` — `revenue_limit`.

- B4.75 PR-8 (audit D3, D9, D11): jadvallar 1440 px da sig'adi — Mahsulotlar 1 631 → 1 158 px, Ombor 1 526 → 1 158 px,
  Buyurtmalar 1000 px da 1 159 → 902 px: sarlavha matni so'z bo'yicha bo'linadi ("/" dan keyin ham, `<wbr>`), sichqonchada
  sarlavhadagi "?" 24 px, keng jadvallarda katak chekkasi 8–12 px, Omborda 8rem eng kam kenglik faqat nom ustunida, qator
  amallari ustma-ust, summa izohlari va "Taxminiy" belgilari qatorga o'tadi. Bosh sahifadagi TOP / zarar qatorlari SKU
  sahifasiga havola. Brauzer yorlig'ida belgi (`favicon.svg`; manifest va PNG — B6.3).

- B4.75 PR-7 (audit T1–T3): Playwright mobil loyihasi 360 px da (avval 390); vizual asoslar Mahsulotlar, SKU, Buyurtmalar,
  Xarajatlar, Ombor, Sozlamalar va Boshlang'ich holat uchun; axe Mahsulotlar, SKU, Buyurtmalar, Xarajatlar va Kargolarda.
  Tuzatildi: Mahsulotlar jadvalidagi SKU izohi kontrasti (12 px matn `text-muted` → `text-secondary`, 3,84 → AA); bosh
  sahifadagi telefon KPI kartochkasi chekkasi (mobil qoida ishlamay qolgan edi).

- B4.75 PR-6 (audit K13, K14, R4): `upcore.metrics` dan eskirgan va faqat testlarda ishlatilgan funksiyalar olib tashlandi
  (`profit_summary`/`ProfitSummary` — F12–F15 endi faqat `upcore.pnl.Statement` da; `payout_mismatches`, `uzum_expenses`,
  `own_expenses`, `realization_rate`, `cancel_share`, `gross_units`, `period_return_share`); `daily_sku_metrics.ads` ustuni
  (yozilardi, hech kim o'qimasdi) — migratsiya 0021. Reja hujjatlari amaldagi kodga moslandi (02 M6, 03 §8/§10/§12, 04
  §1/§2.1/§6.4/§7.4, 05 B4.55–B4.61, ADR-040 havolasi); `index.html` yorug' `theme-color` — `#F6F5F1` (`bg-page`).

- B4.75 PR-5 (audit X1, X3, T4): `open_org` a'zolik so'rovi tashkilot bo'yicha ham (RLS'dan tashqari ikkinchi qavat); CI'da
  `pip-audit` va `pnpm audit`; CI har PR'da bir marta (branch push'da emas).
- B4.75 PR-4 (audit D4, D10, D13): telefonda bosish maydoni ≥ 44 px hamma sahifa va karkasda (umumiy CSS), Ombor KPI
  kartalari 2 ustunda, Foyda sahifasida "?" nom bilan bir qatorda; `e2e/touch.spec.ts` (13 sahifa, 360 px).
- B4.73 (ADR-057 Q11), 3-qism: Buyurtmalar telefonda ro'yxat ko'rinishida (sana — ostida holat, SKU, yalpi foyda).
- B4.73 (ADR-057 Q11), 2-qism: Ombor telefonda ro'yxat ko'rinishida (nom, holat, zaxira kunlari; amallar nom ostida).
- B4.73 (ADR-057 Q11, audit D2), 1-qism: Mahsulotlar telefonda ro'yxat ko'rinishida (nom, foyda/dona, zaxira kunlari;
  gorizontal skrollsiz); `DataTable` — umumiy `mobileList` rejimi va ustunning `mobile` belgisi.
- B4.72 (ADR-057 Q10, audit D1) Bosh sahifa tartibi: uch raqam → davr → "Diqqat talab qiladi" → grafik → zinapoya va
  yig'iladigan KPI guruhlari → TOP/zarar → tovardagi pul.
- B4.71 (ADR-057 Q12) Menyu: tayyor bo'lmagan "Pul oqimi" va "Hisobotlar" yashirildi (marshrut "qurilmoqda" bilan qoladi).
- B4.69 (ADR-057 Q6, audit K8, K9) "Taxminiy" belgisi: Markaziy bank kursi va "tarixiy" narx — aniq (taxminiy qismga
  qo'shilmaydi, Buyurtmalarda izoh); lot tayyor sanasi qabul / kargo to'lovi bo'lmasa keyingi bosqichdan (Uzumga yuborildi, yopildi).
- B4.68 (ADR-057 Q4, audit K6) "▲ %" va oy prognozi: Jarayondagi qism yakunlanish ulushiga (F16 R) ko'paytiriladi,
  summalar o'zgarmaydi; `/pnl`, `/dashboard` → `rows[].change_estimated`, `forecast.estimated`; UI'da "≈" va izoh.
- B4.70 (ADR-057 Q7) Sinxron: bugungi qoldiq snapshoti har mahsulot sinxronida yangilanadi, kun ichida 0 ko'rilsa
  `sku_daily.zero_seen`; sotuv qatori birinchi marta Yakunlangan ko'rilgan vaqt — `sale_items.completed_seen_at` (migratsiya 0020).
- B4.67 (ADR-057 Q2, audit K3) Ombor: ikki signal — "Buyurtma berish" (F26 holati va F27 sanasi hamma joydagi tovardan:
  Uzum, postavka, o'z omborim, yo'lda, Xitoyda) va "Uzumga yuborish" (Uzumdagi zaxira topshirish muddatiga yetmaydi, omborimda
  bor). `/inventory` → `ship`, `days_of_stock_all`, `?ship=true`; `/dashboard` → `attention.stock_ship`; Ombor tabi va belgi.
- B4.66 (ADR-057 Q1, audit K1, K2) F23 sotuv tezligi: oyna — oxirgi 14 ta savdoda bo'lgan kun (60 kungacha orqaga);
  Jarayondagi dona × yakunlanish ulushi (F16 R, 90 kun); "7 kunga bo'lish" faqat 7 kundan yosh tovarda; qaytish darajasi
  ko'paytiruvchisi olib tashlandi. `/inventory` → `velocity.completion`, `new_item` (`return_rate` o'rniga).
- B4.74 Reja (faqat hujjat; ADR-059, ADR-060): B4.27, B4.55, B4.61, sahifalash qoldig'i, B4.76 va B4.81 → B5.0 (B5 boshi);
  tartib B4 → B6.1–B6.2 → B5 → B6.3; PWA — B6.3, jamoa ekrani va qurilmalar — B8.0, foydalanish hodisalari — B8.9; 03 §2 va §9
  haqiqatga (o'z CSS tokenlari va komponentlari; ADR-004 qisman almashtirildi); README "Temurdan kutilmoqda" 6 bandga qisqardi;
  ish oqimi — Claude o'z PR'ini CI yashil bo'lsa merge qiladi (CLAUDE.md).
- B4.54b (ADR-055): SKU sahifasi — `supplies` (postavka sanalari), qoldiq grafigi "Savdodagi qoldiq" nomi bilan postavka davri shtrixli oraliq va izoh
  bilan (Uzum postavkani qabul qilgach savdoga chiqarishga vaqt oladi — shu davrda qoldiq 0), narx grafigi faqat narx o'zgargan bo'lsa,
  "Uzumdagi narx" KPI; ishonchlilik qoidasi.
- B4.54a: SKU sahifasi tanqidiy tahlili — grafik kartalari jadval ko'rinishida cho'zilmaydi (ichki skroll), kunlik o'q davrning hamma
  kuni, siyrak chiziq nuqtalari ko'rinadi, snapshot izohi, KPI raqami kesilmaydi, Dona/O'rtacha narx/Holat/ABC tushuntirishi.
- B4.54: Mahsulotlar va SKU sahifasi mobilda (360 px): KPI'lar ikki ustunda, bosish maydoni ≥ 44 px, mobil e2e; "Sotuvsiz kunlar
  xarajati" ostiga izoh.
- B4.53: Mahsulotlar jadvalida Dona, O'rtacha narx, Qoldiq, ABC, Holat ustunlariga "?" tushuntirishi; filtr bo'lsa "Jadvaldan tashqari"
  izohi; SKU grafigida sotuvsiz kundagi xarajat ko'rinadi.
- B4.52: "Tovardan ajratish" tasdiq oynasi bilan; tovar tanlovi qidiruvi serverda (`/items?q=&limit=`, `total`) — 500+ tovarda ham
  hammasi topiladi.
- B4.51: Mahsulotlar Excel'ida "Holat" o'zbekcha va "Doʻkon" ustuni; Excel sarlavhalarida oʻ/gʻ — U+02BB (avval U+02BC).
- B4.50: SKU sahifasidan "Mahsulotlarga qaytish" qidiruv, filtr, saralash va sahifani saqlaydi (URL'da); "Zaxira kunlari"
  saralashida harakatsiz qoldiq (tezlik 0) cheksiz zaxira sifatida tepada; nom bo'yicha saralash ko'rinadigan nom va `fold` bilan.
- B4.49: Unit kalkulyator to'xtovsiz qayta chizilmaydi (debounce kiritishning matn ko'rinishida); server 422 bersa eski natija
  o'rniga aniq xato matni chiqadi.
- B4.56–B4.60 (ADR-054): sahifalash Buyurtmalar, Uzum xarajatlari, Xaridlar va Omborga — `Pagination`, `page` URL'da, umumiy
  "Sahifada" o'lchami; `/sales`, `/expenses` — `page` rejimi (`cursor` drill-down uchun qoladi) va `total`/`page`/`pages`;
  `/inventory` — `page`/`limit`; `/purchases` — ixtiyoriy `limit`/`page`; "Yana yuklash" olib tashlandi.
- B4.48 (ADR-054): umumiy sahifalash — `Pagination` komponenti (sahifa raqamlari, 20/50/100, standart 50, o'lcham brauzerda eslanadi,
  `page` URL'da); `/skus` `cursor` o'rniga `page`/`limit` (≤ 100) va `page`, `pages` javobi; Mahsulotlarda "Yana yuklash" va virtual
  skroll o'rniga sahifalar; Excel eksport hamma qatorni sahifalashsiz oladi; birinchi Mahsulotlar e2e.
- B4.47 (tamoyil 9, F13): Mahsulotlar jadvalida qisman tannarxsiz SKU'ning "Marja" va "Holat" ustunlarida "tannarxsiz N%"
  belgisi (izohida sotuvlar soni va nima qilish kerakligi) — avval bunday SKU belgisiz "Foydali" chiqardi.

- B4.46: SKU sahifasidagi "Qaytishlar sabablari" endi mijozga topshirilib qaytgan (Bekor + topshirilgan) sotuvlarni ham sanaydi
  (ADR-043, F18) — avval faqat qisman qaytarishlar kirardi. Sabablar Buyurtmalar tahlili bilan bitta funksiyadan
  (`reports.cells.cause_sums`).

- B4.45: bitta SKU tannarxi hamma joyda bir xil — SKU sahifasidagi "Tannarx/dona" KPI'si jadvaldagidek (sotuvsiz SKU'da
  oxirgi partiya / boshlang'ich narx / yo'ldagi partiya, izoh bilan; "?" — F21, F20), kalkulyator ham shu partiya zanjiridan
  (boshlang'ich narx va yo'ldagi partiya qo'shildi, boshlashdan oldingi partiya olinmaydi). API: `SkuRowOut.lot_unit_cost`,
  `lot_source` va `sort=lot_unit_cost` olib tashlandi.

- B4.44: Mahsulotlarda davrda sotilmagan har SKU holati — "Sotuv yo'q" (avval xarajati yo'q yoki kompensatsiya tushganlari
  "Ma'lumot yo'q" chiqardi; filtr va Excel ham). "Ma'lumot yo'q" — faqat sotuv bor, hammasi tannarxsiz. Reja: Mahsulotlar
  tahlilidagi 22 ta kamchilik B4.45–B4.55 da bo'lib tuzatiladi, ro'yxatlar sahifalanadi (ADR-054, B4.48, B4.56–B4.60).

- B4.43 (ADR-053, Temur chizmasi): bosh sahifadagi "Buyurtmadan sof foydagacha" — endi zinapoya: buyurtmalar summasi 100%,
  har bo'lak (bekor, qaytarish, Uzum ushlab qolgan, tannarx, o'z xarajatlar, soliq, tannarxi kiritilmagan) chiziqda o'z
  o'rnida o'ngdan chapga ayriladi, chapda sof foyda; har qatorda "summa / ulush". "Tushum" va "Uzumdan keyin qoladi"
  qatorlari yo'ldan olindi (kartochkalarda qoldi). Zarar — chapdan qizil. Yangi formula F49 (`upcore.pnl.order_to_profit`),
  `/dashboard` → `summary.flow`.

- B4.42 (ADR-052): Mahsulotlarda "Oxirgi partiya" ustuni olib tashlandi — "Tannarx/dona" o'zi sotuv bo'lmasa oxirgi partiya
  (yoki boshlang'ich narx, yo'ldagi partiya) tannarxini izoh bilan ko'rsatadi; saralash va Excel ("Tannarx manbasi") ham.
- ADR-050 (reja): B5.3 aniqlashtirildi — xarid ↔ FBO postavka SKU bo'yicha avtomatik bog'lanishi va "Uzumga yuborish" Excel'i
  Uzum kabineti shablonida (shtrix-kod, tannarx, dona); shablon fakti 08 §4 da.
- B4.28 (ADR-044): xarid sahifasidagi «Qatorlar» → **«Partiyadagi tovarlar»** («Tovar qo'shish»; xarajatda «Tovarlarga
  taqsimlash»), ruscha «Товары в партии». Tovar ro'yxati `items` o'rniga SKU'lardan — bog'lanmagan SKU'lar ham chiqadi.

- B4.26 (ADR-043): Uzum "bekor" qatori ikkiga — mijozga topshirilgan (`dateIssued`) — **qaytarish** (F18), topshirilmagan —
  **bekor** (F17). F17 = bekor / yalpi dona, F18 = qaytgan / (sotilgan + qaytgan), sotilgan — Yakunlangan + Jarayonda.
  Buyurtmalar sahifasi, sotuvlar ro'yxati va SKU jadvali shu ta'rif bilan; "topshirilgandan keyin bekor" o'rniga dona va
  summa. "Qo'shimcha ko'rsatkichlar" bloki "Tovardagi pul" bo'ldi (qolganlari KPI sarhisobda). Migratsiya 0015.
- B4.23 (ADR-040): saqlash endi Uzum qoidasi bo'yicha faqat pullik saqlashdagi tovarlarga yoziladi (aylanma 60 kundan
  oshgan, yangi bo'lmagan SKU), qaytim saqlash — qaytgan tovarlarga. Sotilmagan tovar saqlashi kabi sotuvsiz xarajatlar
  yakunlangan va kutilayotgan qismlarga o'sha kungi tushum ulushida bo'linadi — "Bugun" da yakunlangan sof foyda endi
  sababsiz manfiy chiqmaydi; "shundan sotuvsiz xarajatlar" izohi olib tashlandi.
- B4.22: Asosiy sahifada Yakunlangan kartochkasida "shundan sotuvsiz xarajatlar" — yakunlangan sotuv yo'q davrda
  yakunlangan sof foyda nega manfiy ekani (sotilmagan tovarlar saqlashi, sotuv bo'lmagan kun xarajati). Realcheck'ga
  saqlash qoidasi farazlari, jarima → postavka va qaytim saqlash → qaytarish havolalari, Yakunlangan qatorlarda Uzum
  to'lagan summa (`withdrawnProfit`) tekshiruvi.
- B4.21 (ADR-039, Temur talabi): xarajat o'z sotuvi va SKU'siga. Buyurtmaga bog'liq reklama ("Xaridor tovarni olganida
  ... yechib oldik") endi Uzum yechgan kunga emas, o'sha sotuvning buyurtma kuni, tovari va qismiga (kutilayotgan /
  yakunlangan) yoziladi; hali topshirilmagan sotuvlarga kutilayotgan reklama oxirgi 30 kundagi ulush bo'yicha "≈"
  taxminiy qo'shiladi (F42). Saqlash tovarlarga Uzum omboridagi qoldiq × saqlash narxi bo'yicha bo'linadi (F43) —
  sekin sotilayotgan tovarning saqlashi endi o'zida. Bir necha SKU'li tovarga bog'langan o'z xarajati — faqat shu
  SKU'larga. Xarajatlar sahifasi va drill-down P&L bilan bir xil sana (qatorda buyurtma sanasi ham). Realcheck'ga
  boshqa xarajatlar havolalari, logistika farqi namunalari va saqlash modeli tekshiruvi.
- B4.20 (ADR-038, Temur taklifi): "Naqd" nomi hamma joyda **"Yakunlangan"** bilan almashtirildi — Yakunlangan sof foyda +
  Kutilayotgan sof foyda = Jami (uch raqam, davr plitkalari, grafik, hisob varag'i ustuni va almashtirgichi, kesimlar,
  formulalar, yordam). "Naqd" pul qo'lga tushgan degan ma'noni berardi, aslida bu — davr buyurtmalarining yakunlangan
  qismi (pul Uzum balansida yoki yechilgan). Hisob va API o'zgarmadi; rus tilida "Факт".
- B4.18 (ADR-037, Temur taklifi): foyda uch raqamda — **naqd** (yakunlangan sotuvlar) + **kutilayotgan** (jarayondagi
  sotuvlar) = **jami** sof foyda. Kutilayotgan qism xuddi naqd kabi hisoblanadi: komissiya, logistika, tannarx, Uzum va o'z
  xarajatlarining tushum ulushi, soliq ayriladi; Uzum hali yozmagan logistika (tovar topshirilmagan) oxirgi pullik tarif
  × dona bilan taxminiy qo'shiladi va "≈ / Taxminiy" deb belgilanadi. Asosiy sahifa — "bir qarashda": uchta kartochka
  (naqd + kutilayotgan = jami), davr plitkalarida "naqd · kutilayotgan", kunlik grafikda sof foyda qatlamlari (tushumga
  almashtirish mumkin); hisob varag'i va "Jarayondagi sotuvlar" ko'rsatkichi Asosiydan olib tashlandi. Foyda sahifasi —
  "qanday hisoblandi": har qator naqd, kutilayotgan va jami ustunlarida (tor ekranda almashtirgich), kutilayotgan sof
  foyda bloki, kesimlarda "shundan naqd / kutilayotgan". Migratsiya 0013: `daily_sku_metrics` ga Jarayondagi qism
  ustunlari va to'liq qayta qurish so'rovi.
- B4.16 (ADR-036, ADR-017 ning "foyda = faqat Yakunlangan" qismi almashtirildi): Jarayondagi sotuvlar tushum, komissiya,
  logistika, tannarx va foydaga Uzum hozir bergan qiymatlar bilan kiradi (Bugun, Kecha, Shu oy, Oy prognozi endi 0 emas);
  bekor yoki qaytsa — sinxrondan keyin o'zi chiqadi. Har joyda "shundan jarayonda: N dona, X so'm", kunlik grafikda
  yakunlangan va jarayondagi qatlamlar, P&L'da "Jarayondagi sotuvlar" bloki (R — fakt, ko'paytirilmaydi), drill-down'da
  "Jarayonda" belgisi. Bekor/qaytish ulushi va R — faqat yakuniy holatlardan. Sotuv tezligi (F23) ham Jarayondagilarni
  oladi. Oldingi davrda sotuv bo'lmasa o'zgarish foizi ko'rsatilmaydi (masalan, "▲47 228%" o'rniga). Migratsiya 0012:
  `daily_sku_metrics` ga Jarayondagi qism ustunlari va to'liq qayta qurish so'rovi.

### Olib tashlandi

- B4.15 (ADR-035, ADR-031 almashtirildi): Uzum bonuslari funksiyasi — P&L'dagi "Uzum logistikani olmagan ko'rinadi /
  Bonus deb belgilash" taklifi va banneri, Sozlamalar → Uzum bonuslari, "Bonus davri" belgisi (buyurtmalar, drill-down,
  Excel), grafik soyasi, "Me'yoriy foyda/dona" (jadval, SKU sahifasi, Excel), `/fee-waivers` API va `upcore.waivers`;
  migratsiya 0011 `fee_waivers` jadvalini o'chiradi. Uzum xarajatlari API bergandek olinadi (0 kelsa — 0). F40 endi
  kalkulyator uchun standart logistika: oxirgi pullik tarif, bo'lmasa do'konning odatiy tarifi (0 qatorlar avtomatik
  hisobga olinmaydi).

### Tuzatildi

- B4.75b (CI): `E2E va vizual` job'ida brauzer apt'siz o'rnatiladi (`playwright install chromium`), tizim paketlari
  (`install-deps`) — 2 urinish, bo'lmasa ogohlantirish bilan davom (ular faqat qo'shimcha shriftlar; ularsiz e2e va skrinshotlar
  bir xil o'tishi tekshirildi). Runner'dan Ubuntu arxivi ochilmaganda testlar ishga tushmay qizarardi (2026-11-11).
- B4.75b (legacy test): `StockTests.test_page_renders_with_all_sections` sahifani haqiqiy bugungi sana bilan chizardi,
  ma'lumot esa `NOW` (2026-10-22) atrofida — 2026-11-12 dan S-FAST "Buyurtma vaqti" dan chiqib qizardi. Sana `NOW` ga qotirildi.
- B4.41 (ADR-051): boshlang'ich qoldiq tugagach boshlashdan oldingi bekor buyurtmalardan qaytgan tovar "Taxminiy · partiyalar
  yetmadi" bo'lardi. Endi manba FBO postavkalaridan: postavka yo'q — boshlang'ich narx, belgisiz; postavka va partiya bor — partiya
  narxi, belgisiz; postavka bor, partiya kiritilmagan — "Taxminiy" yangi sabab bilan. B4.39 dagi "qoldiq tugasa ham doim boshlang'ich
  narx" qoidasi almashtirildi.
- B4.40: deploy'dan keyin saqlangan tannarx natijalari (`sale_costs`, kunlik agregat) eski qoida bo'yicha tungi 03:40 gacha qolardi —
  B4.39 tuzatishiga qaramay "Taxminiy · partiyalar yetmadi" ko'rinardi. Endi ishchi ishga tushganda hamma tashkilot uchun to'liq qayta
  hisob navbatga qo'yiladi.
- B4.39: boshlang'ich holatda narxi kiritilgan tovarning qoldig'i tugagach ham sotuv kunidagi kiritilgan narx aniq tannarx hisoblanadi —
  "Taxminiy" ("partiyalar yetmadi") belgisi chiqmaydi; "lot yetmadi" faqat haqiqiy partiyalar tugaganda.
- B4.38: Mahsulotlarda sotilmagan SKU'lar "Zarar" o'rniga **"Sotuv yo'q"**; "Oxirgi partiya" partiya bo'lmasa boshlang'ich holat
  narxini ko'rsatadi; buyurtmalardagi "Taxminiy" / "Tannarxsiz" belgisi bosilganda sabablar ochiladi.
- B4.37: **zarar SKU soni** — "Zarar bilan sotilayotgan SKU" va Asosiy sahifadagi zarar ro'yxati sotilmagan SKU'larni (faqat saqlash yoki
  reklama xarajati bor) ham sanardi; endi faqat davrda sotuvi bor SKU. Hamma sotuvi tannarxsiz SKU "Zarar" o'rniga "Maʼlumot yoʻq"
  (sotuvsiz kunlardagi xarajat F15 da to'liq ayrilar, tushumi hisobga kirmasdi). **"Taxminiy" belgisi** — sababi ko'rinmasdi va tannarxi
  yo'q qatorda ham chiqardi; endi sababi (belgi ustida) va "Tannarxsiz" belgisi. **Mahsulotlar** — yangi "Oxirgi partiya" ustuni (F20):
  xarid tannarxi sotuvga bog'liq emas (avval faqat davrdagi sotuvlardan, sotuvsiz SKU'da bo'sh edi).
- B4.29: xarid sahifasida "CNY uchun ... sanasigacha kurs yo'q" — CBU arxivi bitta global eng eski kundan orqaga yurar edi,
  shuning uchun tarixi uzoq valyuta (USD) boshqasining (CNY) bo'shlig'ini yopmasdi. Endi arxiv eng kam to'lgan valyutadan
  boshlanadi; xarid saqlanganda kerakli sana kursi yo'q bo'lsa `fx.cbu` ishi `since` bilan qo'yiladi (sanadan 10 kun
  oldingacha cheklovsiz), keyin hisob qayta quriladi.
- B4.29: `python -m upapi.fxcheck` va `infra/staging/fxcheck.sh` — CBU kurslari diagnostikasi (tarmoq, `fx_rates`, `fx.cbu` ishlari).

- B4.26: qaytish ulushi faqat Yakunlangan qatorlardagi `amountReturns` dan hisoblanardi (real ma'lumotda doim 0), bekor
  ulushi esa mijoz olib qaytargan tovarlarni ham sanardi — ADR-043 bilan tuzatildi.
- B4.25 (ADR-042, Temur kuzatuvi): logistika endi Uzum **aslida yechgan** summa bo'yicha. Uzum bonusni tovar olib
  ketilgan kunga qarab bergan, sotuv qatoridagi summa esa buyurtma sanasiga qarab yozilgan: noyabrda olib ketilgan
  oktabr buyurtmalari (qatorda 0) uchun Uzum logistika yechmoqda, 9–31-oktabrda olib ketilgan oldingi buyurtmalardan
  esa yechmagan. Hali olib ketilmagan, qatorda 0 sotuvga yana taxminiy logistika qo'shiladi (B4.24 dagi o'chirish xato
  xulosaga asoslangan edi).
- B4.24 (ADR-041, sof foyda auditi): kutilayotgan foydaga bonusli oktabr buyurtmalari (Uzum logistikani 0 yozgan —
  bepul) uchun ham taxminiy logistika qo'shilardi (byDurii ~600 ming so'm ortiqcha xarajat) — taxmin o'chirildi,
  logistika Uzum yozgandek. Reklamasi allaqachon yechilgan sotuvga taxminiy reklama ham qo'shilardi — endi bir marta.
  Har xarajat bir marta ayirilishi xossa testi bilan qotirildi.
- B4.19: "Tannarxsiz sotuvlar hisobga kirmadi", garchi hamma tovarga narx yozilgan bo'lsa ham (Temur, byDurii). Sabablar:
  (1) narx yozilgan, lekin boshlash kunidagi qoldiq 0 va partiya yo'q tovar sotilsa — sotuv tannarxsiz qolardi
  ("lot yo'q"); endi o'sha kundagi tarixiy narx, "lot yetmadi" (taxminiy) belgisi bilan hisoblanadi (F21, F41);
  (2) sotuv qatori SKU'ga faqat `skuTitle` = `skuFullTitle` aniq tengligi bilan bog'lanardi — nom o'zgargan,
  bo'sh joy / harf farq qilsa sotuv abadiy bog'lanmay (tannarxsiz) qolardi; endi bir ma'noli bo'lsa: harf va bo'sh
  joydan qat'i nazar, mahsulot (`productId`) ichida nom bo'yicha, yoki mahsulotning yagona SKU'siga bog'lanadi
  (ikki ma'noli — bog'lanmaydi); keyingi sinxronda eski bog'lanmaganlar ham bog'lanib, tannarxi qayta hisoblanadi;
  (3) Boshlang'ich holatda "Narx yozilgan: N / M" da qaysi turga narx yo'qligini topish qiyin edi — "Faqat narxsiz
  turlar (N)" filtri qo'shildi.
- B4.17: Boshlang'ich holat sahifasi hamma SKU'ga tannarx so'rardi — endi faqat sotilgan yoki qoldig'i / postavkasi bor
  (yoki narxi allaqachon saqlangan) tovarlar; arxivlangan, bloklangan va hech qachon tovar kelmagan kartochkalar
  ko'rsatilmaydi, soni sahifada yoziladi.

- Boshlang'ich holat: saqlagandan keyin keyingi qadam aniq emas edi (sahifa o'zgarmay qolardi, faqat toast) — endi
  sahifa tepaga qaytadi, tepada natija (nechta turga narx, qamrov, hisob fonda) va "Foydani ko'rish" / "Omborni ko'rish"
  havolalari; narx maydonida ortiqcha ",00" yo'q (Temur topdi).
- Ombor KPI: "Yo'ldagi tovar" postavkadagi (qabul qilinmagan) tovarni ham o'z ichiga oladi ("shundan postavkada N"),
  muzlagan pul izohida "Uzumda, postavkada va o'z omborimda" (B4.14 dan keyin Temur ko'rdi: postavka KPI'da ko'rinmasdi).
- Boshlang'ich holat soddalashtirildi (Temur bilan kelishildi): jadvalda odatda faqat **Tur (SKU)** va **Tannarx**. Tushum
  ustuni olib tashlandi (tartib qoladi); Uzum qoldig'i Uzumdan o'zi olinadi va SKU ostida matn bilan ko'rinadi (kiritish
  ustuni faqat qoldiq noma'lum bo'lsa — o'tgan sana, snapshot yo'q); "O'z omborimda" ustuni — "O'z omborimda ham tovar
  bor" belgisi bilan. Qamrov endi doimiy 90 kun emas, boshlash sanasigacha bo'lgan tushum bo'yicha (shu narx qo'llanadigan
  sotuvlar) va faqat yozilgan narxlarni sanaydi; tartib ham shu tushum bo'yicha.
- Boshlang'ich holat jadvali: ustun sarlavhalari bir qatorda va o'z ustunidagi maydon bilan tekis (avval "Tannarx" tugmasi
  sarlavha qatorini balandlatib, sarlavhalar har xil balandlikda edi; "Tushum" o'ngga tekislangan edi); tugma ixcham.
- Boshlang'ich holat sahifasi yuqoridagi do'kon filtrini e'tiborsiz qoldirardi (byDurii tanlansa ham ikkala do'kon
  tovarlari chiqardi): endi `GET/PUT /opening?shop=` — tanlangan do'konda SKU'si bor tovarlar; ikki do'konda sotiladigan
  tovar "boshqa do'konda ham" belgisi bilan (tannarx va qoldiq tovar bo'yicha umumiy).
- Yuqori panel sahifa ishlatmaydigan filtrlarni ham ko'rsatardi (Xaridlar, Sozlamalar, Ma'lumotlar holati — hech birini;
  Ombor — davrni; Mahsulotlar, Buyurtmalar, Xarajatlar — solishtirishni): endi faqat ishlatiladiganlari (`pageFilters`),
  filtrsiz sahifada "Butun tashkilot bo'yicha" yozuvi; mobil "Yana" panelida solishtirish ham shunday.
- Shell testlari soatga bog'liq edi (oyning 1-kunida standart "Shu oy" davri "Bugun" deb nomlanadi) — soat qotirildi.
- Davr nomi: 30 kunlik oyning 30-kunida (va 1-yanvarda) standart "Shu oy" davri "30 kun" ("Bugun") deb ko'rinardi —
  bir xil kunlarga tushgan tayyor davrlarda taqvim nomi ustun (`matchPreset`).
- B4.63 (audit, 09 §9 PR-2) Oy prognozi bugungi tugamagan kunni to'liq kun deb sanardi (soat 10:00 da 1-sanada −60%,
  10-sanada −6%): endi oy boshidan kechagacha bo'lgan to'liq kunlar bo'yicha, oyning 1-kuni prognoz yo'q.
- B4.63 Buyurtmalar → "Bekor bo'lish" va "Qaytarilish" 360 px da sahifani gorizontal skroll qildirardi (68 va 105 px) —
  jadvallar endi o'z ichida skroll qiladi; `e2e/orders.spec.ts`.
- B4.63 Dona grafiklarida o'q qadami butun son (kichik sonlarda yorliqlar "1, 1, 1, 0, 0, 0" bo'lib takrorlanardi).
- B4.63 KPI kartasida pul birligi so'z o'rtasidan bo'linmaydi ("1 200 000 soʻ" / "m" o'rniga butun "soʻm" keyingi qatorga).
- B4.65 (ADR-056, audit K4) Postavka "keldi" = tovar savdoga chiqarilgan kun (`dateAccepted`), yaratilgan kun emas: yaratilgandan
  savdoga chiqquncha sotilgan dona qaytgan eski tovar sifatida boshlang'ich narxda, belgisiz hisoblanadi (avval shu sotuvlar
  "postavka bor, partiya kiritilmagan" belgisi yoki oxirgi partiya narxi bilan chiqardi).
- B4.79b Dinamik soliq profili — Sozlamalar: aylanma rejimida soliq qatorlari muharriri (foizli yoki qat'iy: so'm yoki BHM soni,
  oy / chorak / yil) va tayyor shablonlar (YaTT: aylanmadan foiz + 1 BHM; MChJ aylanmadan; bo'sh); BHM ma'lumotnomadan
  ko'rsatiladi; profillar jadvalida qatorlar tavsifi; uz va ru; 360 px.
- B4.79b (tuzatish) Soliq ma'lumotnomalari (`ref_tax_rates`, `ref_amounts`) deploy'da to'lmasdi (`seed` faqat dev): YaTT shablonida
  stavka bo'sh qolardi, BHM noma'lum bo'lib ijtimoiy soliq hisoblanmasdi. Endi ma'lumotnoma = bazadagi yozuv + `upcore`
  boshlang'ich qiymatlari (bazadagi ustun). Shablon tanlangach tanlov tanlangan shablonni ko'rsatadi ("Tanlang…" ga qaytmaydi).
- B4.79 Dinamik soliq profili — API: Sozlamalar javobida profil qatorlari (`lines`) va joriy BHM (`tax_amounts`); `POST/PATCH
  /tax-profiles` da qatorlarni berish/almashtirish (tekshiruv: shakl, takror nom, ko'pi bilan 10 ta; faqat aylanma rejimi).
  Migratsiya 0019: mavjud aylanmadan foiz profillari bitta foizli qatorga ko'chadi (hisob natijasi o'zgarmaydi).
- B4.78 Dinamik soliq profili — hisob varag'i: bir necha foizli qator va qat'iy qator (n × BHM yoki summa; kunlarga teng, o'z xarajati
  mexanizmi bilan taqsimlanadi) "Soliq" ostida alohida qatorlar bo'lib ko'rinadi; BHM ma'lumotnomada yo'q kunlar uchun ogohlantirish
  (`tax_missing_bhm`); sof foyda formulasi o'zgarmadi. Qatorsiz profillar avvalgidek ishlaydi. `upcore.tax.daily_rule` →
  `daily_rules`.
- B4.77 Dinamik soliq profili, 1-bosqich (ilova xatti-harakati o'zgarmadi): migratsiya 0018 — `tax_lines` va `ref_amounts` (BHM 412 000
  / 440 000 sana bo'yicha); `upcore.tax` — soliq qatorlari (`TaxLine`), eski profilni qatorlarga o'girish, qat'iy soliqning
  kunlik hisobi (n × BHM yoki summa; oy / chorak / yil; yig'indi aniq), BHM noma'lum bo'lsa `None`. Keyingi: P&L va API (B4.78).
- B4.77a Dinamik soliq profili — dizayn (faqat hujjat): ADR-058 (profil = soliq qatorlari: foizli va qat'iy / n × BHM; shablonlar YaTT,
  MChJ; BHM va chegaralar `ref_amounts` da sana bo'yicha; chegara ogohlantirishi), 02 F11 qayta yozildi, 08 §6 (BHM 440 000 —
  2026-09-01 dan), 05 da B4.77–B4.81.
- B4.75a (audit PR-3, K7) Foyda sahifasida "Soliq hisoblanmadi" ogohlantirishi: QQS + foyda yoki Uzum agenti rejimi davrda
  amalda bo'lsa (`upcore.tax.uncalculated_regimes`, `/pnl` → `untaxed_regimes`); Sozlamalardagi rejim yordam matni
  to'g'rilandi (avval "oylik taxmin sifatida hisoblanadi" deyilardi, aslida soliq 0).
- B4.64 Audit, 2-qism (faqat hujjat): `09-audit.md` §11 — S1–S3 o'lchovlari, Uzum kabinetidagi "Daromad" va "Foyda" formulasi (Foyda = Daromad − faqat komissiya; 1–11 noyabrda ≈ 3,5 barobar baland), soliq va xarajat nomlari; ADR-056 (postavka "keldi" = `dateAccepted`), ADR-057 (Q1, Q2, Q4–Q14); 08 §6 YATT soliq; 05 da B4.65–B4.76.
