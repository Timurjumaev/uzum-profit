# Uzum foyda: sotuvchi uchun foyda va buxgalteriya dasturi

Uzum seller kabinetidan (OpenAPI) sotuv, xarajat va mahsulotlarni oladi, sening partiya
tannarxing bilan birlashtirib, **haqiqiy foyda**ni ko'rsatadi. Faqat Python standart kutubxonasi:
**hech narsa o'rnatish shart emas** (Python 3.8 yoki yangisi; Mac'dagi `python3` yetadi,
tekshirish: `python3 --version`).

Veb-interfeys to'rt sahifadan iborat:

| Sahifa | Nima uchun |
|---|---|
| **Bosh sahifa** | davr bo'yicha haqiqiy foyda, xarajatlar, bekor qilinganlar |
| **SKU foyda** | har bir SKU bo'yicha dona, tushim, tannarx, foyda, qaytgan %, qoldiq |
| **Ombor** | Uzum omboridagi qoldiq, yo'ldagi partiyalar, qachon buyurtma berish kerakligi |
| **Partiyalar** | Xitoydan olingan tovarlar: tannarxni shu yerda bosqichma-bosqich kiritasan |

## 1. Birinchi ishga tushirish

Terminalda shu papkada:

```bash
# 1) Ma'lumotni yuklash. Ikki yo'ldan biri:
python3 -m uzum_profit import-json uzum_history.json     # tayyor fayldan (API kerak emas)
#   yoki .env ga kalit yozib (3-bo'limga qarang):
python3 -m uzum_profit sync --days 120                   # to'g'ridan-to'g'ri API'dan

# 2) Veb-interfeysni ochish
python3 -m uzum_profit serve                              # keyin brauzerda http://127.0.0.1:8000
```

To'xtatish: terminalda `Ctrl+C`. Terminalda qisqa hisobot ham bor:
`python3 -m uzum_profit report --from 2026-10-01`.

Hamma ma'lumot `uzum.db` faylida saqlanadi (SQLite). **Uni vaqti-vaqti bilan nusxalab qo'y**:
Uzum ma'lumotlarini API'dan qayta olish mumkin, lekin sen kiritgan partiyalar faqat shu yerda turadi.

## 2. Yangi versiyaga o'tish

`uzum-profit` papkasi turgan joyda (yangi `uzum-profit.zip` ham shu yerda tursin):

```bash
unzip -o uzum-profit.zip      # kodni yangilaydi
cd uzum-profit
python3 -m uzum_profit serve  # eski serverni avval Ctrl+C bilan to'xtat
```

`uzum.db` va `.env` zip ichida yo'q, shuning uchun ularga tegilmaydi: partiyalar va kalit joyida qoladi.
Eski baza birinchi ochilganda o'zi yangilanadi (yangi ustunlar qo'shiladi, ma'lumot yo'qolmaydi).
Keyin bir marta **"API'dan yangilash"**ni bos: Ombor sahifasidagi "Brak" soni shunda to'ladi.

## 3. API kalit (.env)

`.env.example` ni `.env` deb nusxala va `UZUM_API_KEY=` dan keyin kalitni yoz. Kalit faqat shu
faylda turadi, kodga yozilmaydi. Dastur faqat O'QISH (GET) so'rovlarini yuboradi, lekin kalitning o'zi
narx/qoldiqni o'zgartira oladi, shuning uchun uni parol kabi saqla. Boshqa sozlamalar
(bepul logistika davri, `LEAD_DAYS` va hokazo) ham `.env.example` ichida izohlangan.

Har kuni yangilash: veb-sahifadagi **"API'dan yangilash"** tugmasi yoki
`python3 -m uzum_profit sync`. Oxirgi 30 kun qayta olinadi (statuslar yangilanadi).

## 4. Partiyalar: tannarxni bosqichma-bosqich kiritish

**Partiyalar → "+ Yangi partiya"**. Partiya sening haqiqiy tartibingda to'ldiriladi: hamma
ma'lumot birdaniga kerak emas.

| Qachon | Nima qilasan | Formada |
|---|---|---|
| Xitoyga pul to'laganda | do'kon, sana, tovar uchun jami CNY, CNY kursi | **1-bo'lim** (faqat shu shart) |
| Tovar yo'lda (20-25 kun) | mahsulotlar: SKU qidirib tanlaysan, soni yoniga yoziladi | **2-bo'lim** |
| Kartochka chiqqanda | partiyani tahrirlab, nomli qatorga SKU biriktirasan | **2-bo'lim** |
| Tovarni olib, kargoni to'laganda | kargo USD, USD kursi, tovar olingan sana | **3-bo'lim** |
| Chiqim bo'lsa | summa va nima uchun ekani | **4-bo'lim** |

- **SKU qidirish**: «spo» deb yozsang «SPONJ» chiqadi. Lotin harfda yozsang kirill harfli kod va
  nomlar ham topiladi. Yangi SKU ro'yxatda ko'rinmasa, avval **"API'dan yangilash"**ni bos.
- **Kartochka hali yo'q bo'lsa**, qatorga nom yoz (masalan «Qizil kurtka M») va sonini kirit. Bu qator
  dona sifatida hisoblanadi (kargo va chiqimlar unga ham bo'linadi), lekin SKU biriktirilmaguncha
  tannarxga kirmaydi. Kartochka chiqqach partiyani tahrirlab, qatorga SKU yozasan.
- **Qo'shimcha chiqimlar**: dastlab bo'sh. «+ Qo'shimcha chiqim qo'shish»ni bossang ikkita maydon ochiladi:
  avval summa, keyin nima uchun ekani (shtrix kod rulon, paket, skotch, Uzum omboriga logistika...).
- **Narxlar har xil bo'lsa**: «Mahsulotlar narxi har xil» belgisini qo'yib, har qatorga CNY narx yoz.
  Narx yozilmagan donalar umumiy summaning qolgan qismini teng bo'lib oladi.
- Har partiya yonida holat belgisi turadi: «Mahsulotlar kiritilmagan», «SKU biriktirilmagan: N qator»,
  «Kargo narxi kiritilmagan» yoki «To'liq». Belgini bossang, kerakli bo'limga olib boradi.
- Partiyani istalgan payt tahrirlash yoki o'chirish mumkin: hisobotlar har safar qayta hisoblanadi.

Tannarx har bir partiya uchun shunday hisoblanadi:

```
tovar      = (tovar uchun jami CNY / dona) × CNY kursi            (to'lov kunidagi kurs)
kargo      = (kargo USD / dona) × USD kursi                       (kargo kunidagi kurs)
qo'shimcha = qo'shimcha chiqimlar yig'indisi / dona
tannarx    = tovar + kargo + qo'shimcha
```

Misol: 50 ta kurtka, 2000 CNY, kargo 200 USD, 50 000 so'm qo'shimcha chiqim, kurslar 1800 va 12000:
tovar 40 CNY = 72 000, kargo 4 USD = 48 000, qo'shimcha 1 000, **tannarx 121 000 so'm/dona**.

**Tannarx qaysi sotuvga qo'llanadi:**

- Partiya **kargo sanasidan** (tovar qo'lga olingan kun) boshlab hisobga olinadi; sana yozilmasa buyurtma
  sanasidan. Shundan oldingi sotuvlar eski partiyalar tannarxi bilan hisoblanadi.
- Bitta SKU bir necha partiyada bo'lsa, sotuv sanasigacha olingan partiyalarning **vaznli o'rtachasi** olinadi.
- **Kargosi kiritilmagan partiya yo'lda hisoblanadi** va SKU'ning boshqa to'liq partiyasi bo'lsa,
  tannarxga aralashmaydi (yo'ldagi tovar hali sotilmaydi). Faqat shu partiya bor bo'lsa (tovar kelib sotilgan,
  kargo esa kiritilmagan), tannarx kargosiz olinadi va bosh sahifada ogohlantirish chiqadi.
- Sotuv sanasigacha hech qanday partiya bo'lmasa, hamma partiyalar o'rtachasi olinadi (jadvalda `~` belgisi).

### Valyuta kursi ("Bank kursi" tugmasi)

CNY va USD maydonlari yonidagi **"Bank kursi"** tugmasi O'zbekiston Markaziy bankining rasmiy kursini
(cbu.uz) qo'yib beradi: CNY uchun buyurtma sanasidagi, USD uchun kargo sanasidagi (u bo'sh bo'lsa,
buyurtma sanasidagi) kurs. Bu faqat **tavsiya**: maydonni o'zing o'zgartira olasan, dastur sen yozgan
qiymatni ishlatadi (haqiqiy to'lagan kursing bank kursidan farq qilishi mumkin). Internet kerak; bank sayti
ochilmasa xabar chiqadi va kursni qo'lda yozasan. Bank o'sha sana uchun kurs bermagan bo'lsa (dam olish
kuni), forma qaysi sanadagi kurs olinganini yozib ogohlantiradi.

## 5. Ombor sahifasi

- Tepada to'rt karta: **Omborda (FBO)** dona va tannarxdagi qiymati, **Yo'lda** partiyalar, **Buyurtma kerak**
  SKU soni, **Brak** (Uzum yaroqsiz deb topgan donalar va ularning tannarxdagi qiymati).
- **SKU jadvali**: FBO qoldiq, yo'ldagi dona, sotuv tezligi (dona/kun), necha kunga yetishi va **qachon buyurtma
  berish kerakligi**. Holatlar: *Tugagan*, *Buyurtma vaqti*, *Yaqinlashmoqda*, *Yetarli*. Eng shoshilinchlari tepada.
- **Buyurtma muddati** `LEAD_DAYS` (standart 30 kun): buyurtmadan tovar Uzum omborida sotuvga chiqquncha
  (Xitoydan kelish 20-25 kun + shtrix kod va Uzumga topshirish). `.env` da o'zingga moslab o'zgartir.
- Sotuv tezligi = oxirgi 30 kundagi bekor qilinmagan buyurtmalar / kun (shu davrda sotuv bo'lmasa 60 kun;
  yangi SKU uchun kamida 7 kunga bo'linadi). Holat faqat Uzum omboridagi qoldiqqa qarab beriladi: yo'ldagi
  tovar holatga ta'sir qilmaydi, "Yo'lda" ustuni bilan o'zing solishtirasan. Tugagan SKU'larning haqiqiy talabi
  ko'rsatilgandan yuqori bo'lishi mumkin (qoldiq yo'q kunlarda sotuv ham bo'lmagan).
- Kuniga 0,2 dondan kam sotiladigan SKU'lar va oxirgi 60 kunda sotilmagan "yotib qolgan" tovarlar
  pastda alohida yig'ilgan ro'yxatlarda turadi: asosiy jadval shovqinsiz bo'lishi uchun.
- **Yo'ldagi partiyalar** = kargo narxi hali kiritilmagan partiyalar. "Taxminiy omborda" = buyurtma sanasi +
  `LEAD_DAYS`. Undan 15 kun o'tib ham kargo kiritilmagan bo'lsa, «kechikdi?» belgisi chiqadi (tovar kelgan
  bo'lsa, kargo narxini kirit).
- Uzum omboriga yuborilgan, lekin hali qabul qilinmagan fakturalar ro'yxati ham shu yerda.

## 6. Raqamlar qanday hisoblanadi

- **Uzum bergan sof tushim** = narx × soni − komissiya − logistika (Uzum hisobotiga bir so'mgacha mos).
- **Reklama, saqlash, jarima** Uzum hisobotida yo'q; xarajatlar oqimidan olinadi (reklama aniq summada).
- **Haqiqiy foyda** = Uzum sof tushimi − tannarx − reklama − saqlash − jarima (+ kompensatsiya).
  Tannarxi kiritilmagan sotuvlar foydaga qo'shilmaydi (ogohlantirish chiqadi).
- **Kutilayotgan foyda**: "Qayta ishlanmoqda" buyurtmalar × `PENDING_REALIZATION` (bir qismi bekor bo'ladi).
- **Standart tarifdagi foyda**: bepul logistika davridagi (`FREE_LOGISTICS_*`) buyurtmalarga oddiy logistikani
  qo'shib hisoblanadi. Narx va rentabellik qarorlarini shu raqamga qarab qil.
- **Qaytgan %** = qaytgan / (sotilgan + qaytgan): Uzum kabinetidagi hisob bilan bir xil.
- Sotuvlar buyurtma yaratilgan sana bo'yicha davrga kiradi; xarajatlar yechilgan sana bo'yicha.

## 7. Xavfsizlik

- Veb-interfeys faqat sening kompyuteringda (`127.0.0.1`) ochiladi, tarmoqdan ko'rinmaydi. Boshqa sayt
  orqali forma yuborish (CSRF) va soxta Host so'rovlari rad etiladi.
- Uzum API'ga faqat o'qish (GET) so'rovlari ketadi. Sertifikat (TLS) tekshiruvi hech qachon o'chirilmaydi:
  Python xato bersa, tizimdagi `curl` ishlatiladi.
- `.gitignore` `.env`, `*.db`, `uzum_history.json`, `uzum_samples*.json` fayllarini git'ga qo'shmaydi.

## 8. Sinov

**Haqiqiy Uzum API bilan tekshiruv:** `python3 -m uzum_profit selfcheck` (kalit `.env` dan olinadi). U oxirgi
7 kunni vaqtinchalik bazaga yuklaydi (`uzum.db` ga tegmaydi), kutilgan maydonlar borligini va bank kursini
tekshiradi. Hisobotda kalit yo'q: uni Claude'ga bemalol yuborish mumkin.


```bash
python3 -m unittest tests.test_all -v
```

Python 3.8 va 3.13'da o'tadi. `uzum_history.json` shu papkada bo'lsa (yoki
`UZUM_TEST_HISTORY=/yo'l/uzum_history.json` deb ko'rsatsang), haqiqiy ma'lumot bilan solishtirish sinovlari ham
ishlaydi (qaytgan %, ombor yig'indilari).

**Birinchi marta ishlatganda ko'z bilan tekshir** (bular sinovda haqiqiy Uzum va bank serverlarisiz,
Safari'siz ko'rilgan):
1. Bosh sahifadagi "Uzum sof tushimi" Uzum kabinetidagi hisobot bilan mosligini.
2. "Bank kursi" tugmasi bergan kursni cbu.uz saytidagi bilan.
3. Partiya formasi (SKU qidirish, «+» tugmalari) Safari'da ishlashini. Ishlamasa, Chrome'da och.

## 9. Hali yo'q (keyingi qadamlar)

- **Kargoni og'irlik/hajm bo'yicha taqsimlash.** Hozir kargo dona bo'yicha teng bo'linadi (sening daftar
  usulingdek). Uzum kartochkalaridagi og'irliklar ishonchsiz, shuning uchun bu qadam qoldirildi; kerak bo'lsa,
  partiya qatoriga og'irlikni qo'lda yozish usuli qo'shiladi.
- **Faktura ichidagi SKU ro'yxati.** Uzum bu ma'lumotni beradi (`/invoice/products`, haqiqiy API bilan
  tekshirilgan), lekin hozircha qabul qilinmagan faktura bo'lmagani uchun "yo'lda" holatdagi maydonlar
  nomi ko'rilmadi. Keyingi safar Uzum omboriga tovar yuborganingda, faktura qabul qilinishidan oldin
  `selfcheck` ni yurgiz: shundan keyin yuborilgan tovar "Omborda" hisobiga qo'shiladi.
- **Qaytgan tovarning jismoniy hisobi.** Uzum "qaytarishlar" ro'yxatini (brak, pullik saqlash) beradi, lekin
  dastur uni hozircha saqlamaydi: qaytgan tovar omborga qaytib sotuvga chiqdimi yoki yo'qolganmi, hisoblanmaydi.
  Hozir faqat qaytgan % va "Brak" soni ko'rsatiladi.
- **FIFO yoki harakatlanuvchi o'rtacha tannarx.** Hozir sotuv sanasigacha olingan partiyalarning vaznli
  o'rtachasi ishlatiladi. Partiyalar orasida narx keskin farq qilsa, FIFO aniqroq bo'ladi.
- **Ko'p foydalanuvchili versiya** (FastAPI + PostgreSQL), boshqa sellerlarga sotish uchun: alohida katta
  bosqich (kirish, har bir seller uchun alohida kalit va baza, to'lov).
