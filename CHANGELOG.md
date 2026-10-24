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
