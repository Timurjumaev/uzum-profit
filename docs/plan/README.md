# Production rejasi — bosh sahifa

**Maqsad:** hozirgi lokal ilovani (legacy) Uzum sotuvchilariga sotiladigan, raqobatchilardan har tomonlama kuchli
bulutli dasturga aylantirish. Reja 2026-10-23 da tuzilgan; har ish shu reja bo'yicha qilinadi.

## Holat

| | |
|---|---|
| Joriy bosqich | **B4. Asosiy ekranlar.** **B2 tugadi** (2026-10-27: B2.11 real sinov, 24 soat xatosiz), **B3 tugadi** (2026-10-26) |
| Keyingi vazifa | **B4.27** "Yo'qotishlar va imkoniyat" bloki (ADR-043, Temur tasdig'idan keyin); **B4 chiqish mezoni** — Temur 14 kun faqat yangi dasturda ishlaydi (B4.1–B4.26, B4.28–B4.40 tayyor; B4.9 bekor — ADR-032), keyin B5. B3 qoldig'i: Temur Q1 tovar belgisi tekshiruvi (ADR-030), `sellermax.uz` domenini ro'yxatdan o'tkazish |
| Temurdan kutilmoqda | B4.40 bo'yicha: merge va deploy'dan bir necha daqiqa keyin Buyurtmalarda boshlang'ich narxli sotuvlarda "Taxminiy" yo'qolganini ko'rish (B4.39 tuzatishi shu bilan eski sotuvlarga ham yetadi); B4.38 bo'yicha: staging'da Mahsulotlar → Holat "Zarar" va "Sotuv yo'q" (zarar faqat sotilganlarda), "Oxirgi partiya" (boshlang'ich narx ko'rinishi) va Buyurtmalarda "Taxminiy" belgisini bosib sabablarini ko'rish; B4.37 bo'yicha: staging'da Asosiy → "Zarar bilan sotilayotgan SKU" soni kamayganini, Mahsulotlarda "Oxirgi partiya" ustunini va Buyurtmalarda "Taxminiy" belgisi ustiga sichqoncha olib borib sababini tekshirish (kutilganidek bo'lmasa — skrinshot bilan yozish); B4.36 ni merge qilib, staging'da Asosiy, Foyda va Mahsulotlarni ko'rish (yoqmagan joyni skrinshot bilan yozish); B4.35 bo'yicha: staging'da Asosiy, Ombor, Buyurtmalar, Xarajatlar va Sozlamalar sahifalarining yangi ko'rinishini ko'rish (yoqmagan joyni skrinshot bilan yozish); B4.34 bo'yicha: staging'da Kargo sahifasidagi xarajat turlarini va «Ajratish» tugmasini ko'rish (kargoga avval yozilgan «Tovar» xarajati bo'lsa — o'chirib, xarid sahifasida kiritish); B4.33 bo'yicha: staging'da Xaridlar va Kargolar sahifalarining yangi (yorug') ko'rinishini ko'rish — yoqmagan joyni skrinshot bilan yozish (keyingi o'tish — mobil jadvallar tuzilishi va Asosiy sahifa qayta tuzilishi, B4.38; Temur ko'rib chiqqandan keyin); B4.32 bo'yicha: deploy'dan keyin staging'da xarid sahifasidan (Turi = Kargo) va kargo sahifasidan («Xarid biriktirish») xaridni kargoga biriktirib, tannarxni tekshirish; B4.31 (kargo) bo'yicha: staging'da Kargo yaratib 2 ta xaridni bog'lash va tannarxni tekshirish; deploy'dan keyin kursi yo'q xaridda komponentni qayta saqlash (zaxira bozor kursi to'ladi, xato yo'qoladi); Xaridlarda «Tovar qo'shish» oynasini sinash (B4.28); deploy'dan keyin staging'da realcheck (`cancel_split`) va Uzum kabinetidagi oktabr qaytarish / bekor sonlari bilan solishtirish; Bosh sahifadagi KPI sarhisobni ko'rib chiqish; xohlasa — Sozlamalar → "Ogohlantirish chegaralari". Oldingilar: boshlang'ich holatni kiritish (`/opening`) va yo'ldagi partiyalarni Xaridlarga kiritish (ADR-033); Foyda sahifasida oktabr/noyabr logistikasini kabinet bilan solishtirish (B4.25) |
| Oxirgi yangilanish | 2026-11-05 (B4.40: deploy'dan keyin tannarx natijalari darhol qayta hisoblanadi) |

(Har vazifa tugaganda shu jadval va 05-bosqichlar.md dagi belgi yangilanadi.)

## Fayllar

| Fayl | Nima bor |
|---|---|
| [01-mahsulot.md](01-mahsulot.md) | kim uchun, bozor, raqobat, ustunliklar, qilinmaydigan narsalar, tariflar, o'lchovlar |
| [02-funksiyalar.md](02-funksiyalar.md) | modullar M1–M21, qabul mezonlari, **formulalar F1–F48** |
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
