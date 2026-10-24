# CLAUDE.md — bu repozitoriyda ishlash qoidalari

## Avval o'qing

**Har sessiya boshida:** `docs/plan/README.md` (holat va tamoyillar), keyin `docs/plan/05-bosqichlar.md` dagi
joriy bosqich. Hamma ish shu production rejasi bo'yicha. Rejadan chetga chiqish faqat
`docs/plan/07-qarorlar.md` dagi tartib bilan.

## Loyiha

Uzum Market sotuvchilari uchun foyda, tannarx (Xitoy partiyalari) va ombor hisobi. Egasi — Temur (GitHub:
Timurjumaev). Avval o'z do'konlari (byDurii 106121, EL-ONE 135204), keyin boshqa sotuvchilarga SaaS sifatida.

## Muloqot

- Temur bilan o'zbek tilida (lotin), samimiy ("jigar"), qisqa. U band — faqat u qila oladigan narsani so'rang.
- Uzum API kalitini **hech qachon so'ramang**. Real API tekshiruvi: legacy'da Temur `python3 -m uzum_profit selfcheck`
  ishlatadi; yangi tizimda — staging serverda o'zi kalit kiritadi.
- **Real ma'lumot kerak bo'lsa — to'xtash.** Vazifa uchun real Uzum API, Temurning kompyuteridagi ma'lumot
  (`uzum.db`, `uzum_history.json` va h.k.) yoki `.env` kerak bo'lsa: taxmin qilmasdan ishni shu joyda to'xtating va
  Temurga yozing — "Mac'da shu buyruqni ishga tushir:" + **aniq, nusxalab qo'yiladigan buyruq** (qaysi papkada,
  qaysi `python3` bilan) + **natijani qayerga yuborish** (masalan: "chiqqan matnni shu chatga tashla" yoki
  "`~/uzum_samples.json` faylini shu yerga yukla"). Buyruq kalitni chiqarmasligi kerak; kalitni so'ramang.

## Tuzilma

- `uzum_profit/`, `tests/` — **legacy** ilova (Python 3.8 stdlib, SQLite). Temurning Mac'ida ishlaydi
  (2026-10 dan Python 3.15: `/Library/Frameworks/Python.framework/Versions/3.15/bin/python3`). B4 oxirigacha faqat
  kritik tuzatishlar; Python 3.8 bilan ham mos bo'lishi shart (CI: 3.8, 3.13, 3.15).
- `scripts/compare_legacy.py` — B1.9 solishtirish (faqat stdlib, Temurning Mac'ida `python3` bilan lokal).
  Testlar: `UZUM_TEST_HISTORY=/mnt/user-data/uploads/uzum_history.json python3 -m unittest tests.test_all`
  (fayl bo'lmasa 3 test o'tkazib yuboriladi); Python 3.8: `/root/.local/bin/python3.8`.
- `packages/core`, `apps/api`, `apps/web`, `apps/bot`, `infra/` — yangi tizim (B0 dan boshlab), tafsilot
  `docs/plan/03-arxitektura.md`.

## Qat'iy qoidalar

- `.env`, `*.db`, `uzum_history.json`, `uzum_samples*.json` — repozitoriyga kirmaydi.
- Pul — `Decimal`; formulalar faqat `packages/core` da, docstring'da F-raqam (`docs/plan/02-funksiyalar.md`).
- UI matnlarida oʻ/gʻ uchun U+02BB, tutuq uchun U+02BC; ranglar va shrift `docs/plan/04-dizayn.md` dan.
- Sandbox Uzum API'ga chiqa olmaydi (WAF va tarmoq) — real ma'lumot faqat Temur yoki staging orqali.
- Commit: Conventional Commits; har vazifadan keyin `docs/plan/README.md` holat jadvali va `05` belgisi yangilanadi.

## Ish oqimi (Temur tasdiqlagan)

1. Har vazifa `main` dan yangi branch'da (`claude/<vazifa>-...`), oldingi PR merge bo'lgandan keyingina.
2. Vazifa tugagach: holat jadvali, `05` belgisi, `CHANGELOG.md` → commit → push → **PR'ni o'zim ochaman**
   (`.github/pull_request_template.md` bo'yicha) va PR faoliyatiga obuna bo'laman.
3. CI yashil bo'lguncha kuzataman: qizarsa o'zim tuzataman, izohlarga javob beraman.
4. **Merge faqat Temur qiladi.** U "merge bo'ldi" deganidan keyin keyingi vazifa yangi branch'da boshlanadi.
5. Har qadamdan keyin Temurga o'zbekcha qisqa xabar.
