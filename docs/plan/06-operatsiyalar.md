# 06. Operatsiyalar: server, zaxira, yordam, huquq, to'lov, marketing

## 1. Infratuzilma

- **Joylashuv:** faqat O'zbekiston (shaxsiy ma'lumot qonuni; Uzum WAF chet el IP'larini HTML 403 bilan to'sadi).
- **Provayder (Q2):** nomzodlar — Servercore.uz (tez ishga tushadi, obyekt saqlash, zaxira, DBaaS, Terraform;
  mustaqil benchmark'da tezroq) va UzCloud (5 ta Tier III markaz, 99,95% SLA, S3, DBaaS). Ikkalasida 7 kunlik sinov:
  Uzum API'ga ping, disk, deploy tezligi, yordam javobi → tanlanadi. Zaxira nusxa boshqa provayderda.
- **O'lcham:** staging 2 vCPU / 4 GB / 40 GB SSD (~210–260 ming so'm/oy); production boshlanishi 4 vCPU / 8 GB /
  80 GB NVMe (~520 ming – 1,1 mln so'm/oy); S3 zaxira (kam).
- **Domen:** staging uchun boshida `<ip>.sslip.io` (Caddy HTTPS bilan), keyin brend domeni (Q7).

## 2. Deploy

- `main` → staging avtomatik; `vX.Y.Z` teg → production. Har deploy: zaxira → migratsiya → yangi konteynerlar →
  sog'liq tekshiruvi → muvaffaqiyatsiz bo'lsa avvalgi image.
- Migratsiyalar orqaga mos ("kengaytir → ko'chir → toraytir"); xavfli migratsiya tungi oynada (01:00–05:00 Toshkent).
- Versiyalash: SemVer; `CHANGELOG.md` va ilovadagi "Yangiliklar" sahifasi bir manbadan.

## 3. Zaxira va tiklash

- PostgreSQL: WAL arxivi (pgBackRest) — 7 kungacha istalgan nuqtaga tiklash; tungi to'liq nusxa; 30 kun saqlash.
- Nusxalar shifrlangan, boshqa provayderdagi S3 ga (O'zbekistonda). Shifrlash kaliti nusxa bilan birga saqlanmaydi.
- RPO ≤ 15 daqiqa, RTO ≤ 2 soat. **Har oy tiklash mashqi** (staging'ga tiklab, tekshirish) — jurnalga yoziladi.

## 4. Kuzatuv va hodisalar

- Ogohlantirishlar admin Telegram guruhiga: sayt ishlamayapti, xatolar ko'paydi, sinxron 2 soat to'xtagan,
  yaroqsiz kalitlar birdan ko'paydi, disk > 80%, zaxira muvaffaqiyatsiz.
- Runbook'lar (`infra/runbooks/`): Uzum API ishlamayapti; kvota tugadi; WAF to'lqini; DB disk to'ldi;
  deploy muvaffaqiyatsiz; zaxiradan tiklash; kalit sizib chiqdi (tokenlarni bekor qilish tartibi).
- Status sahifa (Uptime Kuma). Jiddiy hodisadan keyin 1 sahifalik tahlil: nima bo'ldi, ta'sir, sabab, tuzatish.

## 5. Mijozlarga yordam

- Kanal: Telegram yordam chati (bot orqali), ilova ichida "Fikr bildirish" tugmasi (skrinshot bilan).
- Ish vaqti: Du–Sh 09:00–20:00 (Toshkent). Birinchi javob < 2 soat; kritik xato (foyda noto'g'ri, sinxron to'xtagan)
  24 soat ichida tuzatiladi yoki aylanma yo'l beriladi.
- Ustuvorlik: P0 (ma'lumot noto'g'ri / kirib bo'lmaydi), P1 (asosiy funksiya ishlamaydi), P2 (noqulaylik), P3 (taklif).
- Yordam markazi (uz/ru): ulanish, tannarx kiritish, xarid, formulalar, tez-tez so'raladigan savollar, videolar.

## 6. Huquqiy va muvofiqlik ro'yxati (B8.6)

- [ ] Yuridik shaxs (Q4): MChJ yoki YaTT — buxgalter/yurist bilan; bank hisob raqami.
- [ ] Soliq rejimi va o'z daromadimiz bo'yicha soliq (2026: YaTT aylanma 1% yiliga 1 mlrd so'mgacha; yuridik shaxs
  bazaviy stavkalar — buxgalter tasdiqlaydi).
- [ ] IT Park: imtiyozlar asosan eksport > 50% bo'lganlarga (2040 gacha uzaytirilgan, QQS'siz) — ichki bozorga
  sotadigan SaaS uchun foydasi tekshiriladi, oldindan hisoblanmaydi.
- [ ] Ommaviy oferta (xizmat shartlari), maxfiylik siyosati, shaxsiy ma'lumotlarni qayta ishlashga rozilik
  (ro'yxatdan o'tishda belgilanadi, operator nomi va STIR, maqsad, muddat ko'rsatiladi).
- [ ] Shaxsiy ma'lumotlar bazasini Davlat reestrida ro'yxatdan o'tkazish (Davlat personallashtirish markazi,
  15 kungacha).
- [ ] Ma'lumotlar O'zbekistondagi serverlarda (asosiy va zaxira); GlitchTip va boshqa vositalar ham shu yerda.
- [ ] Uzum Seller API foydalanish shartlari: uchinchi tomon xizmati sotuvchi kalitini ishlatishi mumkinligini
  tekshirish (raqobatchilar ochiq ishlaydi, lekin yozma tasdiq olinadi yoki shartlar o'qiladi).
- [ ] Tovar belgisi: nomda "Uzum" yo'q; **"SellerMax" band emasligini tekshirish** (ipa.gov.uz, WIPO Global Brand Database — Temur, ADR-030); keyin o'z brendimizni ro'yxatdan o'tkazish.
- [ ] To'lovlar uchun fiskal chek: xizmat uchun MXIK (IKPU) kodi (tasnif.soliq.uz), to'lov provayderi orqali
  fiskalizatsiya.
- [ ] Ma'lumotni o'chirish tartibi: tashkilot o'chirilsa 30 kundan keyin butunlay o'chiriladi (zaxiralardan
  saqlash muddati tugagach).

## 7. To'lov operatsiyalari (B8.2)

- Provayder (Q5): Payme / Click / Multicard / Uzum Bank — karta tokeni bilan takroriy to'lov va fiskal chek
  imkoniyati asosiy mezon. Python'da `tolov` paketi Payme, Click, Uzum, Paynet, Octo, Multicard'ni qo'llaydi
  (Multicard: token bilan yechish + OFD fiskal ma'lumot) — integratsiya oldidan rasmiy hujjat bilan tekshiriladi.
- Oqim: sinov tugashidan 3 kun oldin eslatma → to'lov → muvaffaqiyatsiz bo'lsa 3 urinish (1, 3, 5-kun) →
  7 kun muhlat → "faqat o'qish" rejimi (ma'lumot o'chmaydi) → to'lansa darhol tiklanadi.
- Har to'lovga hisob-faktura va fiskal chek havolasi; qaytarish siyosati ofertada.
- Tarif o'zgarishi keyingi davrdan; promo-kodlar va referral kreditlari admin panelda.

## 8. Marketing va chiqish

- **Asosiy xabar:** "Uzum'dagi haqiqiy sof foydangizni ko'ring — Xitoydan kelgan har partiya tannarxi bilan."
- **Kanallar:** Uzum sotuvchilari Telegram guruhlari va kanallari; Temurning YouTube kanali (qo'llanma videolar);
  Instagram reels; kargo kompaniyalari bilan hamkorlik (ular mijozlariga tavsiya qiladi); 1688/Pinduoduo
  o'qituvchilari bilan hamkorlik; ochiq kalkulyator (landing) — qidiruv orqali kelish.
- **Kontent rejasi (birinchi 10 ta):** Uzum'da sof foydani hisoblash; kargo xarajatini tovarlarga to'g'ri bo'lish;
  CNY kursi va karta yechimi; qachon qayta buyurtma berish; Uzum to'lov jadvali va komissiya; yo'qolgan tovar va
  kompensatsiya; reklama ulushi (DRR); nelikvid tovar; FIFO va o'rtacha tannarx.
- **Ishonch:** faqat haqiqiy mijoz fikrlari (ruxsati bilan), soxta sharh yo'q.
- **Chiqish ro'yxati:** landing (uz/ru), narxlar, ochiq kalkulyator, yordam markazi, Telegram kanal, 3 ta video,
  referral, beta ishtirokchilari fikrlari.

## 9. Mijoz suhbatlari (B1–B8, Temur o'tkazadi)

Maqsad: 10 suhbat. 20 daqiqa, yozib olish ruxsati bilan. Savollar:
1. Uzum'da qancha vaqtdan beri sotasiz, nechta do'kon, taxminan oylik tushum?
2. Tovarni qayerdan olasiz (Xitoy, mahalliy), qanday to'laysiz, qanday olib kelasiz?
3. Hozir foydani qanday hisoblaysiz (daftar, Excel, dastur)? Oxirgi marta qachon hisobladingiz?
4. Tannarxga nimalarni qo'shasiz? Kurs va kargoni qanday bo'lasiz?
5. Oxirgi 3 oyda pul yo'qotgan holat bo'ldimi (zarar bilan sotish, tugab qolish, yo'qolgan tovar, jarima)?
6. Qaysi dasturlarni sinab ko'rgansiz? Nima yoqdi, nima yoqmadi, nega to'xtatdingiz?
7. Ulardan biriga qancha to'laysiz yoki to'lagan bo'lardingiz?
8. Telefonda yoki kompyuterda ishlaysizmi? Telegram'da xabar olishni xohlaysizmi?
9. Xodimlaringiz bormi, ular nimani ko'rishi kerak?
10. Agar bitta muammoni sehrli hal qilsak — qaysi biri bo'lardi?

Natijalar `docs/plan/suhbatlar.md` ga (ismsiz, faqat xulosa).

## 10. Mahsulot analitikasi

- Ichki `events` jadvali: ro'yxatdan o'tish, kalit ulash, tarix yuklandi, birinchi tannarx, birinchi xarid,
  Telegram ulandi, kunlik kirish, to'lov, bekor qilish.
- Oylik ichki hisobot: aktivatsiya voronkasi, haftalik faollik, MRR, churn, eng ko'p ishlatiladigan sahifalar.
- Landing uchun self-hosted Umami (cookie'siz).

## 11. Production chiqish ro'yxati (B8 chiqish mezoni)

- [ ] Hamma B0–B7 vazifalari bajarilgan, CI yashil, ochiq P0/P1 xato yo'q.
- [ ] Yuklama testi: 200 tashkilot, API p95 maqsadlarda.
- [ ] Tashkilot ajratish testlari 100% endpoint'larni qamraydi.
- [ ] ASVS L2 ro'yxati to'ldirilgan, topilmalar yopilgan.
- [ ] Zaxiradan tiklash mashqi muvaffaqiyatli (sana jurnalda).
- [ ] Monitoring va ogohlantirishlar sinab ko'rilgan (sun'iy uzilish bilan).
- [ ] Huquqiy ro'yxat (§6) bajarilgan.
- [ ] To'lov oqimi real karta bilan boshidan oxirigacha sinalgan, fiskal chek kelgan.
- [ ] Landing, narxlar, yordam markazi, oferta, maxfiylik siyosati e'lon qilingan.
- [ ] Begona sinovchi (Temur emas) yo'riqnomasiz ro'yxatdan o'tib, do'konini ulab, 10 daqiqada foydani ko'rgan.
