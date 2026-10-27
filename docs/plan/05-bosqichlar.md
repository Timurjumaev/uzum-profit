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
- [x] B2.10 Staging server: O'zbekistondagi VPS (Q2), Docker Compose, Caddy (HTTPS), deploy workflow, tungi zaxira.
  ✓ 2026-10-25: staging ishlayapti — https://16-170-178-179.sslip.io (AWS eu-north-1, Ubuntu 26.04, Elastic IP;
  vaqtincha, ADR-029: Uztelecom Sandbox VM'iga tashqaridan kirib bo'lmadi). Uzum API shu serverdan javob beradi (401). `infra/compose/staging.yml` (postgres, migrate, api, worker `up_app` bilan, caddy), `infra/caddy/` (web
  build + Caddy: HTTPS, xavfsizlik sarlavhalari, CSP), `infra/staging/` (`bootstrap.sh` — Ubuntu 22.04/24.04, Docker,
  ufw, swap, `deploy` foydalanuvchisi, tungi zaxira taymeri; `gen-env.sh` — tasodifiy sirlar; `deploy.sh` — zaxira →
  migratsiya → konteynerlar → HTTPS orqali sog'liq → ishlamasa oldingi image), `infra/backup/` (`pg_dump` + tekshiruv
  + 14 kun; tiklash), `deploy-staging.yml` (GHCR, SSH, server kaliti oldindan ma'lum). Migratsiya roli —
  POSTGRES_USER (superuser), ilova — `up_app`. Kirish kodi IP bo'yicha soatiga 20 ta (`upapi.ratelimit`, Caddy
  `X-Forwarded-For` ni almashtiradi — soxtalashtirib bo'lmaydi). CI `staging` ishi: shu oqimning o'zi (strict staging
  tekshiruvlari, HTTPS, zaxira → tiklash, qayta deploy); skriptlar testi `infra/tests/` (qaytish, migratsiya xatosi).
- [x] B2.11 Real sinov: Temur staging'da o'z kalitini kiritadi → to'liq sinxron → legacy raqamlari bilan solishtirish;
  `PARTIALLY_CANCELLED`, `amountReturns`, qaytishlar semantikasi tasdiqlanadi va testga yoziladi. B2.6 dan
  tekshiriladigan taxminlar: postavka tarkibida `skuForInvoiceDtoList[].id` = SKU id, faktura `dateCreated` matn
  formati, `/v1/return` sahifalash (`dateFrom` qo'llanmaydi) va hajmi, logistika xarajati `externalId` = sotuv qatori id.
  Vositalar tayyor (2026-10-25): `scripts/staging_connect.py` (kirish va kalit, Mac'da), `python -m upapi.realcheck` /
  `infra/staging/realcheck.sh` (serverda hisobot), `scripts/compare_staging.py` (legacy bilan, Mac'da) — `docs/staging.md`
  "Real sinov". ✓ 2026-10-25 natija: ikkala do'kon to'liq tarix, legacy bilan har oy 0 so'm farq, to'rt taxmin
  tasdiqlandi (08 §4). Topildi va tuzatildi: Bekor qatorda `amount` = 0, dona `amountReturns` da — F17/F16 bekor
  donani yo'qotardi, F18 va ombor tezligi bekorni qaytish deb sanardi (02 F2, F17, F18; testlar). `PARTIALLY_CANCELLED`
  real ma'lumotda yo'q — taxmin qoladi. ✓ 2026-10-27 qayta tekshiruv (Temur, realcheck + compare): ikkala do'konda
  24 soatda xato ishlar 0, iyul–oktabr har oy 0 so'm farq, taxminlar ✓. 7 ta buyurtmada holat farqi (CANCELED ↔
  PROCESSING, TO_WITHDRAW emas) — sinxron vaqti farqi: staging holatni oxirgi 3 kun uchun tez-tez, 45 kun uchun kuniga
  bir marta qayta oladi (`docs/staging.md`).
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
dona legacy bilan 1 so'mgacha bir xil. ✓ 2026-10-27 — B2 yopildi.

## B3. Frontend poydevori va dizayn tizimi — 6–9 kun

- [x] B3.1 Vite + React + TS, TanStack Router/Query, openapi-fetch, xato chegaralari.
  ✓ 2026-10-25 (B2 ning 24 soatlik tekshiruvini kutish vaqtida, Temur roziligi bilan): `lib/api/client` (openapi-fetch,
  cookie, CSRF sarlavhasi, problem+json → `ApiError`), `app/query` (staleTime 60 s, 4xx qayta so'ralmaydi, 401 →
  `/login?redirect=`), `app/router` (lazy marshrutlar, kirish talab qiladigan `app` tartibi, ichki `redirect`),
  xato chegaralari (marshrut xatosi — so'rov ID va "Qayta urinish", 404, ildiz `AppErrorBoundary`); boshlang'ich JS
  ~103 KB gzip, CI'da byudjet (`pnpm --filter web size`, ≤ 250 KB).
- [x] B3.2 i18n (uz-Latn, uz-Cyrl transliteratsiya, ru), `lib/format` (04 §8.4) + testlar.
  ✓ 2026-10-25: `lib/i18n` (i18next; uz-Cyrl — uz-Latn'dan avtomatik `translit.ts` + so'z istisnolari va kalit
  tuzatishlari; ru qo'lda, kalitlar tip bilan majburiy; tanlov `localStorage` → brauzer tili; `<html lang>`;
  `useFormat()`; atamalar `terms` / `glossary.ts`; xato matni API `code` bo'yicha), `searchKey` (lotin/kirill va
  apostrof turlaridan qat'i nazar qidiruv), `lib/format` (U+00A0, vergul, U+2212, pul, valyuta, ixcham, foiz,
  o'zgarish, sana/kun/davr/hafta kuni Toshkent bo'yicha, nisbiy vaqt, rus ko'plik shakli; satr ustida ROUND_HALF_UP);
  eslint: `toLocaleString`/`Intl` faqat `lib/format` da. Profil tili (`user.language`) bilan bog'lash — B3.7 sozlamalar.
- [x] B3.3 Tokenlar (04 §4), Inter subset, yorug'/qorong'i rejim.
  ✓ 2026-10-25: `styles/tokens.ts` (yagona manba: ranglar 04 §4.2, grafik slotlari va rollari §4.3, tipografik
  shkala §2.1, oraliq, radius, breakpointlar) = `styles/tokens.css` (test); WCAG kontrasti testda (topildi va
  tuzatildi: `border-input` yorug' `#8B909C` → `#858A96`, 04 §4.4); Inter variable (wght + opsz) o'zimizda, 4 subset
  (lotin, lotin-ext, kirill, kirill-ext; ʻ ʼ U+00A0 U+202F − № qamrovi testda), lotin fayli preload; mavzu — tizim
  yoki qo'lda (`lib/theme`, `data-theme`, `localStorage`, `theme-color`, `public/theme-init.js` — CSP'ga mos,
  miltillamaydi). Mavzu tanlash tugmasi — B3.5 topbar.
- [x] B3.4 Komponentlar katalogi (04 §5) + `/ui-kit` sahifasi.
  ✓ 2026-10-25: `components/ui` — Button, TextInput/NumberInput/MoneyInput (`parseNumber`: "1 234,5", "1234.5",
  "1.234.567,50"), Select, Combobox (lotin/kirill, apostrofsiz qidiruv, klaviatura, ARIA), DateRangePicker (8 tayyor
  davr + kalendar, `lib/dates`), CompareToggle, KPI (rang = yo'nalish × yaxshimi, sparkline), FormulaPopover,
  LedgerTable (04 §6.1), DataTable (asos: tabular, qotgan birinchi ustun, jami), Badge/StatusPill (ikon + matn),
  Banner, Dialog/Drawer (fokus tuzog'i, Esc), Popover, Tooltip, Toast, Stepper, Timeline (04 §6.2), EmptyState,
  Skeleton (300 ms), ProgressBar, ProductThumb, FileDrop; `/ui-kit` (kirishsiz, mavzu va til tanlash). axe-core:
  jiddiy xato 0 (ochiq qatlamlar bilan ham, CI'da). DataTable ustun tanlash/eksport/virtual — B4.3; sahifa
  karkasi komponentlari (Sidebar, TopBar, CommandPalette, SyncIndicator) — B3.5; grafiklar — B3.6.
- [x] B3.5 Karkas: sidebar, topbar (do'kon, davr, solishtirish, SyncIndicator), mobil tab bar, Ctrl+K.
  ✓ 2026-10-25: `components/shell` — `AppShell` (`app` marshruti ostida; bitta `<main>`, "o'tkazib yuborish" havolasi),
  Sidebar (232/64 px, tanlov saqlanadi; 768–1023 px da har doim yig'ilgan), TopBar (do'kon — bir nechta, davr,
  solishtirish; hammasi URL'da: `app/filters` — `shop`, `from`, `to`, `cmp`, noto'g'ri qiymat jim tashlanadi,
  tanlanmagan davr = "Shu oy", bo'limdan bo'limga o'tganda saqlanadi), SyncIndicator (M3: uzilish / xato / eskirgan
  > 1 soat / hali yo'q / yangi — ikon + matn; bosilsa tur bo'yicha holat, "Hozir yangilash", "Ma'lumotlar holati";
  har daqiqa yangilanadi) va Uzum uzilishi sariq banneri, MobileTabBar (Asosiy · Foyda · Ombor · Xaridlar · Yana;
  "Yana" — qolgan bo'limlar, solishtirish, mavzu/til, chiqish), CommandPalette (Ctrl/⌘ + K, `searchKey`: lotin/kirill va
  apostrofsiz qidiruv, ↑ ↓ Enter Esc; manba — `PaletteItem`: hozir sahifalar va amallar (mavzu, til); SKU va xarid
  guruhlari B4.3/B4.6 da shu ro'yxatga qo'shiladi), foydalanuvchi menyusi (mavzu — B3.3 topbar tugmasi shu yerda, til,
  chiqish). Sahifalari yo'q bo'limlar (`/pnl`, `/products`, `/orders`, `/expenses`, `/purchases`, `/inventory`,
  `/cash`, `/reports`, `/settings`) "qurilmoqda" sahifasiga olib boradi. Testlar: `shell.test.tsx` (menyu, filtrlar,
  sinxron holatlari, Ctrl+K, chiqish, tab bar, axe: jiddiy xato 0), `filters.test.ts`, `sync.test.ts`; umumiy soxta API
  `src/test/api.ts` (App.test unga o'tkazildi). Boshlang'ich JS 146,8 KB gzip. Qoldi (B3.8): vizual skrinshotlar.
- [x] B3.6 Grafik komponentlari (ECharts temasi, tooltip, jadval ko'rinishi).
  ✓ 2026-10-26: `components/charts` — LineBarChart (ustun + chiziq, bitta o'q, annotatsiyalar), StackedBarChart,
  WaterfallChart (qo'shiluvchi slot 1, ayriluvchi slot 8, yakuniy — siyoh; nol chizig'idan o'tadi), HeatmapChart (hafta
  kuni × soat), CalendarHeatmap; Sparkline B3.4 da. Har birida: tooltip (hamma seriya qiymati asl satrdan, nomlar
  escape), "Grafik | Jadval" almashtirgich, legenda (≥ 2 seriya), `role="img"` + matnli tavsif (eng yuqori/past), bo'sh
  holat, yuklanmasa "Qayta urinish". 04 §5.1 qoidalari `options.ts` da (ustun ≤ 24 px, uchi 4 px, 2 px oraliq; chiziq
  2 px, marker ≥ 8 px; hairline to'r; ≤ 4 chiziqda to'g'ridan-to'g'ri yorliq). Ranglar — `styles/tokens.ts` dan
  (`palette.ts`); `prefers-reduced-motion` — animatsiyasiz. ECharts 6 (`echarts/core` + SVG renderer) alohida bo'lak
  (~84 KB gzip, birinchi grafikda yuklanadi); boshlang'ich JS 147,8 KB. Grafik hisoblamaydi: jami va qadam summalari
  API'dan (tamoyil 4); songa aylantirish faqat joylashuv uchun. Qarorlar: qorong'i rejimda ketma-ket shkala teskari
  (04 §4.3 ga yozildi), sinxron uzilgan kunlar — punktir ramkali maydon (ECharts markArea shtrixni qo'llamaydi),
  tor ekranda sharshara yorliqlari qiya. `/ui-kit` da "Grafiklar" bo'limi. Testlar: `options.test.ts` (sof quruvchilar),
  `charts.test.tsx` (ramka, hayot sikli, axe), `echarts.smoke.test.tsx` (haqiqiy ECharts jsdom'da, ogohlantirishsiz —
  ECharts 6 da `containLabel` va `api.style` eskirganini shu test ushladi).
- [x] B3.7 Kirish sahifalari, onboarding wizard (M2), "Ma'lumotlar holati" sahifasi.
  ✓ 2026-10-26: `features/auth` — `/login` (telefon → Telegram kodi; raqam har ko'rinishda — `lib/phone`; 6 raqamda o'zi
  yuboriladi; qayta yuborish 30 s; xato matni API `code` bo'yicha), `/invite?token=` (M1 taklifi), profil tili
  (`user.language`: qo'lda tanlangan til kirishda profilga yoziladi, tanlanmagan bo'lsa — profil tili qo'llanadi,
  menyudan almashsa profilga ham yoziladi). `features/onboarding` — `/onboarding` (karkassiz, chapda qadamlar / mobilda
  progress; holat serverdan: tashkilot → kalit → do'konlar → tarix, istalgan joyda to'xtab davom etish): tashkilot
  (nom, STIR), Uzum kaliti (parol maydoni; kalit URL'ga, matnga, holatga tushmaydi; egasidan boshqasiga o'chirilgan),
  do'konlar (tanlash, qisqa nom, 8 rang — 1-do'kon 1-rang), tarix yuklanishi (do'kon × tur bo'yicha progress, har 5 s;
  kutmasdan o'tish mumkin). `features/status` — "Ma'lumotlar holati" (M3): do'kon × tur jadvali, akkaunt va kvota.
  Tashkilotsiz foydalanuvchi `app` marshrutida onboarding'ga yo'naltiriladi. **Qoldi / o'zgardi:** M2 4–6-qadamlar (soliq,
  tannarx, Telegram) tegishli endpointlar bilan (B4.8, B5, B6); yo'riqnomada rasm yo'q (matn); "taxminiy qolgan vaqt" yo'q
  — API bermaydi. **Topilgan va tuzatilgan:** TanStack Router bola marshrutga ota marshrutning xom qidiruvini ham beradi
  — `useSearch` tekshirilmagan `redirect` qaytarardi (ochiq qayta yo'naltirish); endi qiymat ishlatilgan joyda qayta
  tekshiriladi (`app/search.ts`, testi bor). Testlar: `auth.test.tsx`, `onboarding.test.tsx`, `status.test.tsx` (hammasida
  axe: jiddiy xato 0), `phone.test.ts`; boshlang'ich JS 154 KB gzip.
- [x] B3.8 Playwright: e2e (kirish, onboarding), vizual skrinshotlar, axe.
  ✓ 2026-10-26: `apps/web/e2e` + `playwright.config.ts` (`pnpm --filter web e2e`; CI'da alohida `E2E va vizual` job'i).
  Production build brauzerda (`vite preview`), API — marshrut darajasida holatli soxta (`e2e/support/api.ts`: kirish,
  tashkilot, kalit, do'kon tahriri; vaqt qotirilgan Toshkent 2026-10-26 14:00) — backend va baza kerak emas, natija
  deterministik. Ikki o'lcham (1440 va 390 px). **E2E** (28): kirish (kod, xato, qaytish manzili, ochiq qayta
  yo'naltirish, til), to'liq onboarding (kirish → tashkilot → noto'g'ri/to'g'ri kalit → do'kon nomi va rangi → tarix
  → bosh sahifa; kalit URL'da yo'q; yuborilgan so'rovlar tanasi tekshiriladi), karkas (menyu, Ctrl+K, filtrlar URL'da,
  mavzu, chiqish, holat sahifasi). **axe — haqiqiy brauzerda, KONTRAST bilan** (jsdom'da o'lchanmaydi): 9 sahifa ×
  yorug'/qorong'i × desktop/mobil + ochiq qatlamlar — jiddiy xato 0 (topildi va tuzatildi: qidiruv tugmasining
  ko'rinadigan matni ("Ctrl K") nomiga kirmagan edi, WCAG 2.5.3). **Vizual**: 10 sahifa × yorug'/qorong'i × 2 o'lcham = 40
  skrinshot asosi `e2e/__screenshots__` da (3,5 MB; sozlama: farq ≤ 1% piksel, animatsiyasiz); yangilash —
  `pnpm --filter web e2e:update`, farqni ko'zdan kechirib commit. Haqiqiy backend bilan e2e (staging) — B8.
- T: `/ui-kit` va onboarding skrinshotlarini ko'rib fikr bildirish; Q1 — brend nomini tanlash.
  ✓ 2026-10-25 `/ui-kit` skrinshotlari (yorug'/qorong'i, 1440/390 px) Temur tomonidan ma'qullandi (B3.4 komponentlari
  o'zgarishsiz qoladi). ✓ 2026-10-26 onboarding va "Ma'lumotlar holati" skrinshotlari (1280/390 px, yorug'/qorong'i)
  Temur tomonidan ma'qullandi. ✓ 2026-10-26 Q1: brend nomi **SellerMax** (ADR-030); qoldi — tovar belgisi tekshiruvi (Temur).

**Chiqish:** UI-kit skrinshotlari (yorug'/qorong'i, 1440/390 px) Temur tomonidan ma'qullangan ✓ 2026-10-25; axe — jiddiy
xato 0 (B3.4 dan CI'da; B3.8 dan haqiqiy brauzerda, kontrast bilan, hamma asosiy sahifada). Onboarding skrinshotlari ma'qullangan ✓ 2026-10-26 (B3.7). **B3 yopildi** — Temurning Q1 tovar belgisi tekshiruvi B4 ni to'xtatmaydi (ADR-030).

## B4. Asosiy ekranlar — Temur yangi dasturga o'tadi — 10–15 kun

- [x] B4.1 Bosh sahifa (M4) — hisob varag'i, davr chizig'i, grafik, "Diqqat talab qiladi", TOP/zarar SKU.
  ✓ 2026-10-26: `features/home` — hisob varag'i (hero + qatorlar API tartibida: tushum → komissiya → logistika → = Uzum
  to'lovi → tannarx → Uzum xarajatlari toifa bo'yicha → o'z xarajatlari → soliq → tannarxsiz qism → = sof foyda;
  yalpi foyda P&L sahifasida; xarajat yo'q bo'lsa nol qator), har qatorda o'zgarish (xarajatda kattalik bo'yicha, rang =
  yo'nalish × yaxshimi) va FormulaPopover (F-raqam); drill-down drawer: sotuv qatorlari (`/sales?group=completed`),
  Uzum toifasi (`/expenses?category=`), o'z xarajatlari; hisoblanadigan qatorlar (soliq, sof foyda) — faqat formula.
  Davr chizig'i (prognoz — "Taxminiy"), kunlik grafik, "Diqqat talab qiladi", TOP/zarar SKU (mobilda tab),
  ko'rsatkichlar (marja yonida tannarxsiz qism, kutilayotgan foyda R'siz sababi bilan). Sotuv yo'q + sinxron muammoli —
  "sotuv yo'q" deyilmaydi (tamoyil 8). **Reja o'zgarishlari:** (1) API'ga `RowOut.change` qo'shildi (core `compare`) — tamoyil 4;
  (2) "O'tgan yil" solishtirish dashboard API'da yo'q — hozir oldingi davr bilan, banner aytadi (B5.6); (3) "Diqqat talab
  qiladi" da jarima, kechikayotgan kargo, Uzum to'lovi — B5 (ma'lumot yo'q); (4) bepul logistika soyasi — B4.2 (ADR-031);
  (5) drill-down'da Uzum toifasi xarajatlari `VIEW_SETTINGS` ruxsatini talab qiladi (API shunday) — ruxsat yo'q bo'lsa
  drawer'da xato matni. **Topildi va tuzatildi:** davr chizig'i `grid` ichida sahifani 655 px kengaytirardi (360 px'da
  gorizontal skroll). **Qoldi:** M4 tezlik mezoni (p95 < 700 ms) staging'da Temur ma'lumotida o'lchanadi; yetmasa —
  natija keshi yoki oylik agregat; standart muddatlar (F25) sozlamasi — B4.8.
- [x] B4.2 Foyda va zarar (M5) — drill-down, sharshara, oylar, kutilayotgan, qamrov banneri, F40;
  F9/F10 qatorlarida to'g'ridan-to'g'ri va taqsimlangan xarajatlar alohida (ADR-026).
  ✓ 2026-10-26: `features/pnl` — hisob varag'i to'liq (yalpi foyda bilan; tannarxsiz sotuvlar to'lovi yalpi foydadan
  oldin ayriladi — har oraliq summa zanjirga mos) va ustunlar: joriy, tushumga nisbatan, oldingi davr, farq, o'zgarish
  (< 640 px da joriy + o'zgarish); sharshara; kutilayotgan blok (F16, do'konlar bo'yicha); qamrov sariq banneri;
  drill-down (bosh sahifa `Drill`); kesimlar oylar / do'konlar / SKU (`?view=`), do'kon va SKU kesimida F9/F10
  to'g'ridan-to'g'ri va taqsimlangan, "Taqsimlanmagan" va "SKU bog'lanmagan" alohida. Bepul logistika kunlari
  (`upapi.reports.free`: ma'lumotdan, do'kon × kun ≥ 90%, + `free_logistics_periods`) — bosh sahifa grafigida soya
  (B4.1 qoldig'i), haqiqiy hisobga ta'sir qilmaydi. **Reja o'zgarishi (ADR-031, Temur tasdiqladi):** Uzum bonusi —
  vaqtinchalik ma'lumot; P&L'da "standart tarif bo'yicha foyda" (eski F40) qatori yo'q — avval qilingan, olib
  tashlandi; F40 endi me'yoriy (bonussiz) foyda/dona — B4.3. **Qoldi:** "toifa bo'yicha" kesim — B4.3; drill-down
  eksporti va Excel/PDF — B4.10 / M14 (B7); "o'tgan yil" — B5.6 (banner).
- [x] B4.2a Uzum bonuslari (ADR-031): `fee_waivers` migratsiyasi (`free_logistics_periods` o'rniga; do'kon yoki
  hammasi, sanalar, bepul turlar, sabab, manba), CRUD API (audit bilan), aniqlash takliflari (tasdiqlanmaguncha
  ta'sirsiz), sotuv qatorida `waiver_id` va UI'da "Bonus davri" belgisi, P&L banneri (sabab, turlar, sanalar) va
  vaqtincha shu yerda qo'shish shakli; grafik soyasi tasdiqlangan davrlardan.
  ✓ 2026-10-26: `upcore.waivers` (turlar — sotuv logistikasi + P&L'ga kiradigan Uzum toifalari, kodda sana yo'q;
  tekshiruv, `waiver_for`, takliflar), migratsiya 0008 (`fee_waivers`, RLS), `/fee-waivers` (o'qish — `view_finance`,
  o'zgartirish — `manage_settings`, audit: create/update/delete/dismiss), `/pnl` `waivers` + `waiver_suggestions`,
  `/dashboard` `waivers` (grafik soyasi), `/sales` `waiver_id`. UI: P&L'da bonus banneri (o'chirish), taklif —
  "Bonus deb belgilash" (shakl taklif bilan to'ladi, `source = detected`) yoki "Yo'q, bonus emas" (`dismissed` —
  qayta so'ralmaydi), "Uzum bonusini qo'shish" shakli (do'kon yoki hammasi, sanalar, turlar API'dan, sabab);
  drill-down'da "Bonus davri" belgisi. **Qarorlar:** taklifni har qanday yozuv (boshqa tur bo'lsa ham) qoplasa — shu
  kunlar qayta taklif qilinmaydi; tahrirlash UI'si — B4.8 (API'da PATCH bor). **T:** oktabr bonusini kiritish
  (P&L → taklif → "Bonus deb belgilash", sabab va turlar: sotuv logistikasi, saqlash).
- [x] B4.3 Mahsulotlar (M6) — jadval, SKU sahifasi, unit kalkulyator (F35/F36 me'yoriy tariflar bilan), me'yoriy
  (bonussiz) foyda/dona (F40, ADR-031), tovar ↔ SKU bog'lash; SKU xarajatlari
  "to'g'ridan-to'g'ri" va "taqsimlangan" ustunlarda, "Taqsimlanmagan" qatori alohida (ADR-026).
  ✓ 2026-10-26: `/skus` (xarajat ustunlari ikki qismda, me'yoriy foyda/dona, `label`/`abc` filtrlari, saralash kalitlari,
  `bonus`), `/skus/{id}`, `/unit-calc` (`upcore.unit`, F35/F36), `/items` va `PUT /skus/{id}/item` (audit, qayta hisob).
  F40: `upcore.waivers.normative_profit` — sotuv logistikasi (SKU'ning bonusdan tashqari oxirgi pullik tarifi, bo'lmasa
  do'konning odatiy tarifi, oxirgi 90 kun) va saqlash (`storage_price` × qoldiq-kunlar); boshqa tur baholanmaydi va
  ochiq aytiladi (`unestimated_kinds`), baho yo'q SKU'da "Baho yo'q". UI: jadval (qidiruv, filtrlar, saralash URL'da,
  ustun tanlash va ko'rinishlar — brauzerda, formula "?", virtual skroll), SKU sahifasi (KPI, tarix grafiklari, lotlar,
  qaytish sabablari, bog'lash, kalkulyator — boshlang'ich qiymatlar manbasi bilan). **Qoldi:** SKU izohlari (jadval
  kerak — keyingi migratsiya bilan); F37 (hajm bo'yicha tarif) — tovar o'lchamlarini tahrirlash (B4.6) bilan; "toifa
  bo'yicha" kesim va ABC bo'yicha Uzum `rankInfo` ustuni; saqlangan ko'rinishlar hozircha qurilma bo'yicha; vizual
  e2e asoslari; Uzum mahsulot havolasi formati (`uzum_product_url`) real sahifada tekshirilmagan (Temur bir marta
  ochib ko'radi); saqlash bonusining `storage_price` ma'nosi (dona/kun) real ma'lumotda tasdiqlanadi.
- [x] B4.4 Buyurtmalar (M7) — ro'yxat ("Bonus davri" belgisi bilan), bekor va qaytish tahlili.
  ✓ 2026-10-27: `/orders/analysis` (F17 va F18 ulushi, topshirilgandan keyin bekor — `issued_at`, kunlik trend, bekor va
  qaytish sabablari, SKU bo'yicha, qaytim saqlash xarajati — C000004, kompensatsiya ayirilgan; `upcore.metrics.late_cancel_share`).
  UI `/orders`: bo'limlar "Ro'yxat / Bekor bo'lish / Qaytarilish" va ro'yxat holati filtri URL'da; ro'yxat — mavjud
  `/sales` (kursor bilan sahifalanadi, "Bonus davri", "Taxminiy", tannarxsiz qator "—"). **Qoldi:** FBS faol buyurtmalar va
  muddatlar — B5; bekor ulushi trendi (foizli grafik) — grafik komponentiga "foiz" birligi qo'shilgach; eksport — B4.10.
- [x] B4.5 Xarajatlar (M8) — Uzum xarajatlari, o'z xarajatlarim (takroriy, amortizatsiya).
  ✓ 2026-10-27: `/expenses` — "Uzum xarajatlari" (toifalar F9, oylar trendi, eng katta jarimalar, ro'yxat toifa filtri bilan;
  P&L'ga kirmaganlari belgilanadi) va "O'z xarajatlarim" (F10: jami, toifalar, ro'yxat). API: `POST/PATCH/DELETE
  /own-expenses` (`manage_settings`, audit), `GET /own-expense-categories` (mavjud + tavsiya etilgan toifalar; yangi toifa
  nomi bilan yaratiladi). Bir martalik, davr (amortizatsiya — summa kunlarga teng) va takroriy (`repeat_months`: har oy
  uchun alohida bir kunlik yozuv, oy kuni qisqartiriladi). P&L jadvalni to'g'ridan-to'g'ri o'qiydi — qayta hisob kerak
  emas. **Qoldi:** cheksiz takrorlash va seriyani birga tahrirlash (ochiq muddatli ijara); toifani qayta nomlash/o'chirish;
  xarajatni tovar bo'yicha taqsimlash va tushum ulushi (02 M8) — B4.8 bilan; chek rasmi va Excel import — B7; eksport — B4.10.
- [ ] B4.6 Xaridlar (M9) — yangi model: xarid hayoti, qatorlar, komponentlar, kurs rejimlari, taqsimot,
  Partiya yo'li, kech kiritilgan xarajatda qayta hisob.
- [ ] B4.7 Ombor (M10 asos) — joylar, qoldiq, zaxira kunlari, holat, buyurtma sanasi.
- [ ] B4.8 Sozlamalar (M16) — soliq profili, tannarx usuli, to'lov jadvali, muddatlar, do'konlar, Uzum bonuslari
  (ADR-031: davrlar ro'yxati, qo'shish/tahrirlash, tizim takliflarini tasdiqlash).
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
