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
