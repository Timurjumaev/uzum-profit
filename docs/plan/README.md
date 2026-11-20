# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **B5 — ustunlik funksiyalari** (kod: B5.0b ✓, B5.0d ✓; keyingisi B6.4). Parallel: **B4 yopilishi** — Temurning 14 kunlik sinovi; ta'minot (TM1–TM8, ADR-061) — kod tugadi, Temur real xaridlarda sinaydi; **B6** — Temur kunlik xulosani olyapti (7 kunlik sinov B6.4 dan keyin sanaladi). **Reja:** B5–B10 tanqidiy tahlili tugadi (2026-11-16, ADR-063–067, 09 §12–§16) |
| Keyingi vazifa | **B5.4** (B6.5 ✓, B5.2 ✓ 2026-11-19, TM9 ✓, B5.0d ✓, B6.4 kodi ✓ — yopilishi: A21 staging so'rovi va 7 kunlik sinov, B5.1 ✓ 2026-11-18) → B5.7 → B5.6 (+ B5.0f) → B5.5 → B5.9 → B5.8 → B6.3 → B6.6 → **B7** (B7.1 → B7.2 → B7.3 → B7.5) → **B8-A** (betaga tayyor; birinchi — B8.6a Uzum API shartlari) → **B9** (yopiq beta, 6–8 hafta) → **B8-B** (tarif va to'lov) → **B10** ([05](05-bosqichlar.md); qarorlar — [07](07-qarorlar.md) ADR-063–067; topilmalar — [09](09-audit.md) §12–§16). Har bosqichning "Keyinga" ro'yxati B9.6 da yopiladi |
| Temurdan kutilmoqda | **0) B5.4 o'lchovi (staging deploy bo'lgach):** `ssh -i ~/Downloads/awskey.pem ubuntu@16.170.178.179 'sudo -u deploy /srv/uzum-profit/infra/staging/realcheck.sh' > ~/realcheck.json` → fayldagi `checks.lost` bo'limini yuborish (F31/F32 shundan keyin). (ADR-059: "ishlatib ko'r, xato chiqsa yoz".) **1) 22-noyabrgacha — yangi Uzum kaliti:** Ruxsatlar — Faqat o'qish; Do'kon — Barcha do'konlar; muddat — 1 yil yoki cheklanmagan; staging'da almashtirib, "Ma'lumotlar holati" yashilligini tekshirish (05 B8.16). **2) 14 kunlik sinov** — kundalik ish faqat staging'da; xato yoki noqulay joy — skrinshot bilan bir qator (B4 chiqishi); real xaridlarda ta'minot oqimi (ADR-061). **3) B5 savollari** (8 ta, chatda 2026-11-16): Uzumda necha kunlik zaxira; karrali partiya; kompensatsiya qaysi narxdan; bekor tovar necha kunda qaytadi; kabinetda yo'qolgan tovar soni; to'lov o'zi o'tadimi; qaysi to'lov jadvali; oxirgi 2–3 real to'lov; + B5.0f qatori kerakmi. **4) Uzum yordam xizmatidan yozma javob** — uchinchi tomon servisi API kalitini ishlatishi mumkinmi (B8.6a; shartnoma va kabinet o'qildi — 08 §9, noaniq). **5) B8 "T — hozir"** (kalendar ishlari): `sellermax.uz` domeni va tovar belgisi tekshiruvi (ADR-030), yuridik shaxs bo'yicha buxgalter maslahati (Q4), O'zbekistondagi server provayderida akkaunt (Q2), shaxsiy ma'lumotlar bazasi arizasi. **6)** MChJ va o'zini o'zi band qilganlar uchun Uzum soliq ushlashi va stavkalari (08 §6); BHM 440 000 kuchga kirish sanasi — farmon matni |
| Oxirgi yangilanish | 2026-11-19 — **B5.4 (1-qadam)** F30 tuzatildi: hech sotilmagan tovar Uzumda birinchi ko'ringanidan 30 kun o'tgach nelikvid (kecha kelgan yangi tovar emas); B5.4 ning qolgani (F31/F32) real ma'lumot talab qiladi — `realcheck lost` Temur tomonidan staging'da. **B6.5 tugadi**: hodisa "Uzumga yuborish kerak" (yangi SKU kirganda bir marta; yuboriladigan dona F54 bo'yicha), Jo'natmalarga havola; keyingi — B5.4. **B5.2 tugadi (5-qadam)**: jo'natma qoralamasida "Tavsiya bo'yicha to'ldirish" (F54); keyingi — B6.5. **B5.2 (4-qadam)** F54 yuborish rejasi: maqsad qamrov ABC bo'yicha Sozlamalarda (standarti yo'q), Omborda "Yuborish rejasi" va 60 kun ogohlantirishi; qoldi: jo'natma qoralamasida "Tavsiya bo'yicha to'ldirish". **B5.2 (3-qadam)** Omborda qatorlarni tanlash: jami byudjet va bitta ko'p tovarli xarid; qoldi: F54 "Uzumga yuborish rejasi" (Temurning javobi: Uzumda necha kunlik zaxira). **B5.2 (2-qadam)** odatiy partiya hajmi: tovarda ixtiyoriy maydon (standart yo'q), Ombor qatorida "Partiya hajmi", tavsiya shunga karrali yaxlitlanadi; qoldi: tanlanganlar byudjeti va bitta tez xarid, F54. **B5.2 (1-qadam)** tovar darajasida reja: bir tovarning bir necha SKU'si bitta reja — talab, qoldiq va yo'ldagi dona yig'indisi, tavsiya SKU'larga tezlik bo'yicha bo'linadi; qoldi: partiya hajmi, jami byudjet, F54. 2026-11-18 — **B5.1 tugadi (2-qadam)**: Ombor jadvalida muddat manbasi, hodisa "Kargo kechikmoqda" + "Diqqat" qatori, tez xaridda ixtiyoriy yetkazib beruvchi. **B5.1 (1-qadam)** F25 ikki bo'lak (yo'l va Uzumga topshirish): tovar → yetkazib beruvchi → tashkilot → standart tartibida o'rganiladi, manba yoziladi; Sozlamalar 5 → 2 maydon; eski `LEAD_STAGES`/`timeline` tozalandi; qoldi: manba matni UI'da, "Kargo kechikmoqda", yetkazib beruvchi maydoni. **B6.4 (5-qadam, kod tugadi)** kanal uzilsa ilovada "Telegram uzildi — qayta ulang" qatori (`telegram_lost`), `stage` qiymatlari ADR-063 ga moslandi, 02 M15 dan kvota olib tashlandi; B6.4 yopilishi: A21 (Temurning staging so'rovi) va 7 kunlik sinov. **B6.4 (4-qadam)** xulosa: sof foyda uch qismda (jami / kutilayotgan / R / HH:MM), sana sarlavhasi, o'z kunidan o'tgan xulosa yuborilmaydi, dushanba bitta xabar, imzo faqat ko'p tashkilotda, davr boshida oldingi davr, "Batafsil" tilda, "Tez orada" kodsiz; qoldi: A21 (Temurning staging so'rovi), "Telegram uzildi" qatori, `stage` qiymatlari. **B6.4 (3-qadam)** sinxron "to'xtadi" ikkiga: kalit yaroqsiz (kritik, 3 kunda eslatma) va yangilanmayapti (kritik emas, uzilishda yo'q) + "tiklandi" xabari; qoldi: xulosa (A1, A18–A21, A7–A8), "Telegram uzildi" qatori. **B6.4 (2-qadam)** hodisalar: qoldiq va zarar faqat yangi SKU uchun (bazaviy ro'yxat), tannarxsiz — faqat yangi SKU, haftalik xulosa hafta ichida, og'ir hisob kamaydi; qoldi: sinxron ikkiga (A4), xulosa (A1, A18–A21, A7–A8). **B6.4 (1-qadam)** yetkazish ishonchliligi: Telegram `BadRequest` kanalni uzmaydi, `retry_after` hurmat qilinadi, 90 kunlik tozalash; B6.4 davom etadi (hodisalar, xulosa). **B5.0d** Foyda tafsiloti (drill-down) sahifa raqamlari bilan ("Yana yuklash" olib tashlandi). **D1 (ADR-070)** zamonaviy, bezakli dizayn: Temurning qat'iy talabi 04 §1 va tamoyil 12 ga yozildi; **D1 tugadi (5 qadam):** tokenlar, Bosh sahifa, grafiklar va ikonkalar, umumiy komponentlar, Partiya yo'li, kirish/onboarding, qorong'i mavzu. **TM9.7** jo'natma Excel'ida tannarx tahrirlanadi (taxminiy — belgi, noma'lum — 0 emas, kiritiladi); "Ikkiga bo'lish" sanalgandan keyin ham (sanalmagan qoldiq yangi xaridga); "Tovar qo'limda" — brak va qadoq qo'shimchasi. **TM9.6** umuman kelmagan tovar puli boshqa tovarga yuklanmaydi — "Kelmagan tovar zarari" (F55), sanashda "Kelmadi"; sotuvchi qaytargan summa o'z qatoriga (standart — kam kelgan qatorlarga). **TM9.4** "Uzum yo'qotdi" kamomadi yopilganda dona partiyadan ham chiqadi, F52 — partiyadan chiqqan qiymatdan. **TM9.2** qabul farqi e'lon qilingan son bo'yicha va qabul tugagach (7 kun / son yetdi), da'vo muddati 30 kun, "adashganman" oqibati oldindan. 2026-11-17 — **TM9.1** postavka ↔ jo'natma har qanday yo'lda: qisman mos nomzod, qo'lda — hamma postavkadan, e'lon qilingan songa tenglashtirish, jo'natmasiz postavka — "Omborimdan ketgan / emas". **TM9.8** "Keldi" — sanashdan oldin: kargo puli oynasida majburiy "Keldimi? Ha / Hali yo'q", ro'yxatda "Keldi", "Omborimda · sanalmagan"; F21 — keldi sanasi (eski yozuvlar o'zgarmaydi), F25 yo'l — buyurtma → keldi. **TM9.5**: trekli kargo puli takror yozilmaydi (`cargo_twice`); tovar summasi kiritilmagan xarid — "taxminiy" belgisi va "Diqqat" qatori. **TM9.3** butunlik himoyasi: jo'natilgan / o'tkazilgan / hisobdan chiqarilgan donali xarid va qator o'chirilmaydi, soni kamaytirilmaydi, SKU almashtirilmaydi; qabul qilingan postavka jo'natmasi bekor qilinmaydi; Omborimda manfiy qoldiq — "xato", `realcheck supply`. Oldin: ta'minot (ADR-061) tanqidiy tahlili: 17 topilma (09 §17), tuzatishlar — TM9 (ADR-068 tasdiqlandi; kelmagan tovar — F55, qaytarilgan summa — o'z qatoriga), "Keldi" — ADR-069 (tasdiqlandi; kargo puli oynasida "Keldimi? Ha / Hali yo'q" — standartsiz); faqat hujjat. Oldin: B5–B10 tahlili (ADR-063–067). Oldingi yozuvlar — `CHANGELOG.md` |

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
12. **Dizayn bezakli, yorqin va jozibali** (Temurning qat'iy talabi, ADR-070; 04 §1) — sokin/quruq ko'rinish qabul qilinmaydi.
13. **Temurning vaqti qimmat** — undan faqat u qila oladigan narsa so'raladi (qaror, akkaunt, sinov).
