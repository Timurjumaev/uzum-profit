# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **Ta'minot qayta loyihasi (ADR-061, TM1–TM8) — kod qismi tugadi (2026-11-13)**, Temur staging'da real xaridlarda sinaydi; parallel: **B4 yopilishi** — Temurning 14 kunlik sinovi (B4 kod qismi tugadi). B2 tugadi (2026-10-27), B3 tugadi (2026-10-26) |
| Keyingi vazifa | ~~TM0 reja~~ ✓ → ~~TM1 model va yadro~~ ✓ → ~~TM2 uch holat va xarid oynasi~~ ✓ → ~~TM3 kargo puli jadvali~~ ✓ → ~~TM4 sanash~~ ✓ → ~~TM5 omborim~~ ✓ → ~~TM6 Uzumga jo'natish~~ ✓ → ~~TM7 qabul farqi~~ ✓ → ~~TM8 yakun~~ ✓ → ~~B6.1 hodisalar~~ ✓ → ~~B6.2 Telegram bot~~ ✓ → ~~B5 tanqidiy tahlili~~ ✓ (ADR-063, 09 §12) → ~~B6 tanqidiy tahlili~~ ✓ (ADR-064 tasdiqlandi, 09 §13) → **B5**: ~~B5.0b~~ ✓ (PR #170 da) → **B5.0d** → **B6.4** (xabar tuzatishlari) → **B5.1** (F25 tuzatish) → B5.2 → B5.4 → B5.7 → B5.6 → B5.5 → B5.9 → B5.8 ([05](05-bosqichlar.md), [07 ADR-063](07-qarorlar.md)); B5.0e → B8.10, B5.10 → B9.5. **Keyin:** B6.3. B4 chiqishi: Temur 14 kun faqat yangi dasturda, kritik xato yo'q; keyin legacy `legacy/` ga. B3 qoldig'i: Q1 tovar belgisi tekshiruvi (ADR-030), `sellermax.uz` domeni |
| Temurdan kutilmoqda | (ADR-059: eski tekshiruvlar ro'yxati o'rniga — "ishlatib ko'r, xato chiqsa yoz".) 1) **14 kunlik sinovni boshlash** — kundalik ish faqat staging'da, legacy ochilmaydi; 2) xato yoki noqulay joy — skrinshot bilan bir qator; 3) Uzum API'ni uchinchi tomon ishlatishi shartlari — kabinetdagi matn (Q13); 4) MChJ va o'zini o'zi band qilganlar uchun Uzum soliq ushlashi va stavkalari (08 §6, ADR-058); 5) BHM 440 000 kuchga kirish sanasi (1 sentyabr / 1 iyul) — farmon matni; 6) har TM dan keyin staging'da real xarid bilan sinash (ADR-061); 7) Q1 tovar belgisi tekshiruvi va `sellermax.uz` domeni (B3 qoldig'i); 8) ~~ADR-063 ga "ha"; pul yechish jadvali — butun akkauntga bitta~~ ✓ 2026-11-16; **B5 savollari** (chatda, 2026-11-16: 8 ta qisqa savol — B5.2, B5.4, B5.7 uchun); **ADR-067 ga "ha"** (B9 va B10 qayta tuzilishi); **B8 "T — hozir"** kalendar ishlari (05 B8: domen, tovar belgisi, yuridik shaxs maslahati, provayder akkaunti, reyestr arizasi); 9) ~~bot tokeni~~ ✓ 2026-11-15 — **7 kun kunlik xulosani olish** (B6 chiqishi: raqamlar ilova bilan bir xil, keraksiz xabar yo'q) |
| Oxirgi yangilanish | 2026-11-16 (ADR-067: B9 va B10 tanqidiy tahlili — 16 topilma (09 §16), faqat hujjat; ADR-066 tasdiqlandi; B7.4 — "Keyinga"; oldin: ADR-066: B8 tanqidiy tahlili — 16 topilma (09 §15), B8 ikki qismga bo'lindi (B8-A → B9 → B8-B), faqat hujjat; ADR-065 tasdiqlandi; oldin: ADR-065: B7 tanqidiy tahlili — 14 topilma (09 §14), B7 qayta tuzildi, faqat hujjat; ADR-064 tasdiqlandi, bot chatidan A18–A21; oldin: ADR-064: B6 tanqidiy tahlili — 17 topilma (09 §13), B6 qayta tuzildi, faqat hujjat; oldin: B5.0b: "Chegarada" marja chegarasi Sozlamalarda; ADR-063 tasdiqlandi; oldin: ADR-063: B5 tanqidiy tahlili — 21 topilma (09 §12), B5 qayta tuzildi, faqat hujjat; oldin: ADR-062: umumiy xarajatlar — akkaunt xarajatlari, qat'iy soliq, do'konsiz o'z xarajatlari — do'konlarga taqsimlanmaydi, alohida ko'rsatiladi; oldin: akkaunt xarajati ikki marta yozilishi tuzatildi, migratsiya 0030) |

(Har vazifa tugaganda shu jadval va 05-bosqichlar.md dagi belgi yangilanadi.)

## Fayllar

| Fayl | Nima bor |
|---|---|
| [01-mahsulot.md](01-mahsulot.md) | kim uchun, bozor, raqobat, ustunliklar, qilinmaydigan narsalar, tariflar, o'lchovlar |
| [02-funksiyalar.md](02-funksiyalar.md) | modullar M1–M21, qabul mezonlari, **formulalar F1–F53** |
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
