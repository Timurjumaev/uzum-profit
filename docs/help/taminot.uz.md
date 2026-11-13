# Ta'minot: xariddan Uzum qabuligacha

Bu maqola Xitoydan (yoki mahalliy) tovar olib kelib, Uzum omboriga topshirishgacha bo'lgan yo'lni dasturda qanday
yuritishni tushuntiradi. Har qadam bitta ekran; tannarx har qadamda o'zi qayta hisoblanadi.

Xaridning uch holati bor va ular qo'lda bosilmaydi — qilingan ishdan o'zi aniqlanadi:

| Holat | Qachon |
|---|---|
| **Yo'lda** | xarid saqlangan, tovar hali sanalmagan |
| **Omborimda** | tovar sanalgan, qo'lingizda |
| **Uzumda** | Uzumga jo'natilgan va postavka bilan bog'langan |

## 1. Xarid kiritish

**Xaridlar → Yangi xarid.** Tovarlarni (SKU) va donasini tanlang. Bitta buyurtmada har xil tovar bo'lsa, har qatorga
1688'dagi **qator summasini** yozing (dona narxi emas). Pastda **"Jami to'landi"** — hisobingizdan haqiqatda yechilgan summa
(CNY, USD yoki UZS) va kurs: Markaziy bank kursi yoki o'zingiz kiritgan kurs. Trek raqami ixtiyoriy.

Tovar allaqachon qo'lingizda bo'lsa (mahalliy xarid), **"Tovar qo'limda"** belgisini qo'ying — kargo kutilmaydi.

Saqlangan zahoti xarid **Yo'lda** holatida va "1 dona ≈ … so'm" taxminiy tannarx ko'rinadi (kargo hali kiritilmagan —
"Taxminiy" belgisi bilan).

## 2. Kargo puli

**Xaridlar → Kargo puli.** Kargo kompaniyasi hisobini yuborganda shu yerga kiriting:

- **Har xaridning o'z kargosi** bo'lsa — qatordagi summa maydoniga yozing (kg ixtiyoriy).
- **Bitta quti — bir nechta xarid** bo'lsa — xaridlarni belgilang va **"Bitta qutiga birlashtirish"**: umumiy summa dona
  bo'yicha bo'linadi, istalgan ulushni qo'lda o'zgartirish mumkin (qolgani yana dona bo'yicha).

Kargo kiritilgach "Taxminiy" belgisi yo'qoladi va tannarx yangilanadi.

## 3. Sanash

Tovar kelganda xarid sahifasida **"Sanash"**: har qatorga kelgan son va brak. Hammasi to'liq bo'lsa — **"Hammasi keldi"**.
Kam kelgan bo'lsa va sotuvchi pulni qaytargan bo'lsa — **"Sotuvchi qaytargan summa"**. Brak donalar tannarxi sog' donalarga
taqsimlanadi.

Bir qismi keyinroq keladigan bo'lsa — **"Xaridni ikkiga bo'lish"**: keladigan qism alohida xarid bo'lib qoladi.

Sanalgach xarid **Omborimda** holatiga o'tadi.

## 4. Omborim

**Ombor → Omborim.** SKU bo'yicha qo'lingizdagi qoldiq va uning tannarxdagi qiymati. Bu yerda:

- **Boshqa SKU'ga o'tkazish** — masalan, rangni adashtirib kiritgan bo'lsangiz; dona tannarxi bilan birga o'tadi.
- **Keyin topilgan brak** — hisobdan chiqadi, foyda hisobida "Brak zarari" qatori bo'ladi.

## 5. Uzumga jo'natish

**Omborim → Uzumga jo'natish.** Do'konni tanlang — Omborimdagi uning hamma SKU'lari to'liq soni bilan chiqadi. Sonni
kamaytiring yoki keraksiz qatorni olib tashlang va **"Excel yuklab olish"**. Fayl Uzum kabineti shablonida (shtrix-kod,
tannarx, dona) — uni kabinetda postavka yaratishda yuklang. Shtrix-kodi yo'q SKU fayl'ga kirmaydi (ogohlantirish chiqadi).

Excel yuklangan zahoti donalar **"Jo'natilmoqda"** — Omborimdan band qilinadi. Postavka kabinetda yaratilib, dasturga
kelganda jo'natma **o'zi bog'lanadi** (bir nechta mos postavka bo'lsa — ro'yxatdan tanlaysiz). Shundan keyin xarid **Uzumda**.
Jo'natmani bekor qilsangiz yoki postavka bekor bo'lsa, donalar Omborimga qaytadi.

## 6. Uzum qabulidagi farq

**Uzumga jo'natish → Qabul farqi.** Uzum postavkani qabul qilgach, jo'natilgan va qabul qilingan son solishtiriladi.
Farq bo'lsa bosh sahifadagi **"Diqqat"** blokida ko'rinadi.

**Kam qabul qilingan bo'lsa** — ikkitadan birini tanlang:

- **"Uzum yo'qotdi"** — donalar **kamomad ro'yxatiga** tushadi. Keyin holatini o'zgartirasiz: **Topildi**, **Kompensatsiya
  qilindi** (Uzum to'lagan summa bilan) yoki **Zarar deb yopildi**. Kompensatsiyadan ortgan yoki yopilgan zarar foyda hisobida
  alohida qator ("Uzum qabulida yo'qotish", F52).
- **"Men sanashda adashganman"** — xaridning kelgan soni tuzatiladi, tannarx qayta hisoblanadi.

**Ko'p qabul qilingan bo'lsa** — shu SKU'da ochiq kamomad bo'lsa **"Topildi"** (kamomad yopiladi), bo'lmasa **"Sonni
oshirish"** (xarid soni oshiriladi).

Qabul kamomadi bo'yicha Uzum jarimasi (C000007) bo'lsa, u farq kartochkasida ko'rinadi.

## Eski xaridlar

Avvalgi bosqichli xaridlar (to'landi, Xitoy omborida, yo'lda, keldi…) o'chmaydi: holati sanalaridan aniqlanadi — qabul
qilingan bo'lsa **Omborimda**, Uzumga yuborilgan yoki yopilgan bo'lsa **Uzumda**, qolgani **Yo'lda**. Ularning sanalari
"Yo'lda" muddatini (kutilgan sanash sanasi) hisoblashda ishlatiladi.
