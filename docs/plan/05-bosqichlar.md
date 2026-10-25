# 05. Bosqichlar: hozirgi holatdan production'gacha

Qoidalar:
- Bosqichlar tartib bilan bajariladi. Keyingi bosqichga **chiqish mezoni** bajarilgandan keyingina o'tiladi.
- Har vazifa: kod + testlar + (UI bo'lsa) skrinshotlar + yordam matni + CI yashil + shu faylda belgi + CHANGELOG.
- **T:** bilan boshlangan qatorlar — Temurning vazifasi (faqat u qila oladi: akkaunt, to'lov, qaror, sinov).
- Hajm — diqqat bilan ishlangan ish kunlari, taxminiy. Kalendar muddat Temurning javob tezligiga bog'liq.

## Boshlang'ich nuqta (2026-10-23)

Legacy ilova (`uzum_profit/`, Python 3.8 stdlib, SQLite, lokal veb-server) Temurning Mac'ida ishlaydi:
- Uzum Open API'dan sotuvlar, xarajatlar, mahsulotlar, postavkalar ro'yxati; har do'kon uchun to'liq tarix
  (byDurii: 2465 sotuv 2026-07-14 dan, EL-ONE: 203 sotuv 2026-10-02 dan — Uzum API bergan hamma narsa).
- Bosqichma-bosqich partiyalar (CNY tovar + USD kargo + qo'shimchalar, "yangi tovar" qatorlari), CBU kurslari.
- Bosh sahifa (foyda, kutilayotgan foyda, bekorlar), SKU jadvali, Ombor (qoldiq, yo'ldagi partiyalar, buyurtma vaqti).
- `selfcheck` (real API tekshiruvi), 62 test (Python 3.8 va 3.13).
- Cheklovlar: bitta foydalanuvchi, lokal, Telegram yo'q, qaytarishlar va postavka tarkibi saqlanmaydi, qoldiq tarixi
  yo'q, ba'zi doimiylar `.env` da (03-arxitektura.md §16).

---

## B0. Poydevor — 1–2 kun

- [x] B0.1 Production rejasi yozildi va saqlandi (`docs/plan`, `CLAUDE.md`, Project hujjati, xotira).
- [x] B0.2 Monorepo skeleti: `packages/core`, `apps/api`, `apps/web`, `apps/bot`, `infra/` (legacy joyida qoladi).
- [x] B0.3 CI (`ci.yml`): ruff, mypy, pytest (core, api, legacy), web lint/typecheck/test/build.
- [x] B0.4 Kod tartibi: pre-commit, Conventional Commits, `CHANGELOG.md`, PR shabloni, versiyalarni qotirish.
- [x] B0.5 `infra/compose/dev.yml`: postgres + bo'sh api + bo'sh web, `make dev` bitta buyruq.
- [x] B0.6 Legacy siyosati README'da: faqat kritik tuzatishlar.
- T: rejani ko'rib chiqish (xohlasa), Q8 (tannarx usuli standarti) ni tasdiqlash. ✓ FIFO (ADR-025)

**Chiqish:** CI yashil; `docker compose up` bilan bo'sh API (`/health`) va bo'sh web sahifa ochiladi.

## B1. Domen yadrosi (`packages/core`) — 5–8 kun

- [x] B1.1 `money`, `fx`: Decimal, valyutalar, yaxlitlash, CBU kursi (dam olish kuni → oxirgi ish kuni).
- [x] B1.2 Metrikalar F3–F19, F35–F36 (02-funksiyalar.md) + misol testlari.
- [x] B1.3 Xarajat klassifikatori: kod normallashtirish (С/C, У/U/Y variantlari), lug'at (08-tadqiqot.md §4 kodlari), statuslar,
  `BALANCE_CORRECTION`, dublikatlar, reklama matnidan aniq summa.
- [x] B1.4 Xarid tannarxi F20: komponentlar, 5 taqsimot usuli, 3 kurs rejimi, yaxlitlash qoldig'i, taxminiy belgilar.
- [x] B1.5 Lot dvigateli F21–F22: FIFO va o'rtacha, qaytish, brak, "lot yetmadi", erta sotuv, qayta hisob.
- [x] B1.6 P&L F12–F16: hisobot qatorlari, kesimlar (davr, do'kon, SKU, oy), tannarx qamrovi, realizatsiya.
- [x] B1.7 Ombor F23–F34: tezlik (stockout kunlarisiz), zaxira, muddat, holat, tavsiya miqdor, ABC/XYZ, nelikvid,
  muzlagan pul, yo'qolgan tovar, kompensatsiya, kamomad, yo'qotilgan foyda.
- [x] B1.8 Tariflar va soliq: F37 (sana bo'yicha jadval), F40, F11 profillari, F38–F39.
- [x] B1.9 Legacy bilan solishtirish testi (Temurning ma'lumoti, lokal): har partiyaning birlik tannarxi legacy bilan
  bir xil; tushum, komissiya, logistika, xarajat toifalari bir xil; sotuv tannarxi va foydadagi farqlar
  (legacy kumulyativ o'rtacha → FIFO / harakatlanuvchi o'rtacha, tuzatilgan xatolar) sababi bilan hujjatlanadi.
- T: real `uzum_history.json` / `uzum.db` lokal testi natijasini ko'rish (men xulosa yuboraman).
  ✓ 2026-10-24: majburiy tekshiruvlar o'tdi, farqlar sababi bilan `docs/legacy-farqlari.md` da. Vosita: `scripts/compare_legacy.py` (faqat stdlib, Python 3.15 da tekshirilgan), farqlar ro'yxati — `docs/legacy-farqlari.md`.

**Chiqish:** core qamrovi ≥ 95%, mypy strict toza, hypothesis testlari yashil, legacy farqlari ro'yxati tayyor.
✓ 2026-10-24 bajarildi: qamrov 100%, mypy strict toza, hypothesis yashil (3.13 va 3.15), `docs/legacy-farqlari.md`.
Ochiq: F21 real ma'lumotda — partiyalarga SKU biriktirilgach (yoki B2.11).

## B2. Backend poydevori va staging — 8–12 kun

- [x] B2.1 FastAPI skeleti: sozlamalar, structlog, problem+json xatolar, sog'liq endpoint'i.
- [x] B2.2 DB sxemasi (03 §5) + Alembic + RLS + sintetik seed.
- [x] B2.3 Kirish: telefon + OTP — kod Telegram orqali (ADR-027: Telegram Gateway yoki o'z bot, narx va
  ishlashi tekshirilib tanlanadi; SMS zaxira keyin), sessiyalar, rollar, taklif, audit. Tanlandi: Telegram Gateway
  (ADR-028).
- [x] B2.4 Marketplace ulanishi: kalitni AES-GCM bilan saqlash, tekshirish, do'konlarni tanlash. Qo'shimcha: kalitni
  almashtirish va uzish, yaroqsiz kalit urinishlari cheklovi, kalit maxfiyligi testi (`test_token_secrecy.py`).
  Real Uzum bilan tekshiruv — B2.11 (staging).
- [x] B2.5 Uzum mijozi: xato turlari, tezlik navbati, kvota, xom JSON, yozib olingan javoblar bilan testlar.
  Haqiqiy kasseta Temurning Mac'ida yozildi (`scripts/record_uzum.py`, anonimlashtirilgan); topilmalar 08 §8 da.
- [x] B2.6 Sinxron ishlari (Procrastinate): to'liq tarix, inkremental, kunlik snapshot, postavka tarkibi, qaytarishlar,
  `sync_runs`, uzilish rejimi, "Ma'lumotlar holati" API. Qo'shimcha: chuqur (45 kun) sinxron, tarixni kursordan davom
  ettirish, "Hozir yangilash", kalit ulanganda tarix navbatga, ishchi (`python -m upapi.worker`, dev compose).
  Real Uzum bilan tekshiruv — B2.11.
- [x] B2.7 CBU kurslari ishi (kuniga 2 marta + arxiv). Toshkent 09:05 va 16:05 (`fx.cbu`), USD/CNY/RUB/EUR, arxiv
  eng eski kundan 730 kungacha orqaga (har ishda ≤ 30 kun); yozuv `fx_upsert()` orqali (`up_app` jadvalga yozmaydi).
  Real cbu.uz arxiv URL formati va dam olish kunlari javobi — B2.11 da tekshiriladi.
- [x] B2.8 Hisob ishlari: lotlar, `sale_costs`, `daily_sku_metrics` qayta qurish. `upapi.calc`: navbat
  `recalc_queue` (manba bilan bitta tranzaksiyada), `calc.org` (sinxrondan keyin) va `calc.nightly` (to'liq),
  faqat o'zgargan tovarlar va kunlar; "qayta hisoblandi" belgisi. Real ma'lumotda tekshiruv (qaytish va
  `amount` semantikasi) — B2.11. B4 ga: xarid va SKU → tovar tahrirlari `upapi.calc.request` ni chaqiradi.
- [x] B2.9 O'qish API'lari: dashboard, pnl, skus, sales, expenses, inventory (core ustida) + OpenAPI tiplari.
  `upapi.reports`: P&L kataklari `daily_sku_metrics` dan (`upcore.pnl.build_cells(totals=...)`, qatorlardan qurilgani
  bilan bir xil — test), bosh sahifa = P&L = SKU jadvali, ustunlar va drill-down yig'indilari testda; F16, "qayta
  hisoblandi", `meta.freshness`, kursor; ombor F23–F30 (omborchiga summasiz). `apps/api/openapi.json` →
  `apps/web/src/lib/api/schema.d.ts` (CI'da farq — xato). Tezlik (M4 maqsadi p95 < 700 ms): og'ir sintetik yil
  (50 000 qator, 3 000 reklama) — bosh sahifa ~0,8 s (sandbox), qolganlari ~0,6–0,7 s; B4.1 ga yozildi.
- [ ] B2.10 Staging server: O'zbekistondagi VPS (Q2), Docker Compose, Caddy (HTTPS), deploy workflow, tungi zaxira.
  **Kod tayyor (2026-10-25), server ishga tushirilishi qoldi** (Temur, `docs/staging.md`; VM — Uztelecom Cloud,
  ADR-029). `infra/compose/staging.yml` (postgres, migrate, api, worker `up_app` bilan, caddy), `infra/caddy/` (web
  build + Caddy: HTTPS, xavfsizlik sarlavhalari, CSP), `infra/staging/` (`bootstrap.sh` — Ubuntu 22.04/24.04, Docker,
  ufw, swap, `deploy` foydalanuvchisi, tungi zaxira taymeri; `gen-env.sh` — tasodifiy sirlar; `deploy.sh` — zaxira →
  migratsiya → konteynerlar → HTTPS orqali sog'liq → ishlamasa oldingi image), `infra/backup/` (`pg_dump` + tekshiruv
  + 14 kun; tiklash), `deploy-staging.yml` (GHCR, SSH, server kaliti oldindan ma'lum). Migratsiya roli —
  POSTGRES_USER (superuser), ilova — `up_app`. Kirish kodi IP bo'yicha soatiga 20 ta (`upapi.ratelimit`, Caddy
  `X-Forwarded-For` ni almashtiradi — soxtalashtirib bo'lmaydi). CI `staging` ishi: shu oqimning o'zi (strict staging
  tekshiruvlari, HTTPS, zaxira → tiklash, qayta deploy); skriptlar testi `infra/tests/` (qaytish, migratsiya xatosi).
- [ ] B2.11 Real sinov: Temur staging'da o'z kalitini kiritadi → to'liq sinxron → legacy raqamlari bilan solishtirish;
  `PARTIALLY_CANCELLED`, `amountReturns`, qaytishlar semantikasi tasdiqlanadi va testga yoziladi. B2.6 dan
  tekshiriladigan taxminlar: postavka tarkibida `skuForInvoiceDtoList[].id` = SKU id, faktura `dateCreated` matn
  formati, `/v1/return` sahifalash (`dateFrom` qo'llanmaydi) va hajmi, logistika xarajati `externalId` = sotuv qatori id.
- T: Q2 — provayder tanlash, akkaunt ochish va staging VPS uchun to'lash (taxminan 210–260 ming so'm/oy).
- T: GitHub Actions uchun SSH kirishini qo'shish (men qadam-baqadam yo'riqnoma beraman).
- T: @BotFather'da bot yaratish (admin ogohlantirishlari, keyin B6 xulosalari uchun) va tokenni staging sozlamasiga
  kiritish (yo'riqnoma beraman).
- T: gateway.telegram.org'da o'z raqami bilan akkaunt ochish va API tokenini staging sozlamasiga kiritish (o'z
  raqamiga kodlar bepul; balans production oldidan, ADR-028).
- T: staging'da Uzum kalitini o'zi kiritadi (kalit menga berilmaydi).

**Chiqish:** staging API `up_app` roli bilan ulanadi (migratsiya — alohida ega roli); superuser, `BYPASSRLS`, jadval
egasi yoki boshqa rol a'zosi bo'lgan rol bilan, yoki xavfli sozlama bilan (dev OTP siri/yuboruvchisi, HTTPS'siz
cookie) API ishga tushmaydi — xato beradi; deploy'da `python -m upapi.db.guard` yashil. Temurning 2 do'koni staging'da
to'liq sinxronlangan; 24 soat xatosiz; tushum, komissiya, logistika,
dona legacy bilan 1 so'mgacha bir xil.

## B3. Frontend poydevori va dizayn tizimi — 6–9 kun

- [ ] B3.1 Vite + React + TS, TanStack Router/Query, openapi-fetch, xato chegaralari.
- [ ] B3.2 i18n (uz-Latn, uz-Cyrl transliteratsiya, ru), `lib/format` (04 §8.4) + testlar.
- [ ] B3.3 Tokenlar (04 §4), Inter subset, yorug'/qorong'i rejim.
- [ ] B3.4 Komponentlar katalogi (04 §5) + `/ui-kit` sahifasi.
- [ ] B3.5 Karkas: sidebar, topbar (do'kon, davr, solishtirish, SyncIndicator), mobil tab bar, Ctrl+K.
- [ ] B3.6 Grafik komponentlari (ECharts temasi, tooltip, jadval ko'rinishi).
- [ ] B3.7 Kirish sahifalari, onboarding wizard (M2), "Ma'lumotlar holati" sahifasi.
- [ ] B3.8 Playwright: e2e (kirish, onboarding), vizual skrinshotlar, axe.
- T: `/ui-kit` va onboarding skrinshotlarini ko'rib fikr bildirish; Q1 — brend nomini tanlash.

**Chiqish:** UI-kit skrinshotlari (yorug'/qorong'i, 1440/390 px) Temur tomonidan ma'qullangan; axe — jiddiy xato 0.

## B4. Asosiy ekranlar — Temur yangi dasturga o'tadi — 10–15 kun

- [ ] B4.1 Bosh sahifa (M4) — hisob varag'i, davr chizig'i, grafik, "Diqqat talab qiladi", TOP/zarar SKU.
  B2.9 dan: M4 tezlik mezoni (p95 < 700 ms) staging'da o'lchanadi; yetmasa — tashkilot × davr bo'yicha natija keshi
  (hisob ishi tugaganda bekor qilinadi) yoki oylik agregat. Standart muddatlar (F25) sozlamasi — B4.8.
- [ ] B4.2 Foyda va zarar (M5) — drill-down, sharshara, oylar, kutilayotgan, qamrov banneri, F40;
  F9/F10 qatorlarida to'g'ridan-to'g'ri va taqsimlangan xarajatlar alohida (ADR-026).
- [ ] B4.3 Mahsulotlar (M6) — jadval, SKU sahifasi, unit kalkulyator, tovar ↔ SKU bog'lash; SKU xarajatlari
  "to'g'ridan-to'g'ri" va "taqsimlangan" ustunlarda, "Taqsimlanmagan" qatori alohida (ADR-026).
- [ ] B4.4 Buyurtmalar (M7) — ro'yxat, bekor va qaytish tahlili.
- [ ] B4.5 Xarajatlar (M8) — Uzum xarajatlari, o'z xarajatlarim (takroriy, amortizatsiya).
- [ ] B4.6 Xaridlar (M9) — yangi model: xarid hayoti, qatorlar, komponentlar, kurs rejimlari, taqsimot,
  Partiya yo'li, kech kiritilgan xarajatda qayta hisob.
- [ ] B4.7 Ombor (M10 asos) — joylar, qoldiq, zaxira kunlari, holat, buyurtma sanasi.
- [ ] B4.8 Sozlamalar (M16) — soliq profili, tannarx usuli, to'lov jadvali, muddatlar, do'konlar.
- [ ] B4.9 Legacy import: `uzum.db` yuklash → xaridlar; solishtirma hisobot.
- [ ] B4.10 Excel eksport har jadvalda.
- [ ] B4.11 Yordam: har ko'rsatkichda FormulaPopover, asosiy sahifalar uchun qisqa yordam matnlari.
- T: legacy `uzum.db` ni yuklash; 14 kun faqat yangi dasturda ishlash; topilgan har noqulaylikni yozib yuborish.

**Chiqish:** Temur 14 kun faqat yangi dasturdan foydalangan; kritik xato yo'q; legacy `legacy/` papkaga ko'chirildi.

## B5. Ustunlik funksiyalari — 12–18 kun

- [ ] B5.1 Yetkazib beruvchilar va kargo kompaniyalari; muddatlarni o'rganish (F25).
- [ ] B5.2 Buyurtma rejasi (F23–F27): tavsiya miqdor, CNY va so'm byudjeti, rejadan xarid yaratish.
- [ ] B5.3 FBO yuborish rejasi + Excel; postavkalar: e'lon va qabul, kamomad (F33), bog'liq jarima.
- [ ] B5.4 Yo'qolgan tovar (F31) + kompensatsiya (F32); nelikvid (F30); muzlagan pul (F29); yo'qotilgan foyda (F34).
- [ ] B5.5 Reklama tahlili (DRR, ACOS, SKU bo'yicha), ABC/XYZ, hafta kuni × soat issiqlik xaritasi.
- [ ] B5.6 Davrlarni solishtirish barcha hisobotlarda.
- [ ] B5.7 Pul oqimi (M11): hisoblar, tranzaksiyalar, Uzum to'lov prognozi (F38), 90 kunlik kalendar (F39).
- [ ] B5.8 Reja-fakt (M12).
- [ ] B5.9 Kalkulyator (M13) + ochiq versiya komponenti (landing uchun).
- [ ] B5.10 FBS (do'konda bo'lsa): faol buyurtmalar va muddatlar.
- T: yetkazib beruvchi va kargo ma'lumotlarini kiritish; har funksiyani real ma'lumotda sinab ko'rish.

**Chiqish:** har funksiya Temurning real ma'lumotida tekshirilgan, yordam maqolasi yozilgan.

## B6. Bildirishnomalar va Telegram — 5–7 kun

- [ ] B6.1 Hodisalar katalogi (M15), qoidalar, chegaralar, tinch soatlar, dublikatsiz yuborish.
- [ ] B6.2 Telegram bot (aiogram): bog'lash, kunlik/haftalik xulosa, buyruqlar, "Batafsil" havolalar.
- [ ] B6.3 Ilova ichidagi bildirishnomalar markazi; web push (PWA).
- T: botni Telegram'da sinash, kunlik xulosa vaqtini tanlash (bot B2 da yaratilgan).

**Chiqish:** Temur 7 kun kunlik xulosa oladi, raqamlar ilova bilan bir xil, keraksiz xabar yo'q.

## B7. Import va hisobotlar — 4–6 kun

- [ ] B7.1 Excel import: tannarx, xaridlar, o'z xarajatlari, eski Uzum hisobotlari (API bermagan davr uchun).
- [ ] B7.2 Oylik PDF hisobot, buxgalter paketi, rejalashtirilgan yuborish.
- [ ] B7.3 To'liq eksport (ZIP).
- T: mart–aprel (API bermagan davr) uchun Uzum kabinetidan hisobot faylini yuborish.

**Chiqish:** Temurning eski hisoboti import qilinib, "Hammasi" davri do'kon ochilgan oydan boshlanadi.

## B8. SaaS tayyorgarlik — 10–15 kun

- [ ] B8.1 Tariflar, limitlar, 14 kunlik sinov, obuna holatlari (faol → qarzdor → faqat o'qish).
- [ ] B8.2 To'lov (Q5): karta tokeni bilan takroriy to'lov, fiskal chek (MXIK), hisob-faktura, muvaffaqiyatsiz
  to'lovda 3 urinish + 7 kun muhlat.
- [ ] B8.3 Admin panel (M17).
- [ ] B8.4 Xavfsizlik: ASVS L2 ro'yxati, tashkilot ajratish testlari, yuklama testi (200 tashkilot), zaxiradan
  tiklash mashqi.
- [ ] B8.5 Monitoring: GlitchTip, Uptime Kuma, admin Telegram ogohlantirishlari, status sahifa, runbook'lar.
- [ ] B8.6 Huquqiy (06 §6): oferta, maxfiylik siyosati, rozilik oqimi, shaxsiy ma'lumotlar bazasini ro'yxatdan
  o'tkazish, Uzum API shartlarini tekshirish, MXIK kodi.
- [ ] B8.7 Landing (uz/ru): taklif, narxlar, ochiq kalkulyator, yordam markazi, "Yangiliklar".
- [ ] B8.8 Production server, domen (Q7), pochta, Telegram kanal va yordam chati.
- T: Q4 yuridik shaxs (buxgalter maslahati), Q5 to'lov provayderi bilan shartnoma, Q6 narxlarni tasdiqlash,
  Q7 domen, production VPS to'lovi, shaxsiy ma'lumotlar bazasi arizasi.

**Chiqish:** 06-operatsiyalar.md chiqish ro'yxati 100%; begona odam ro'yxatdan o'tib, do'konini ulab, to'lab,
ishlata oladi (sinov bilan tekshirilgan).

## B9. Yopiq beta — 3–4 hafta (kalendar)

- [ ] B9.1 5–10 sotuvchi (T: topadi; 3 oy bepul, haftalik fikr evaziga).
- [ ] B9.2 Har biriga onboarding qo'ng'irog'i (T yoki men tayyorlagan video), haftalik fikr so'rovi.
- [ ] B9.3 Xatolar SLA: kritik — 24 soat, oddiy — 1 hafta.
- [ ] B9.4 O'lchov: aktivatsiya (48 soatda kalit + TOP-20 tannarx), haftalik faollik, birinchi foyda vaqti.

**Chiqish:** aktivatsiya ≥ 60%; kritik xato 0; kamida 3 sotuvchi pullik tarifga o'tishga tayyor.

## B10. Ommaviy chiqish va o'sish — davomiy

- [ ] B10.1 Chiqish: landing, Telegram kanal, sotuvchilar guruhlari, YouTube videolar (T), referral dasturi.
- [ ] B10.2 AI yordamchi (M19) + MCP server (Pro).
- [ ] B10.3 Yandex Market (O'zbekiston), keyin Wildberries/Ozon (M20).
- [ ] B10.4 Narx boshqaruvi va FBS operatsiyalari (M21).
- [ ] B10.5 Telegram Mini App (bosh sahifa Telegram ichida).
- [ ] B10.6 Mobil ilova (PWA yetarli bo'lmasa).

## Parallel yo'l: mijoz suhbatlari (B1 dan B8 gacha)

- [ ] T: B8 gacha 10 ta sotuvchi bilan 20 daqiqalik suhbat (savollar 06-operatsiyalar.md §9).
- [ ] Natijalar `docs/plan/suhbatlar.md` ga yoziladi; B5 ustuvorliklari va B8 narxlari shunga qarab tasdiqlanadi.

## Umumiy hajm

Ishlab chiqish ≈ 60–90 ish kuni + beta 3–4 hafta. Haftasiga 5 kun ish bo'lsa, ommaviy chiqishgacha taxminan
4–5 oy. Eng katta xavf — qaror va akkauntlarni kutish (Q2, Q4, Q5): ular oldindan hal qilinsa muddat qisqaradi.
