# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **B2. Backend poydevori va staging** (B1 tugadi, 2026-10-24) |
| Keyingi vazifa | B2.10 Staging server (Q2 kerak) |
| Temurdan kutilmoqda | Q2 (server provayderi) — B2.10 gacha; ixtiyoriy: partiya qatorlariga SKU biriktirish |
| Oxirgi yangilanish | 2026-10-25 (B2.9 tayyor: o'qish API'lari — dashboard, pnl, skus, sales, expenses, inventory + OpenAPI tiplari) |

(Har vazifa tugaganda shu jadval va 05-bosqichlar.md dagi belgi yangilanadi.)

## Fayllar

| Fayl | Nima bor |
|---|---|
| [01-mahsulot.md](01-mahsulot.md) | kim uchun, bozor, raqobat, ustunliklar, qilinmaydigan narsalar, tariflar, o'lchovlar |
| [02-funksiyalar.md](02-funksiyalar.md) | modullar M1–M21, qabul mezonlari, **formulalar F1–F40** |
| [03-arxitektura.md](03-arxitektura.md) | texnologiyalar, repo, ma'lumotlar modeli, Uzum integratsiyasi, tannarx dvigateli, xavfsizlik, testlar, CI/CD |
| [04-dizayn.md](04-dizayn.md) | shrift, ranglar (tekshirilgan), komponentlar, maketlar, matn va formatlash |
| [05-bosqichlar.md](05-bosqichlar.md) | **B0–B10 vazifalar ro'yxati**, chiqish mezonlari, Temurning vazifalari |
| [06-operatsiyalar.md](06-operatsiyalar.md) | server, zaxira, yordam, huquq, to'lov, marketing, mijoz suhbatlari, chiqish ro'yxati |
| [07-qarorlar.md](07-qarorlar.md) | ADR jurnali, ochiq savollar Q1–Q9, rad etilgan g'oyalar, rejani o'zgartirish tartibi |
| [08-tadqiqot.md](08-tadqiqot.md) | raqobatchilar, xorijiy namunalar, g'oyalar banki, Uzum API, tariflar, soliq, huquq faktlari (manbalar bilan) |

## Ish tartibi (har sessiyada)

1. Shu faylni, keyin 05-bosqichlar.md dagi joriy bosqichni o'qish.
2. Navbatdagi belgilanmagan vazifani olish; kerakli bo'limlarni (02, 03, 04) o'qish.
3. Alohida branch → kod + testlar → CI yashil → merge.
4. 05 dagi belgi, shu faylning "Holat" jadvali va `CHANGELOG.md` yangilanadi.
5. Temurga o'zbekcha qisqa xabar: nima qilindi, undan nima kerak (bo'lsa).

Temur rejadan tashqari narsa so'rasa: qaysi bosqichga tegishli ekanini aytib, rejaga qo'shish (07 tartibi bilan)
yoki hozir qilish kerakligini kelishib olish. Joriy bosqich chiqish mezoni bajarilmaguncha keyingisiga o'tilmaydi.

## Tamoyillar (hamma qarorlar shunga tekshiriladi)

1. **Har raqam tushuntiriladi** — formula (F-raqam) va manba yozuvlar bir bosishda.
2. **Hech qanday biznes doimiysi kodda qotirilmaydi** — tariflar, kodlar, soliq, davrlar bazada, sana bo'yicha.
3. **Pul faqat Decimal** — float yo'q.
4. **Bitta formula — bitta joy** (`packages/core`); API va UI qayta hisoblamaydi.
5. **Faqat rasmiy Uzum Open API**; parol yoki kabinet tokeni so'ralmaydi.
6. **Ma'lumot O'zbekistonda**; Uzum kaliti shifrlangan, loglarda yo'q.
7. **Sotuvchi kiritgani muqaddas** — sinxron uni hech qachon o'zgartirmaydi yoki o'chirmaydi.
8. **"Ma'lumot yo'q" ≠ "sinxron ishlamayapti"** — har sahifada ma'lumot yangiligi ko'rinadi.
9. **Taxmin yashirilmaydi** — tannarxsiz yoki taxminiy qism doim belgilanadi.
10. **Mobil va Telegram birinchi** — 360 px da to'liq ishlaydi.
11. **Testsiz kod yo'q**; CI yashil bo'lmasa merge yo'q.
12. **Temurning vaqti qimmat** — undan faqat u qila oladigan narsa so'raladi (qaror, akkaunt, sinov).
