# 09. Tanqidiy tahlil (audit) — 2026-11-11

Loyihaning hozirgi holati (kod, ma'lumot, dizayn) va rejasi (README, 01–08) to'liq o'qib, brauzerda ko'rib va
raqobatchilar bilan solishtirib chiqildi. Bu fayl — topilmalar ro'yxati. **Hech narsa bu hujjat bilan o'zgarmaydi:**
tasdiqsiz tuzatiladiganlar alohida kichik PR'larda (§9), qolganlari Temurning qaroridan keyin (§8, 07 tartibi bilan).

## 1. Qisqa xulosa

- **Poydevor mustahkam.** Hamma tekshiruv yashil (§2), pul faqat `Decimal`, formulalar bitta joyda, RLS va kalit
  maxfiyligi testlar bilan, UI matnlarida oʻ/gʻ va tutuq xatosi yo'q (1 515 satr tekshirildi). Foyda sahifasidagi
  hisob varag'i va "?" formulalar — bozorda yo'q darajada shaffof.
- **Eng jiddiy topilmalar ombor hisobida** (bizning asosiy ustunligimiz bo'lishi kerak bo'lgan joy): sotuv tezligi
  tovar tugab qolgandan keyin 3,5 barobar kam chiqadi (K1), bekor bo'ladigan buyurtmalar talabga to'liq qo'shiladi
  (K2), "Kritik / hozir buyurtma ber" holati o'z ombori va yo'ldagi tovarni ko'rmaydi (K3).
- **Tannarxda bitta nomuvofiqlik:** ADR-051 qoidasi ADR-055 da aniqlangan fakt (tovar savdoga postavka yaratilgan kuni
  emas, `dateAccepted` da chiqadi) bilan yangilanmagan (K4).
- **Dizaynda uchta tizimli muammo:** bosh sahifada "Diqqat talab qiladi" 24 ta kartochka ostida (telefonda 7-ekran);
  jadvallar telefonda faqat nomni ko'rsatadi, 1440 px da ham sig'maydi; bosish maydoni 44 px qoidasi faqat ikki
  sahifada bajarilgan.
- **Reja:** B4 yopilmayapti (61 kichik vazifa, 14 kunlik sinov boshlanmagan); rejada umuman yo'q narsalar bor (PWA,
  jamoa ekrani, qurilmalar, foydalanish hodisalari); Telegram xulosa juda kech turibdi.
- **Raqobat:** sahifasi o'qilgan 7 ta Uzum servisining birortasida partiya / FIFO / valyuta / kargo taqsimoti yo'q —
  ustunligimiz saqlanib turibdi. Lekin uchta asosiysida (SellerPro, MARGN, SellerMind) Telegram xabarlari, SellerPro'da
  mobil ilova, bir nechtasida AI bor.

## 2. Nima tekshirildi, nima tekshirilmadi

| | |
|---|---|
| To'liq o'qildi | `docs/plan` (README, 01–08; 05 dagi B0–B10, 55 ta ADR), `packages/core` (12 modul), `apps/api`: `calc/*`, `reports/cells`, `reports/stock`, `reports/common`, `reports/products`, `routes/dashboard`, `auth/*`, `db/session`, `db/rls`, `middleware`, `ratelimit`, `main`, `sync/store`, CI (`ci.yml`) |
| Qisman (aniq savol bo'yicha) | `sync/engine`, `settings`, `db/models` (jadval va ustunlar), qolgan marshrutlar (xarid sanalari, soliq, jamoa, sessiya), `apps/web`: router, navigatsiya, karkas, bosh sahifa, Buyurtmalar tahlili, CSS (jadval, bosish maydoni), i18n matnlari (skript bilan) |
| O'qilmadi | `realcheck.py`, `uzum/client.py`, `routes/` dagi `purchases`, `shipments`, `opening`, `skus` ning to'liq matni, veb testlari, `infra/` skriptlari, legacy ilova |
| Ishga tushirildi (lokal) | ruff, ruff format, mypy (85 fayl), OpenAPI tekshiruvi — toza; pytest 1 248 ta (shundan API 939 ta; qamrov: yadro 99,92%, API 98,79%), benchmark 4 ta, legacy 62 ta; eslint, tsc, vitest 598 ta, build, boshlang'ich JS 195,3 KB (chegara 250); Playwright 203 ta. `pnpm audit` va `pip-audit` — zaiflik topilmadi |
| Brauzer | Playwright (Chromium), soxta API bilan, 22 sahifa × 360 / 1000 / 1440 px = 66 skrinshot; har birida gorizontal skroll, 44 px dan kichik bosish maydonlari, ichki skrollar va shrift o'lchamlari o'lchandi |
| Cheklovlar | Lokal PostgreSQL 16 (CI — 18). **Real ma'lumot ko'rilmadi** (staging so'rovi yuborilmadi): K2, K6, K10 kattaligi — taxmin, §10 dagi so'rovlar bilan o'lchanadi. Qorong'i mavzu va rus tili ko'z bilan ko'rilmadi (avtomatik testlari bor). Skrinshotlar soxta ma'lumotda — Temurning haqiqiy ekrani farq qilishi mumkin |

## 3. Topilgan muammolar: hisob va ma'lumot

Xavf: **Y** — yuqori (noto'g'ri qarorga olib keladi), **O'** — o'rta, **P** — past. Holat: *PR-n* — tasdiqsiz
tuzatiladi (§9); *Q-n* — Temurning qarori kerak (§8).

| ID | Xavf | Muammo | Joyi | Dalil | Holat |
|---|---|---|---|---|---|
| K1 | Y | **F23 tezlik tugab qolishdan keyin kam chiqadi.** "Kamida 7 kunga bo'lish" yangi tovar uchun yozilgan, lekin savdoda bo'lgan kuni kam har SKU'da ishlaydi; oyna 14 kun — tugab qolishdan oldingi sotuv unutiladi | `upcore/inventory.py` `velocity`; `reports/stock.py` | Kuniga 17 dona sotilgan SKU 15 kun savdoda bo'lmadi, qaytgan 2-kuni: tezlik **4,86** (17 o'rniga), 65 dona "13,4 kunga yetadi" (aslida 3,8). Butun oyna qoldiqsiz bo'lsa — tezlik 0. Aynan shu holat ADR-055 dagi SKU'da bo'lgan (25.10–08.11) | Q1 |
| K2 | Y | **F23 dagi "qaytish darajasi" amalda ishlamaydi.** Manba — Yakunlangan qatordagi `amountReturns`, real ma'lumotda u doim 0 (B2.11, B4.26). Jarayondagi buyurtmalar to'liq sanaladi, bir qismi esa bekor bo'lib tovar qoldiqqa qaytadi — talab oshib, zaxira kunlari kamayib ko'rinadi | `reports/stock.py` (`metrics[...] = (units, returns)`) | Kod; kattaligi o'lchanmagan (S1). sellerdata: tezlik "по выкупам, а не по заказам" — aks holda "завышен на десятки процентов" | Q1 |
| K3 | Y | **F26 holat va F27 buyurtma sanasi faqat Uzumdagi qoldiqni** to'liq (Xitoygacha) muddat bilan solishtiradi; postavkadagi, o'z omboridagi, yo'ldagi tovar hisobga olinmaydi (tavsiya miqdorda esa olinadi). O'z omborida zaxira tutadigan sotuvchida deyarli hamma SKU "Kritik, buyurtma: hozir" | `reports/stock.py:378,436`; `upcore.inventory.stock_status`, `order_by` | Uzumda 10, omborimda 15, yo'lda 30, Xitoyda 20, tezlik 2 → "Kritik", "hozir"; aslida 37 kunlik tovar bor, to'g'ri amal — Uzumga yuborish. Sellerboard: prep-markaz, buyurtma qilingan va yuborilgan tovar ham sanaladi | Q2 |
| K4 | Y | **ADR-051 ↔ ADR-055.** "Postavka kuni" — yaratilgan sana, lekin tovar savdoga `dateAccepted` da chiqadi (misolda 28.10 → 09.11). Oraliqda sotilgan dona — qaytgan eski tovar; dvigatel esa uni "postavka bor" deb oxirgi partiya narxida yoki "postavka bor, partiya kiritilmagan" belgisi bilan hisoblaydi | `calc/costs.py` `supplies()`; `upcore.costing.Opening.supplied_on` | ADR-055 matni; `fbo_invoices.raw.dateAccepted` bazada bor (SKU sahifasi undan foydalanadi) | Q3 |
| K5 | O' | **Oy prognozi** bugungi tugamagan kunni to'liq kun deb sanaydi | `routes/dashboard.py` `forecast` | Kuniga 1 mln sur'atda soat 10:00 da: 1-sanada 12 mln (−60%), 2-sanada −30%, 10-sanada −6% | PR-2 |
| K6 | O' | **"▲ %" va prognoz bekor bo'lishni hisobga olmaydi.** Joriy davrda Jarayondagi buyurtmalar to'liq turadi, oldingi davrdan bekorlar allaqachon chiqib ketgan — o'sish tizimli ravishda ko'proq ko'rinadi | `upcore.pnl.compare`, `routes/dashboard.py` | Mantiq; kattaligi o'lchanmagan (S2). MPSTATS: "прогноз продаж и прибыли по новым заказам, не дожидаясь выкупа" | Q4 |
| K7 | O' | **"QQS + foyda solig'i" va "Uzum soliq agenti" rejimida soliq 0**, Sozlamalar esa "oylik taxmin sifatida hisoblanadi" deydi. `vat_profit_estimate` hech qayerdan chaqirilmaydi (tamoyil 9) | `upcore/tax.py` `daily_rule`; `settings.tax.regimeHelp` | Kod; QQS to'lovchida sof foyda oshib ko'rinadi | PR-3, Q5 |
| K8 | O' | **F21 tayyor sana.** "Uzumga yuborildi" yoki "Yopildi" sanasi bor, "Qabul qilindi" yo'q xarid loti "yo'lda" hisoblanadi — sotuvlarda "Taxminiy · qabul belgilanmagan"; Ombor esa shu xaridni Uzumda deb biladi | `upcore.purchasing.Purchase.ready_date`; `calc/lots.py` | Bosqich sanalari ixtiyoriy (API faqat tartibni tekshiradi) | Q6 |
| K9 | O' | **"Taxminiy" belgisi standart holatda ham chiqadi.** Kurs rejimi standarti — Markaziy bank; u `cbu_rate` belgisini beradi; valyutadagi har xarid sotuvi "Taxminiy" bo'ladi. ADR-051 ruhiga zid ("taxminiy faqat sotuvchi tuzata oladigan holatda"), belgi qadrsizlanadi | `upcore.purchasing.Flag.CBU_RATE`; `CostCell.tsx` | Kod: faqat "tarixiy" belgisi taxmin emas deb olingan | Q6 |
| K10 | P | **R (F16) pastga og'adi:** oxirgi 90 kunga hali yetilmagan buyurtmalar ham kiradi (bekor tezroq yakunlanadi) | `reports/cells.py` `realization` | Mantiq; o'lchanmagan (S2) | Q4 |
| K11 | P | **Kunlik snapshot faqat 23:50–24:00** oynasida; ishchi band yoki o'chiq bo'lsa kun yo'qoladi (UI'dagi "N kunning M tasi uchun bor" izohi shundan) | `sync/engine.py` `is_due` | Kod; bo'shliqlar soni — S3 | Q7 |
| K12 | P | **Sotuv qachon Yakunlangan bo'lgani yozilmaydi** (`sale_items` da ustun yo'q). Pul oqimi (F38, B5.7) va "pul necha kunda keladi" uchun kerak; keyin tiklab bo'lmaydi | `db/models.py` | Jadval ustunlari | Q7 |
| K13 | P | **Eskirgan kod.** `metrics.profit_summary` — F12 ning eski (faqat Yakunlangan) varianti, "bitta formula — bitta joy"ga zid; `own_expenses`, `uzum_expenses`, `payout_mismatches`, `realization_rate`, `period_return_share`, `cancel_share` — faqat testlarda. `daily_sku_metrics.ads` yoziladi, hech kim o'qimaydi | `upcore/metrics.py`; `calc/daily.py` `_ads` | grep: API va skriptlarda 0 ta chaqiruv | PR-6 |
| K14 | P | **Biznes doimiylari kodda** (tamoyil 2): F43 saqlash qoidasi (`SEED_STORAGE_RULES` to'g'ridan-to'g'ri), to'lov jadvali shartlari, "Chegarada" 5% (B4.55), R oynasi 90 kun, reklama ulushi 30 kun | `upcore/tariffs.py`, `routes/settings.py`, `reports/cells.py` | ADR-040 dagi "(B7)" havolasi noto'g'ri — bu M17 / B8.3 | PR-6 (hujjat), B8.3 |
| K15 | P | **Xarajat klassifikatori faqat o'zbekcha matnga tayanadi** ("kompensatsiya", "jarima", "olganida … so'm"). Uzum boshqa sotuvchiga ruscha matn bersa — toifa "boshqa", reklama summasi yaxlitlangan bo'ladi | `upcore/expenses.py` | Tekshirilmagan — Temurga savol (§10) | savol |

## 4. Xavfsizlik, ishonchlilik, testlar

| ID | Xavf | Muammo | Dalil | Holat |
|---|---|---|---|---|
| X1 | P | Tashkilotlarni ajratish amalda **bitta qatlam** (RLS + ishga tushish qo'riqchisi); 03 §10 va `models.py` "ikki qavat" deydi. `open_org` dagi a'zolik so'rovida `org_id` sharti yo'q | `auth/deps.py`; prod'da xavfsiz (RLS majburiy, `test_rls.py`), dev'da superuser bilan — yo'q | PR-5 |
| X2 | P | Foydalanuvchi bo'yicha 120 so'rov/daq cheklovi (03 §8) yo'q — faqat kirish kodi IP cheklovi | `ratelimit.py`, `main.py` | B8.4 ga |
| X3 | P | CI'da `pip-audit` / `pnpm audit` yo'q (03 §10 da "bor") | `ci.yml`; bugun ikkalasi toza | PR-5 |
| X4 | O' | Har ishchi ishga tushishida **hamma tashkilot to'liq qayta hisoblanadi** (B4.40). 2 do'konda sezilmaydi; 200 tashkilotda har deploy — yuklama to'lqini | `sync/jobs.py` `rebuild_all` | B8.4 yuklama testiga |
| X5 | O' | **Uzum API'ni uchinchi tomon ishlatishi shartlari tekshirilmagan** (08 §9, B8.6 da turibdi). Bu mahsulotning mavjudlik xavfi — B8 ni kutmasdan aniqlash kerak | 08 §9 | Q13 |
| T1 | O' | Vizual asos (skrinshot) **yo'q**: Mahsulotlar, SKU, Buyurtmalar, Xarajatlar, Ombor, Sozlamalar, Boshlang'ich holat | `e2e/visual.spec.ts` (15 nom: kirish, onboarding, Asosiy, Foyda, holat, Xaridlar, Kargolar, UI-kit) | PR-7 |
| T2 | O' | Mobil e2e loyihasi 390 px; tamoyil 10 — 360 px. 360 px tekshiruvi ayrim sahifalarda — D5 shu sababli o'tib ketgan | `playwright.config.ts` | PR-7 |
| T3 | P | axe (kontrast bilan) qamrovida yo'q: Mahsulotlar, SKU, Buyurtmalar, Xarajatlar, Kargolar | `e2e/a11y.spec.ts` | PR-7 |
| T4 | P | CI har PR'da ikki marta ishlaydi (`push: claude/**` + `pull_request`) | `ci.yml` | PR-5 |

## 5. Reja bo'yicha topilmalar

| ID | Topilma | Tavsiya |
|---|---|---|
| R1 | **B4 yopilmayapti.** 61 kichik vazifa; chiqish mezoni (14 kun faqat yangi dasturda) boshlanmagan; README'dagi "Temurdan kutilmoqda" — 40 ga yaqin tekshiruv bitta abzatsda (tamoyil 12 ga zid). Umumiy hajm bahosi (60–90 kun) eskirgan | Q8 |
| R2 | **Telegram kunlik xulosa (B6) B5 (12–18 kun) dan keyin.** Tamoyil 10 ("Telegram birinchi"), 01 D8; SellerPro, MARGN va SellerMind'da Telegram xabarlari bor. Xulosa — eng arzon ushlab qolish vositasi, 14 kunlik sinovda ham foydali | Q9 |
| R3 | **Rejada yo'q, lekin kerak:** (a) PWA — `apps/web/public` da manifest ham, ikonka ham, favicon ham yo'q; ADR-001 "veb + PWA" deydi, 05 da faqat web push (B6.3); (b) jamoa ekrani — API bor (`/members`, `/invites`), UI'da faqat taklifni qabul qilish; (c) "qurilmalarim" va "hamma qurilmadan chiqish" (M1); (d) onboarding 4–6-qadamlar va bosh sahifadagi "Sozlash: 4/6" ro'yxati (M2); (e) foydalanish hodisalari — `events` ga faqat 2 hodisa yoziladi, B9.4 o'lchovlari (aktivatsiya, haftalik faollik) uchun yetmaydi | Q13 |
| R4 | **Eskirgan yoki zid bandlar:** 02 M6 "virtual skroll" (ADR-054 dan keyin); 03 §2 va ADR-004 — Tailwind, shadcn/ui, TanStack Table, React Hook Form, Zod, date-fns amalda ishlatilmagan (o'z CSS va komponentlar); 03 §8 "kursor"; 03 §10 "pip-audit", "ikki qavat"; 03 §12 "390 px"; 04 §1 va §2.1 "katta harfli yorliq yo'q" ↔ §6.4 "katta harf"; 04 §6.4 "radius yo'q" ↔ §3; 04 §7.4 "mobilda ro'yxat" ↔ amalda jadval; ADR-040 "(B7)"; 05 da B4.61 / B4.55 tartibi va B4.56–B4.60 belgisi; `index.html` dagi `theme-color` eski rang (`#F5F6F8`) | PR-6; ADR-004 — Q14 |
| R5 | **Tekshirilmagan muhim faktlar:** Uzum kabinetidagi "Analitika" (bepul rasmiy raqobat; qo'llanma sayti avtomatik o'qishga yopiq); Uzum soliqni agent sifatida ushlaydimi (08 §6) | §10 |

## 6. Dizayn va UX topilmalari

O'lchovlar: Playwright, soxta ma'lumot, 2026-11-11. "Kichik nishon" — balandligi yoki eni 44 px dan kam tugma, havola, maydon.

| ID | Xavf | Topilma | O'lchov | Holat |
|---|---|---|---|---|
| D1 | Y | **Bosh sahifa ierarxiyasi.** "Diqqat talab qiladi" (yagona harakatga chorlovchi blok) KPI sarhisob (24 kartochka) va grafikdan keyin. 04 §1 dagi vazifa — "5 soniyada: qancha foyda va nimani buyurtma qilish" — ikkinchi yarmi bajarilmaydi. 24 kartochka — 04 §1 o'zi rad etgan "kartochkalar devori" | 1440 px: 3-ekran (y ≈ 2 680 / 3 180); 360 px: sahifa 5 770 px, blok 7-ekranda | Q10 |
| D2 | Y | **Telefonda jadvallar faqat nomni ko'rsatadi.** Foyda, marja, zaxira — gorizontal skroll ortida. 04 §7.4 "mobilda ro'yxat (rasm, nom, foyda/dona, zaxira kunlari)" — bajarilmagan | 360 px: Mahsulotlar 1 637 px kontent / 326 ko'rinadi; Ombor 1 526; Buyurtmalar 1 159; Foyda (SKU) 1 751 | Q11 |
| D3 | Y | **1440 px da ham jadval sig'maydi.** Omborda "Tavsiya miqdor" va "Xarid yaratish", Mahsulotlarda "Holat", "Qoldiq" — ekrandan tashqarida, "Holat" ustunida esa bo'sh joy ko'p | Mahsulotlar 1 631 / 1 158; Ombor 1 526 / 1 158; 1000 px da Buyurtmalar 1 159 / 902 | PR-8 |
| D4 | Y | **Bosish maydoni < 44 px** (04 §11). B4.54 faqat Mahsulotlar va SKU sahifasini tuzatgan; karkas (do'kon, davr, sinxron, qidiruv — 36 px) va "?" (32 × 32) hamma sahifada | 360 px da kichik nishonlar: Asosiy 43, Foyda 35, Sozlamalar 27, Ombor 20, Xarid 18, Buyurtmalar 16, Boshlang'ich holat 15; Mahsulotlar va SKU — 4 (faqat karkas) | PR-4 |
| D5 | O' | **Buyurtmalar → "Bekor bo'lish" va "Qaytarilish": sahifa gorizontal skroll qiladi** (tamoyil 10) | 360 px: 68 va 105 px; sabab — `.orders-analysis__tables` grid ustuni cheklanmagan | PR-2 |
| D6 | O' | **Grafik o'qida takror yorliqlar:** kichik sonlarda "1, 1, 1, 0, 0, 0" (butun son qadami yo'q) | "Kunlik qaytarishlar" grafigi | PR-2 |
| D7 | O' | **KPI qiymati so'z o'rtasidan bo'linadi:** "1 200 000 soʻ" / "m" | SKU sahifasi, 360 px, "Tushum" kartasi | PR-2 |
| D8 | O' | **Menyuda ishlamaydigan bo'limlar:** "Pul oqimi", "Hisobotlar" — "qurilmoqda" sahifasi (9 tadan 2 tasi) | `nav.ts` | Q12 |
| D9 | O' | Asosiydagi "Eng foydali 5 / Zarar qilayotgan 5" qatorlari **havola emas** — SKU'ga o'tib bo'lmaydi | `home/Blocks.tsx` `SkuTable` | PR-8 |
| D10 | P | Ombor va Buyurtmalarda KPI kartalari telefonda bitta ustun — jadval birinchi ekrandan pastda (SKU sahifasida ikki ustun) | Ombor 360 px: jadval y ≈ 830 dan | PR-4 |
| D11 | P | Brauzer yorlig'ida ikonka yo'q; `theme-color` eski rang (R3 a, R4) | `index.html` | PR-8, Q13 |
| D12 | P | Telefonda 12 px matn juda ko'p (ikkinchi darajali raqamlar: "oldingi", "yakunlangan · kutilayotgan") | Asosiy 360 px: 139 element 12 px da; 04 §2.1: mobil asosiy matn 15 px | Q11 bilan |
| D13 | P | Foyda sahifasida uzun qator nomida "?" alohida satrga tushadi (telefon) | `pnl-360` | PR-4 |

**Yaxshi chiqqan joylar (o'zgartirilmaydi):** hisob varag'i (Foyda), "Buyurtmadan sof foydagacha" zinapoyasi, uch raqam,
"Partiya yo'li", har ko'rsatkichdagi formula, snapshot bo'shlig'i haqidagi halol izoh, 22 sahifadan 20 tasida
360 px da gorizontal skroll yo'q.

## 7. Raqobatchilar (2026-11-11 da saytlari qayta o'qildi)

Faqat sahifaning o'zida yozilgani; "—" — sahifada yo'q. Narxlar so'm/oy, o'sha kungi.

| Servis | Bozor | Narx | Tannarx qanday kiritiladi | Ombor / qayta buyurtma | Kuchli tomoni | Kuchsiz tomoni |
|---|---|---|---|---|---|---|
| [SellerPro](https://sellerpro.uz/) | Uzum (+ WB, Ozon, Yandex kabinetlari) | Pro 1 199 000 (yonida 399 200 ham ko'rsatilgan), Business 1 499 000; bepul daraja; 7 kun sinov | "Себестоимость вы вводите сами по каждому SKU" | qoldiq va buyurtma sanasi, slotni avto-band qilish, yo'qolgan tovar | bozor tahlili, avto-stavka, repricer, AI javob, iOS/Android, Business'da API va MCP | qimmat; partiya, valyuta, kargo yo'q |
| [MARGN](https://margn.uz/) | faqat Uzum | Start 499 000, Pro 699 000; 14 kun sinov | SKU bo'yicha, Excel; "tannarxsiz kartochkalarni topish" | ombor, nakladnoy farqi, FBO Excel, yo'qolgan tovar da'vosi | ABC × XYZ, reklama (ACOS, DRR, ROMI), Telegram bot | partiya, valyuta yo'q; saytdagi sonlar bir-biriga zid |
| [SellerMind](https://sellermind.uz/en) | WB, Ozon, Uzum, Yandex | 299 000 (5 kabinet); 15 kun sinov | — (faqat "COGS kalkulyatori") | WMS (kirim, chiqim, sanoq, skaner), soatlik qoldiq sinxroni | PWA, yetkazib beruvchilar, reja-fakt | mijoz fikrlari "namuna" deb belgilangan; AI "tez orada" |
| [Robohub](https://robohub.uz/) | Uzum, WB, Ozon, Yandex | 500 000 (sahifaning pastki qismi xulosadan — qayta tekshirilsin) | "Tannarx" maydoni | FBO rejasi, yo'qolgan tovar | "1 000 dan ortiq sotuvchi", 7 til | foyda ta'riflari zaif (ADR-043 tahlili) |
| [Uzumer](https://uzumer.com/en) — **yangi** | Uzum | Essential 299 000 (2 do'kon), Pro 799 000 | — (marja kalkulyatori) | — | bozor va raqobatchi tahlili, bepul Chrome kengaytmasi | raqamlar "estimates derived from public marketplace data" |
| [Baraka Data](https://barakadata.uz/) | Uzum | 360 000 (yillik 252 000) | — | — | nisha qidirish | o'z sotuvlari "пока нет" |
| [SellerFlow](https://sellerflow.uz/) | Uzum | o'qib bo'lmadi (sahifa JavaScript bilan chiziladi) | — | — | — | tekshirilmadi |
| Uzum Sellers (rasmiy ilova) | Uzum | bepul | — | — | balans, pul yechish, sotuv voronkasi (2.38.0) | foyda yoki marja yo'q |
| [Sellerboard](https://sellerboard.com/) (Amazon) | Amazon, Walmart, Shopify | $19–79 (3 000–50 000 buyurtma/oy); 1 oy sinov | FIFO, partiya, davr; "partiya tugadi" va "tannarxsiz sotuv" ogohlantirishlari | tezlik "adjusted for out-of-stock days"; yo'ldagi, buyurtma qilingan, prep-markazdagi tovar sanaladi; "Missed Profit" 90 kun | 20 000+ sotuvchi; P&L issiqlik xaritasi; yilma-yil solishtirish | Uzum yo'q |
| [sellerdata](https://sellerdata.ru/) (WB, Ozon) | WB, Ozon, Yandex | 500–4 000 ₽ (aylanma bo'yicha); 1 oy sinov | davr va o'lcham bo'yicha | tezlik "по выкупам"; buyurtma nuqtasi = tezlik × (muddat + zaxira) | arzon, sodda | partiya yo'q |
| [MPfact](https://mpfact.ru/), [MPSTATS](https://mpstats.io/), [TrueStats](https://truestats.ru/), [UVIX](https://uvix.app/) | WB, Ozon | 2 280–13 200 ₽; 5 520–12 746 ₽; —; hozircha bepul | MPfact — partiya; UVIX — partiya | MPfact — "неснижаемый остаток"; MPSTATS — "Умная логистика" | kassa uzilishi ogohlantirishi; выкупsiz prognoz; Claude/ChatGPT ulash; MCP | Uzum yo'q |

**Xulosalar.**
1. *Ustunligimiz saqlanmoqda.* Sahifasi o'qilgan 7 ta Uzum servisining birortasi partiya, FIFO, valyuta kursi yoki kargo
   taqsimotini aytmaydi — tannarx "SKU'ga bitta raqam" (SellerFlow sahifasini o'qib bo'lmadi). Landing xabari shu bo'lishi kerak (06 §8 da bor).
2. *Ombor hisobi — raqobatchilarda bor, bizda xato bilan.* SellerPro, MARGN, Robohub buyurtma sanasi va yo'qolgan
   tovarni beradi. K1–K3 tuzatilmasa, D4 ustunligi ("o'zi o'rganadigan buyurtma rejasi") ishonchni yo'qotadi.
3. *Narx taklifimiz o'rinli.* Bozor 299 000 – 1 499 000; bizning 149 000 / 299 000 / 590 000 (01 §7) pastki chegarada.
   Aylanmaga bog'liq tarif — MPfact va sellerdata'da ham shunday.
4. *AI va MCP endi farqlovchi emas.* SellerPro Business'da MCP bor; Uzum API uchun ochiq MCP-ulagich chiqqan
   ([AnythingMCP](https://anythingmcp.com/guides/uzum-market-to-mcp), 16 vosita). Bizning M19 ning ma'nosi — xom API
   emas, **hisoblangan** foyda va tannarx. Reja o'zgarmaydi (B10.2), lekin landingda shunday aytiladi.
5. *Uchta asosiy raqobatchida Telegram xabarlari bor, bizda hali yo'q* (R2).

## 8. Temurning qarori kerak (har biriga tavsiya)

"Ha" desang — ADR yozib, 02/04/05 ni yangilab, kod va testni qilaman. Tavsiya birinchi turibdi.

**Temur qarori (2026-11-11): Q1–Q14 — hammasiga "ha"** (Q3 ni avval tushunmagan edi; tushuntirilgach — ha). Q4: S2 o'lchovi farqni 3% dan ancha katta ko'rsatdi (§11.2) — (a) varianti. Qarorlar: ADR-056 (Q3), ADR-057 (qolganlari); bajarilish tartibi — 05 B4.65–B4.76. Yangi savol: Q15 (§11.5).

| ID | Savol | Variantlar | Tavsiya va sababi |
|---|---|---|---|
| Q1 | F23 sotuv tezligi (K1, K2) | (a) oxirgi 14 ta **savdoda bo'lgan** kun (60 kungacha orqaga qarab), "7 kunga bo'lish" faqat tovar yoshi < 7 kun bo'lsa; Jarayondagi dona × yakunlanish ulushi; (b) faqat birinchi qismi; (c) o'zgartirmaslik | **(a).** Hozirgi tezlik aynan tovar qaytgan kuni 3,5 barobar xato — buyurtma qarori shu kuni qilinadi |
| Q2 | Holat va buyurtma sanasi (K3) | (a) ikki alohida signal: **"Buyurtma berish"** — hamma joydagi tovar (Uzum + postavka + omborim + yo'lda + Xitoyda) to'liq muddatga yetmaydi; **"Uzumga yuborish"** — Uzumdagi zaxira topshirish muddatidan kam, omborimda bor; (b) faqat holatga hamma tovarni qo'shish; (c) o'zgartirmaslik | **(a).** Ikki xil qaror — ikki xil signal; B5.2 va B5.3 baribir shuni talab qiladi |
| Q3 | ADR-051 ni ADR-055 ga moslash (K4) | "postavka keldi" = birinchi `dateAccepted` (savdoga chiqarilgan); hali chiqmagan postavka — kelmagan | **Ha.** Yangi fakt eski qarorni noto'g'ri qilgan (07 tartibi, 1-hol) |
| Q4 | Taqqoslash va prognoz (K6, K10) | (a) prognoz va "▲ %" da kutilayotgan qism × yakunlanish ulushi, "taxminiy" belgisi bilan; uch raqam o'zgarmaydi (ADR-036/037); (b) taqqoslash faqat yalpi buyurtmalar (F44) bo'yicha; (c) faqat izoh | **Avval S2 o'lchovi**, keyin (a): farq 3% dan kichik bo'lsa — (c) yetarli |
| Q5 | QQS rejimi (K7) | (a) hozir: "soliq hisoblanmadi" ochiq yoziladi (PR-3), to'liq hisob — QQS to'lovchi birinchi mijoz paydo bo'lganda; (b) oylik taxminni hozir qilish | **(a).** Hozircha bunday foydalanuvchi yo'q; yolg'on matn esa darhol tuzatiladi |
| Q6 | "Taxminiy" belgisi (K8, K9) | (a) tayyor sana: qabul → kargo to'langan → **keyingi bosqich sanasi**; Markaziy bank kursi — belgi emas, izoh ("kurs: Markaziy bank"); (b) faqat birinchi qismi | **(a).** "Taxminiy" faqat raqam haqiqatan noaniq bo'lganda chiqsin — sen ADR-051 da shuni so'ragansan |
| Q7 | Ma'lumotni hozirdan yig'ish (K11, K12) | snapshot — har mahsulot sinxronida bugungi qator yangilanadi (+ "kun ichida 0 ko'rildi" belgisi); sotuvda "Yakunlangan deb birinchi ko'rilgan vaqt" ustuni (migratsiya) | **Ha.** Arzon; keyin tiklab bo'lmaydi; pul oqimi (B5.7) va yo'qotilgan foyda (F34) shunga tayanadi |
| Q8 | B4 ni yopish (R1) | (a) B4.27, B4.55, B4.61 va sahifalash qoldig'i B5 boshiga ko'chadi; 14 kunlik sinov shu hafta boshlanadi; "Temurdan kutilmoqda" 5–7 bandga qisqaradi (qolgani: "ishlatib ko'r, xato chiqsa yoz"); (b) hozirgidek davom etish | **(a).** Aks holda B4 yopilmaydi; sinov — eng yaxshi tekshiruv |
| Q9 | Telegram oldinga (R2) | (a) B6.1–B6.2 (kunlik xulosa, kritik zaxira, tannarxsiz sotuv) B5 dan oldin; (b) hozirgi tartib | **(a).** 5–7 kunlik ish, har kuni foyda beradi, uchta asosiy raqobatchida bor |
| Q10 | Bosh sahifa tartibi (D1) | (a) uch raqam → davr chizig'i → **Diqqat talab qiladi** → kunlik grafik → zinapoya → KPI guruhlari (yig'iladi, tanlov eslanadi) → TOP/zarar → tovardagi pul; (b) faqat "Diqqat"ni tepaga; (c) o'zgartirmaslik | **(a).** Ma'lumot yashirilmaydi, faqat tartib o'zgaradi; ikkala variant skrinshotini PR'da ko'rsataman |
| Q11 | Telefonda ro'yxat ko'rinishi (D2) | tartib: Mahsulotlar → Ombor → Buyurtmalar (04 §7.4 da bor; Xaridlar namunasi bo'yicha: nom + 2–3 asosiy raqam, bosilsa tafsilot) | **Ha, shu tartibda.** Har biri alohida PR |
| Q12 | Menyu (D8) | tayyor bo'lmagan "Pul oqimi" va "Hisobotlar" yashiriladi (sahifa tayyor bo'lganda qaytadi) | **Ha** |
| Q13 | Rejaga qo'shimchalar (R3, X5) | PWA (manifest, ikonka) — B6.3 ga; jamoa ekrani va qurilmalar — B8.1 oldiga; hodisalar — B8 ga; Uzum API shartlarini tekshirish — hozir (sendan: kabinetdagi API shartlari matni) | **Ha** |
| Q14 | 03 §2 va ADR-004 ni haqiqatga moslash (R4) | hujjatda "o'z CSS tokenlari va komponentlari" deb yoziladi; kod o'zgarmaydi | **Ha** (faqat hujjat) |

## 9. Tasdiqsiz tuzatiladiganlar (har biri alohida kichik PR, oldingisi merge bo'lgach)

| PR | Mavzu | Nima kiradi |
|---|---|---|
| PR-1 | Shu hisobot | faqat hujjat |
| PR-2 | Aniq xatolar | K5 (oy prognozi), D5 (Buyurtmalar gorizontal skroll), D6 (grafik o'qi), D7 (KPI bo'linishi) — har biriga avval qizaradigan test |
| PR-3 | Soliq rejimi halolligi | K7: Sozlamalar matni va Foyda sahifasida "soliq hisoblanmadi" ogohlantirishi |
| PR-4 | Telefon: bosish maydoni | D4 (hamma sahifa va karkas), D10, D13; 360 px e2e hamma sahifaga |
| PR-5 | Xavfsizlik va CI | X1 (a'zolik so'rovi), X3 (bog'liqliklar auditi), T4 |
| PR-6 | Hujjat va eskirgan kod | R4 (Q14 dan tashqari), K13, K14 (havola) |
| PR-7 | Test qamrovi | T1, T2, T3 |
| PR-8 | Jadval va mayda jilo | D3 (ustun kengliklari), D9, D11 (ikonka, `theme-color`) |

## 10. Temurdan kerak

**Holat (2026-11-11): 1–3-bandlar bajarildi — natijalar §11 da.**

1. **§8 dagi qarorlar** — "hammasiga ha" yoki rozi bo'lmaganlaring raqami.
2. **Uchta o'lchov** (faqat o'qish, sir chiqmaydi) — so'rov matnini keyingi xabarda yuboraman, natijani chatga tashlaysan:
   S1 — oxirgi 14 kunlik tezlik hozir va 30 kundan keyin (K2); S2 — buyurtma yoshiga qarab yakunlanish ulushi
   (K6, K10); S3 — snapshot bo'lmagan kunlar soni (K11).
3. **Uchta savol** (sen bu bozorda ishlaysan): Uzum xarajat nomlarini boshqa sotuvchiga ruscha beradimi (K15);
   kabinetdagi "Analitika" bo'limida foyda yoki tannarx bormi — bir-ikki skrinshot (R5); Uzum sendan soliqni o'zi
   ushlab qoladimi (08 §6).

## 11. Javoblar va o'lchovlar (2026-11-11)

Manbalar: Temurning javoblari; staging'da faqat o'qish so'rovlari S1–S6 (summalar o'z do'konlarining; sir yo'q); Uzum
kabineti "Tahlil" bo'limi skrinshotlari (Xulosa, Sotuv voronkasi, Hodisalarni tahlil qilish); SellerMax "Asosiy"
(1–11 noyabr, ikkala do'kon, skrinshot).

### 11.1 Qarorlar

Q1–Q14 — "ha" (ADR-056, ADR-057). Q4 — (a): S2 farqi katta. Yangi: Q15 (11.5).

### 11.2 S1–S3 o'lchovlari

| | Natija | Xulosa |
|---|---|---|
| S1 (K2) | Oxirgi 14 kun, byDurii: 331 dona tezlikka kirgan — yakunlangan 16 (5%), jarayonda topshirilgan 132, topshirilmagan 183; bekor 115 (kirmagan). EL-ONE: 1 / 43 / 35, bekor 22 | Tezlikning 95% i yakunlanmagan buyurtmalardan. Yetilgan haftalarda 61% yakunlanadi (S2) — kutilgan yakuniy dona byDurii 0,61 × 446 = 272 (hisoblangan 331 → **≈ +22%**), EL-ONE 0,646 × 101 = 65 (79 → **≈ +21%**). Bu taxmin, aniq o'lchov emas |
| S2 (K6, K10) | byDurii 3–11-haftalar (yetilgan): yakunlangan 60,6%, bekor 30,7%, qaytarilgan 8,7%; EL-ONE 3–5-haftalar: 64,6% / 23,2% / 12,1%. Jarayondagi dona: byDurii 337 (0–2-haftalar), EL-ONE 84 | Joriy davrda "jarayonda" to'liq sanaladi, yetilgan davrda 39% chiqib ketgan — farq 3% dan ancha katta → **Q4 (a)** |
| S3 (K11) | Ikkala do'konda 25.10–10.11: 17 kun, 0 kun yo'q | Snapshot bo'shlig'i hozir muammo emas; Q7 baribir arzon va keyin tiklab bo'lmaydi |

### 11.3 Uzum kabineti "Tahlil": Daromad va Foyda qanday hisoblanadi

**Formulalar (isbot bilan):**
- **Daromad** = Σ sotuv narxi × dona, buyurtma yaratilgan sanasi bo'yicha, bekor qilinganlarsiz, **jarayondagilar ichida**
  (noyabrda hamma sotuv hali `PROCESSING`). Isbot: 10.11 da kabinet "Kecha" 1 383 400 — bizning bazada ham aynan 1 383 400 (S5b).
- **Foyda** = Daromad − **faqat komissiya**. Logistika, reklama, saqlash, jarima ayirilmaydi. Isbot: foyda/daromad
  kabinetda 6 581 043 / 8 404 200 = 78,3%, bazada 1 − 1 867 770 / 8 592 740 = 78,26% (S5a); 10.11 da kabinet foydasi
  1 095 512, bizning `sellerProfit` (F6: tushum − komissiya − logistika) 806 762, ayirma 288 750 — logistikaning kunlik
  hajmi. Aniq komissiya (10.11) hali o'lchanmagan. B2.11 da tasdiqlangan: `sellerProfit` = F3 − F4 − F5.

**1–11 noyabr, ikkala do'kon (SellerMax, skrinshot):**

| Qator | So'm | Buyurtmadan | Tushumdan |
|---|---|---|---|
| Buyurtmalar summasi | 11 092 970 | 100% | |
| − Bekor qilingan | 1 947 460 | 17,6% | |
| − Qaytarilgan | 527 790 | 4,8% | |
| = **Tushum** (kabinet "Daromad" ga mos) | 8 617 720 | 77,7% | 100% |
| − Uzum ushlab qolgan (komissiya, logistika, reklama, saqlash, jarima) | 4 031 538 | 36,3% | 46,8% |
| − Tannarx | 2 647 460 | 23,9% | 30,7% |
| = **Sof foyda** | 1 938 722 | 17,5% | **22,5%** |

Kabinet "Foyda"si ≈ tushum − komissiya = 8 617 720 × 0,7826 ≈ **6,74 mln** (komissiya ulushi S5a dan). Haqiqiy sof
foyda — 1,94 mln: kabinet raqami **≈ 3,5 barobar baland**. Farq 4,81 mln = logistika va boshqa Uzum xarajatlari ≈ 2,16
mln (S5a: logistika 1 799 250; S6: reklama 218 398, saqlash 51 700, jarima 2 500; yig'indi 4 031 538 dan komissiya ≈ 1,87
mln ayirilgan; ±0,1 mln — sinxron vaqti va xarajat sanasi farqi) + tannarx 2,65 mln.

**Kabinet hisobidagi kamchiliklar:**

| ID | Topilma | Holat |
|---|---|---|
| U1 | Foyda tannarxsiz (Uzum tannarxni bilmaydi) — marja 78% ko'rinadi, haqiqiy 22,5% | Tasdiqlandi |
| U2 | Foyda logistikani ayirmaydi (tushumning ≈ 20,9%) | Tasdiqlandi (S5a, nisbat) |
| U3 | Reklama, saqlash, jarima ayirilmaydi (1–11 noyabr: 272 598, tushumning 3,2%) | Tasdiqlandi (nisbat 78,3% = faqat komissiya) |
| U4 | Bekor va qaytish: jarayondagilar to'liq turadi; yetilgan davrda 39% chiqib ketadi → joriy oy ≈ 20% baland. Bizda: bekor qatorlar hozir 22,6%, yakuniy 39% (S2) → yana ≈ −21% kutiladi | Hisoblangan taxmin |
| U5 | "Bugun −82,49%" — yarim kun kechagi to'liq kun bilan (bizdagi K5 ning o'xshashi) | Tasdiqlandi (skrinshot) |
| U6 | Logistika vaqti: qatorda buyurtma paytida (oktabr — 0), Uzum aslida olib ketilganda yechadi (B4.23). Kabinet qator qiymatini olsa, oktabr foydasi baland, noyabrniki past chiqadi. Noyabr: qatorda 1 799 250, yechilgani 1 185 000 − 152 750 = 1 032 250 | Qisman (B4.23, S6); kabinet qatorni olishi — taxmin |
| U7 | Soliq (1% aylanma, YATT ijtimoiy soliq) ayirilmaydi | Tasdiqlandi |
| U8 | Brak (`DEFECTED`) va yo'q qilingan (`UTILIZED`) tovar tannarxi sanalmaydi | Mantiq |
| U9 | "Qaytarishlar" 358 dona (2 ta do'kon), davri yozilmagan — solishtirib bo'lmaydi; "O'rtacha chek" da 6 oy va joriy oy aralash | Skrinshot |
| U10 | "Sotuv voronkasi" buyurtma yaratilgan sanasi bo'yicha; foyda ustuni yo'q (so'nggi ustun nomi o'qilmadi, qiymatlari sotib olish foiziga o'xshaydi) | Skrinshot, qisman |

**Qaytish sabablari** (kabinet, 358 dona; B4.54a da so'ralgan ro'yxat): Mijoz sababni ko'rsatmadi 302 (84,3%); O'lcham
mos kelmadi 25 (6,9%); Mahsulot sifati yoqmadi 12 (3,3%); Nuqson 7 (1,9%); Mahsulot saytdagi rasmga mos kelmaydi 7
(1,9%); Noto'g'ri mahsulot keldi 4 (1,1%); Mahsulot to'plami bilan bog'liq muammo 1 (0,2%).

**Ma'nosi mahsulot uchun:** Uzumning o'z "foyda"si sotuvchini 3,5 barobar aldaydi — bu bizning asosiy ustunligimiz
(tannarx va hamma xarajat bilan sof foyda). Landing uchun real misol: "Kabinetda 6,7 mln, aslida 1,9 mln" — Temur ruxsati bilan
(06 §8 ga qo'shiladi). Kod: kabinet bilan solishtirish uchun Foyda sahifasida "Uzum kabineti ko'rsatadigan" qatorni qo'shish — taklif (Temur ko'rsin).

### 11.4 Xarajat nomlari (K15, S4)

Temurning ikkala do'konida xarajat matnlari faqat o'zbekcha; toifa **kodga** qarab aniqlanadi (`LOGISTICS-VOLUME`,
`Y000120`, `C000003` …) — til ta'sir qilmaydi. Matnga faqat reklama summasi tayanadi ("Xaridor tovarni olganida … so'm").
Boshqa sotuvchida matn ruscha kelishi mumkinligi **tekshirilmadi** — birinchi tashqi sotuvchi bilan (B8), ruscha namuna
bo'lsa regressiya testi bilan. Shablonlar: logistika xizmatlari to'lovi, logistika to'lovini qaytarish, "Buyurtmalarni
ko'paytirish to'lovi, tovar IDsi — #. Xaridor tovarni olganida # so'm …" (reklama), saqlash xizmatlari, qaytarishni
saqlash (yukxat bo'yicha), qabul qilishdagi farqlar (yetishmovchilik / ortiqcha — jarima), "[Kompensatsiya] …".

### 11.5 Soliq (Temur javobi) va yangi savol Q15

- **YATT:** Uzum soliqni **ushlamaydi** — soliq to'lovchining soliq akkauntiga keladi (Temur). Ikki to'lov: ijtimoiy soliq
  har oy — 1 BHM (Temur: 440 000 so'm; BHM miqdori rasmiy manbadan tekshirilmadi), va aylanmadan soliq — **1%**,
  Temurning fikricha tushumdan (rasmiy tekshirilmadi; 08 §6: 2026 da 1%, yillik 1 mlrd gacha).
- **MChJ va o'zini o'zi band qilganlar:** aniqlanmadi. Qidiruv (gov.uz, buxgalter.uz) bo'yicha 2026 da bazaviy stavkalar:
  QQS 12%, foyda solig'i 15%, aylanma solig'i 4% (elektron tijorat uchun pasaytirilgan stavkalar bekor — 08 §6 bilan mos);
  platformaning soliq agentligi Uzum sotuvchilari uchun **topilmadi** (taksi agregatorlari uchun bor). Aniqlash yo'li:
  Uzum seller yordami yoki soliq maslahatchisi — taxmin qilinmaydi. 08 §6 dagi "to'lov tashkilotlarining raqamli platformalari
  soliq agenti" bandi YATT uchun Temurning tajribasiga zid — YATT uchun Temur gapi ustun, 08 §6 yangilandi.
- **Topilma:** kodda va rejada YATT ijtimoiy soliq (oyiga 1 BHM) umuman uchramaydi (`packages`, `docs/plan` bo'yicha qidiruv: 0 ta);
  sof foyda ijtimoiy soliq hisobiga oyiga ≈ 440 000 so'mga baland ko'rinadi. Do'kon foydasiga bo'linmaydigan
  doimiy oylik xarajat — Xarajatlar (o'z xarajati) sifatida kiritish mumkin.
- **Q15 (yangi, Temur hal qiladi):** YATT ijtimoiy soliqni qanday ko'rsatamiz? (a) hozir: Sozlamalar → soliq matnida
  eslatma — "ijtimoiy soliqni Xarajatlarga o'zingiz kiriting" (hisob o'zgarmaydi; PR-3 ga kiradi); (b) Sozlamalarda
  "Ijtimoiy soliq (oyiga, so'm)" maydoni, har oy tashkilot darajasida sof foydadan ayriladi (formula o'zgaradi — F11, ADR bilan).
  **Tavsiya: (a) hozir, (b) — birinchi YATT mijoz so'raganda yoki Temur xohlasa.**
