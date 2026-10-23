# 07. Qarorlar jurnali

## Rejani o'zgartirish tartibi

Reja doimiy. O'zgartirish faqat quyidagi hollarda:
1. Yangi fakt eski qarorni noto'g'ri qilsa (masalan, Uzum API o'zgardi, qonun o'zgardi, kutubxona ishlamay qoldi).
2. Temur yangi talab qo'ysa.

Tartib: ADR'ga yangi yozuv (sana, sabab, nima o'zgardi, nimaga ta'sir qiladi) → Temurga qisqa xabar → tasdiq →
tegishli fayllar yangilanadi. Eski qaror o'chirilmaydi, "almashtirildi: ADR-0XX" deb belgilanadi.

## Qabul qilingan qarorlar (ADR)

| ID | Sana | Qaror | Sabab | Ko'rib chiqilgan muqobillar |
|---|---|---|---|---|
| ADR-001 | 2026-10-23 | Mahsulot — bulutli SaaS (veb + PWA + Telegram bot); lokal ilova faqat legacy | Telegram ogohlantirishlari va tungi sinxron uchun 24/7 server kerak; telefon; avtomatik yangilanish; obuna to'lovi; Uzum WAF O'zbekiston IP'sini talab qiladi; qonun | lokal desktop ilova; gibrid |
| ADR-002 | 2026-10-23 | Backend: Python 3.13, FastAPI, SQLAlchemy 2 async, PostgreSQL | Temurning bilimi; legacy domen mantig'i Python'da; OpenAPI → frontend tiplari | Django (og'irroq), Node/NestJS |
| ADR-003 | 2026-10-23 | Fon ishlari: Procrastinate (PostgreSQL navbati) | qo'shimcha servis (Redis) kerak emas; qulflar "bir kalit — bir navbat"ga mos; davriy ishlar | Celery + Redis; ARQ + Redis — Procrastinate'da to'siq chiqsa (qulf yoki davriy ish ishlamasa) ARQ'ga o'tiladi |
| ADR-004 | 2026-10-23 | Frontend: React + TypeScript + Vite SPA, TanStack (Router, Query, Table), Tailwind v4 + shadcn/ui | murakkab jadval, grafik, forma, mobil va PWA uchun eng boy ekotizim; komponentlar o'zimizda | Jinja + HTMX (boy UI qiyin), Next.js (SSR kerak emas), Vue |
| ADR-005 | 2026-10-23 | Grafiklar: Apache ECharts, o'z temamiz bilan | sharshara, issiqlik xaritasi, kalendar, katta ma'lumot | Recharts (turlari kam), Chart.js |
| ADR-006 | 2026-10-23 | Shrift: Inter (variable) | oʻ/gʻ (U+02BB) to'g'ri, o'zbek kirill, tabular raqamlar, to'g'ri minus; glif tekshiruvi va skrinshot (04 §2) | Onest, IBM Plex Sans, Noto Sans, Geist, Manrope va b. |
| ADR-007 | 2026-10-23 | Pul: `Decimal` / `numeric`; API'da satr | float xatolari moliyada qabul qilinmaydi | float |
| ADR-008 | 2026-10-23 | Tannarx: lot dvigateli; usul tashkilot sozlamasi; yangi tashkilotlar uchun standart **FIFO**, Temurning tashkiloti uchun Q8 javobi | sotuvchi partiya bilan o'ylaydi; kurs va kargo partiyadan partiyaga o'zgaradi; o'rtacha ham qo'llanadi | faqat o'rtacha; faqat FIFO |
| ADR-009 | 2026-10-23 | Faqat rasmiy Uzum Open API; kabinet (norasmiy) API va parol/sessiya tokeni ishlatilmaydi | ishonch, qoidalar, barqarorlik | kabinet API orqali sharh, reklama, analitika |
| ADR-010 | 2026-10-23 | Server va zaxiralar O'zbekistonda | shaxsiy ma'lumotlar qonuni (27-1-modda), Uzum WAF | chet el bulutlari |
| ADR-011 | 2026-10-23 | Kirish: telefon + bir martalik kod, parolsiz; sessiya 30 kun | O'zbekistonda odatiy (bank, Uzum); parol unutilmaydi | email + parol |
| ADR-012 | 2026-10-23 | Ko'p tashkilotli: bitta baza, `org_id` + PostgreSQL RLS | sodda va arzon; ikki qavatli himoya | har mijozga alohida baza |
| ADR-013 | 2026-10-23 | Tillar: uz-Latn (asosiy), uz-Cyrl (avtomatik transliteratsiya + tuzatishlar), ru; en keyin | auditoriya | faqat uz |
| ADR-014 | 2026-10-23 | Monorepo; legacy ilova B4 oxirigacha ildizda, keyin `legacy/` | Temurning hozirgi ishi buzilmaydi | yangi repo |
| ADR-015 | 2026-10-23 | Biznes doimiylari (tariflar, kodlar, soliq, bepul davrlar) bazadagi jadvallarda, sana bo'yicha; kodda emas | "100% dinamik" talabi | `.env` / kod |
| ADR-016 | 2026-10-23 | Uzum'dagi `purchasePrice` (tan narx) foyda hisobiga ishlatilmaydi, faqat ishora sifatida ko'rsatiladi | sotuvchilar u yerga sun'iy (oshirilgan) narx yozadi (Temur tasdiqlagan) | onboarding'da avtomatik olish |
| ADR-017 | 2026-10-23 | Davr asosi: buyurtma sanasi (Toshkent); foyda = Yakunlangan (`TO_WITHDRAW`) | Open API FBO uchun yetkazilgan sanani bermaydi | yetkazilgan sana |
| ADR-018 | 2026-10-23 | Bildirishnoma: Telegram birinchi, keyin ilova ichida va web push; email keyin | auditoriya Telegram'da | email/SMS |
| ADR-019 | 2026-10-23 | Tarif: aylanmaga bog'liq darajalar + bepul daraja (narxlar Q6) | kichik sotuvchiga arzon, katta sotuvchidan adolatli | bitta narx |
| ADR-020 | 2026-10-23 | Xato kuzatuvi self-hosted (GlitchTip) | shaxsiy ma'lumot chet elga chiqmaydi | Sentry bulut |
| ADR-021 | 2026-10-23 | AI yordamchi va MCP — B10 da, faqat o'z ma'lumotiga asoslangan javob | asosiy hisob birinchi; AI noaniqlikka yo'l qo'ymasligi kerak | erta AI |
| ADR-022 | 2026-10-23 | Grafik va rang qoidalari — dataviz usuli: bitta o'q, qat'iy kategoriya tartibi, validator bilan tekshiruv | izchil va rangni ajrata olmaydiganlar uchun ham tushunarli | ko'z bilan tanlash |
| ADR-023 | 2026-10-23 | Landing va yordam markazi — alohida statik sayt (Astro), ilova bilan bitta domenda | qidiruv tizimlari va tezlik; yordam maqolalari Markdown'da (ilova ichidan ham ochiladi) | SPA ichida landing (SEO yomon), Next.js |

## Ochiq qarorlar (Temur hal qiladi)

| ID | Savol | Qachongacha | Standart (javob bo'lmasa) |
|---|---|---|---|
| Q1 | Brend nomi | B3 oxiri | ishchi nom ichkarida qoladi, UI'da vaqtincha "Foyda" |
| Q2 | Server provayderi | B2.10 | 7 kunlik sinovdan keyin tezroq ishlagani (Servercore.uz yoki UzCloud) |
| Q3 | Kirish kodi kanali: SMS provayder (masalan, Eskiz) yoki Telegram orqali kod | B2.3 | staging: kod admin Telegram'iga; production: SMS |
| Q4 | Yuridik shaxs (MChJ / YaTT) | B8 boshi | buxgalter maslahatidan keyin |
| Q5 | To'lov provayderi | B8.2 | takroriy to'lov va fiskal chekni eng sodda bergan provayder |
| Q6 | Tarif narxlari | B8.1 | 01-mahsulot.md §7 dagi taklif |
| Q7 | Domen (.uz / .com) | B8.8 | Q1 nomi bo'yicha bo'sh domen |
| Q8 | Temurning tashkiloti uchun tannarx usuli: FIFO yoki o'rtacha (hozirgi daftar usuli o'rtachaga yaqin) | B1 oxiri | FIFO (ikkalasi bir tugma bilan almashadi) |
| Q9 | Beta ishtirokchilari | B9 boshi | Temurning tanishlari va guruhlardan 5–10 sotuvchi |

## Rad etilgan g'oyalar (qayta ko'tarilmasligi uchun)

| G'oya | Nega yo'q |
|---|---|
| Kabinet API orqali sharhlarga AI javob, reklama boshqaruvi | ADR-009 |
| O'z bozor tahlili (scraping) | doiradan tashqari (01 §6), Uzum bloklashi mumkin |
| Lokal desktop ilovani sotish | ADR-001 |
| 1C integratsiyasi | talab bo'lmaguncha; eksport yetarli |
| Uzum'ning `purchasePrice` ni avtomatik tannarx qilish | ADR-016 |
| Nomda "Uzum" so'zi | tovar belgisi xavfi |
