# 01. Mahsulot: kim uchun, nima uchun, qanday pul topadi

## 1. Bir jumlada

**Uzum sotuvchisi uchun haqiqiy sof foyda: Xitoyga buyurtma bergan kundan Uzum pulni o'tkazgan kungacha har bir
so'm hisobda — va qachon, nimani, qanchaga qayta buyurtma qilish kerakligi.**

Brend nomi: **SellerMax** (ADR-030, `sellermax.uz`); ishchi nom "uzum-profit" faqat ichkarida (repo, paketlar). Nomda "Uzum" so'zi bo'lmaydi.

## 2. Kim uchun (personalar)

| Persona | Tavsif | Asosiy og'rig'i | Biz beradigan javob |
|---|---|---|---|
| **P1. Xitoydan olib keluvchi kichik sotuvchi** (Temur kabi) | 1–3 do'kon, 50–500 SKU, oyiga 20–300 mln so'm tushum; 1688/Pinduoduo + kargo; daftar yoki Excel | haqiqiy tannarx (kurs, kargo, qo'shimchalar), haqiqiy foyda, qachon buyurtma berish | partiya tannarxi, hisob varag'i, buyurtma rejasi, Telegram xulosa |
| **P2. O'sayotgan biznes** | 3–10 do'kon, 1 000+ SKU, xodimlar (menejer, omborchi), FBO + FBS | jamoa, ombor nazorati, pul oqimi, reklama samarasi | rollar, joylar bo'yicha ombor, pul oqimi, DRR/ACOS |
| **P3. Mahalliy ishlab chiqaruvchi / ulgurjichi** | tovarni O'zbekistonda so'mda oladi | tannarx va foyda | xuddi shu modul, valyutasiz |
| **P4. Buxgalter / hamkor** | bir nechta mijozga xizmat | tayyor reyestrlar | buxgalter roli, eksport, bir nechta tashkilot |

Birinchi navbatda P1 (eng ko'p va eng og'rigan), keyin P2.

## 3. Bozor

- Uzum'da **18 000+ faol sotuvchi** (2025), ularning ~90% kichik va o'rta biznes; GMV 2025 da $500 mln dan oshgan,
  2026 oxirida ~$1 mlrd kutilmoqda ([kun.uz](https://kun.uz/news/2026/07/10/uzum-yonalishidagi-ye-sommerce-aylanmasi-1-milliard-dollarga-yetishi-mumkin)).
- Raqobatchilar o'z saytlarida 37 184 (MARGN) va 49 200 (SellerPro) do'kon deb yozadi — faol bo'lmaganlari bilan.
- O'xshash nish SaaS ishlay olishining dalili: ZoomSelling (Uzum + Qozog'iston) — 200+ to'lovchi mijoz,
  MRR ~$15 000; yangi boshlovchilar tez ketadi, tajribali sotuvchilar oyiga 5–10% ([digitalbusiness.kz](https://digitalbusiness.kz/en/2025-12-08/left-the-comfort-of-a-9-to-5-to-build-a-startup-that-helps-business-owners-earn-more/)).

## 4. Raqobat (qisqa; to'liq jadval 08-tadqiqot.md)

| Guruh | Kimlar | Kuchli tomoni | Bo'shliq |
|---|---|---|---|
| Uzum foyda servislari | SellerFlow, SellerPro, MARGN, SellerMind | API orqali P&L, SKU foydasi, ba'zilarida ombor va AI | tannarx SKU uchun bitta raqam (qo'lda/Excel); import zanjiri, kurs, kargo taqsimoti yo'q; narx 299 000 – 1 499 000 so'm/oy |
| Bozor tahlili | SellerPro, MARGN, Baraka Data, Easy Analytics, Uzumchi, ZoomSelling | raqobatchi, nisha, SEO | o'z foydasi yo'q yoki yuzaki |
| Ombor / ERP | MoySklad (+ Zoomselling, UzumSync), Kublet, Odoo moduli | hujjat, ombor, buyurtma | Uzum foydasi va importga moslashmagan, murakkab |
| Logistika | Fargo Marketplace Hub | fulfilment | hisob-kitob yo'q |
| Xorijiy namunalar | Sellerboard (Amazon), MPfact, TrueStats, sellerdata, UVIX (WB/Ozon) | FIFO partiya tannarxi, pul oqimi, reja-fakt, AI/MCP | Uzum'da yo'q |

## 5. Bizning ustunliklarimiz

| # | Ustunlik | Nimaga asoslangan |
|---|---|---|
| D1 | **Import zanjiri tannarxi**: CNY/USD/so'm to'lovlar, haqiqiy kurs (kartadan yechilgan summa), kargo vazn/hajm bo'yicha, bosqichma-bosqich to'ldirish, yo'ldagi tovar | Temurning real jarayoni; raqobatchilarda yo'q |
| D2 | **Lot bo'yicha FIFO yoki o'rtacha tannarx**, kech kiritilgan xarajatda o'tmish avtomatik qayta hisoblanadi | Sellerboard/UVIX darajasi, Uzum bozorida yo'q |
| D3 | **Har raqam shaffof**: hisob varag'i, formula va manba yozuvlar bir bosishda | sotuvchilar "dastur qanday hisobladi?" deb so'raydi |
| D4 | **O'zi o'rganadigan buyurtma rejasi**: Xitoy → kargo → Toshkent → Uzum muddati, CNY byudjeti | raqobatchilarda faqat "necha kunga yetadi" |
| D5 | **Yo'qolgan tovar, kamomad, kompensatsiya** signallari | MARGN/SellerPro'da qisman |
| D6 | **Pul oqimi**: Uzum to'lov jadvali bo'yicha prognoz, kassa uzilishi ogohlantirishi | Uzum servislarida yo'q |
| D7 | **Adolatli narx**: aylanmaga bog'liq tarif, kichik sotuvchiga arzon, bepul daraja | raqobatchilar 299 000 so'mdan |
| D8 | **O'zbekcha (lotin + kirill) va ruscha, telefon va Telegram birinchi** | auditoriya Telegram'da |
| D9 | **Ishonch**: faqat rasmiy API kalit, parol so'ralmaydi, ma'lumot O'zbekistonda, to'liq eksport | qonun va xavfsizlik |
| D10 | **Tezlik**: ulanishdan 10 daqiqada birinchi foyda (butun tarix avtomatik) | legacy'da sinalgan |

## 6. Biz nima QILMAYMIZ (doirani saqlash uchun)

- Butun bozor tahlili, nisha qidirish, raqobatchi kuzatuvi (SellerPro/MARGN sohasi; keyin hamkorlik mumkin).
- Kartochka yaratish, SEO, AI rasm.
- Reklama stavkalarini avtomatik boshqarish, sharhlarga javob, xaridor chati — bular faqat norasmiy kabinet API
  orqali; parol/sessiya tokeni so'ramaymiz (ADR-009).
- Soliq hisobotlarini topshiradigan to'liq buxgalteriya (1C o'rnini bosish) — faqat reyestrlar eksporti.

## 7. Biznes model va tariflar (taklif — B8.1 da suhbatlar asosida tasdiqlanadi, Q6)

| Tarif | Narx (so'm/oy) | Kimga | Chegaralar |
|---|---|---|---|
| Sinov | 0, 14 kun | hamma | hamma narsa ochiq, karta so'ralmaydi |
| Boshlang'ich | 0 | yangi sotuvchi | 1 do'kon, oyiga 300 tagacha sotuv, oxirgi 90 kun, Telegram kunlik xulosa |
| Start | 149 000 | P1 | 2 do'kon, oyiga 50 mln so'mgacha tushum, to'liq tarix, xaridlar, buyurtma rejasi, ogohlantirishlar, Excel |
| Biznes | 299 000 | P1–P2 | 5 do'kon, 300 mln gacha, 5 xodim, pul oqimi, reja-fakt, PDF hisobotlar |
| Pro | 590 000 | P2 | 15 do'kon, cheksiz tushum, 15 xodim, API/MCP, ustuvor yordam |

- Yillik to'lovda −20%. Oyning tushumi chegaradan 2 oy ketma-ket oshsa — yuqori tarifga o'tish taklifi (majburlamasdan).
- Referral: taklif qilingan sotuvchi to'lasa, ikkalasiga 1 oy bepul.
- Taqqoslash: SellerMind 299 000, MARGN 499 000 / 699 000, SellerPro 1 199 000 / 1 499 000 so'm/oy;
  Sellerboard $19–79/oy.

## 8. Muvaffaqiyat o'lchovlari

| O'lchov | Ta'rif | Maqsad |
|---|---|---|
| Birinchi foyda vaqti | ro'yxatdan o'tishdan hisob varag'i ko'rinishigacha | < 10 daqiqa |
| Aktivatsiya | 48 soatda kalit ulangan + tushumning ≥ 60% ida tannarx | ≥ 60% |
| Haftalik faollik | haftada ≥ 2 kun kirgan to'lovchi tashkilotlar | ≥ 70% |
| Sinovdan to'lovga | 14 kunlik sinovdan keyin to'lagan | ≥ 25% |
| Ketish (churn) | oylik, 3 oydan ortiq mijozlar | < 5% |
| Yordam javobi | ish vaqtida birinchi javob | < 2 soat |
| Biznes | to'lovchi tashkilotlar | beta oxiri 3+, chiqishdan 3 oy keyin 50, 12 oy keyin 300 |

Kuzatiladi: `events` jadvali + oylik hisobot (06 §10).
