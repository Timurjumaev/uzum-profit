# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **B5 — ustunlik funksiyalari** (kod: B5.0b ✓; keyingisi B5.0d). Parallel: **B4 yopilishi** — Temurning 14 kunlik sinovi; ta'minot (TM1–TM8, ADR-061) — kod tugadi, Temur real xaridlarda sinaydi; **B6** — Temur kunlik xulosani olyapti (7 kunlik sinov B6.4 dan keyin sanaladi). **Reja:** B5–B10 tanqidiy tahlili tugadi (2026-11-16, ADR-063–067, 09 §12–§16) |
| Keyingi vazifa | **B5.0d** (Foyda tafsiloti sahifalash) → **B6.4** (Telegram xabar tuzatishlari) → **TM9** (ta'minot tuzatishlari, ADR-068 — tasdiq kutilmoqda) → **B5.1** (F25 muddat — tuzatish) → B5.2 → B6.5 → B5.4 → B5.7 → B5.6 (+ B5.0f) → B5.5 → B5.9 → B5.8 → B6.3 → B6.6 → **B7** (B7.1 → B7.2 → B7.3 → B7.5) → **B8-A** (betaga tayyor; birinchi — B8.6a Uzum API shartlari) → **B9** (yopiq beta, 6–8 hafta) → **B8-B** (tarif va to'lov) → **B10** ([05](05-bosqichlar.md); qarorlar — [07](07-qarorlar.md) ADR-063–067; topilmalar — [09](09-audit.md) §12–§16). Har bosqichning "Keyinga" ro'yxati B9.6 da yopiladi |
| Temurdan kutilmoqda | (ADR-059: "ishlatib ko'r, xato chiqsa yoz".) **1) 22-noyabrgacha — yangi Uzum kaliti:** Ruxsatlar — Faqat o'qish; Do'kon — Barcha do'konlar; muddat — 1 yil yoki cheklanmagan; staging'da almashtirib, "Ma'lumotlar holati" yashilligini tekshirish (05 B8.16). **2) 14 kunlik sinov** — kundalik ish faqat staging'da; xato yoki noqulay joy — skrinshot bilan bir qator (B4 chiqishi); real xaridlarda ta'minot oqimi (ADR-061). **2a) Ta'minot bo'yicha uch javob va ADR-068 ga "ha"** (09 §17: postavkani doim dasturdagi Excel bilan yaratasanmi; Omborim soni haqiqatga mosmi; kiritish tezligi; TM9.6 qarori). **3) B5 savollari** (8 ta, chatda 2026-11-16): Uzumda necha kunlik zaxira; karrali partiya; kompensatsiya qaysi narxdan; bekor tovar necha kunda qaytadi; kabinetda yo'qolgan tovar soni; to'lov o'zi o'tadimi; qaysi to'lov jadvali; oxirgi 2–3 real to'lov; + B5.0f qatori kerakmi. **4) Uzum yordam xizmatidan yozma javob** — uchinchi tomon servisi API kalitini ishlatishi mumkinmi (B8.6a; shartnoma va kabinet o'qildi — 08 §9, noaniq). **5) B8 "T — hozir"** (kalendar ishlari): `sellermax.uz` domeni va tovar belgisi tekshiruvi (ADR-030), yuridik shaxs bo'yicha buxgalter maslahati (Q4), O'zbekistondagi server provayderida akkaunt (Q2), shaxsiy ma'lumotlar bazasi arizasi. **6)** MChJ va o'zini o'zi band qilganlar uchun Uzum soliq ushlashi va stavkalari (08 §6); BHM 440 000 kuchga kirish sanasi — farmon matni |
| Oxirgi yangilanish | 2026-11-17 — ta'minot (ADR-061) tanqidiy tahlili: 16 topilma (09 §17), tuzatishlar — TM9 (ADR-068, tasdiq kutilmoqda), faqat hujjat. Oldin: B5–B10 tahlili (ADR-063–067). Oldingi yozuvlar — `CHANGELOG.md` |

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
