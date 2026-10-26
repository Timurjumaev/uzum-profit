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
| ADR-024 | 2026-10-23 | F13 marja maxraji — tannarxi ma'lum qatorlar tushumi (F15 bilan bir asos); marja yonida tannarxsiz qism ulushi (1 − F15) alohida ko'rsatiladi. Ta'sir: 02 (F13, M4), `upcore.metrics` (B1.2) | F15 bo'yicha sof foyda faqat tannarxi ma'lum qism uchun; umumiy tushumga bo'linsa marja sun'iy kamayadi (25% tannarxsiz → 42% o'rniga 32%). Temur tasdiqladi | F12 / F3 (dastlabki reja) |
| ADR-025 | 2026-10-23 | Q8 javobi: Temurning tashkiloti uchun tannarx usuli — **FIFO** (ADR-008 dagi standart bilan bir xil; o'rtacha sozlamada bir tugma bilan yoqiladi) | Temur tanladi; sotuvchi partiya bilan o'ylaydi, kurs va kargo partiyadan partiyaga o'zgaradi. Ta'sir: B1.5 lot dvigateli, B1.9 legacy farqlari (legacy kumulyativ o'rtacha → FIFO) | harakatlanuvchi o'rtacha |
| ADR-026 | 2026-10-23 | P&L kataklari: F9–F12 va F15 eng mayda katakda — (kun, do'kon, SKU) — hisoblanadi, har kesim (oy, do'kon, SKU, tashkilot) kataklar yig'indisi. Do'kon xarajati o'sha kuni SKU'larga tushum ulushida (F19 qoidasi), tushum bo'lmasa "taqsimlanmagan" katakka; o'z xarajatlari kunlarga amortizatsiya (F10) va tushum ulushida. **Taqsimlangan xarajatlar to'g'ridan-to'g'ri xarajatlardan ajratib ko'rsatiladi** (SKU'ga bog'langan yoki o'z darajasidagi — to'g'ridan-to'g'ri; tushum ulushida bo'lingan — taqsimlangan; har toifa bo'yicha). Temur tasdiqladi (2026-10-24). Ta'sir: `upcore.pnl` (B1.6), B2.8 `daily_sku_metrics` | M5 qabul mezoni (oylar yig'indisi = davr; P&L = bosh sahifa = SKU jadvali) faqat additiv hisobda bajariladi; F15 butun davr bo'yicha qo'llansa kesimlar yig'indisi umumiy natijaga teng chiqmaydi | F15 ni har kesimda alohida (yig'indi mos kelmaydi); oy katagi ("Bugun" ko'rinishi yo'q) |
| ADR-027 | 2026-10-24 | Q3 javobi: kirish kodi **Telegram** orqali (asosiy kanal); SMS (masalan, Eskiz) — keyinroq zaxira kanal. Aniq usul (Telegram Gateway — telefon raqamiga kod, yoki o'z bot — kontakt ulashish orqali) B2.3 da narx va O'zbekistonda ishlashi tekshirilib tanlanadi. Ta'sir: M1, B2.3, 03 §10 | Temur tanladi; auditoriya Telegram'da (ADR-018), SMS narxi va yetkazish kechikishi yo'q | faqat SMS |
| ADR-028 | 2026-10-24 | (Temur tasdiqladi, 2026-10-24.) ADR-027 usuli: **Telegram Gateway** (`sendVerificationMessage`) — foydalanuvchi telefon raqamini kiritadi, kod uning Telegram'iga ("Verification Codes") keladi, bot ochish shart emas. Kodni ilova o'zi yaratadi va tekshiradi (HMAC xesh, 5 daqiqa, 5 urinish → 15 daqiqa blok, raqam bo'yicha 5 ta/soat), Gateway faqat yetkazadi — SMS zaxirasi xuddi shu interfeys bilan (`CodeSender`). Raqam Telegram'da bo'lmasa — `telegram_not_found` (SMS kelguncha). O'z bot (B2.10) — admin ogohlantirishlari va B6 xulosalari uchun qoladi. Ta'sir: M1, B2.3, B2.10, 08 §10 | kirishda ortiqcha qadam yo'q (bot ochish, kontakt ulashish kerak emas); narx ≈ $0.01 / kod, o'z raqamiga bepul (staging'da Temur bepul sinaydi); kod va urinishlar bizda — provayder almashsa xavfsizlik qoidalari o'zgarmaydi. Kamchilik: balans Fragment orqali TON bilan to'ldiriladi (≈ $100 minimal, uchinchi tomon ma'lumoti) — production oldidan (B8) | o'z bot (bepul, lekin har kirishda botga o'tish va kontakt ulashish; yangi foydalanuvchi uchun 3–4 qadam ortiq) |
| ADR-029 | 2026-10-25 | Q2 (staging, **vaqtincha**): **AWS EC2, eu-north-1 (Stokgolm)** — Ubuntu 26.04 LTS, 2 GB RAM, Elastic IP 16.170.178.179, domen `16-170-178-179.sslip.io`. Avval Uztelecom Cloud sinaldi: akkaunt Sandbox/tasdiqlanmagan holatida VM'ga tashqaridan (ping, SSH) kirib bo'lmadi. Uzum API AWS'dan javob beradi (401, WAF to'smaydi). Bu ADR-010 (ma'lumot O'zbekistonda) dan vaqtinchalik chetlanish: staging'da faqat Temurning o'z do'konlari; **production (B8.8) — faqat O'zbekistondagi provayder**, mijoz ma'lumoti chet elga chiqmaydi. Ta'sir: B2.10, B2.11, 06 §1 | Temur tanladi; staging'ni kutmasdan ishga tushirish, AWS barqaror | Uztelecom akkauntini tasdiqlatishni kutish; Servercore.uz |
| ADR-030 | 2026-10-26 | Q1: brend nomi — **SellerMax** (domen `sellermax.uz`, Telegram va Instagram `sellermaxuz`). Temur tanladi; domen, Telegram va Instagram nomi bo'shligini u o'zi tekshirdi. Nomda "Uzum" so'zi yo'q (tovar belgisi xavfi — 04 §12). Repo, Python/JS paket nomlari va ichki ishchi nom (`uzum-profit`) o'zgarmaydi; UI, API sarlavhasi (`SellerMax API`) va hujjat nomi o'zgaradi. **Ochiq xavf:** "SellerMax" tovar belgisi sifatida band emasligi hali tasdiqlanmagan (Temur tekshiradi: ipa.gov.uz va WIPO Global Brand Database). Band chiqsa — nom yoki domen almashtiriladi; nom bitta joyda (`app.name`), shuning uchun tuzatish arzon. Ta'sir: 01, 04 §12, 06 §6 (tovar belgisi), Q7 | Temur tanladi; ma'no ("seller" — sotuvchi, "max" — maksimal foyda), bo'sh domen va hisoblar | Foyda, Ledgo, Hisobchi, Barkod, Tannarx.uz |
| ADR-031 | 2026-10-26 | **Taklif (Temur tasdig'i kutilmoqda).** F40 standart tarifi: SKU'ning oxirgi pullik logistikasi (bir dona), bo'lmasa do'konning eng ko'p uchraydigan pullik tarifi (legacy `std_fee_map`); ikkalasi ham yo'q qator "tarifi noma'lum" — qo'shilmaydi, soni ko'rsatiladi. Bepul kunlar — ma'lumotdan (do'kon × kun, Yakunlangan qatorlarning ≥ 90% ida logistika 0) + `free_logistics_periods`; admin tasdiqlashi B8 da. Ta'sir: `upcore.tariffs`, `upcore.pnl` (F40), `upapi.reports.free` | F37 hajm bo'yicha tarif uchun SKU o'lchamlari bazada yo'q; o'lchamsiz F37 (50 000/dona) foydani haddan tashqari kamaytirardi | F37 birinchi (o'lchamlar yo'q); doimiy 5 250 so'm (biznes doimiysi kodda — ADR-015 ga zid) |

## Ochiq qarorlar (Temur hal qiladi)

| ID | Savol | Qachongacha | Standart (javob bo'lmasa) |
|---|---|---|---|
| Q1 | ~~Brend nomi~~ — **hal qilindi: SellerMax (ADR-030)**; tovar belgisi tekshiruvi ochiq | B3 oxiri | ishchi nom ichkarida qoladi, UI'da vaqtincha "Foyda" |
| Q2 | ~~Server provayderi~~ — **staging uchun hal qilindi (vaqtincha): AWS eu-north-1 (ADR-029)**; production provayderi B8.8 da qayta ko'riladi | B2.10 | 7 kunlik sinovdan keyin tezroq ishlagani (Servercore.uz yoki UzCloud) |
| Q3 | ~~Kirish kodi kanali: SMS provayder (masalan, Eskiz) yoki Telegram orqali kod~~ — **hal qilindi: Telegram, SMS keyinroq zaxira (ADR-027)** | B2.3 | staging: kod admin Telegram'iga; production: SMS |
| Q4 | Yuridik shaxs (MChJ / YaTT) | B8 boshi | buxgalter maslahatidan keyin |
| Q5 | To'lov provayderi | B8.2 | takroriy to'lov va fiskal chekni eng sodda bergan provayder |
| Q6 | Tarif narxlari | B8.1 | 01-mahsulot.md §7 dagi taklif |
| Q7 | Domen — **`sellermax.uz` bo'sh (Temur tekshirdi, ADR-030)**; ro'yxatdan o'tkazish B8.8 gacha (band bo'lib qolmasin) | B8.8 | Q1 nomi bo'yicha bo'sh domen |
| Q8 | ~~Temurning tashkiloti uchun tannarx usuli: FIFO yoki o'rtacha~~ — **hal qilindi: FIFO (ADR-025)** | B1 oxiri | FIFO (ikkalasi bir tugma bilan almashadi) |
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
