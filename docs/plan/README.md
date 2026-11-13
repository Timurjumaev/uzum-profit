# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **Ta'minot qayta loyihasi (ADR-061, TM1–TM8)** — B5 ning boshi, Temur qarori bilan hozir; parallel: **B4 yopilishi** — Temurning 14 kunlik sinovi (B4 kod qismi tugadi). B2 tugadi (2026-10-27), B3 tugadi (2026-10-26) |
| Keyingi vazifa | ~~TM0 reja~~ ✓ → ~~TM1 model va yadro~~ ✓ → ~~TM2 uch holat va xarid oynasi~~ ✓ → ~~TM3 kargo puli jadvali~~ ✓ → ~~TM4 sanash~~ ✓ → ~~TM5 omborim~~ ✓ → ~~TM6 Uzumga jo'natish~~ ✓ → **TM7 qabul farqi** → TM8 yakun ([05](05-bosqichlar.md), [07 ADR-061](07-qarorlar.md)). **Keyin:** B6.1–B6.2 (Telegram), B5.0 va qolgan B5. B4 chiqishi: Temur 14 kun faqat yangi dasturda, kritik xato yo'q; keyin legacy `legacy/` ga. B3 qoldig'i: Q1 tovar belgisi tekshiruvi (ADR-030), `sellermax.uz` domeni |
| Temurdan kutilmoqda | (ADR-059: eski tekshiruvlar ro'yxati o'rniga — "ishlatib ko'r, xato chiqsa yoz".) 1) **14 kunlik sinovni boshlash** — kundalik ish faqat staging'da, legacy ochilmaydi; 2) xato yoki noqulay joy — skrinshot bilan bir qator; 3) Uzum API'ni uchinchi tomon ishlatishi shartlari — kabinetdagi matn (Q13); 4) MChJ va o'zini o'zi band qilganlar uchun Uzum soliq ushlashi va stavkalari (08 §6, ADR-058); 5) BHM 440 000 kuchga kirish sanasi (1 sentyabr / 1 iyul) — farmon matni; 6) har TM dan keyin staging'da real xarid bilan sinash (ADR-061); 7) Q1 tovar belgisi tekshiruvi va `sellermax.uz` domeni (B3 qoldig'i) |
| Oxirgi yangilanish | 2026-11-13 (TM6: Uzumga jo'natish — Excel Uzum shablonida, donalar band, postavka bilan avtomatik bog'lash, xaridda dona darajasidagi holat; migratsiya 0026) |

(Har vazifa tugaganda shu jadval va 05-bosqichlar.md dagi belgi yangilanadi.)

## Fayllar

| Fayl | Nima bor |
|---|---|
| [01-mahsulot.md](01-mahsulot.md) | kim uchun, bozor, raqobat, ustunliklar, qilinmaydigan narsalar, tariflar, o'lchovlar |
| [02-funksiyalar.md](02-funksiyalar.md) | modullar M1–M21, qabul mezonlari, **formulalar F1–F52** |
| [03-arxitektura.md](03-arxitektura.md) | texnologiyalar, repo, ma'lumotlar modeli, Uzum integratsiyasi, tannarx dvigateli, xavfsizlik, testlar, CI/CD |
| [04-dizayn.md](04-dizayn.md) | shrift, ranglar (tekshirilgan), komponentlar, maketlar, matn va formatlash |
| [05-bosqichlar.md](05-bosqichlar.md) | **B0–B10 vazifalar ro'yxati**, chiqish mezonlari, Temurning vazifalari |
| [06-operatsiyalar.md](06-operatsiyalar.md) | server, zaxira, yordam, huquq, to'lov, marketing, mijoz suhbatlari, chiqish ro'yxati |
| [07-qarorlar.md](07-qarorlar.md) | ADR jurnali, ochiq savollar Q1–Q9, rad etilgan g'oyalar, rejani o'zgartirish tartibi |
| [08-tadqiqot.md](08-tadqiqot.md) | raqobatchilar, xorijiy namunalar, g'oyalar banki, Uzum API, tariflar, soliq, huquq faktlari (manbalar bilan) |
| [09-audit.md](09-audit.md) | tanqidiy tahlil (2026-11-11): topilgan muammolar, reja va dizayn topilmalari, raqobatchilar, Temurning qarori kerak bo'lgan savollar |

## Ish tartibi (har sessiyada)

1. Shu faylni, keyin 05-bosqichlar.md dagi joriy bosqichni o'qish.
2. Navbatdagi belgilanmagan vazifani olish; kerakli bo'limlarni (02, 03, 04) o'qish.
3. Alohida branch → kod + testlar → CI yashil → merge.
4. 05 dagi belgi, shu faylning "Holat" jadvali va `CHANGELOG.md` yangilanadi.
5. Temurga o'zbekcha qisqa xabar: nima qilindi, undan nima kerak (bo'lsa).

Temur rejadan tashqari narsa so'rasa: qaysi bosqichga tegishli ekanini aytib, rejaga qo'shish (07 tartibi bilan)
yoki hozir qilish kerakligini kelishib olish. Joriy bosqich chiqish mezoni bajarilmaguncha keyingisiga o'tilmaydi.
(Istisno — ADR-061: ta'minot B4 sinovi bilan parallel.)

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
