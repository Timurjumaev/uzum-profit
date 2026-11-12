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
- [x] B4.6 Xaridlar (M9) — yangi model: xarid hayoti, qatorlar, komponentlar, kurs rejimlari, taqsimot,
  Partiya yo'li, kech kiritilgan xarajatda qayta hisob.
  ✓ 2026-10-30: `/purchases` CRUD (bosqich sanalari tartib bilan, joriy bosqich — sanasi bor eng oxirgisi), qatorlar
  (mavjud tovar yoki "yangi tovar": nom, havola, rasm; variant; buyurtma/qabul donasi, kamomad; narx valyutada; vazn,
  hajm), komponentlar (9 tur; CBU — to'lov sanasi, qo'lda, kartadan yechilgan summa; dona/vazn/hajm/qiymat/qo'lda
  ulush; tegishli qatorlar), "qayta buyurtma" (nusxa — sanalar, qabul va komponentlarsiz), minimal yetkazib beruvchi va
  kargo (nomi bilan). Birlik tannarx (F20) javobda jonli — lotlarni quradigan yo'l bilan bir xil (`calc.lots.evaluate`),
  kurs o'zgarsa darhol. Partiya yo'li — `upcore.purchasing.timeline` (kutilgan sana — tashkilot tarixidagi F25 bosqich
  medianasi; tarix yo'q bo'lsa yo'q). Kech kiritilgan xarajat: so'rov yozuv bilan bir tranzaksiyada, `calc.org` commitdan
  keyin navbatga (avval faqat sinxron yoki tungi ish olardi) → o'tgan sotuvlar tannarxi va P&L "qayta hisoblandi".
  Omborchi — summasiz (narx va komponentlar 403). **Qarorlar:** komponentda alohida tanlangan qatorni o'chirib bo'lmaydi
  (409 — sotuvchi kiritgani jim o'zgarmaydi); bosqich sanalari tartibi API'da tekshiriladi. **Qoldi:** qabulda brak/kamomadni
  hisobdan chiqarish yoki da'vo (`stock_moves`) — B4.7 bilan; yetkazib beruvchi va kargo kartochkasi, muddatlarni
  o'rganish — B5.1; standart muddatlar (F25) sozlamasi — B4.8; tovar o'lchamlari va F37 — keyinga; "yangi tovar"ni SKU'ga
  bog'lash (qator `item_id` ni tahrirlash bor, tovar yaratish — SKU sahifasida); Excel import — B7; vizual e2e asoslari.
- [x] B4.7 Ombor (M10 asos) — joylar, qoldiq, zaxira kunlari, holat, buyurtma sanasi.
  ✓ 2026-10-31: `/inventory` sahifasi — KPI (muzlagan pul, yo'ldagi tovar, o'z omborim, o'rtacha sotilish muddati),
  holat guruhlari (F26) va qidiruv URL'da, jadval: Uzumda (FBO/FBS), boshqa joylar (Xitoyda / yo'lda / omborimda /
  brak), tezlik (F23), zaxira kunlari (F24), buyurtma sanasi va tavsiya miqdor + byudjet (F27), qiymat; har ustunda
  formula; "Xarid yaratish" (tavsiya miqdorli qoralama xarid); omborchi summasiz. Joylar xarid bosqichidan hisoblanadi;
  o'z omborim — qabul qilingan, Uzumga yuborilmagan xaridlar (+ tuzatish − hisobdan chiqarish) — F27 va F29 ga
  kiradi. B4.6 qoldig'i: `stock_moves` — hisobdan chiqarish (brak, yo'qotish, kamomad) va inventarizatsiya
  tuzatishi (API + oyna, o'chirib qaytarish), tannarxda lotdan chiqim va qayta hisob. **Qarorlar:** o'z omborim
  qoldig'i xarid bosqichidan olinadi — "Uzumga yuborildi" sanasi qo'yilmagan eski xarid o'z omborimda turib qoladi
  (muzlagan pulni oshiradi, tavsiyani kamaytiradi): sanani qo'yish yoki tuzatish yozuvi kerak; hisobdan chiqarish
  faqat o'z omborim hisobiga ta'sir qiladi (Uzum qoldig'i Uzumdan). **Qoldi:** FBO yuborish rejasi va Excel,
  postavkalar, yo'qolgan tovar (F31–F34), nelikvid va muzlagan pul bo'limlari, qoldiq tarixi grafigi — B5; standart
  muddatlar (F25) sozlamasi — B4.8; Excel eksport — B4.10; vizual e2e asoslari.
- [x] B4.8 Sozlamalar (M16) — soliq profili, tannarx usuli, to'lov jadvali, muddatlar, do'konlar, Uzum bonuslari
  (ADR-031: davrlar ro'yxati, qo'shish/tahrirlash, tizim takliflarini tasdiqlash).
  ✓ 2026-10-31: `/settings` sahifasi, bo'limlar ketma-ket: **tannarx usuli** (FIFO / o'rtacha; almashsa tasdiq so'raladi va
  hamma sotuv tannarxi navbat orqali qayta hisoblanadi), **soliq profili** (F11: sana bo'yicha ro'yxat, qo'shish /
  tahrirlash / o'chirish; rejimga mos maydonlar — aylanma stavka va baza, QQS + foyda, agent, yo'q; ma'lumotnoma
  stavkasi tavsiya), **Uzum to'lov jadvali** (F38: har do'kon uchun sana bo'yicha, oy kunlari va yechish foizi
  ko'rsatiladi), **muddatlar va qamrov** (F25 standart yetkazish muddati — tarix yo'q bosqich uchun; ABC qamrov kunlari
  F27), **do'konlar** (nom, rang, hisobga olish — faqat egasi), **Uzum bonuslari** (to'liq ro'yxat, qo'shish, tahrirlash
  — `WaiverForm` P&L bilan umumiy, rad etilgan belgisi, o'chirish tasdiq bilan). API: `GET /settings`, `PUT
  /settings/cost-method`, `PUT /settings/inventory`, `POST/PATCH/DELETE /tax-profiles`, `POST/DELETE /payout-schedules`;
  migratsiya 0009 (`orgs.settings` JSONB — muddat va qamrov bazada, tamoyil 2); o'qish `view_settings`, yozish
  `manage_settings`, audit. Standart muddatlar B4.6/B4.7 qoldig'ini yopdi: tarix yo'q tovarda ham holat (F26), buyurtma
  sanasi va tavsiya (F27) chiqadi, xarid sahifasida kutilgan sana (F25) ham shundan. **Qarorlar:** soliq profili va
  to'lov jadvali sana bo'yicha — eski davr hisobi o'zgarmaydi, bir sanada bitta qator (409); muddat sozlamasi yoki
  hamma 5 bosqich, yoki hech biri (qisman — taxmin); to'lov jadvali shartlari (oy kunlari, yechish foizi) hozircha
  ma'lumotnoma (`upcore.cash` seed) dan, har do'kon uchun faqat jadval turi tanlanadi. **Qoldi:** tashkilot nomi/INN/til
  tahriri, valyuta va kurs manbasi, ogohlantirish chegaralari, Telegram, to'liq eksport, tashkilotni o'chirish (30 kun)
  — keyingi bosqichlar (B5–B8); to'lov jadvali shartlarini tahrirlash — B5 (Pul oqimi); vizual e2e asoslari.
- [x] ~~B4.9 Legacy import: `uzum.db` yuklash → xaridlar; solishtirma hisobot.~~ Bekor (ADR-032, 2026-10-31): Temur
  2 ta legacy partiyani Xaridlar sahifasida qo'lda kiritadi. (ADR-033 dan: shart emas — boshlang'ich holat.)
- [x] B4.10 Excel eksport: server tomonda `openpyxl` (`GET /orgs/{id}/exports/{sales,skus,expenses,purchases,inventory}.xlsx`),
  tugma — Buyurtmalar, Mahsulotlar, Xarajatlar (Uzum va o'z), Xaridlar, Ombor. Eksport ro'yxat endpoint'ining o'zini
  sahifalab chaqiradi (filtr, tartib, rol bo'yicha yashirish ro'yxat bilan bir xil); ruxsat `export` / `export_inventory`
  (omborchi faqat ombor va xaridlar, summasiz). Formatlangan fayl: nom va davr, qotirilgan sarlavha, avtofiltr, so'm
  `#,##0`, foiz, sana; `SUM` jami; `=`/`+`/`-`/`@` bilan boshlanadigan matn formulaga aylanmaydi. **Qoldi:** drill-down
  va P&L eksporti, oylik PDF, buxgalter paketi va to'liq eksport (ZIP) — M14 / B7; xaridlar eksporti hozircha guruh
  tabi filtrisiz (hamma xarid).
- [x] B4.11 Yordam: `PageHelp` — 8 asosiy sahifada (Asosiy, Foyda, Mahsulotlar, Buyurtmalar, Xarajatlar, Xaridlar, Ombor,
  Sozlamalar) sarlavha yonidagi "?" (3 qisqa satr, ≤ 75 belgi; uz-Latn/uz-Cyrl/ru). FormulaPopover yetishmagan
  ko'rsatkichlarga qo'shildi: Buyurtmalar qatorlari (F4–F8), qaytim saqlash (F9), Ombor (tavsiya miqdor F27, qiymat va
  yo'ldagi F29). Testlar: PageHelp (ochilish, Esc, matnlar to'liqligi va uzunligi), Buyurtmalar sahifasi. **Qoldi:** yordam
  maqolalari, videolar, "Yangiliklar" sahifasi — M18 / B8.
- [x] B4.12 Boshlang'ich holat (ADR-033, F41): eski partiyalarsiz boshlash — boshlash sanasi, tovar tarixiy tannarxi
  (sana bo'yicha davrlar API'da), boshlash kunidagi qoldiq; dvigatelda tarixiy sotuv lotga tegmaydi, boshlang'ich qoldiq —
  birinchi lot. ✓ 2026-11-01: `upcore.costing` (`Opening`, `PricePoint`, `historical` belgisi, `superseded`), migratsiya
  0010 (`orgs.cost_start_on`, `item_costs`, `opening_stock`, RLS), `upapi.calc.costs` (tovar bo'yicha boshlang'ich holat),
  `GET/PUT /opening` (tovarlar va tovarsiz SKU'lar 90 kun tushumi bo'yicha, Uzum qoldig'i taklifi — joriy yoki oldingi kun
  snapshoti, oxirgi partiya narxi ishorasi, qamrov; tovarsiz SKU'ga narx yozilsa tovar yaratiladi va bog'lanadi; audit;
  sana o'zgarsa hamma tovar qayta hisoblanadi), ombor qiymatida boshlang'ich narx (partiya yo'q bo'lsa), unit
  kalkulyator tannarxi — oxirgi partiya. Web: `/opening` sahifasi (Sozlamalar → Tannarx usulidan havola), qidiruv, 50 tadan
  ko'rsatish, 360 px. **Qoldi:** narx davrlarini sahifada tahrirlash (API bor; sahifa ko'rsatadi), CNY + kurs bilan kiritish,
  o'tgan sana uchun snapshot yo'q bo'lsa qoldiqni sotuv va postavkalardan taxminlash, "dastur qoldig'i ↔ Uzum qoldig'i"
  mosligi tekshiruvi (B5.3/B5.4 bilan), onboarding'dagi 5-qadamga ulash (M2), Excel shablon (B7.1), vizual e2e asosi.
  ✓ 2026-11-01 tuzatish (Temur topdi): sahifa do'kon filtriga bo'ysunadi (`?shop=`, umumiy tovar belgisi); yuqori panel
  har sahifada faqat o'sha sahifa ishlatadigan filtrlarni ko'rsatadi (`pageFilters`; Xaridlar, Sozlamalar, holat —
  "Butun tashkilot bo'yicha").
  ✓ 2026-11-01 (Temur taklifi): Uzum kabinetidagi SKU jadvali kabi — har mahsulot karta va jadval, "Tannarx" sarlavhasidagi
  tugma bilan "Barcha turlar uchun qo'llash", keyin istalgan turini alohida o'zgartirish mumkin.
  ✓ 2026-11-01 soddalashtirish (Temur bilan): jadvalda Tur va Tannarx; Uzum qoldig'i avtomatik (matn), o'z omborim —
  belgi bilan; qamrov — boshlash sanasigacha bo'lgan tushum bo'yicha (90 kunlik doimiy oyna olib tashlandi).
- [x] B4.13 Tovar joylari — real ma'lumot (ADR-034, 1-qadam): `realcheck` ga "qoldiq joylari" bo'limi — SKU `quantity*`
  maydonlari (yig'indi, nol bo'lmagan, SKU va mahsulot holati bo'yicha, hujjatda yo'q maydonlar, `quantityAvailableByStockType`
  ko'rinishi, maydonlar munosabatlari), postavka holatlari (e'lon qilingan / qabul qilingan), qaytarish turi × holati, oxirgi
  60 kun sotuv holatlari; faqat yig'indilar. ✓ 2026-11-01 vosita tayyor. **T:** merge'dan keyin staging'da `realcheck.sh` ni
  ishga tushirib natijani yuborish — maydonlar ma'nosi 08 §4 ga yoziladi.
- [x] B4.14 Tovar joylari — FBO (ADR-034, 2-qadam): "postavkada" — qabul qilinmagan postavkalar (yopiq holat: qabul
  qilingan, bekor) SKU bo'yicha; o'z omborimdan ayiriladi (ikki marta sanalmaydi), F27 da yo'ldagi tovarga qo'shiladi,
  F29 qiymatida alohida joy; Ombor sahifasi va Excel'da "Postavkada"; boshlang'ich holat qoldig'i = sotuvda + FBS + brak +
  kutilayotgan + fotostudiya + postavkada (sahifada "shundan postavkada N"). ✓ 2026-11-01. **Qoldi:** "Uzumga qaytmoqda"
  (API son bermaydi — faqat taxmin, keyin), Uzum qaytarishlari (`ASSEMBLED` — olib ketish kutilmoqda; `UTILIZED` —
  hisobdan chiqim), o'z omborimni xarid bosqichi o'rniga postavkalar bo'yicha hisoblash (boshlash sanasidan keyin; bo'lib
  jo'natish) — B5.3 postavkalar bilan.
- [x] B4.15 Uzum bonuslari funksiyasini olib tashlash (ADR-035, ADR-031 almashtirildi): API nima bersa, shu — logistika
  0 kelsa 0, sababi so'ralmaydi. ✓ 2026-11-01: `upcore.waivers`, `/fee-waivers`, P&L taklif va banneri, Sozlamalar →
  Uzum bonuslari, "Bonus davri" belgisi, grafik soyasi, "Me'yoriy foyda/dona" ustuni (jadval, SKU sahifasi, Excel)
  olib tashlandi; migratsiya 0011 (`fee_waivers` o'chiriladi). F40 — kalkulyator uchun standart logistika (oxirgi
  pullik tarif, bo'lmasa do'konning odatiy tarifi), bonus davrlarisiz. B4.2a ning **T** (oktabr bonusini kiritish) bekor.
- [x] B4.16 Jarayondagi sotuvlar hisobga kiradi (ADR-036, ADR-017 ning "foyda = faqat Yakunlangan" qismi almashtirildi):
  F3–F8, F12–F15 = Yakunlangan + Jarayonda, Uzum hozirgi qiymatlari bilan; holat o'zgarsa qayta hisob. ✓ 2026-11-02:
  `upcore.metrics.counted`, `SaleTotals`/`Statement` da Jarayondagi qism, F16 → `PendingSales` (R — fakt), migratsiya 0012
  (`daily_sku_metrics.units_processing`, `revenue_processing` + to'liq qayta qurish so'rovi), F17/F18/R — Yakunlangan =
  `units − units_processing`; `/sales?counted=true` (P&L drill-down), `/dashboard` davrlar va kunlarda Jarayondagi qism,
  oldingi davrda sotuv bo'lmasa o'zgarish foizi yo'q. UI: "shundan jarayonda" (bosh sahifa sarlavhasi, davr
  kartochkalari, P&L), grafikda ikki qatlam, "Jarayondagi sotuvlar" bloki va ko'rsatkichi, drill-down'da "Jarayonda"
  belgisi. F23 sotuv tezligi ham Jarayondagi sotuvlarni oladi (oxirgi 14 kun endi bo'sh emas).
- [x] B4.17 Boshlang'ich holat: faqat tannarx kerak bo'ladigan tovarlar (Temur, 2026-11-02). ✓ 2026-11-02: `/opening`
  jadvalida biror marta sotilgan (Yakunlangan yoki Jarayonda) yoki hozir qoldig'i / postavkasi bor SKU'lar, yoki saqlangan
  narx, qoldiq yoki partiyasi bor tovarlar; qolganlari (arxivlangan, bloklangan, hech qachon tovar kelmagan kartochkalar)
  ko'rsatilmaydi — soni (`hidden`) sahifada yoziladi.
- [x] B4.18 Foyda uch raqamda: naqd + kutilayotgan = jami (ADR-037, Temur, 2026-11-02) — Asosiy va Foyda sahifalari
  vazifasi ajratildi. ✓ 2026-11-02: `upcore.pnl` — har katakda Jarayondagi qism (`Cell.processing`): o'z sotuvlari,
  katak xarajatlarining (F9, F10) tushum ulushidagi qismi, o'z soliq summasi (F11) va F15; `Statement.processing`,
  `net_profit_done` / `net_profit_processing`, `compare()` da har qatorda `done` / `processing`; F5 — Uzum hali yozmagan
  Jarayondagi logistika (topshirilmagan, 0) F40 tarifi × dona bilan taxminiy (`logistics_due`, `with_expected_logistics`,
  hisobot kunidagi tarif), "taxminiy" sifatida sanaladi; F16 eski bloki (`PendingSales`) o'rniga kutilayotgan qism.
  Migratsiya 0013 (`daily_sku_metrics` ga Jarayondagi qismning hamma pul ustunlari va taxmin asosi donalari + to'liq
  qayta qurish so'rovi), `calc.daily` — `issued_at`. API: `StatementOut` (naqd/kutilayotgan sof foyda, taxminiy
  logistika), `RowOut.done/processing`, `/dashboard` `expected` (R — tanlangan do'konlar birga), davrlar va kunlarda
  qismlar, `/pnl` `expected` / `expected_shops`, `/sales` `logistics_estimated` (drill-down va Excel'da ham). Web: Asosiy —
  uch kartochka (naqd + kutilayotgan = jami, izoh va formulalar, "Qanday hisoblandi" → Foyda), davr plitkalarida
  "naqd · kutilayotgan", kunlik grafik — sof foyda qatlamlari / tushum almashtirgichi, "Jarayondagi sotuvlar" KPI
  olib tashlandi; hisob varag'i Asosiydan olib tashlandi. Foyda — hisob varag'i ustunlari naqd / kutilayotgan / jami +
  solishtirish, "≈" taxminiy logistika va izohi, tor ekranda ustun almashtirgichi (`Segmented`, UI-kit'da), kutilayotgan
  sof foyda bloki (do'konlar bilan), kesimlarda "shundan naqd / kutilayotgan", drill-down va Buyurtmalarda logistika
  "Taxminiy" belgisi. PageHelp matnlari yangilandi; `realcheck` ga "processing_logistics" bo'limi (Jarayondagi qatorlar: `dateIssued` ×
  logistika 0 / > 0). ✓ 2026-11-02 realcheck (Temur): `dateIssued` ishonchli, qoida tasdiqlandi — bonus olib ketilgan kunga qarab, olib
  ketilgan va 0 — haqiqiy 0, olib ketilmagan va 0 — taxmin. **Qoldi:** kutilayotgan foyda "qachon pulga aylanadi"
  (to'lov sanasi bo'yicha) — B5.7 Pul oqimi bilan.
- [x] B4.19 Tannarxsiz sotuvlar tuzatishi (Temur, 2026-11-02: byDurii — "Narx yozilgan 166 / 169", "4 ta sotuv tannarxsiz").
  ✓ 2026-11-02: F41/F21 — narx bor, qoldiq 0 va partiya yo'q tovarning sotuvi tarixiy narxda ("lot yetmadi", taxminiy);
  `store.link_sales` — sotuv → SKU bir ma'noli bo'lsa nom (harf/bo'sh joysiz), mahsulot ichida nom yoki mahsulotning
  yagona SKU'si bo'yicha; `/opening` da "Faqat narxsiz turlar" filtri.
- [x] B4.20 "Naqd" → "Yakunlangan" (ADR-038, Temur, 2026-11-03) va xarajatlar vaqti tekshiruvi (07 Q10, Temur savoli:
  kutilayotgan foydada logistika, reklama va saqlash qaysi kunga yoziladi).
  ✓ 2026-11-03: UI'da hamma joyda "Yakunlangan sof foyda + Kutilayotgan sof foyda = Jami" (uch raqam, davr plitkalari,
  grafik legendasi va sarlavhasi, hisob varag'i ustuni va tor ekran almashtirgichi, kesimlarda "shundan yakunlangan",
  formulalar, sahifa yordami, atamalar), testlar, skrinshot asoslari (home, palette, pnl, ui-kit); hisob, API maydonlari
  va rus matni ("Факт") o'zgarmadi. Tahlil: logistika ikki marta ayrilmaydi — u sotuv qatorining maydoni va buyurtma
  kuniga yoziladi, `finance/expenses` dagi logistika qatorlari P&L'ga kirmaydi; saqlash, jarima, pul yechish — Uzum
  yechgan kunga (davr xarajati); buyurtmaga bog'liq reklama ham hozir yechilgan kunga — Q10. `realcheck` ga uch bo'lim:
  `logistics_reconcile` (Uzum yechgan logistika ↔ sotuv qatoridagi, holat bo'yicha; bekor qatorda yechilgan — yashirin
  xarajat), `ads` (kod bo'yicha: "xaridor olganida" matni, `AD#` → sotuv qatori; bog'langanlarda yechilgan kun buyurtma
  va topshirilgan kunga nisbatan, `AD#` dagi sana nimani bildiradi; matnlar raqamsiz), `expense_dates` (`dateService` ↔
  `dateCreated`, 60 kunda yechilgan kunlar). **T:** merge va deploy'dan keyin staging'da `realcheck.sh` → xulosa
  qatorlarini chatga; Q10 qarori.
- [x] B4.21 Xarajat o'z sotuvi va SKU'siga (ADR-039; Temur: Q10 "ha" va "har chiqim o'z SKU'siga", 2026-11-03).
  ✓ 2026-11-03: buyurtmaga bog'liq reklama (`AD#` → sotuv qatori, `store.link_expenses`) P&L'da o'sha sotuvning buyurtma
  kuni, SKU'si va qismiga (`ExpenseItem.processing`), `/expenses` ham shu kun bilan (qatorda `order_date`); hali
  topshirilmagan Jarayondagi sotuvga kutilayotgan reklama F42 (SKU / do'kon ulushi, oxirgi 30 kun) "≈" bilan — hisob
  varag'i, kutilayotgan blok, Asosiy kartochka, drill-down; saqlash F43 — SKU'larga qoldiq × saqlash narxi (`sku_daily`,
  `paidStoragePriceItem`), sotuvi yo'q SKU ham oladi; bir necha SKU'li tovarga bog'langan o'z xarajati — shu SKU'larga.
  `realcheck` ga: `expense_refs` (boshqa turlar matni / `externalId`, sotuv / SKU / mahsulotga mosligi),
  `logistics_differ` (qatordagi va yechilgan logistika farqi namunalari, qaytim qatorlari ko'rinishi), `storage_model`
  (Uzum yechgani ↔ qoldiq × narx). B4.20 realcheck natijasi: reklama 100% buyurtmaga bog'liq va bog'landi; bekor
  qatorlar logistikasi to'liq qaytarilgan (qaytim summasi = yechilgan); Yakunlangan qatorlarda qatordagi logistika
  Uzum yechganidan ~575 ming so'm ko'p (97 qator) — `logistics_differ` bilan aniqlanadi. **T:** merge va deploy'dan
  keyin `realcheck.sh` → xulosa chatga.
- [x] B4.22 Realcheck (B4.21) natijasi va "yakunlangan nega minus" (Temur, 2026-11-03).
  ✓ 2026-11-03: Asosiy — Yakunlangan kartochkasida "shundan sotuvsiz xarajatlar" (`Statement.idle_expenses`: sotilmagan
  tovar saqlashi F43, sotuv bo'lmagan kun xarajati — hech qaysi kutilayotgan sotuvga tegishli emas). Realcheck natijasi:
  saqlash `externalId` = sana + do'kon id — Uzum SKU'ni bermaydi; qoldiq × narx modeliga EL-ONE ~86%, byDurii ~5% —
  Uzum hamma qoldiqdan emas, ba'zi tovarlardan oladi; jarima — qabul farqi ("№ ... yuk xati"), qaytim saqlash —
  "N - sonli yukxat"; Yakunlangan qatorlardagi logistika farqi — 9–12 oktabr olib ketilgan, qatorda 5 250, Uzum 0
  yechgan (uzilish kompensatsiyasi). `realcheck` ga: `storage_rule` (hammasi / aylanma N kun / yosh N kun farazlari),
  `expense_links` (jarima → postavka, qaytim saqlash → qaytarish), `logistics_payout` (`withdrawnProfit` qaysi logistika
  bilan to'g'ri keladi). **T:** merge va deploy'dan keyin `realcheck.sh` → fayl chatga; kabinetda saqlash bo'yicha SKU
  hisobi bormi — ko'rib aytish.
- [x] B4.23 Saqlash Uzum qoidasi bo'yicha, sotuvsiz xarajat qismlarga (ADR-040; Temur, 2026-11-03).
  ✓ 2026-11-03: F43 — kunlik saqlash faqat pullik saqlashdagi SKU'larga (aylanma 15 kun o'rtacha qoldiq / o'rtacha
  kunlik sotuv > 60 kun, yangi emas — `upcore.tariffs.paid_storage`), qoldiq × narx; qaytim saqlash — qaytarish
  SKU'lariga; sotuvsiz katak xarajati qismlarga kun × do'kon tushumining Jarayondagi ulushida (`_finish(day_share)`) —
  "Bugun" da yakunlangan endi faqat do'konda sotuv bo'lmagan kunlarda manfiy; "shundan sotuvsiz xarajatlar" izohi olib
  tashlandi. Logistika — o'zgarishsiz (Uzum `sellerProfit` qatordagi summani ayiradi). Realcheck `storage_rule` ga
  `uzum_rule` modeli. **T:** merge va deploy'dan keyin `realcheck.sh` → fayl chatga (qoida modeli yechilgan summaga
  qanchalik yaqin).
- [x] B4.24 Sof foyda hisobi auditi (ADR-041; Temur: "100% qayta tekshir", 2026-11-03).
  ✓ 2026-11-03: ayirish tartibi sof foydaga ta'sir qilmaydi — xossa testi (`test_conservation_every_cost_once`: har
  xarajat bir marta, yakunlangan + kutilayotgan = jami, kesimlar yig'indisi = jami; 300 tasodifiy holat). Topilgan va
  tuzatilgan: (1) kutilayotgan logistika taxmini (ADR-037) bonusli oktabr buyurtmalariga (Uzum 0 yozgan — bepul) ~5 250
  dan qo'shardi (byDurii 115 qator, ~600 ming) — o'chirildi, logistika Uzum yozgandek (core: `logistics_fee` berilmasa
  taxmin yo'q; API, `/sales`); (2) F42 reklama taxmini reklamasi allaqachon yechilgan sotuvga ham qo'shilardi — endi
  yo'q. Realcheck: `not_issued_zero_recent` nazorati. Formulalar matni yangilandi.
- [x] B4.25 Logistika — Uzum aslida yechgan summa (ADR-042; Temur kuzatuvi, 2026-11-03).
  ✓ 2026-11-03: sotuv logistikasi = sotuvga bog'langan logistika chiqimlari (yo'q bo'lsa qatordagi summa; qatorda 0 va
  olib ketilmagan — F40 taxmini, ADR-037 qaytdi) — `upapi.calc.daily.effective_logistics` (kunlik agregat, P&L, `/sales`);
  sinxron yechim o'zgargan sotuvlar kunidan agregatni qayta quradi; migratsiya 0014 — to'liq qayta qurish. ADR-041 ning
  "bonus buyurtma sanasiga qarab" xulosasi tuzatildi (Uzum olib ketilgan kunga qarab yechadi).
- [x] B4.26 Bekor va qaytarish alohida; bosh sahifada KPI sarhisob (ADR-043; Temur, 2026-11-04 — Robohub tahlili).
  ✓ 2026-11-04: Bekor holat topshirilgan (`dateIssued` — qaytarish, F18) / topshirilmagan (bekor, F17) bo'yicha ikkiga;
  F44–F48 (yalpi summa va dona, buyurtmalar, Uzum ushlab qolgan, Uzumdan keyin qoladi, o'rtacha chek / narx / buyurtmadagi
  tovarlar) — `upcore.metrics.OrderFlow`, `upcore.pnl.Statement`; migratsiya 0015 (`daily_sku_metrics`: topshirilgan bekor
  dona va summalar, to'liq qayta qurish). `/dashboard` → `summary`: 4 guruh × 24 kartochka (joriy, oldingi, o'zgarish —
  ulushda punkt, trend nuqtalari kunlik / haftalik / oylik, ogohlantirish); bosh sahifada "Buyurtmadan sof foydagacha" yo'li
  va kartochkalar (04 §6.4), "Qo'shimcha ko'rsatkichlar" → "Tovardagi pul". Buyurtmalar sahifasi (bekor / qaytarish: dona,
  summa, sabab), `/sales`, `/skus` — yangi F17/F18. Sozlamalar → "Ogohlantirish chegaralari" (`PUT /settings/alerts`).
  Realcheck `cancel_split`: bekor holat oyma-oy topshirilgan / topshirilmagan, logistika yechilgan va qaytarilgani, sabablar,
  `/v1/return` donalari. **Topildi:** eski qaytish % faqat Yakunlangan `amountReturns` dan (real ma'lumotda doim 0), bekor %
  qaytarishlarni ham sanardi. **T:** staging'da realcheck → Uzum kabinetidagi oktabr qaytarish va bekor sonlari bilan
  solishtirish; xohlasa — Sozlamalarda chegaralar.
- [→] B4.27 (**ko'chdi → B5.0a**, ADR-057 Q8) "Yo'qotishlar va imkoniyat" bloki (ADR-043 (5), AI'siz, formula bilan): qaytarish xarajati, zarardagi SKU,
  tannarxsiz sotuvlar; bekor summasi yo'qotish emas.
- [x] B4.28 Xarid tovarlari: tanlov SKU'dan, «Qatorlar» → «Partiyadagi tovarlar» (ADR-044; Temur, 2026-11-04).
  ✓ 2026-11-04: tovar tanlash ro'yxati `items` o'rniga hamma SKU'dan (`GET /sku-picker`: do'kon, mahsulot, variant, qoldiq,
  Uzum holati; arxivlangan va bloklangan ham, qoldig'i yoki sotuvi borlari oldinda) + SKU'siz tovarlar; `LineIn.sku_id` —
  tovari yo'q SKU'ga tovar yaratiladi (`item_of_sku`, `/opening` bilan umumiy); `POST /purchases/{id}/lines/bulk` — bir
  nechta SKU bitta tranzaksiyada; shaklda ko'p tanlash (har biriga dona, narx/vazn hammasiga) va takror belgisi; ekran nomi
  «Partiyadagi tovarlar», «Tovar qo'shish» (uz-Latn va ru). Model o'zgarmadi (har qator — bitta tovar, tannarx tovar
  darajasida). Testlar: API (`test_sku_picker_lists_every_sku_and_lines_from_skus`), web (`model`, `purchases`).
  **T:** staging'da Xaridlar → partiya → «Tovar qo'shish»: ikkala do'kondagi hamma SKU ko'rinishini tekshirish.
- [x] B4.29 CBU kursi yetishmasligi tuzatishi (Temur, 2026-11-04: xarid sahifasida "CNY uchun 2026-10-07 sanasigacha kurs yo'q").
  ✓ 2026-11-04: kurs arxivi (`upapi.fx.sync_fx`) endi **eng kam to'lgan valyutadan** orqaga yuradi (avval bitta global eng eski
  kun: bir valyuta tarixi uzoq bo'lsa, boshqasi hech to'lmasdi); xarid saqlanganda to'lov sanasi kursi bazada yo'q bo'lsa
  `fx.cbu` ishi `since` bilan qo'yiladi — o'sha sanadan 10 kun oldingacha cheklovsiz to'ldiradi va tashkilotlar hisobi qayta
  quriladi. Testlar: `test_fx` (valyuta bo'yicha boshlanish, `since`), `test_purchases` (ish qo'yilishi).
  Keyin (Temur: xato staging'da qoldi): `upapi.fxcheck` + `infra/staging/fxcheck.sh` — diagnostika (cbu.uz serverdan ochiladimi,
  `fx_rates` valyuta bo'yicha, `fx.cbu` ishlari); sabab shu hisobotdan aniqlanadi (`docs/staging.md`).
- [x] B4.30 Zaxira kurs manbai — bozor kursi (ADR-045; Temur, 2026-11-04: cbu.uz AWS serverdan ochilmaydi, `curl` — vaqt tugadi).
  ✓ 2026-11-04: CBU javob bermasa joriy kurs va arxiv zaxira manbadan (`fx_market_urls`: jsDelivr va Cloudflare Pages
  currency-api, ko'zgular tartibi bilan); `fx_rates.source = market` (`fx_upsert_market()`, migratsiya 0016); bir kunda
  CBU ustun (`upcore.fx.rate_on`); lotda `market_rate` belgisi, xarajatda "bozor kursi, Markaziy bank emas" (`rate_source`);
  arxiv har manba uchun o'z bo'shlig'idan; `fx.cbu` ishi `since` bilan zaxirada ham ishlaydi. Qo'lda va "karta" kurslari
  zaxiradan ustun. Testlar: `test_fx` (zaxira, ko'zgu, ikkala manba yo'q, CBU qaytsa), `test_purchases`, core, web.
  **T:** deploy'dan keyin kursi yo'q xaridda komponentni qayta saqlash (yoki worker 09:05 / 16:05 da o'zi to'ldiradi), so'ng
  `fxcheck.sh` bilan `fx_rates` da `market` qatorlarini ko'rish.
- [x] B4.31 Kargo: bitta kargo — ko'p xarid (ADR-046; Temur taklifi, 2026-11-04).
  ✓ 2026-11-04: `shipments` jadvali, `purchases.shipment_id`, `cost_components.shipment_id` (xarajat yoki xaridniki, yoki
  kargoniki — CHECK; migratsiya 0017); `upcore.purchasing.compute_shipment_lots` / `compute_shipment_shares` — kargo xarajati
  hamma xaridlarning hamma tovarlariga bitta taqsimotda (yig'indi tiyinigacha, xossa testi); `upapi.calc.lots`
  (`evaluate_shipment`, `rebuild_lots` qo'shni xaridlarni o'zi oladi; biror xarid hisoblanmasa butun kargo xato bilan);
  `/shipments` (CRUD, xarajatlar, xaridlar va tovarlar bo'yicha ulush), `/purchases` (`shipment_id`, kargodan sanalar,
  `shipment_components`); ekranlar: Kargolar ro'yxati va sahifasi, xarid shaklida kargo tanlovi, xarid sahifasida kargo
  bloki; "Yangi kargo…" (kompaniya) → "Yangi kompaniya…". Testlar: core (taqsimot, xossa), API (`test_shipments`, 5),
  web (`shipments.test`, 11), e2e (kargo sahifasi, 360 px). **T:** staging'da kargo yaratib 2 ta xaridni bog'lash, kargo
  narxini kiritish va xaridlardagi tannarxni tekshirish.
- [x] B4.32 Xarid ↔ kargo biriktirish (ADR-047; Temur talabi, 2026-11-05).
  ✓ 2026-11-05: xarid sahifasida "Yangi xarajat" → Turi = Kargo — summa o'rniga kargolar ro'yxati (holati va sanasi bilan,
  "Kargosiz", "Yangi kargo…"), saqlash xaridni kargoga biriktiradi (komponent yaratilmaydi — ikki marta hisoblanmaydi);
  kargo sahifasida "Xarid biriktirish" (kargosiz va boshqa kargodagi xaridlardan bir nechtasi; ketma-ket `PATCH`, qisman xato
  aniq aytiladi). Backend o'zgarmadi. Testlar: web (`shipments.test`, +9: ro'yxat, yangi kargo, almashtirish/ajratish, izoh,
  ko'p xarid, qisman xato, bo'sh holat, rol, a11y). **T:** staging'da xarid sahifasidan va kargo sahifasidan biriktirib ko'rish.
- [x] B4.33 Dizayn jilosi: Xaridlar va Kargolar (ADR-048; Temur talabi, 2026-11-05; yo'nalish A, standart yorug').
  ✓ 2026-11-05: standart mavzu yorug'; iliq qog'oz tokenlari (`bg-page`, `bg-raised`, `border-hairline`, yangi `border-strong`,
  `border-input` ≥ 3:1); jadval (sarlavha fon + siyoh chiziq, bo'shliqlar, burchak), mobil ro'yxat (ustunlar yashirin, meta qator),
  tugma (submit — primary), yig'indi paneli (hisob daftari qatorlari), tanlov qatorlari, bo'sh holat; Xaridlar, Xarid, Kargolar,
  Kargo sahifalari va oynalari. Testlar: theme/shell (yangi standart), e2e vizual (+xaridlar va kargolar, 16 asos), a11y (qorong'i aniq
  tanlanadi). **T:** staging'da Xaridlar va Kargolar sahifalarini yorug' rejimda ko'zdan kechirib, yoqmagan joylarni skrinshot bilan
  yozing; yoqsa — qolgan sahifalarga (Mahsulotlar, Ombor, Foyda, Xarajatlar, Bosh sahifa) yoyiladi (B4.35).
- [x] B4.34 Kargo sahifasi tuzatishlari (ADR-049; Temur topdi, 2026-11-05).
  ✓ 2026-11-05: kargo xarajati turlari faqat kargoga tegishlilari (Kargo, Bojxona, Qadoqlash, Shtrix-kod / yorliq, Uzum omboriga
  yetkazish, Boshqa); Tovar, Xitoy ichki yetkazish va agent — xaridniki (API `422 kind_not_for_shipment`, `SHIPMENT_KINDS` core'da);
  eski yozuv turi bilan tahrirlanadi; boshlang'ich tur Kargo; to'g'ri tugma yozuvlari (Xarajatni / Kargoni / Sanalarni saqlash); kargodagi
  xaridni shu sahifadan ajratish; xaridsiz kargoda tushuntirish. Testlar: API (`test_shipments`), web (`shipments.test`, +3), vizual asoslar.
  **T:** staging'da Kargo sahifasida "Xarajat qo'shish" turlarini, "Ajratish" tugmasini ko'rish; kargoga avval yozilgan "Tovar" xarajati bo'lsa — uni o'chirib, xarid sahifasida kiritish.
- [x] B4.35 Dizayn jilosi: qolgan sahifalar (ADR-048 davomi; Temur: "o'zing qulayidan boshla, xatosiz").
  ✓ 2026-11-05: hamma sahifa (Asosiy, Foyda, Mahsulotlar, Buyurtmalar, Xarajatlar, Ombor, Sozlamalar) mock ma'lumot bilan 1440 va 390 px da
  ko'zdan kechirildi; umumiy kamchiliklar tuzatildi: KPI kartalarda raqamlar bir chiziqda (kartalar teng balandlikda cho'zilganda ichki
  qatorlar surilmaydi; "?" tugmali va tugmasiz yorliq bir xil balandlikda), Ombor holat belgilari katak kengligiga cho'zilmaydi,
  Buyurtmalarda filtr va Excel tugmasi bir chiziqda, "?" tugmalari qatorga tushib qolmaydi, Xarajatlarda Excel tugmasi cho'zilmaydi,
  Sozlamalarda bo'lim sarlavhasi, izoh va forma sarlavhalari (legend) oralig'i. Faqat CSS; mantiq va matn o'zgarmadi. Vizual asoslar yangilandi.
  **T:** staging'da Asosiy, Ombor, Buyurtmalar, Xarajatlar, Sozlamalarni ko'rib, yoqmagan joyni skrinshot bilan yozing (keyingi o'tish:
  mobil jadvallar — Ombor/Mahsulotlar, Asosiy sahifa qayta tuzilishi).
- [x] B4.36 Dizayn jilosi: Asosiy, Foyda, Mahsulotlar kartochkalari va jadval skroll ishorasi (ADR-048 davomi; Temur: "hammasi yaxshi, davom et").
  ✓ 2026-11-05: kartochkalar hamma sahifada bir xil burchakda (10 px; avval Asosiy, Foyda va Mahsulotlarda burchaksiz, boshqa sahifalarda
  10 px edi): Asosiy ("uch raqam", davr kartalari, KPI kartalari, "Diqqat talab qiladi"), Foyda ("Kutilayotgan sof foyda"), Mahsulotlar
  ("Jadvaldan tashqari", SKU bloklari); hisob varag'i burchaksiz qoldi. Davr kartalarida "?" tugmali sarlavha bir chiziqda. Jadvallarda
  gorizontal skroll bo'lsa, chetida yengil soya (mobilda ma'lumot o'ngda davom etishi ko'rinadi). Faqat CSS; ma'lumot yashirilmadi.
  Vizual asoslar (Asosiy, Palitra) yangilandi. **T:** staging'da Asosiy, Foyda, Mahsulotlarni ko'rib, yoqmagan joyni skrinshot bilan yozing.
- [x] B4.37 **("Oxirgi partiya" ustuni olib tashlandi: ADR-052, B4.42)** Mantiq tuzatishlari: zarar SKU soni, "Taxminiy" belgisi sababi, partiya tannarxi (Temur topdi, 2026-11-05: 3 ta savol).
  ✓ 2026-11-05: (1) **Zarar SKU:** "Zarar bilan sotilayotgan SKU" va Asosiy sahifadagi zarar ro'yxati davrda sotuvi bor SKU'larni sanaydi
  (`Statement.sold_at_loss`); avval faqat saqlash yoki reklama xarajati bor, sotilmagan SKU'lar ham kirib, son oshib ketardi. Hamma sotuvi
  tannarxsiz SKU (F15 qamrovi 0) endi "Zarar" emas, "Maʼlumot yoʻq": sotuvsiz kunlardagi xarajat to'liq ayriladi, tushumi esa hisobga
  kirmasdi — manfiy son tannarx yo'qligidan chiqardi (`Statement.label`; Mahsulotlar jadvali holat belgisi va filtri ham shunday). (2)
  **"Taxminiy" belgisi:** F22 ning har qanday belgisida chiqar, sababi ko'rinmasdi, tannarxi yo'q ("—") qatorda ham "Taxminiy" turardi.
  Endi belgi ustiga sabab matni yoziladi (sichqoncha ustida va ekran o'quvchi uchun): kargo kiritilmagan, qabul qilinmagan, kurs CBU,
  lot yetmadi va h.k.; tannarxi yo'q qator "Tannarxsiz" (sabab: SKU bog'lanmagan, partiya yo'q). Buyurtmalar va Asosiy drill-down'da bir xil
  (`CostCell`). (3) **Mahsulotlarda tannarx:** "Tannarx/dona" davrda sotilgan donalar o'rtachasi (F21) — sotuv yo'q SKU'da bo'sh edi;
  yangi "Oxirgi partiya" ustuni (F20) tovarning oxirgi partiyasi tannarxini sotuvdan mustaqil ko'rsatadi (yo'ldagi partiya "(yo'lda)"),
  saralanadi, Excel'da ham. Xarid qatori SKU'ga bog'lanmagan ("yangi tovar") bo'lsa xarid sahifasida shu haqda izoh. Formulalar o'zgarmadi.
  **T:** staging'da Asosiy → "Zarar bilan sotilayotgan SKU" sonini, Mahsulotlarda "Oxirgi partiya" ustunini va Buyurtmalarda "Taxminiy"
  belgisi ustiga sichqoncha olib borib sababini tekshiring.
- [x] B4.38 B4.37 davomi: staging'da topilgan kamchiliklar (Temur skrinshoti, 2026-11-05).
  ✓ 2026-11-05: (1) Mahsulotlar jadvalida 121 ta SKU ham "Zarar" chiqqan edi — ularning ko'pi davrda sotilmagan (faqat saqlash xarajati):
  yangi holat **"Sotuv yo'q"** (`ProfitLabel.IDLE`, filtrda ham); "Zarar" faqat sotilgan SKU uchun. (2) "Oxirgi partiya" ustuni bo'sh edi:
  tannarx boshlang'ich holat oynasida kiritilgan (partiya emas) — endi partiya bo'lmasa boshlang'ich narx ("(boshlang'ich)") ko'rinadi;
  tartib: tayyor partiya → boshlang'ich narx → yo'ldagi partiya (`lot_source`). (3) "Taxminiy" sababi sichqoncha ustida chiqmasdi
  (brauzer tooltip'i): belgi endi tugma — bosilsa sabablar katak ichida ochiladi (telefonda ham ishlaydi). **T:** staging'da Mahsulotlar →
  Holat = "Zarar" va "Sotuv yo'q", "Oxirgi partiya" va Buyurtmalarda "Taxminiy" belgisini bosib ko'ring.
- [x] B4.39 **(qoldiq tugagandagi qoidasi almashtirildi: ADR-051, B4.41)** Boshlang'ich holatda narxi kiritilgan tovar sotuvida "Taxminiy" chiqmaydi (Temur: "men har biriga aniq tannarx kiritganman, qoldiqni dastur o'zi
  olgan — hech qachon taxminiy chiqmasin", 2026-11-05).
  ✓ 2026-11-05: boshlang'ich qoldiq (Uzumdan olingan dona) tugagan yoki 0 bo'lgan tovarning keyingi sotuvi sotuv kunidagi kiritilgan narxda
  hisoblanadi va endi belgilanmaydi (avval "lot yetmadi" — "partiyalar yetmadi" matni bilan taxminiy edi); qoldiq tugagach narx kunlar bo'yicha
  yangilanadi (oxirgi qatlam narxi emas, `valid_from` jadvali). "Lot yetmadi" faqat haqiqiy partiyalar tugaganda. Boshlashdan oldingi sotuvlarning "tarixiy" belgisi ham
  jadvalda "Taxminiy" ko'rsatmaydi (sotuvchi kiritgan narx). 02 (F22, F41) yangilandi.
  **T:** kerak emas; shunday sotuvlarda "Taxminiy" yo'qolganini tekshiring.
- [x] B4.40 Deploy'dan keyin tannarx natijalari darhol qayta hisoblanadi (Temur skrinshoti, 2026-11-05: B4.39 dan keyin ham
  boshlang'ich narxli sotuvlarda "Taxminiy · partiyalar yetmadi").
  ✓ 2026-11-05: sabab — dvigatel emas (B4.39 to'g'ri), saqlangan natija: `sale_costs` (tannarx va belgilar) faqat manba o'zgarganda
  yoki tungi 03:40 dagi to'liq qayta qurishda yangilanadi, deploy esa hisob qoidasini o'zgartirsa ham eski qatorlarga tegmasdi — B4.39
  tuzatishi eski sotuvlarga ertalabgacha yetib bormasdi (oldingi dvigatel tuzatishlarida ham shunday bo'lgan). Endi ishchi ishga
  tushganda (har deploy uni qayta yaratadi) hamma ulangan tashkilot uchun to'liq qayta qurish navbatga qo'yiladi (`rebuild_all`, tungi
  ish bilan bir xil; idempotent, faqat farqlar yoziladi). Versiya raqami o'rniga har ishga tushishda — oshirishni unutib bo'lmaydi.
  **T:** deploy tugagach bir necha daqiqadan keyin Buyurtmalar sahifasini yangilab, o'sha sotuvlarda "Taxminiy" yo'qolganini ko'ring.
- [x] B4.41 Boshlang'ich qoldiq tugaganda tannarx — FBO postavkalari bo'yicha (ADR-051; Temur: B4.39 qoidasi noto'g'ri, 2026-11-05).
  ✓ 2026-11-05: staging so'rovi — Uzum qaytish sanasini bermaydi; GUBKA-БЕЛЫЙ va FRENCH-МОЛОЧ dagi "ortiqcha" donalar boshlashdan
  oldingi bekor buyurtmalardan qaytgan eski tovar. Endi qoldiq va partiyalar tugaganda: postavka yo'q — boshlang'ich narx, belgisiz
  (yo'ldagi partiyaga tegilmaydi); postavka bor, partiya kiritilgan — oxirgi partiya narxi, belgisiz; postavka bor, partiya
  kiritilmagan — "Taxminiy" ("postavka bor, partiya Xaridlarga kiritilmagan"). Postavka sinxroni qayta hisobni chaqiradi.
  **T:** deploy'dan keyin Buyurtmalarda GUBKA va FRENCH sotuvlarida "Taxminiy" yo'qligini ko'rish.
- [x] B4.42 Mahsulotlar: bitta "Tannarx/dona" ustuni (ADR-052; Temur talabi, 2026-11-05).
  ✓ 2026-11-05: "Oxirgi partiya" ustuni olib tashlandi; "Tannarx/dona" — davrda sotuv bo'lsa sotilgan donalar o'rtachasi (F21), bo'lmasa
  oxirgi partiya / boshlang'ich narx / yo'ldagi partiya, yonida izoh. Saralash va Excel ("Tannarx manbasi" ustuni) ham shunday.
  **T:** staging'da Mahsulotlar → "Tannarx/dona" ustunida sotuvsiz SKU'larda ham qiymat (izoh bilan) borligini ko'rish.
- [x] B4.43 Asosiydagi "Buyurtmadan sof foydagacha" — Temur chizmasi bo'yicha zinapoya (ADR-053, F49; 2026-11-05).
  ✓ 2026-11-05: buyurtmalar summasi 100%, bekor → qaytarish → Uzum ushlab qolgan → tannarx → o'z xarajatlar → soliq →
  tannarxi kiritilmagan bo'laklari o'ngdan chapga, chapda sof foyda; har qatorda "summa / ulush"; zarar — chapdan qizil.
  **T:** staging'da Asosiy sahifadagi yangi chiziqni ko'rish (yoqmagan joyni skrinshot bilan yozish).
- [x] B4.44 Mahsulotlar tahlili, 1-qism: holat belgisi — davrda sotilmagan har SKU "Sotuv yo'q" (Temur, 2026-11-09).
  Tahlil (2026-11-06): Mahsulotlar sahifasida 22 ta kamchilik topildi; Temur qarori — bo'lib-bo'lib tuzatiladi, har biri
  alohida PR (B4.44–B4.55), keyin sahifalash boshqa sahifalarga (B4.56–B4.60, ADR-054).
  ✓ 2026-11-09: avval sotilmagan SKU xarajati bo'lsa "Sotuv yo'q", xarajati yo'q yoki kompensatsiya tushgan bo'lsa
  "Ma'lumot yo'q" chiqardi (filtr va Excel ham) — endi `Statement.label`: sotuv qatori yo'q → doim "Sotuv yo'q";
  "Ma'lumot yo'q" — faqat sotuv bor, hammasi tannarxsiz. **T:** staging'da Mahsulotlar → Holat "Sotuv yo'q" filtrini ko'rish.
- [x] B4.45 Tannarx bir xil: SKU sahifasi KPI va kalkulyator jadvaldagi "Tannarx/dona" zanjirini ishlatadi (sotuv → oxirgi
  partiya → boshlang'ich → yo'ldagi; boshlashdan oldingi partiya olinmaydi), KPI "?" — F21/F20; ishlatilmaydigan
  `lot_unit_cost`, `LABEL_SORT_ORDER`, `COLUMN_OF_SORT` olib tashlanadi.
  ✓ 2026-11-09: SKU sahifasi "Tannarx/dona" KPI'si — `unit_cost` (sotuvsiz SKU'da ham qiymat, izoh "(oxirgi partiya)" /
  "(boshlang'ich)" / "(yo'ldagi partiya)"), "?" — F21, F20 (avval F7 jami formulasi). Kalkulyator tannarxi — jadval bilan bir
  xil partiya zanjiri (`latest_lot_costs`), keyin davr o'rtachasi (narx qo'yish uchun partiya ustun — ADR-033); yangi manbalar
  `opening`, `transit`; boshlashdan oldingi partiya olinmaydi. `SkuRowOut.lot_unit_cost` / `lot_source`, `sort=lot_unit_cost`
  olib tashlandi (ADR-052 dagi "qoladi" bekor). **T:** staging'da boshlang'ich narxi bor, davrda sotilmagan SKU sahifasida
  KPI va kalkulyatorda jadvaldagi narx chiqishini ko'rish.
- [x] B4.46 SKU sahifasi "Qaytishlar sabablari" — "Bekor + topshirilgan" qaytishlar ham (ADR-043, Buyurtmalar bilan bir xil).
  ✓ 2026-11-09: avval faqat Yakunlangan qatordagi qisman qaytarish sanalardi — "Qaytish" KPI'si (F18) bor, jadvalda "qaytish
  yo'q" chiqishi mumkin edi. Endi sabablar bitta funksiyadan (`reports.cells.cause_sums`): qaytarish — qisman qaytarish +
  mijozga topshirilgan Bekor qator, bekor — topshirilmagani; Buyurtmalar tahlili ham shundan. **T:** staging'da qaytishi bor
  SKU sahifasida sabablar jadvalini Buyurtmalar → "Qaytarilish" bilan solishtirish.
- [x] B4.47 Jadvalda tannarxsiz qism belgisi (tamoyil 9, F13): `uncovered_share` > 0 bo'lsa marja/sof foyda yonida.
  ✓ 2026-11-09: qisman tannarxsiz SKU'da "Marja" va "Holat" ustunlarida "tannarxsiz 25%" (ogohlantirish rangida; ustiga
  kelganda: nechta sotuv va nima qilish kerak); hammasi tannarxsiz ("Ma'lumot yo'q") SKU'da — faqat marja yonida.
  **T:** staging'da Mahsulotlarda tannarxi qisman kiritilgan SKU yonida belgini ko'rish.
- [x] B4.48 Umumiy sahifalash (ADR-054): `Pagination` komponenti (sahifa raqamlari, 20/50/100, standart 50, URL'da `page`),
  API sahifa + jami; Mahsulotlarga ("Yana yuklash" va virtual skroll o'rniga — 500+ qator xatosi va offset takrori yo'qoladi);
  Mahsulotlar uchun birinchi e2e.
  ✓ 2026-11-09: `Pagination` (`components/ui`): "1–50 / 340 ta", sahifa raqamlari (ko'pida "…"), oldingi/keyingi, "Sahifada" 20/50/100
  (tanlov brauzerda eslanadi, standart 50), ≤ 20 ta bo'lsa chizilmaydi, tugmalar ≥ 44 px. `/skus`: `cursor` o'rniga `page` (1 dan) va
  `limit` ≤ 100 (standart 50), javobda `page` va `pages`; so'ralgan sahifa oxirgisidan oshsa API oxirgisini beradi va URL shunga
  o'tadi; saralash/filtr/qidiruv/o'lcham o'zgarsa — 1-sahifa. Excel eksporti sahifalashsiz hamma qatorni oladi (`skus.ranked`).
  Mahsulotlarda "Yana yuklash" olib tashlandi; jadval ≤ 100 qator bo'lgani uchun virtual skroll ishlamaydi (500+ qator xatosi
  yo'qoldi). Birinchi Mahsulotlar e2e (`e2e/products.spec.ts`, desktop + mobil 360 px). **T:** staging'da Mahsulotlarda sahifalarni
  almashtirish, "Sahifada" tanlovini va SKU'dan qaytganda sahifa saqlanmasligini ko'rish (saqlash — B4.50).
- [x] B4.49 Kalkulyator: to'xtovsiz qayta chizish (debounce) va noto'g'ri qiymatda aniq xato matni (422).
  ✓ 2026-11-09: sabab — `toInput(values)` har renderda yangi obyekt, `useDebounced` esa obyektning o'zini kuzatardi: effekt har
  renderda qayta ishga tushib, 300 ms'da `setOut` → yana render → ... (kalkulyator to'xtovsiz qayta chizilardi). Endi
  kechiktirilgan narsa — kiritishning matn ko'rinishi (`JSON.stringify`), obyekt undan `useMemo` bilan olinadi. Server 422
  bersa (summa 0–10¹², foiz 0–100 dan tashqari) eski natija yashiriladi va "Qiymat notoʻgʻri: summalar 0 dan 1 000 000 000 000
  gacha, foizlar 0 dan 100 gacha boʻlishi kerak" chiqadi; boshqa xatolar — umumiy matn (`errorText`). **T:** staging'da
  kalkulyatorga komissiya 150 yozib xato matnini ko'rish.
- [x] B4.50 SKU'dan qaytganda qidiruv, filtr, saralash va sahifa saqlanadi; "Zaxira kunlari" saralashida harakatsiz qoldiq
  (tezlik 0, qoldiq bor) yuqorida; nom bo'yicha saralash ko'rinadigan nom, katta-kichik harfsiz, lotin/kirill tartibida.
  ✓ 2026-11-09: (1) SKU sahifasi marshrutiga ham `productsSearch` ulandi: jadvaldagi SKU havolasi `q`, `sort`, `label`, `abc`, `page`
  ni olib yuradi, "Mahsulotlarga qaytish" ularni tiklaydi (URL'da — ulashsa ham, orqaga bosilsa ham ishlaydi). (2) "Zaxira kunlari"
  saralashi: tezlik 0 bo'lib qoldig'i bor SKU (F24 `None`) endi cheksiz zaxira — kamayishda eng tepada, o'sishda oxirgi qoldiqli;
  qoldiqsizlar doim oxirida. (3) Nom bo'yicha saralash ko'rinadigan nom (SKU nomi, yo'q bo'lsa mahsulot nomi) bo'yicha, qidiruv bilan
  bir xil `fold` (katta-kichik harf, kirill/lotin, tutuq) — avval xom `title` va nomsizlar tasodifiy edi. **T:** staging'da SKU
  ochib qaytganda qidiruv/filtr/sahifa saqlanishini, "Zaxira kunlari" ni bosganda harakatsiz qoldiq tepada chiqishini ko'rish.
- [x] B4.51 Mahsulotlar Excel'i: "Holat" o'zbekcha, "Do'kon" ustuni; Excel sarlavhalarida oʻ/gʻ — U+02BB.
  ✓ 2026-11-09: Mahsulotlar Excel'ida "Holat" endi jadvaldagidek o'zbekcha (Zarar, Chegarada, Foydali, Maʼlumot yoʻq, Sotuv yoʻq —
  avval `loss`, `no_data`...); "SKU" va "Tovar"dan keyin "Doʻkon" ustuni (taxallus, yo'q bo'lsa nom). Sarlavhalardagi oʻ/gʻ
  U+02BB bilan: Oʻrtacha narx, Uzum toʻlovi, Doʻkonlar, Davrga toʻgʻri keladigani, Oʻz xarajatlarim, Yoʻlda, Oʻz omborimda va
  "Ha/Yoʻq" katagi (avval U+02BC edi); tutuq (P&Lʼga) joyida. **T:** staging'da Mahsulotlar Excel'ini yuklab ustunlarni ko'rish.
- [x] B4.52 Tovarga bog'lash: "Tovardan ajratish" tasdiq bilan; tovar qidiruvi serverda (500+ tovar).
  ✓ 2026-11-09: (1) "Tovardan ajratish" endi tasdiq oynasi bilan: qaysi SKU qaysi tovardan ajralishi, tannarx hisoblanmay qolishi
  va tovarning o'zi saqlanishi yoziladi; "Bekor qilish" — so'rov ketmaydi. (2) Tovar tanlovi avval faqat birinchi 500 ta tovarni
  yuklab mijozda filtrlardi — 500+ tovarda qolgani topilmasdi. Endi yozilgan matn (250 ms) `GET /items?q=` bilan serverda
  qidiriladi; `limit` (standart 50) va `total` qo'shildi, mos kelganlar ko'p bo'lsa "Birinchi 50 ta ko'rsatildi, jami N ta —
  aniqroq yozing" izohi chiqadi; tanlangan nom ro'yxat o'zgarsa ham maydonda qoladi (`Combobox` — `onSearch`, `selectedLabel`,
  `total`). **T:** staging'da SKU sahifasida "Tovardan ajratish" tasdiqini va tovar tanlovida qidiruvni ko'rish.
- [x] B4.53 Tushuntirishlar: Dona, O'rtacha narx, Qoldiq, ABC, Holat ustunlarida "?"; "Jadvaldan tashqari" matni filtrda;
  sof foyda grafigida sotuvsiz kunlar xarajati.
  ✓ 2026-11-09: (1) Dona (F2), O'rtacha narx (F3), Qoldiq (F24), ABC (F28) va Holat (F12, F13) ustun sarlavhalarida "?" —
  formula, manba va qoida (`home.formula.units|avgPrice|stock|abc|label`; uz-Latn va ru; "Holat" ichida chegara — marja 5% dan past,
  B4.55 sozlama qilgach matn yangilanadi). (2) "Jadvaldan tashqari" blokida qidiruv yoki filtr bor bo'lsa "bu qismlarga taʼsir
  qilmaydi — butun davr va tanlangan doʻkonlar bo'yicha" izohi. (3) SKU sahifasi kunlik grafigida sotuvsiz kundagi xarajat (sof foyda
  ≠ 0) endi chiziqda ko'rinadi (avval `units > 0` bo'lmasa kun bo'sh edi) va izoh chiqadi. **T:** staging'da Mahsulotlarda ustun
  "?" larini, filtr bilan "Jadvaldan tashqari" izohini va xarajatli sotuvsiz kuni bor SKU grafigini ko'rish.
- [x] B4.54 Mobil (360 px): Mahsulotlar jadvali va SKU sahifasi KPI'lari, bosish maydoni ≥ 44 px, mobil e2e.
  ✓ 2026-11-09: 360 px'da ko'rib chiqildi (screenshot). SKU sahifasi KPI'lari bitta ustun (ekran uzun) edi — endi ikki ustun, katta
  raqam kichikroq shriftda sig'adi (gorizontal skroll 0). Mahsulotlar va SKU sahifalarida (faqat shu ikki sahifa ichida) tugma,
  havola, maydon, saralash sarlavhasi, grafik/jadval almashtirgich va "?" bosish maydoni ≥ 44 px (avval 19–36 px). Yuqori panel
  (do'kon, davr, yangilanish, qidiruv) umumiy qobiq — 36 px, alohida vazifa. Jadval o'z ichida gorizontal skroll qiladi (ustun
  ko'p). Mobil e2e (`e2e/products.spec.ts`): SKU sahifasi va Mahsulotlar jadvalida kichik bosish maydoni yo'qligi, gorizontal
  skroll yo'qligi, KPI ikki ustunda. Qo'shimcha (Temur savoli): "Sotuvsiz kunlar xarajati" ostiga izoh — doʻkonda sotuv boʻlmagan kun
  xarajati, hech bir SKUʼga boʻlinmaydi, lekin jami sof foydadan ayriladi. **T:** telefonda staging'da Mahsulotlar va SKU
  sahifasini ko'rib, qulay emas joyni skrinshot bilan yozish.
- [x] B4.54a SKU sahifasi tanqidiy tahlili (Temur skrinshotlari, 2026-11-09): topilgan va tuzatilgan kamchiliklar.
  ✓ 2026-11-09: (1) Grafik kartalari yonma-yon turganda biri "Jadval"ga o'tsa (~120 qator), ikkinchisi ham shu balandlikka
  cho'zilib, grafik o'rtada bo'sh qolardi — endi kartalar o'z balandligida (`align-items: start`), jadval ko'rinishi `max 24rem` +
  ichki skroll + qotgan sarlavha (hamma grafikda). (2) Jadval ko'rinishida "—" qatorlari (ma'lumotsiz kunlar) yo'q. (3) Kunlik
  o'q avval faqat ma'lumotli kunlarni ko'rsatardi (kategoriya o'qi) — 22-sentabrdan keyin 26-sentabr kelib vaqt siqilardi; endi
  davrning hamma kuni (`fillDays`), bo'sh kunlar bo'sh. (4) Siyrak chiziq (kam yoki yolg'iz nuqta) ko'rinmasdi — endi doira bilan
  belgilanadi (`MarkPointComponent` ulandi); narx chizig'i bo'sh kunlar ustidan tutashadi (`connect`). (5) Narx va qoldiq snapshoti
  hamma kunga yozilmagan bo'lsa izoh: "{N} kunning {M} tasi uchun bor, qolgan kunlar bo'sh — nol emas" (tamoyil 8). (6) KPI raqami
  ("4 353 060 soʻm") karta chetidan chiqib kesilardi — karta kengligiga moslangan o'lcham (`cqi`), e2e shuni tekshiradi. (7) Dona
  (F2), O'rtacha narx (F3), Holat va ABC nishonlarida "?" tushuntirish (SKU sahifasi). **Topildi, tuzatilmadi:** "Qaytishlar
  sabablari"da Uzum xom sabab matni (`BAD_QUALITY`, ruscha) — to'liq sabab ro'yxati kerak (Temurdan). **T:** staging'da SKU
  sahifasini 100% masshtabda ko'rish; qaytish sabablari uchun Uzumdagi hamma sabab nomlarini yuborish.
- [x] B4.54b SKU sahifasi: qoldiq grafigi ma'noli qilindi — postavka davri, narx grafigi shartli (ADR-055; Temur: grafik noto'g'ri ko'rindi).
  ✓ 2026-11-10: sabab Uzum xatosi emas, bizning tushunishimiz edi: `quantityActive` = savdoda turgan dona, postavka savdoga
  chiqarilguncha (qabul oynasidan 24 soat – 7 kun) hisobda yo'q; Uzum `ACCEPTED` ni savdoga chiqarish paytida qo'yadi
  (`dateAccepted`). Temur xom postavka ma'lumotini yubordi: 99 dona 09.11 da chiqdi, 17 sotildi → 82 (snapshot bilan mos). Endi:
  SKU sahifasi API'da `supplies` (yaratilgan sana, qabul oynasi, savdoga chiqarilgan sana, dona); qoldiq grafigi "Savdodagi
  qoldiq (FBO + FBS)" nomi bilan, postavka davri shtrixli oraliq ("Postavkada: 99 dona — 09.11.2026 da savdoga chiqarildi" /
  "hali savdoga chiqarilmagan") va tushuntiruvchi izoh bilan; narx grafigi faqat narx o'zgargan bo'lsa (tekis chiziq — yo'q), "Uzumdagi
  narx" KPI qo'shildi; qoldiq jadvali va narx — oldingidek. Izohga: qoldiq kun oxirida olinadi, bekor/qaytgan tovar qoldiqqa qaytib qayta sotilishi mumkin (Temur tasdiqladi — qoldiq 0 kunlardagi sotuvning sababi). **T:** staging'da SKU sahifasida qoldiq grafigini ko'rish (28.10–09.11 shtrixli oraliq).
- [→] B4.61 (**ko'chdi → B5.0c**, ADR-057 Q8; toraytirildi, past ustuvorlik) Ombor: postavka tarkibi va qisman chiqarish (ADR-055 §3). Ochiq postavka "Postavkada" hisoblanadi
  (to'g'ri, 02.11–09.11 ham); kamchiliklar: (1) holat `ACCEPTED` bo'lgach (savdoga chiqarish boshlangach) hali chiqarilmagan qism
  (`quantityToStock − quantityAccepted`, masalan 25 dona 09.11 07:05–10.11 13:39) hech qaysi joyda ko'rinmaydi; (2) postavka tarkibi
  (`quantityAccepted`) faqat postavka holati o'zgarganda qayta o'qiladi — keyin chiqarilgan qism yangilanmaydi. Tuzatish: tarkibni
  qabul soni o'zgarganda qayta o'qish va qismni "postavkada (qisman qabul)" deb ko'rsatish.
- [→] B4.55 (**ko'chdi → B5.0b**, ADR-057 Q8) "Chegarada" chegarasi Sozlamalarda (Temur: "statik emas, dinamik"; standart 5%, F13).
- [x] B4.56–B4.60 Sahifalash (ADR-054) boshqa sahifalarga (qoldig'i **ko'chdi → B5.0d**, ADR-057 Q8): **Buyurtmalar, Uzum xarajatlari, Xaridlar, Ombor — qilindi** (quyida,
  B4.56–B4.58 + Xaridlar; Temur bitta PR'da so'radi); qoldi: Foyda tafsiloti (drill-down) va Kargolar.
  ✓ 2026-11-09: har biri `Pagination` bilan: `page` URL'da (filtr/bo'lim/tur o'zgarsa — 1-sahifa), "Sahifada" 20/50/100 umumiy
  (brauzerda eslanadi), "Yana yuklash" olib tashlandi. API: `/sales` va `/expenses` — `page` (offset) rejimi qo'shildi,
  javobda `total`, `page`, `pages`; `cursor` rejimi saqlandi (P&L drill-down va Excel uchun); `/inventory` — `cursor` o'rniga
  `page`/`limit` ≤ 100 (Excel `selection`/`rows_for` orqali sahifalashsiz); `/purchases` — ixtiyoriy `limit` ≤ 100 + `page`
  (`limit` siz — hammasi: Excel va kargoga biriktirish ro'yxati). So'ralgan sahifa oxirgisidan oshsa — API oxirgisini beradi.
  **T:** staging'da Buyurtmalar, Xarajatlar (Uzum), Xaridlar va Ombor sahifalarida sahifa raqamlari va "Sahifada" tanlovini ko'rish.
- [x] B4.62 Tanqidiy tahlil (audit; Temur topshirig'i, 2026-11-10): reja, kod, dizayn va raqobatchilar — `09-audit.md`.
  ✓ 2026-11-11: hamma tekshiruv yashil (pytest 1 248, vitest 598, Playwright 203); 22 sahifa 360 / 1000 / 1440 px da
  skrinshot qilinib o'lchandi; 7 ta Uzum servisi va Sellerboard, sellerdata, MPfact, MPSTATS, TrueStats, UVIX saytlari
  qayta o'qildi. Topildi: hisobda 15 ta (K1–K15; eng jiddiylari — F23 tezlik, F26/F27 holat, ADR-051 ↔ ADR-055),
  xavfsizlik va testda 9 ta, rejada 5 ta, dizaynda 13 ta. Kod o'zgarmadi. **Davomi:** tasdiqsiz tuzatishlar PR-2…PR-8
  (09 §9); formula, reja va katta dizayn o'zgarishlari — Q1–Q14 (09 §8), Temur qaroridan keyin ADR bilan.
  **T:** 09 §8 dagi qarorlar va §10 dagi savollarga javob; staging'da S1–S3 so'rovlari.
- [x] B4.63 Audit, 1-qism — aniq xatolar (09 §9, PR-2: K5, D5, D6, D7); har biriga avval qizaradigan test.
  ✓ 2026-11-11: (1) **Oy prognozi** oy boshidan kechagacha bo'lgan to'liq kunlar bo'yicha (avval bugungi tugamagan kun
  to'liq kun deb sanalardi: soat 10:00 da 1-sanada −60%, 10-sanada −6%); oyning 1-kuni — prognoz yo'q ("Ma'lumot
  yetarli emas"); formula matni yangilandi (`forecast_basis`, `routes/dashboard.py`). (2) **Buyurtmalar → Bekor bo'lish /
  Qaytarilish** 360 px da sahifani 68 / 105 px kengaytirardi (grid ustuni cheklanmagan) — endi jadval o'z ichida skroll
  qiladi; yangi `e2e/orders.spec.ts` (uchala bo'lim, 360 px). (3) **Grafik o'qi:** dona grafigida qadam butun son
  (avval kichik sonlarda "1, 1, 1, 0, 0, 0"). (4) **KPI qiymati** tor kartada so'z o'rtasidan bo'linardi ("1 200 000
  soʻ" / "m") — endi sig'masa butun "soʻm" keyingi qatorga (`KpiValue`; matn o'zgarmaydi). **T:** telefonda
  Buyurtmalar → "Qaytarilish" va SKU sahifasini ko'rish.
- [x] B4.64 Audit, 2-qism — Temur javoblari va o'lchovlar (faqat hujjat): `09-audit.md` §11 (S1–S3 natijasi; Uzum kabineti
  "Daromad" va "Foyda" formulasi — **Foyda = Daromad − faqat komissiya**, haqiqiy sof foydadan ≈ 3,5 barobar baland; soliq;
  xarajat nomlari), ADR-056 (Q3: postavka "keldi" = `dateAccepted`; ADR-051 qisman almashtirildi), ADR-057 (Q1, Q2,
  Q4–Q14), 08 §6 yangilandi. Kod o'zgarmadi. **T:** Q15 — hal qilindi: dinamik soliq profili (ADR-058).
  **Navbatdagi vazifalar** (har biri alohida PR, oldingisi merge bo'lgach; xato tuzatilsa — avval qizaradigan test; 02/04/05
  shu PR ichida yangilanadi):
  - [x] B4.65 (ADR-056) Postavka "keldi" = savdoga chiqarilgan kun (`dateAccepted`), yaratilgan kun emas: `calc.costs.arrival_day`
    (`supplies()` shuni ishlatadi; `Opening.supplied_on`). Yaratilgandan savdoga chiqquncha sotilgan dona — qaytgan eski tovar
    (boshlang'ich narx, belgisiz); `CREATED` postavka kelmagan; `dateAccepted` yo'q `ACCEPTED` (eski qator) — yaratilgan sana.
    02 F41 yangilandi. Test: `test_supply_arrives_when_put_on_sale` (avval qizardi). **T:** deploy'dan bir necha daqiqa keyin
    staging'da ADR-055 dagi SKU (postavka 28.10 yaratilgan → 09.11 savdoga chiqqan): shu oraliqdagi sotuvlarda "Postavka bor,
    partiya kiritilmagan" belgisi yo'qligini ko'rish.
  - [x] B4.66 (Q1) F23 sotuv tezligi: savdodagi kunlar, tovar yoshi < 7 kun qoidasi, yakunlanish ulushi (`inventory.velocity`).
    ✓ 2026-11-12: `upcore.inventory.velocity` — oxirgi 14 ta savdoda bo'lgan kun (60 kungacha orqaga), eng yangi 7 tasi 2× vazn;
    kunlik dona = Yakunlangan + Jarayondagi × F16 R (`DayStat.processing`, `expected`); "7 kunga bo'lish" faqat tovar yoshi
    < 7 kun (`Velocity.new_item`); qaytish darajasi ko'paytiruvchisi olib tashlandi (R ichida). API: `reports.stock` 60 kunlik
    oyna, do'kon bo'yicha R (`completion_by_shop`, 90 kun); `/inventory` → `velocity.completion`, `new_item` (`return_rate`
    o'rniga). 02 F23, UI formula matni (uz, ru). Testlar (avval qizardi): K1 holati (17/kun, 15 kun qoldiqsiz → 17, avval
    4,86), yoshi katta tovarda 3 kunga bo'linishi, Jarayondagi × R; API mustaqil hisob. **T:** kerak emas (Ombor sahifasida
    tezlik va zaxira kunlari o'zgaradi — odatda tezlik ≈ 20% pastroq, tovar qaytgan SKU'larda balandroq).
  - [x] B4.67 (Q2) F26/F27 ikki signal: "Buyurtma berish" va "Uzumga yuborish" (Ombor, Asosiy, Mahsulotlar holati).
    ✓ 2026-11-12: (1) "Buyurtma berish" — F26 holati va F27 buyurtma sanasi hamma joydagi tovardan (Uzum + postavka + o'z
    omborim + yo'lda + Xitoyda; tartiblash ham); "Harakatsiz" faqat Uzumda / postavkada turgan tovar. (2) "Uzumga yuborish" —
    `upcore.inventory.ship_signal` (Uzum + postavka / F23 ≤ "Uzumga topshirish" bosqichi va omborimda bor). API: `/inventory`
    → `ship`, `days_of_stock_all`, `?ship=true` filtri, `totals.ship`; `/dashboard` → `attention.stock_ship`; Excel ustuni.
    Web: Ombor — "Uzumga yuborish" tabi va qatorda belgi ("omborimda N"), F26/F27 izohi; Asosiy "Diqqat talab qiladi" —
    "Uzumga yuborish kerak" bandi, kritik/yuqori matnlari "Buyurtma berish" deb (uz, ru). **Mahsulotlar** sahifasida ombor
    holati yo'q (u yerdagi "Holat" — foyda holati), shuning uchun o'zgarmadi. Testlar: core (K3 misoli, chegara), API (hamma
    joydagi zaxira bilan sana, filtr), web (tab, belgi, URL/API). **T:** kerak emas (Ombor sahifasida Kritik SKU'lar kamayadi —
    yo'ldagi va omborimdagi tovar endi hisobga olinadi; omborida tovari bor SKU'larda "Uzumga yuborish" chiqadi).
  - [x] B4.68 (Q4) Prognoz va "▲ %" da kutilayotgan qism × yakunlanish ulushi, "taxminiy" belgisi.
    ✓ 2026-11-12: `upcore.pnl.compare(..., completion)` — o'zgarish ulushi ikkala davrning kutilgan yakuniy qiymatidan
    (`expected_value`: yakunlangan + Jarayondagi × F16 R), qatorda `estimated`; summalar o'zgarmaydi. API: `/pnl` va `/dashboard`
    `rows[].change_estimated`; oy prognozi asosida Jarayondagi qism × R (`forecast.estimated`). Web: taxminiy o'zgarishda
    "≈" va izoh (Asosiy, Foyda). 02 (M4 davr chizig'i, "▲ %"). Testlar: core (100 000 + 100 000 jarayonda vs 150 000, R 0,5 →
    0%, avval +33%), API (R noma'lum — eskicha; R 0,5 — taxminiy, summalar bir xil), web ("≈"). **T:** kerak emas.
  - [x] B4.69 (Q6) "Taxminiy" belgisi: tayyor sana qoidasi, Markaziy bank kursi — izoh.
    ✓ 2026-11-12: (1) F21 tayyor sana — qabul → kargo to'langan → qabuldan keyingi bosqich ("Uzumga yuborildi" / "Yopildi",
    `Purchase.later_date`); avval qabul belgilanmagan, lekin Uzumga yuborilgan xarid "yo'lda" qolib sotuvlari "Taxminiy" edi
    (K8). (2) Markaziy bank kursi — izoh, taxmin emas (K9): `purchasing.INFO_FLAGS`, `LotCost.estimated`; sotuvda
    `costing.is_estimated` (Markaziy bank kursi va "tarixiy" — aniq) — kunlik agregat va P&L kataklarida taxminiy qism
    (F22) faqat haqiqiy taxmindan. Web: Buyurtmalarda faqat CBU kursli sotuvda "Taxminiy" yo'q, kurs izohda (title).
    02 F21, F22. Testlar: core (CBU yolg'iz — taxmin emas, keyingi bosqich sanasi, `is_estimated`), web. **T:** kerak emas
    (deploy'dan keyin tungi qayta hisobda "Taxminiy" belgilari kamayadi).
  - [x] B4.70 (Q7) Kunlik snapshot har sinxronda; sotuvda "yakunlangan birinchi ko'rilgan vaqt" (migratsiya).
    ✓ 2026-11-12: migratsiya 0020 — `sku_daily.zero_seen`, `sale_items.completed_seen_at`. Mahsulot sinxroni (soatiga) bugungi
    `sku_daily` qatorini yangilaydi (`store.snapshot`; avval faqat 23:50 da — kun o'rtasida o'chgan sinxronda kun snapshotsiz
    qolardi); kun ichida Uzum qoldig'i 0 ko'rilsa `zero_seen` qoladi. Sotuvlar sinxroni Yakunlangan holatdagi, hali belgilanmagan
    qatorlarga birinchi ko'rilgan vaqtni yozadi (`store.mark_completed_seen`); migratsiyadan oldingilari — `NULL` (taxmin yo'q).
    Hisob formulalari o'zgarmadi (F23 hali kun oxiridagi qoldiqdan): bu ma'lumot keyin F34 (tugab qolish yo'qotishi) va
    yakunlanish muddati (S2) uchun. Testlar: sinxron (bugungi qator yangilanadi, 0 belgisi qoladi; birinchi ko'rilgan vaqt bir
    marta). **T:** kerak emas.
  - [x] B4.71 (Q12) Menyuda "Pul oqimi" va "Hisobotlar" yashiriladi.
    ✓ 2026-11-12: `nav.ts` — ikkalasi `NAV_MAIN` dan `NAV_HIDDEN` ga (sidebar, "Yana", Ctrl+K da yo'q); marshrutlari "qurilmoqda"
    sahifasi bilan qoladi (eski havola 404 emas). Tayyor bo'lganda qaytadi (B5.7, B7). Testlar: shell (menyu ro'yxati, eski
    havola). **T:** kerak emas.
  - [x] B4.72 (Q10) Bosh sahifa tartibi (ikkala variant skrinshoti PR'da).
    ✓ 2026-11-12: uch raqam → davr → **Diqqat talab qiladi** → kunlik grafik → zinapoya va KPI guruhlari (`<details>`, yig'iladi,
    sukut bo'yicha ochiq; sarlavha 44 px) → TOP/zarar → tovardagi pul. Telefonda "Diqqat talab qiladi" endi 2-ekranda (avval
    KPI kartochkalari ostida, 7-ekranda — audit D1). 04 §7.2, §7.3. Vizual asoslar yangilandi (home, palette — 1440 va 390 px,
    yorug'/qorong'i; eski va yangi rasm PR diff'ida). **T:** kerak emas (yoqmasa — skrinshot bilan yozish).
  - [x] B4.73 (Q11) Mobil ro'yxat: Mahsulotlar → Ombor → Buyurtmalar (uch PR).
    ✓ 1-PR (2026-11-12) Mahsulotlar: `DataTable` ga umumiy `mobileList` rejimi (≤ 639 px da faqat `mobile` ustunlar + birinchi
    ustun; sarlavha va nom qatorga bo'linadi) — Mahsulotlarda nom, foyda/dona, zaxira kunlari (04 §7.4); bosilsa — SKU sahifasi.
    360 px da jadval gorizontal skrollsiz (avval 1 637 px kontent / 326 ko'rinardi, audit D2). Testlar: ui (`ui-col--extra`),
    e2e (360 px: 3 ustun, jadval ichida ham skroll yo'q).
    ✓ 2-PR (2026-11-12) Ombor: nom, holat (signallar — "Uzumga yuborish" belgisi bilan), zaxira kunlari; amallar ("Xarid
    yaratish", "Hisobdan chiqarish") telefonda nom ostida (amallar ustuni yashirin). 360 px da jadval skrollsiz (avval 1 526 px).
    Testlar: web (tugma ikki joyda — CSS bittasini ko'rsatadi), e2e (360 px: 3 ustun, amal ko'rinadi, skroll yo'q).
    ✓ 3-PR (2026-11-12) Buyurtmalar: sana (ostida holat — holat ustuni telefonda yashirin), SKU (nom qatorga bo'linadi), yalpi
    foyda. 360 px da jadval skrollsiz (avval 1 159 px). Testlar: web (holat ikki joyda — CSS bittasini ko'rsatadi), e2e. **T:**
    telefonda Mahsulotlar, Ombor va Buyurtmalarni ochib ko'rish (yoqmagan joyni skrinshot bilan yozish).
  - [x] B4.74 (Q8, Q9, Q13, Q14) Reja hujjatlari: B4 yopish (B4.27, B4.55, B4.61 → B5 boshi), Telegram B6.1–B6.2 oldinga, rejaga
    qo'shimchalar, 03 §2 va ADR-004 haqiqatga; Uzum API shartlari (Temurdan kabinet matni).
    ✓ 2026-11-12 (ADR-059, ADR-060): B4.27, B4.55, B4.61, sahifalash qoldig'i, B4.76 va B4.81 → **B5.0** (B5 boshi); bosqichlar
    tartibi **B4 → B6.1–B6.2 → B5 → B6.3 →** B7…; PWA (manifest, ikonka) — B6.3; jamoa ekrani va qurilmalar — **B8.0**;
    foydalanish hodisalari — **B8.9**; Uzum API shartlari — Temur vazifasi hozir (B4 "T"); 03 §2 va §9, ADR-004 — o'z CSS
    tokenlari va komponentlari (Tailwind, shadcn, TanStack Table, React Hook Form, Zod, date-fns ishlatilmaydi); README
    "Temurdan kutilmoqda" 6 bandga qisqardi. Ish oqimi (ADR-060): B4 kod qismini Claude mustaqil yakunlaydi — CI yashil bo'lsa
    o'z PR'ini o'zi merge qiladi. **B4 da qoldi (kod):** B4.66–B4.73, B4.75, B4.80; sinovdan keyin — legacy `legacy/` ga.
  - [x] B4.75a (audit PR-3, K7) Soliq hisoblanmaganda halol ogohlantirish: Foyda sahifasida (QQS + foyda yoki Uzum agenti
    rejimi davrda amalda bo'lsa) sariq banner "Soliq hisoblanmadi" + Sozlamalarga havola; Sozlamalardagi rejim yordam matni
    to'g'rilandi (avval "oylik taxmin sifatida hisoblanadi" deb yolg'on yozilgan edi). `upcore.tax.uncalculated_regimes` (F11),
    `/pnl` javobida `untaxed_regimes`. **Davomi:** dinamik soliq profili (Temur, 2026-11-11) — alohida ADR bilan.
    **T:** staging'da Foyda sahifasida (agar rejim QQS + foyda yoki agent bo'lsa) bannerni ko'rish.
  - [ ] B4.75 (audit §9) PR-4…PR-8: bosish maydoni 44 px, xavfsizlik/CI, hujjat va o'lik kod, test qamrovi, jadval kengliklari
    va favicon.
  - [x] B4.75b (CI) E2E job'ida brauzer apt'siz o'rnatiladi; apt tizim paketlari ixtiyoriy (2 urinish, keyin ogohlantirish):
    2026-11-11 da runner'dan Ubuntu arxivi ochilmay, main, #135 va #136 testlarsiz qizardi. Paketlar faqat qo'shimcha shriftlar —
    ularsiz e2e va skrinshotlar bir xil o'tishi tekshirildi.
  - [x] B4.77a Dinamik soliq profili — dizayn (faqat hujjat, ADR-058; Temur talabi 2026-11-11): 02 F11 qayta yozildi, 03, 08 §6 (BHM 440 000
    — 2026-09-01 dan; manbalar), 09 §11.5 (Q15 hal).
  - [x] B4.77 Dinamik soliq profili, 1-bosqich: yadro va baza (ilova xatti-harakati o'zgarmadi) — migratsiya 0018: `tax_lines`
    (CHECK `shape`: foizli — stavka 0–100, qat'iy — summa yoki BHM sonidan aynan bittasi; nom profil ichida unikal), `ref_amounts`
    (BHM 412 000 / 440 000 — sana bo'yicha, `seed_reference`); `upcore.tax`: `TaxLine`, `profile_lines` (eski profil → qatorlar),
    `percent_rules`, `fixed_daily` (n × BHM yoki summa, oy / chorak / yil, kunlarga kumulyativ yaxlitlash — har qanday ketma-ket
    kunlar yig'indisi aniq; BHM noma'lum — `None`, 0 emas), `amount_on`. Golden testlar (YaTT: 1% + 1 BHM; oy chegarasida BHM
    412 000 → 440 000; chorak, yil; qisman oy; profil almashishi), DB testlari (CHECK, cascade, seed, RLS).
  - [x] B4.78 Soliq profili: hisob varag'i (P&L). `upcore.pnl`: bir necha foizli qator (`TaxRules`, `Cell.tax_by`), qat'iy qatorlar
    o'z xarajati (F10) mexanizmi bilan kataklarga taqsimlanadi (`tax:<nom>` toifasi), lekin `Statement` da "Soliq" ostiga o'tadi
    (`tax_lines`; `own_expenses` va `direct_total` ga kirmaydi; sof foyda o'zgarmas formula bilan); `rows()` da bir necha qator
    bo'lsa `tax:<nom>` tarqatma qatorlari. `upcore.tax`: `daily_rules`, `fixed_expenses` (eski `daily_rule` olib tashlandi).
    API: `reports/cells.py` profillarni qatorlari bilan va BHM ni `ref_amounts` dan yuklaydi; `/pnl` da `tax_missing_bhm` (BHM
    yo'q kunlar — hisoblanmadi va aytiladi). Web: Foyda sahifasida "Soliq" ostida qatorlar, BHM ogohlantirishi. Qatorsiz
    profillar eskicha ishlaydi (ilova natijasi o'zgarmaydi — qatorlar API/UI orqali B4.79 da kiritiladi). Testlar: core
    (`test_tax_pnl.py`), API (`tax_lines`, BHM bayrog'i), web. **T:** yo'q (qatorlar hali kiritilmaydi).
  - [x] B4.79 Soliq profili: API va ko'chirish (UI yo'q). Sozlamalar javobida profil `lines` va `tax_amounts` (joriy BHM);
    `POST/PATCH /tax-profiles` da `lines` (berilsa qatorlar to'liq almashadi, `[]` — o'chadi, berilmasa o'zgarmaydi; qatorlar
    faqat aylanma rejimida, rejim almashsa ketadi; tekshiruv `upcore.tax` bilan bir xil: shakl, takror nom, ko'pi bilan 10 ta;
    qatorlari bor profilda eski stavka ustuni nol). Migratsiya 0019: stavkasi > 0 aylanma profillar bitta foizli qatorga
    ("Aylanmadan soliq") ko'chadi — hisob natijasi o'zgarmaydi. Testlar: API (yaratish, almashtirish, tekshiruv, cascade,
    audit, ruxsat), migratsiya (ko'chirish, orqaga qaytish). **T:** yo'q (UI keyingi vazifada).
  - [x] B4.79b Soliq profili: Sozlamalar UI. Aylanma rejimida endi **soliq qatorlari muharriri** (`TaxLinesEditor`): foizli (stavka,
    baza) yoki qat'iy (so'm yoki BHM soni; oy / chorak / yil) qatorlar, qo'shish / o'chirish (ko'pi bilan 10), takror nom va
    to'ldirilmagan qator saqlashga yo'l qo'ymaydi; **tayyor shablonlar** — YaTT (aylanmadan foiz + 1 BHM ijtimoiy soliq),
    MChJ aylanmadan, bo'sh (stavkalar `tax_rates` ma'lumotnomasidan, BHM soni — shablon standarti, tahrirlanadi); BHM qiymati
    ma'lumotnomadan ko'rsatiladi (UI hisoblamaydi); jadvalda profil qatorlari ro'yxati. Qatorsiz eski aylanma profili
    tahrirlanganda bitta foizli qatorga aylanadi. 360 px da gorizontal skroll yo'q (e2e), axe (jiddiy buzilish yo'q), uz/ru.
    **Tuzatish (staging'da topildi, 2026-11-11):** (1) deploy `seed` ni ishga tushirmaydi (u faqat dev) — `ref_tax_rates` va
    `ref_amounts` stagingda bo'sh edi: YaTT shablonida stavka bo'sh qolib "Saqlash" o'chiq turardi, BHM noma'lum bo'lib soliq
    hisoblanmasdi. Endi ma'lumotnoma = bazadagi yozuv + `upcore` boshlang'ich qiymatlari (bazadagi ustun; xarajat kodlari
    kabi): Sozlamalar (`tax_rates`, `tax_amounts`) va hisob (`bhm_values`). (2) shablon tanlangach tanlov "Tanlang…" ga
    qaytib, hech narsa tanlanmagandek ko'rinardi — endi tanlangan shablon va "Shablon qo'llandi: N ta qator" xabari ko'rinadi.
    **T:** staging'da Sozlamalar → Soliq profili → "Profil qo'shish" → shablon "YaTT" (stavka 1% va 1 BHM) → saqlash;
    keyin Foyda sahifasida "Soliq" ostida "Aylanmadan soliq" va "Ijtimoiy soliq" qatorlarini ko'rish (o'z sofi foydang bilan
    solishtirib).
  - [ ] B4.80 Yillik tushum chegarasi ogohlantirishi (80% / 100%; YaTT 1 mlrd, MChJ 12 000 BHM, o'zini o'zi band qilgan 100 mln) — Asosiy va Sozlamalarda.
  - [→] B4.81 (**ko'chdi → B5.0e**, ADR-059) 2-bosqich: QQS va foyda solig'i oylik hisobi (kirim QQS, `profit_before_tax` bazasi), shablon "MChJ umumbelgilangan".
  - [→] B4.76 (**ko'chdi → B5.0f**, ADR-059) Kabinet bilan solishtirish (taklif): Foyda sahifasida "Uzum kabineti ko'rsatadigan" qator (09 §11.3) — Temur
    ko'rgach.
- T: boshlang'ich holatni kiritish (`/opening`: sana, har tovarga tannarx, o'z omboridagi qoldiq) va yo'ldagi partiyalarni
  Xaridlarga kiritish (ADR-033; 2 ta legacy partiyani kiritish shart emas); 14 kun faqat yangi dasturda ishlash; topilgan
  har noqulaylikni yozib yuborish.
- T (ADR-057 Q8, Q13): **14 kunlik sinovni boshlash** (kundalik ish faqat staging'da; xato yoki noqulaylik — skrinshot bilan bir
  qator); Uzum API'ni uchinchi tomon ishlatishi shartlari — kabinetdagi matn (Q13).

**Chiqish:** Temur 14 kun faqat yangi dasturdan foydalangan; kritik xato yo'q; legacy `legacy/` papkaga ko'chirildi.

## B5. Ustunlik funksiyalari — 12–18 kun

Tartib (ADR-057 Q9): B5 dan oldin **B6.1–B6.2** (Telegram kunlik xulosa) bajariladi; B6.3 — B5 dan keyin.

- [ ] B5.0 B4 dan ko'chganlar (ADR-057 Q8, ADR-059) — B5 boshida, shu tartibda:
  - [ ] B5.0a (avval B4.27) "Yo'qotishlar va imkoniyat" bloki (ADR-043 (5), AI'siz, formula bilan).
  - [ ] B5.0b (avval B4.55) "Chegarada" chegarasi Sozlamalarda (standart 5%, F13).
  - [ ] B5.0c (avval B4.61) Ombor: postavka tarkibi va qisman chiqarish (ADR-055 §3).
  - [ ] B5.0d (avval B4.56–B4.60 qoldig'i) Sahifalash: Foyda tafsiloti (drill-down) va Kargolar (ADR-054).
  - [ ] B5.0e (avval B4.81) Soliq, 2-bosqich: QQS va foyda solig'i oylik hisobi, shablon "MChJ umumbelgilangan" (ADR-058).
  - [ ] B5.0f (avval B4.76, taklif) Foyda sahifasida "Uzum kabineti ko'rsatadigan" qator (09 §11.3) — Temur ko'rgach.
- [ ] B5.1 Yetkazib beruvchilar va kargo kompaniyalari; muddatlarni o'rganish (F25).
- [ ] B5.2 Buyurtma rejasi (F23–F27): tavsiya miqdor, CNY va so'm byudjeti, rejadan xarid yaratish.
- [ ] B5.3 FBO yuborish rejasi + Excel; postavkalar: e'lon va qabul, kamomad (F33), bog'liq jarima.
  ADR-050: Excel — Uzum kabineti shablonida (shtrix-kod, tannarx, dona); xarid ↔ postavka SKU bo'yicha avtomatik bog'lanish
  (FIFO, qo'lda almashtirish), xarid sahifasida "Uzumga yuborildi / qabul qilindi / kamomad"; o'z omborimni postavkalar bo'yicha
  hisoblash (ADR-034 qoldig'i).
- [ ] B5.4 Yo'qolgan tovar (F31) + kompensatsiya (F32); nelikvid (F30); muzlagan pul (F29); yo'qotilgan foyda (F34).
- [ ] B5.5 Reklama tahlili (DRR, ACOS, SKU bo'yicha), ABC/XYZ, hafta kuni × soat issiqlik xaritasi.
- [ ] B5.6 Davrlarni solishtirish barcha hisobotlarda.
- [ ] B5.7 Pul oqimi (M11): hisoblar, tranzaksiyalar, Uzum to'lov prognozi (F38), 90 kunlik kalendar (F39).
- [ ] B5.8 Reja-fakt (M12).
- [ ] B5.9 Kalkulyator (M13) + ochiq versiya komponenti (landing uchun).
- [ ] B5.10 FBS (do'konda bo'lsa): faol buyurtmalar va muddatlar; FBS qoldig'i — o'z omborim manbasi, ikki marta sanash yo'q
  (ADR-034, 3-qadam); keyin DBS va mahalliy xarid (bozor, o'z ishlab chiqarishi) uchun soddalashtirilgan xarid bosqichlari.
- T: yetkazib beruvchi va kargo ma'lumotlarini kiritish; har funksiyani real ma'lumotda sinab ko'rish.

**Chiqish:** har funksiya Temurning real ma'lumotida tekshirilgan, yordam maqolasi yozilgan.

## B6. Bildirishnomalar va Telegram — 5–7 kun

Tartib (ADR-057 Q9): B6.1–B6.2 — B4 dan keyin, B5 dan **oldin**; B6.3 — B5 dan keyin.

- [ ] B6.1 Hodisalar katalogi (M15), qoidalar, chegaralar, tinch soatlar, dublikatsiz yuborish.
- [ ] B6.2 Telegram bot (aiogram): bog'lash, kunlik/haftalik xulosa, buyruqlar, "Batafsil" havolalar.
- [ ] B6.3 Ilova ichidagi bildirishnomalar markazi; web push (PWA). PWA (ADR-057 Q13, 09 R3 a): `manifest`, ikonkalar, favicon,
  `theme-color` — o'rnatiladigan ilova.
- T: botni Telegram'da sinash, kunlik xulosa vaqtini tanlash (bot B2 da yaratilgan).

**Chiqish:** Temur 7 kun kunlik xulosa oladi, raqamlar ilova bilan bir xil, keraksiz xabar yo'q.

## B7. Import va hisobotlar — 4–6 kun

- [ ] B7.1 Excel import: tannarx, xaridlar, o'z xarajatlari, eski Uzum hisobotlari (API bermagan davr uchun).
- [ ] B7.2 Oylik PDF hisobot, buxgalter paketi, rejalashtirilgan yuborish.
- [ ] B7.3 To'liq eksport (ZIP).
- T: mart–aprel (API bermagan davr) uchun Uzum kabinetidan hisobot faylini yuborish.

**Chiqish:** Temurning eski hisoboti import qilinib, "Hammasi" davri do'kon ochilgan oydan boshlanadi.

## B8. SaaS tayyorgarlik — 10–15 kun

- [ ] B8.0 (ADR-057 Q13, 09 R3 b–c) Jamoa ekrani (`/members`, `/invites` — API bor, UI yo'q), "Qurilmalarim" va
  "Hamma qurilmadan chiqish" (M1).
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
- [ ] B8.9 (ADR-057 Q13, 09 R3 e) Foydalanish hodisalari (`events`): B9.4 o'lchovlari uchun — aktivatsiya, haftalik faollik,
  birinchi foyda vaqti.
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
