# 03. Arxitektura va texnik dizayn

Qarorlarning sabablari 07-qarorlar.md (ADR) da. Bu fayl — qanday quriladi.

## 1. Umumiy ko'rinish

```
 Brauzer / telefon (PWA)            Telegram
        │ HTTPS                         │
        ▼                               ▼
   ┌─────────┐   /api/*   ┌──────────────────┐        ┌───────────────┐
   │  Caddy  │──────────▶ │  api (FastAPI)   │◀──────▶│  PostgreSQL   │
   │ (TLS,   │            └──────────────────┘        │  (+RLS, jobs) │
   │ statik) │──▶ web (React build, statik fayllar)    └───────┬───────┘
   └─────────┘                                                 │
                           ┌──────────────────┐                │
                           │ worker           │◀───────────────┤  (Procrastinate navbati)
                           │ (sinxron, hisob, │                │
                           │  bildirishnoma)  │──▶ Uzum Seller OpenAPI (faqat O'zbekistondagi serverdan)
                           └──────────────────┘──▶ cbu.uz (kurslar)
                           ┌──────────────────┐                │
                           │ bot (aiogram)    │◀───────────────┘
                           └──────────────────┘──▶ Telegram Bot API
   Zaxira: PostgreSQL → shifrlangan nusxa → boshqa provayderdagi S3 (O'zbekistonda)
   Kuzatuv: GlitchTip (xatolar), Uptime Kuma (ishlayaptimi), JSON loglar
```

Hammasi bitta serverda Docker Compose bilan boshlanadi (staging va production alohida serverlar). O'sganda
avval PostgreSQL alohida serverga/DBaaS'ga, keyin worker'lar ko'paytiriladi.

## 2. Texnologiyalar

| Qatlam | Tanlov | Izoh |
|---|---|---|
| Til (backend) | Python 3.13 | Temurning bilimi; legacy domen mantig'i Python'da |
| Web freymvork | FastAPI + Pydantic v2 | OpenAPI avtomatik → frontend tiplari |
| ORM / DB | SQLAlchemy 2 (async) + asyncpg, Alembic | migratsiyalar majburiy |
| Ma'lumotlar bazasi | PostgreSQL 18 | RLS, jsonb, `timestamptz` |
| Fon ishlari | Procrastinate (PostgreSQL ustida navbat) | qulflar (bir kalit — bir navbat), davriy ishlar, qayta urinish. Zaxira variant: ARQ + Redis (ADR-003) |
| HTTP mijoz | httpx (async) | timeout 30 s |
| Telegram | aiogram 3 | alohida servis |
| Excel / PDF | openpyxl / WeasyPrint | server tomonda |
| Shifrlash | cryptography (AES-256-GCM), argon2-cffi | kalit versiyalari bilan |
| Paket boshqaruvi | uv (lock fayl) | |
| Sifat | ruff (lint+format), mypy (core: strict), pytest, hypothesis | |
| Frontend | TypeScript, React 19, Vite | SPA + PWA |
| Marshrut / server holati / jadval | TanStack Router, TanStack Query, TanStack Table | URL'dagi filtrlar tiplangan |
| UI | Tailwind CSS v4 + shadcn/ui (Radix) | komponentlar o'zimizda, dizayn tokenlari bilan |
| Grafiklar | Apache ECharts (o'z temamiz) | sharshara, issiqlik xaritasi, kalendar |
| Formalar | React Hook Form + Zod | |
| Til | i18next (uz-Latn, uz-Cyrl, ru) | |
| Sana | date-fns (+ uz locale) | |
| API tiplari | openapi-typescript + openapi-fetch | backend sxemasidan generatsiya |
| Frontend test | Vitest, Testing Library, Playwright, axe-core | vizual regressiya |
| Paket boshqaruvi (web) | pnpm, Node 24 LTS | |
| Landing va yordam markazi | Astro (statik, uz/ru), yordam maqolalari Markdown'da | qidiruv tizimlari uchun; ochiq kalkulyator React komponenti sifatida (ADR-023) |
| Infra | Docker, Docker Compose, Caddy, GitHub Actions, GHCR | |
| Kuzatuv | GlitchTip (self-hosted), Uptime Kuma, structlog | PII chet elga chiqmaydi |

Versiyalar B0 da aniq qotiriladi (lock fayllar) va faqat ataylab yangilanadi (Dependabot PR).

## 3. Repozitoriy tuzilishi (monorepo)

```
uzum-profit/
  CLAUDE.md                ← har sessiya shu yerdan boshlanadi
  docs/plan/               ← shu reja
  uzum_profit/, tests/     ← LEGACY ilova (B4 oxirigacha shu yerda, keyin legacy/ ga)
  packages/core/           ← sof domen: formulalar, tannarx, P&L, ombor (IO yo'q)
    src/upcore/ ...
    tests/
  apps/api/                ← FastAPI + worker + migratsiyalar
    src/upapi/{main.py, settings.py, db/, auth/, uzum/, sync/, routes/, services/, jobs/, notify/}
    migrations/            ← Alembic
    tests/
  apps/bot/                ← Telegram bot
  apps/web/                ← React ilova
    src/{routes/, features/<modul>/, components/ui/, components/charts/, lib/{api,format,i18n}/, styles/}
  apps/landing/            ← Astro: landing, narxlar, ochiq kalkulyator, yordam markazi (content/help/{uz,ru}/*.md)
  infra/
    compose/{dev,staging,prod}.yml, Caddyfile, backup/, glitchtip/, uptime/
  .github/workflows/{ci.yml, deploy-staging.yml, deploy-prod.yml}
```

Paket nomlari vaqtinchalik (`upcore`, `upapi`); brend nomi tanlangach (Q1) o'zgartirilmaydi — ichki nom.

## 4. Domen yadrosi (`packages/core`)

- Faqat sof funksiyalar va dataclass'lar: kirish → chiqish. Bazaga, tarmoqqa, vaqtga (now) murojaat yo'q.
- Modullar: `money` (Decimal, valyuta, yaxlitlash), `fx`, `metrics` (F3–F19, F35–F36), `expenses`
  (kod normallashtirish va toifa), `purchasing` (komponentlar, taqsimot F20), `costing` (lot dvigateli F21–F22),
  `pnl` (hisobot qatorlari, kesimlar, F15–F16), `inventory` (F23–F34), `tariffs` (F37, F40), `tax` (F11),
  `cash` (F38–F39).
- Har formula funksiyasi docstring'ida F-raqami. Formulalar faqat shu yerda — API va frontend ularni qayta yozmaydi.
- Testlar: har formula uchun misol testlari (02 dagi misollar), hypothesis xossa testlari (masalan: taqsimot
  yig'indisi = komponent summasi; FIFO va o'rtacha bitta lotda bir xil natija; qayta hisoblash idempotent),
  legacy bilan solishtirish (bir xil usulda bir xil natija).

## 5. Ma'lumotlar modeli (PostgreSQL)

Har tashkilot jadvalida `org_id uuid not null` + RLS siyosati. Pul `numeric(18,2)` (so'm), `numeric(18,4)`
(valyuta), kurs `numeric(18,6)`. Vaqt `timestamptz`. Sotuvchi kiritgan yozuvlar o'chirilmaydi, `deleted_at` bilan
yashiriladi. Uzum'dan kelgan yozuvlarda `raw jsonb`.

RLS qoidalari (B2.2, `apps/api/src/upapi/db`): ilova `up_app` roli bilan ulanadi — superuser emas, `BYPASSRLS`
yo'q, jadvallar egasi emas (egasi — migratsiya roli); jadvallarda `FORCE ROW LEVEL SECURITY`. Tashkilot ichidagi
bog'lanishlar kompozit FK `(org_id, x_id) → x (org_id, id)` (FK tekshiruvi RLS'ni chetlab o'tadi), unikal kalitlar
`org_id` bilan boshlanadi, `TRUNCATE`/`REFERENCES`/`TRIGGER` berilmaydi, `app.org_id` bo'sh bo'lsa hech narsa
ko'rinmaydi. Global ma'lumotnomalar — faqat o'qish; kirish jadvallari (sessiyalar, kodlar) ilova roliga
berilmaydi; `audit_log`, `events` — faqat qo'shish. Har jadval uchun o'qish/o'zgartirish/o'chirish/qo'shish
testlari `apps/api/tests/test_rls.py` da (CI'da PostgreSQL 18). Ilova `asyncpg`, migratsiya va testlar `psycopg`.

**Tashkilot va kirish:** `orgs` (nomi, STIR, til, vaqt mintaqasi, tannarx usuli), `users` (telefon E.164 unikal),
`memberships` (org, user, rol), `invites`, `sessions` (token xeshi, qurilma, muddat), `otp_codes`
(kod xeshi, urinishlar), `audit_log` (oldin/keyin jsonb).

**Marketplace:** `mp_accounts` (provayder, shifrlangan token + kalit versiyasi + oxirgi 4 belgi, holat:
faol / yaroqsiz / kvota tugagan / WAF / uzilgan — uzilganda kalit ustunlari NULL, `token_state` cheklovi; kvota qoldig'i;
ketma-ket kalit xatolari, sinxron pauzasi), `shops` (tashqi id, nomi, taxallus, rang, faol,
tarix holati, birinchi sotuv sanasi), `sync_state` (do'kon × tur: oxirgi muvaffaqiyat va urinish, holat, xato,
ketma-ket xatolar, kursor), `sync_runs` (boshlanish, tugash, holat, olingan/yozilgan/jami, so'rovlar, kim boshlagan,
usul, xato kodi, HTTP kod), `provider_health` (tizim jadvali: Uzum uzilishi holati), Procrastinate navbat jadvallari
(`procrastinate_*`, tashkilotsiz — ish argumentlarida faqat id'lar).

**Katalog:** `items` (bizning tovar: nom, rasm, vazn, o'lchamlar), `mp_products`, `mp_skus` (tashqi sku id,
barkod, artikul, IKPU, narx, komissiya %, qoldiqlar: active/fbs/defected/pending, sotilgan, qaytgan, `avgdsales`,
rank, saqlash narxi, holat, `item_id`), `sku_daily` (kunlik snapshot: qoldiqlar, narx, komissiya).

**Uzum faktlari:** `sale_items` (unikal: shop, order_id, id; holat, sana, topshirilgan vaqt, narx, dona, komissiya,
logistika, `sellerProfit`, `amountReturns`, `returnCause`, `purchasePrice` — faqat ma'lumot uchun, ADR-016; SKU nomi
`skuTitle` — `mp_skus.sku_code` = `skuFullTitle` bilan bog'lanadi), `mp_expenses`
(tashqi id unikal; asl va normallashtirilgan kod, toifa, status, summa, tur, sanalar, bog'langan buyurtma/sotuv),
`expense_codes` (global lug'at: kod → toifa, nomlar uz/ru, P&L'ga kiradimi), `fbo_invoices` + `fbo_invoice_items`,
`mp_returns` + `mp_return_items`, `fbs_orders` [B5] (xaridor shaxsiy ma'lumoti SAQLANMAYDI).

**Xarid va ombor (sotuvchi kiritadi):** `suppliers`, `carriers`, `purchases` (holat va bosqich sanalari,
`legacy_batch_id`), `purchase_lines` (tovar yoki vaqtinchalik nom/havola/rasm, variant, buyurtma va qabul donasi,
narx, valyuta, dona vazni/hajmi), `cost_components` (tur, summa, valyuta, to'lov sanasi, hisob, kurs rejimi
va qiymati, yechilgan summa, taqsimot asosi, tegishli qatorlar, qo'lda ulushlar), `stock_moves` (o'z ombor
harakatlari: qabul, Uzumga o'tkazish, tuzatish, hisobdan chiqarish), `fx_rates` (sana, valyuta, kurs, manba).

**Hosila (hisoblangan) jadvallar:** `lots` (xarid qatoridan: effektiv sana, dona, birlik tannarx, belgilar),
`sale_costs` (sotuv qatori → birlik tannarx, COGS, usul, belgilar, lot taqsimoti jsonb), `daily_sku_metrics`
(org × do'kon × sku × sana: tushum, dona, komissiya, logistika, COGS, reklama, qaytish, bekor — bosh sahifa va
P&L tezligi uchun). Hosila jadvallar istalgan payt qayta qurilishi mumkin (manba jadvallardan).

**Pul:** `cash_accounts`, `transactions`, `expense_categories`, `manual_expenses` (takrorlanish, amortizatsiya,
taqsimot), `payout_schedules` (do'kon, jadval turi, amal qilish sanasi), `goals`.

**Sozlama va ma'lumotnoma:** `tax_profiles` (org, rejim, stavka, baza, sanadan), `ref_logistics_tariffs`
(sanadan, qoidalar jsonb), `ref_tax_rates`, `fee_waivers` — Uzum bonus davrlari (do'kon yoki NULL — hammasi, sanalar, bepul turlar, sabab,
manba: qo'lda / taklifdan, rad etilgan taklif `dismissed_at`; ADR-031; 0008 da `free_logistics_periods` o'rniga).

**Bildirishnoma:** `notification_channels` (telegram chat_id, push endpoint), `notification_rules`
(hodisa, yoqilgan, parametrlar, tinch soatlar), `notifications` (`dedupe_key` unikal, holat).

**To'lov (bizning tarif):** `plans`, `subscriptions` (sinov / faol / qarzdor / faqat o'qish / bekor),
`billing_invoices` (fiskal chek havolasi), `payments`.

**Mahsulot analitikasi:** `events` (ichki hodisalar: ro'yxatdan o'tdi, kalit uladi, tannarx kiritdi ...).

## 6. Uzum integratsiya qatlami

- **Provayder interfeysi** `MarketplaceProvider`: `shops()`, `sales(since)`, `expenses(since)`, `catalog()`,
  `supplies()`, `supply_items(id)`, `returns(since)`, `fbs_orders(...)`. Uzum — birinchi realizatsiya.
  Yandex/WB/Ozon keyin shu interfeysga qo'shiladi.
- **Mijoz:** async httpx; sarlavha `Authorization: <kalit>` ("Bearer"siz); timeout 30 s; javob sarlavhalaridan
  `x-ratelimit-remaining-per-day` saqlanadi.
- **Xato turlari:** `AuthError` (JSON 401/403, `404 Token not found`), `WafBlocked` (HTML 403), `BurstLimited`
  (429, kunlik qoldiq > 0), `QuotaExhausted` (429, kunlik qoldiq 0), `UpstreamError` (5xx, tarmoq — 0,8 → 1,6 →
  3,2 s, ko'pi bilan 4 urinish), `BadRequest` (400 — qayta urinilmaydi).
- **Tezlik:** kalit bo'yicha bitta navbat (Procrastinate `lock = account_id`), so'rovlar orasida ≥ 450 ms;
  ustuvorlik: foydalanuvchi amali > fon; kunlik qoldiq < 10 000 bo'lsa fon ishlari to'xtaydi.
  B2.5 (`upapi.uzum`): jarayon ichidagi navbat `RateLimiter` (kalit = akkaunt id, `UP_UZUM_MIN_INTERVAL_SECONDS`,
  kutayotgan foydalanuvchi so'rovi fondan oldin o'tadi); jarayonlar orasida — Procrastinate qulfi. API jarayonidagi
  foydalanuvchi so'rovi (kalit tekshiruvi) ishchi bilan bir vaqtga to'g'ri kelishi mumkin — sekundlik 429 qayta
  urinish bilan yopiladi. Kvota: har javobdagi qoldiq `on_quota` orqali akkauntga; qoldiq `UP_UZUM_QUOTA_RESERVE`
  dan kam bo'lsa fon so'rovi yuborilmaydi (`QuotaReserved`).
- **Sahifalash va xom JSON (B2.5):** har sahifa `Page` — Uzum javobi o'zgarishsiz (`raw`), qatorlar (`rows`, id
  bo'yicha takrorsiz), jami, `has_more`. Birinchi sahifada 400 bo'lsa kichikroq hajm; jami soni bor endpointda Uzum
  hajmni jimgina kessa haqiqiy hajm aniqlanadi. Javob shakllari testlari — yozib olingan kassetalarda
  (`apps/api/tests/fixtures/uzum`, `scripts/record_uzum.py`: Temurning Mac'ida, anonimlashtirilgan).
- **Upsert qoidalari:** tabiiy kalitlar (03 §5), faqat Uzum bergan ustunlar yangilanadi, `NULL` bilan ustidan
  yozilmaydi; bir partiyada dublikat kalit bo'lsa yozishdan oldin birlashtiriladi.
- **Sinxron ishlari** (Procrastinate davriy): 02-funksiyalar.md M3 jadvalidagi chastotalar; do'konlar eng eski
  yangilanganidan boshlab aylantiriladi; har ish `sync_runs` ga yoziladi (0 ta obyekt bilan tugagan ish ham
  ogohlantirish).
  B2.6 (`upapi.sync`): `sync.tick` (har daqiqa) ulangan akkauntlar uchun `sync.account` ishini qo'yadi
  (`queueing_lock` — navbatda bitta; `lock = account:<id>` — bitta kalitga bitta ish; ustuvorlik: "Hozir yangilash" 10,
  kalit ulandi 5, jadval 0). Akkaunt ishi vaqti kelgan turlarni (`UP_SYNC_INTERVALS`; snapshot — Toshkent 23:50 dan
  keyin kuniga bir marta) bajaradi; do'konlar va qaytarishlar butun akkaunt bo'yicha bir so'rov. Sotuv va xarajat
  usullari: **tarix** (birinchi marta 2020-01-01 dan, rad etilsa 1825/1095/730/365/180/100 kun — do'konda "full" /
  "limited:N"; uzilsa kursordagi sahifa va hajmdan davom), **inkremental** (3 kun yoki oxirgi muvaffaqiyatdan 1 kun
  oldin), **chuqur** (kuniga bir marta 45 kun), **uzilish** (tiklangach uzilish davri). Postavka tarkibi — yangi yoki
  holati o'zgargan postavka uchun bir marta (ishda ko'pi bilan 100 ta). Ishchi `up_app` bilan ulanadi; tashkilotlar
  bo'ylab ro'yxat faqat `sync_accounts()` orqali (`SECURITY DEFINER`, egasi `up_sync`, faqat id'lar — 0004).
  Ishchi: `python -m upapi.worker` (migratsiyagacha kutadi; API kabi xavfli sozlama va DB rolida ishga tushmaydi).
- **Xato → akkaunt holati (B2.6):** ketma-ket `UP_SYNC_AUTH_FAILURES` (3) kalit xatosi → "yaroqsiz" (audit), WAF va
  kunlik kvota → holat, `UP_SYNC_PROBE_MINUTES` (30) da bitta sinov, muvaffaqiyatda "faol"; kvota zaxirasi → fon ishi
  "skipped"; 400 va kutilmagan javob — faqat shu tur xatosi. Kunlik qoldiq har ishda birinchi javobdan olinadi
  (saqlangan qiymat eskirgan bo'lishi mumkin). Kalit tekshiruvi yoki almashtirish xatolar hisobini tozalaydi.
- **Uzilish rejimi:** ko'p do'konda bir vaqtda tarmoq xatosi → 15 daqiqa umumiy pauza, vaqti-vaqti bilan bitta
  sinov; tiklangach uzilish davri chuqur sinxron. B2.6 (`upapi.sync.health`, `provider_health`): 5 daqiqa ichida
  `UP_SYNC_OUTAGE_SHOPS` (2) ta do'konda tarmoq/5xx → uzilish; pauza tugagach birinchi ish sinov huquqini oladi
  (`FOR UPDATE`), muvaffaqiyatda uzilish davri saqlanadi va keyingi sotuv/xarajat ishida to'ldiriladi.
- **"Ma'lumotlar holati" API (B2.6):** `GET /orgs/{id}/sync` — do'kon × tur (oxirgi muvaffaqiyat/urinish, oxirgi
  ish: holat, usul, olingan/yozilgan/jami, xato kodi, HTTP kod), akkaunt holati va kvota, uzilish, "yashil" (24 soat
  xatosiz va sotuvlar 24 soat ichida yangilangan), `freshness`; `POST /orgs/{id}/sync/refresh` — "Hozir yangilash"
  (tashkilot bo'yicha 60 s da bir marta, uzilishda 503). Har a'zo uchun.
- **Sinxrondan keyin:** o'zgargan tovarlar uchun tannarx qayta hisob (F21), `daily_sku_metrics` yangilanadi,
  bildirishnoma qoidalari tekshiriladi.

## 7. Tannarx dvigateli (lot)

1. Xarid o'zgarganda: `lots` qayta quriladi (F20).
2. Tovar bo'yicha hodisalar yig'iladi: lotlar (+), sotuvlar (Yakunlangan va Jarayonda, −), sotuvga yaroqli
   qaytishlar (+), brak/yo'qotish (−).
3. Tashkilot usuli (FIFO / o'rtacha) bo'yicha har sotuvga birlik tannarx va belgilar yoziladi (`sale_costs`).
4. Qayta hisob faqat o'zgargan tovarlar uchun, eng erta o'zgargan sanadan. Natija o'zgargan sotuvlar bo'yicha
   P&L'da "qayta hisoblandi" belgisi (oxirgi 7 kun ko'rinadi).
5. Qaytish va qisman bekor semantikasi B2.11 da real ma'lumot bilan tasdiqlanadi va testga yoziladi.
6. Tezlik: 10 000 sotuvli tovar uchun qayta hisob < 1 s (benchmark testi).
7. B2.8 (`upapi.calc`): manba o'zgarganda shu tranzaksiyada `recalc_queue` ga so'rov (`purchase`, `item`, `shop` +
   kun, `metrics` + kun); `calc.org` ishi (Procrastinate, `lock = calc:<org>`) navbatni `FOR UPDATE` bilan oladi,
   bitta tranzaksiyada lotlar → `sale_costs` → `daily_sku_metrics`. Tovar ichida doim to'liq hisoblanadi (keyingi
   lot "erta sotuv" orqali oldingi sotuvga ta'sir qiladi), bazaga faqat farqlar yoziladi; COGS o'zgarsa
   `changed_at`/`previous_cogs`. `amount` qaytganlarsiz (F18), shuning uchun qaytish hodisasi yo'q; hisobdan
   chiqarish — `stock_moves` (`writeoff`, manfiy `adjust`). `calc.nightly` — to'liq qayta qurish (kurs arxivi kech
   kelsa ham). Benchmark: 10 000 sotuvli tovar bazasi bilan < 3 s.
8. Boshlang'ich holat (B4.12, F41, ADR-033): `orgs.cost_start_on`, `item_costs` (tovar, `valid_from`, narx),
   `opening_stock` (tovar, Uzumda, o'z omborimda). Sana bo'lsa — undan oldingi sotuvlar tarixiy narxda (lotsiz),
   boshlang'ich qoldiq birinchi lot, oldingi lotlar ishlatilmaydi (`upcore.costing.Opening`). API `/opening` (o'qish —
   `view_finance`, yozish — `manage_settings`); sana o'zgarsa hamma tovar, aks holda o'zgargan tovarlar qayta hisoblanadi.

## 8. API dizayni

- REST, `/api/v1`, JSON, OpenAPI avtomatik; frontend tiplari undan generatsiya qilinadi (CI'da farq bo'lsa xato).
- Pul qiymatlari satr ("123456.00"), foizlar Decimal satr; sanalar ISO 8601; vaqt UTC.
- Ro'yxatlar: kursor pagination, `sort`, `filter[...]`; eksport endpoint'lari alohida (`.xlsx`, `.pdf`).
- Xatolar: RFC 9457 `application/problem+json`, `code` maydoni bilan (frontend matnni i18n'dan oladi).
- Resurslar: `auth`, `orgs`, `members`, `accounts` (marketplace), `shops`, `sync`, `dashboard`, `pnl`, `skus`,
  `items`, `sales`, `expenses`, `purchases`, `suppliers`, `carriers`, `inventory`, `supplies`, `cash`, `goals`,
  `calculator`, `reports`, `notifications`, `settings`, `billing`, `admin`.
- Har javobda `meta.freshness` (tegishli ma'lumot turlari bo'yicha oxirgi sinxron vaqti).
- Cheklov: foydalanuvchi bo'yicha 120 so'rov/daq; OTP: raqam bo'yicha 5 ta/soat.
- **O'qish API'lari (B2.9, `upapi.reports`):** `GET /orgs/{id}/{dashboard,pnl,skus,sales,expenses,inventory}`;
  davr `start`/`end` (Toshkent kunlari, standart — oxirgi 30 kun), `shop` (bir necha marta). P&L kataklari butun
  tashkilot bo'yicha `daily_sku_metrics` + `mp_expenses` + `manual_expenses` + `tax_profiles` dan bir marta quriladi
  (`upcore.pnl.build_cells`), do'kon filtri keyin — tashkilot xarajati hamma do'konlarga taqsimlanadi. Bosh sahifa, P&L
  va SKU jadvali shu bitta hisobdan. Ruxsat: moliya — `view_finance`, xarajatlar — `view_settings`, ombor —
  `view_purchases` (summalar `view_purchase_amounts` bilan). Og'ir hisobot paytida GC to'xtatiladi
  (`reports.common.paused_gc`). OpenAPI → `apps/api/openapi.json` → `apps/web/src/lib/api/schema.d.ts`.

## 9. Frontend arxitekturasi

- SPA, marshrutlar: `/login`, `/onboarding`, `/` (bosh sahifa), `/pnl`, `/products`, `/products/:id`, `/orders`,
  `/expenses`, `/purchases`, `/purchases/:id`, `/suppliers`, `/inventory`, `/inventory/reorder`, `/inventory/supplies`,
  `/cash`, `/goals`, `/calculator`, `/reports`, `/settings/*`, `/billing`, `/status` (ma'lumotlar holati), `/admin/*`.
- Server holati — TanStack Query (staleTime 60 s, sinxrondan keyin invalidatsiya); filtrlar va davr — URL'da.
- Komponentlar: `components/ui` (shadcn asosida, tokenlar bilan), `components/charts` (ECharts o'ramlari),
  `features/<modul>` (sahifa logikasi).
- Formatlash faqat `lib/format` orqali (04-dizayn.md §8): son, pul, foiz, sana; hech joyda `toLocaleString` to'g'ridan.
- PWA: o'rnatiladigan, oxirgi bosh sahifa oflayn o'qish uchun keshda; web push [B6].
- Tezlik byudjeti: boshlang'ich JS ≤ 250 KB gzip, har marshrut alohida bo'lak, 500+ qatorli jadvallar virtual.

## 10. Xavfsizlik

- **Kirish:** telefon + OTP (xeshlangan, 5 daqiqa, 5 urinish), sessiya cookie `HttpOnly; Secure; SameSite=Lax`,
  token xeshi bazada, har 24 soatda yangilanadi, 30 kun. Kod Telegram Gateway orqali (ADR-028). Sessiya va kod
  jadvallari ilova roliga yopiq: faqat `auth_*` funksiyalari (`SECURITY DEFINER`, egasi `up_auth`), har biri sirni
  talab qiladi — kod (kirish) yoki sessiya tokeni. Yangilangan tokenning eskisi 60 s ishlaydi (parallel so'rovlar).
- **DB roli:** API va ishchi staging/prod'da superuser, `BYPASSRLS`, jadval egasi yoki boshqa rol a'zosi bo'lgan rol
  bilan ishga tushmaydi (`upapi.db.guard`, `upapi.startup`); dev'da — ogohlantirish. Migratsiya — alohida ega roli
  (`UP_MIGRATION_DATABASE_URL`), u `up_auth` (0002) va `up_sync` (0004) rollari a'zosi yoki superuser bo'lishi kerak
  (`SECURITY DEFINER` funksiyalari egasi; ikkalasi NOLOGIN, BYPASSRLS'siz, faqat kerakli ustunlarga huquq).
- **CSRF:** `Origin` tekshiruvi + maxsus sarlavha (`X-Requested-With`) har o'zgartiruvchi so'rovda.
- **Ruxsatlar:** har endpoint rol bo'yicha tekshiriladi (dekorator), testlar bilan.

| Amal | Egasi | Menejer | Buxgalter | Omborchi |
|---|---|---|---|---|
| Foyda, tannarx, pul oqimi ko'rish | ✓ | ✓ | ✓ | — |
| Xarid, ombor, postavka | ✓ | ✓ | ko'rish | ✓ (summasiz) |
| Xarajat, soliq, sozlamalar | ✓ | ✓ | ko'rish | — |
| Marketplace kaliti, xodimlar | ✓ | — | — | — |
| Tarif, to'lov, tashkilotni o'chirish | ✓ | — | — | — |
| Eksport | ✓ | ✓ | ✓ | ombor qismi |

- **Tashkilotlar ajratilgani:** ilova darajasida `org_id` filtri + PostgreSQL RLS (`SET LOCAL app.org_id`);
  admin uchun alohida DB roli. Har endpoint uchun "boshqa tashkilot ma'lumoti ko'rinmaydi" testi.
- **Sirlar:** server `.env`/Docker secrets'da; Uzum tokeni AES-256-GCM, kalit versiyasi bilan (rotatsiya
  mumkin); shifrlash kaliti zaxira nusxalarda yo'q. Token va kod loglarga yozilmaydi (log filtri testi).
  B2.4 (`upapi.crypto`): `UP_TOKEN_KEYS` (versiya → base64 32 bayt, `python -m upapi.crypto keygen`),
  `UP_TOKEN_KEY_VERSION`; bazada `nonce || shifrmatn || teg`, AAD = tashkilot + akkaunt id (shifrmatnni boshqa
  qatorga ko'chirib bo'lmaydi). Rotatsiya: yangi versiya qo'shiladi, joriy unga o'tkaziladi, eski yozuvlar keyingi
  tekshiruvda qayta shifrlanadi. Kalit faqat `SecretStr` da yuradi; Uzum xato matnida kalit ham, javob tanasi ham
  yo'q; transport xatosi zanjirsiz (`from None`). Kalit javob, sarlavha, log (ilova va httpx), xato matni va bazaning
  hech qayerida yo'qligi — `apps/api/tests/test_token_secrecy.py`. Yaroqsiz kalit urinishlari: tashkilot bo'yicha
  soatiga `UP_MP_VERIFY_FAILURES_PER_HOUR` (10). Staging/prod dev shifrlash kaliti bilan ishga tushmaydi.
- **Shaxsiy ma'lumot:** minimal (telefon, ism). DBS xaridor ma'lumoti saqlanmaydi. Ma'lumotlar O'zbekistondagi
  serverlarda (ADR-010).
- **Sarlavhalar:** qat'iy CSP, HSTS, `X-Content-Type-Options`, `Referrer-Policy`, `frame-ancestors 'none'`.
- **Bog'liqliklar:** Dependabot, `pip-audit`, `pnpm audit` CI'da.
- **Chiqishdan oldin:** OWASP ASVS L2 ro'yxati bo'yicha tekshiruv (B8.4).

## 11. Ishlash samaradorligi

- Maqsadlar: API p95 < 300 ms (oddiy), < 700 ms (bosh sahifa, 1 yil, 50 000 qator); sinxron (inkremental) bir
  do'kon < 30 s; to'liq tarix 3 000 sotuv < 5 daqiqa (Uzum tezligi chegarasida).
- `daily_sku_metrics` agregatlari, kerakli indekslar (`org_id, shop_id, date`), og'ir hisobotlar fon ishida.
- Yuklama testi (B8.4): 200 sintetik tashkilot, har biri 2 do'kon, 1 yillik ma'lumot.

## 12. Test strategiyasi

| Daraja | Vosita | Talab |
|---|---|---|
| Domen yadrosi | pytest + hypothesis | qamrov ≥ 95%, mypy strict |
| API | pytest + haqiqiy PostgreSQL (CI servisi) | qamrov ≥ 80%, har endpoint uchun ruxsat va tashkilot ajratish testi |
| Uzum mijozi | yozib olingan javoblar (faqat tuzilma, shaxsiy ma'lumotsiz) | xato turlari, sahifalash, kvota |
| Migratsiyalar | Alembic upgrade/downgrade CI'da | har PR |
| Frontend | Vitest + Testing Library | formatlash va formalar |
| E2E | Playwright | kirish, onboarding, xarid kiritish, P&L, eksport |
| Vizual | Playwright skrinshotlari (yorug'/qorong'i, 1440 va 390 px) | asosiy sahifalar |
| Accessibility | axe-core | jiddiy xato 0 |

Golden ma'lumot: sintetik generator (CI uchun) + Temurning real ma'lumoti faqat lokal (repozitoriyga kirmaydi,
legacy'dagi `UZUM_TEST_HISTORY` kabi).

## 13. CI/CD

- `ci.yml` (har PR va main): ruff, mypy, pytest (core, api, legacy), web lint/typecheck/test/build, OpenAPI tiplari
  sinxronligi, migratsiya testi.
- `deploy-staging.yml` (main'ga merge): Docker image'lar → GHCR → SSH orqali staging: zaxira → `alembic upgrade` →
  `docker compose up -d` → sog'liq tekshiruvi → muvaffaqiyatsiz bo'lsa oldingi image'ga qaytish.
- `deploy-prod.yml` (`v*` teg): xuddi shu, production'ga; migratsiyalar faqat "kengaytir → ko'chir → toraytir"
  tartibida (orqaga mos).
- Ish tartibi: har vazifa alohida branch → PR → CI yashil → merge. Temur PR'larni xohlasa ko'radi.

## 14. Muhitlar

- **dev:** `docker compose -f infra/compose/dev.yml up` (postgres, api, worker, bot, web dev server), sintetik seed
  (`make seed`). API dev'da ham `up_app` bilan ulanadi (`make db-check`); OTP kodi API terminaliga chiqadi.
- **staging:** O'zbekistondagi kichik VPS; Temurning haqiqiy do'konlari shu yerda sinxronlanadi (B2.11).
- **production:** alohida VPS (B8.8); staging bilan bir xil konfiguratsiya, kattaroq resurs.
- Funksiya bayroqlari (bazada) — yangi funksiyalar avval Temurning tashkilotida yoqiladi.

## 15. Kuzatuv

- Loglar: structlog JSON (so'rov id, org id, foydalanuvchi id, token/kodsiz).
- Xatolar: GlitchTip (self-hosted, shaxsiy ma'lumot tozalanadi).
- Ishlayaptimi: Uptime Kuma → admin Telegram'iga xabar.
- Sinxron salomatligi: admin panelida (M17) — oxirgi muvaffaqiyat, xatolar ulushi, kvota, yaroqsiz kalitlar soni
  (birdan oshsa — ehtimol WAF/tarmoq).

## 16. Legacy ilova va ko'chish

- Legacy (`uzum_profit/`, Python 3.8, SQLite) B4 oxirigacha Temurning Mac'ida ishlaydi; faqat kritik xatolar
  tuzatiladi (ADR-014).
- ~~B4.9: `uzum.db` ko'chirish vositasi~~ — bekor (ADR-032): legacy partiyalari Xaridlar sahifasida qo'lda
  kiritiladi, sotuvlar Uzum'dan olinadi.
- Legacy'dan olinadigan saboqlar: xarajat kodining faqat bir varianti (У→U) qamralgan, `PENDING_REALIZATION`
  doimiysi, bepul logistika sanalari `.env` da, FBO qoldig'i faqat `fbo` maydonidan, xarajat statuslari
  filtrlanmagan, tannarxsiz qism bo'lsa hamma xarajat ayiriladi, sotuv tannarxi "sanagacha kelgan hamma partiyalar
  o'rtachasi" (kumulyativ) — hammasi yangi yadroda to'g'rilanadi (02 formulalarida ko'rsatilgan).
