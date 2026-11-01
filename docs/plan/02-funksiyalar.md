# 02. Funksiyalar: modullar, qabul mezonlari, formulalar

Bu fayl dastur NIMA qilishini belgilaydi. Har modulda: vazifasi, ekranlari, funksiyalari (qaysi bosqichda),
qabul mezonlari. Oxirida **formulalar lug'ati (F1–F40)**: dasturdagi har bir raqam shu yerdagi bitta formuladan
hisoblanadi. Kodda formula funksiyasi docstring'ida `F12` kabi raqam bilan belgilanadi.

Belgilar: **[B4]** = shu bosqichda quriladi (05-bosqichlar.md). **[Keyin]** = ommaviy chiqishdan keyin.

---

## M1. Kirish, tashkilot, jamoa [B2, B3]

**Vazifasi.** Sotuvchi o'z tashkilotini (biznesini) ochadi, xodimlarni taklif qiladi, har kim faqat o'ziga ruxsat
etilganini ko'radi.

- Kirish: telefon raqam + bir martalik kod (OTP). Kod Telegram orqali yuboriladi (ADR-027); SMS — keyinroq zaxira kanal.
  Parol yo'q. Sessiya 30 kun, "qurilmalarim" ro'yxati, "hamma qurilmalardan chiqish".
- Tashkilot (tenant): nomi, ixtiyoriy STIR, til, vaqt mintaqasi (standart Asia/Tashkent).
- Bitta foydalanuvchi bir nechta tashkilotda bo'lishi mumkin (masalan, buxgalter bir nechta mijozda).
- Taklif: telefon raqam bo'yicha havola, rol tanlanadi, 7 kun amal qiladi.
- Rollar (ruxsatlar matritsasi 03-arxitektura.md §10 da):
  - **Egasi**: hammasi, tarif va to'lov, tashkilotni o'chirish.
  - **Menejer**: hammasi, tarif va xodimlardan tashqari.
  - **Buxgalter**: faqat ko'rish + eksport, sozlamalarni o'zgartira olmaydi.
  - **Omborchi**: xaridlar, ombor, postavkalar; foyda, tannarx summalari va pul oqimi ko'rinmaydi.
- Audit jurnali: kim, qachon, nimani o'zgartirdi (tannarx, xarid, sozlama, rol). Egasi ko'radi.
- Ixtiyoriy 2FA (TOTP) [B8].

Qabul mezonlari: OTP 5 marta noto'g'ri → 15 daqiqa blok; omborchi API orqali ham foyda summasini ololmaydi
(server tomonda tekshiriladi, testi bor); taklif muddati o'tsa ishlamaydi.

## M2. Onboarding (birinchi ulanish) [B3, B4]

**Maqsad:** ulanishdan 10 daqiqa ichida birinchi haqiqiy foyda hisobotini ko'rsatish.

Qadamlar (wizard, istalgan qadamdan keyin to'xtab, keyin davom etish mumkin):
1. **Uzum API kalitini ulash.** Qisqa yo'riqnoma (rasmlar bilan): seller.uzum.uz → API kalitlar → yaratish → nusxa.
   Kalit tekshiriladi (`/v1/shops`), do'konlar ro'yxati chiqadi. Matn: "Kalit faqat o'qish uchun ishlatiladi,
   shifrlab saqlanadi, parolingiz so'ralmaydi."
2. **Do'konlarni tanlash** (hammasi belgilangan holda), har biriga qisqa nom va rang belgisi.
3. **Tarix yuklanmoqda.** Har do'kon uchun progress: sotuvlar N/jami, xarajatlar, mahsulotlar, postavkalar,
   qaytarishlar; taxminiy qolgan vaqt. Foydalanuvchi shu paytda 4–5-qadamni to'ldiradi.
4. **Asosiy sozlamalar:** soliq rejimi (F11), Uzum pul yechish jadvali (F38), odatiy yetkazish muddati, tannarx usuli
   (FIFO / o'rtacha, standart FIFO — ADR-008).
5. **Tannarx:** uchta yo'l: (a) tushum bo'yicha TOP-20 SKU uchun tezkor jadval (dona narxi so'mda yoki CNY + kurs);
   (b) Excel shablon yuklash [B7]; (c) birinchi xaridni (partiyani) to'liq kiritish. Ekranda: "Tushumning X% ida tannarx bor".
   (a) — **Boshlang'ich holat** sahifasi (`/opening`, B4.12, F41, ADR-033): boshlash sanasi, har tovarga bitta tannarx,
   qoldiq (Uzumdan taklif + o'z omborim); eski partiyalar shart emas.
6. **Telegram'ni ulash** (QR kod / havola) — kunlik xulosa uchun.

Bosh sahifada "Sozlash: 4/6" ro'yxati hamma qadam tugaguncha turadi.

Qabul mezonlari: 2 do'kon, 3 000 sotuvli tarix ≤ 5 daqiqada yuklanadi; yuklash uzilsa (Uzum xatosi) qayta
boshlanadi va qolgan joydan davom etadi; tannarxsiz ham bosh sahifa ishlaydi (tannarxsiz qismi aniq ko'rsatiladi).

## M3. Uzum sinxronizatsiyasi [B2]

**Vazifasi.** Uzum ma'lumotini ishonchli, kvotani tejab, to'xtovsiz olib turish va holatini ko'rsatish.

| Ma'lumot | Endpoint | Chastota | Usul |
|---|---|---|---|
| Do'konlar | `GET /v1/shops` | kuniga 1 | to'liq |
| Sotuvlar | `GET /v1/finance/orders` (`group=false`, size≤5000) | 10–15 daq | eng yangi sahifa; kuniga 1 marta 45 kunlik chuqur |
| Xarajatlar | `GET /v1/finance/expenses` (size≤2000) | soatiga 1 | `dateFrom` bilan |
| Mahsulot, SKU, qoldiq, komissiya | `GET /v1/product/shop/{id}` (size=100) | 30–60 daq | to'liq |
| Kunlik qoldiq snapshot | (mahsulotdan) | kuniga 1, 23:50 | `(shop, sku, sana)` |
| Postavkalar | `GET /v1/shop/{id}/invoice` | soatiga 1 | ro'yxat |
| Postavka tarkibi | `GET /v1/shop/{id}/invoice/products?invoiceId=` | yangi yoki holati o'zgarganda | bir marta |
| Qaytarishlar | `GET /v1/return`, `/v1/shop/{id}/return` | soatiga 1 | `dateFrom` bilan |
| FBS buyurtmalar | `GET /v2/fbs/orders` (size≤50) | faqat do'konda FBS bo'lsa | holat bo'yicha [B5] |
| CBU kurslari | cbu.uz JSON | kuniga 2 | arxiv sana bo'yicha |

- **Birinchi ulanish:** butun tarix (2020-01-01 dan, Uzum qancha bersa). Legacy'dagi mantiq saqlanadi:
  har do'kon uchun "tarix: to'liq / cheklangan" belgisi.
- **Kvota:** kalit bo'yicha ~2 so'rov/s va kuniga 100 000 (akkaunt bo'yicha). Javob sarlavhalaridan qoldiq
  o'qiladi; oxirgi 10 000 faqat foydalanuvchi bosgan amallar uchun saqlanadi.
- **Xatolar:** sekundlik 429 → kutib qayta urinish; kunlik 429 → kalit "kvota tugadi", har 30 daqiqada bitta
  sinov; HTML 403 → WAF (kalit xatosi emas); ketma-ket 3 ta JSON 401/403 → "kalit yaroqsiz", egasiga xabar.
- **Ma'lumot yangiligi:** har sahifa yuqorisida "Yangilandi: 3 daqiqa oldin"; bosilsa har ma'lumot turi bo'yicha holat.
  "Ma'lumotlar holati" sahifasi: har do'kon × ma'lumot turi: oxirgi muvaffaqiyatli sinxron, olingan yozuvlar,
  xato matni, kvota qoldig'i.
- **"Hozir yangilash"** tugmasi: 1 daqiqada 1 marta, ustuvor navbat.
- **Uzum uzilishi** (masalan, 2026-10-08/09 hodisasi): sinxron to'xtatiladi, sahifada sariq banner, tiklangach
  uzilish davri chuqur sinxron bilan to'ldiriladi. Uzilish paytidagi "sotuv yo'q" asosida hech qanday ogohlantirish
  yuborilmaydi.
- **Xarajat kodlari lug'ati** bazada (admin tahrirlaydi): kod → toifa. Noma'lum kod "boshqa" bo'ladi, adminga xabar.
- **Xom javoblar** (`raw` jsonb) saqlanadi: yangi maydon yoki kod topilsa, qayta so'ramasdan qayta ishlanadi.

Qabul mezonlari: bir xil ma'lumotni qayta olish dublikat yaratmaydi; Uzum bermagan maydon `NULL` bilan ustidan
yozilmaydi; sotuvchi kiritgan ma'lumot sinxron tomonidan hech qachon o'zgarmaydi; 24 soat davomida xato bo'lmasa
"Ma'lumotlar holati" yashil.

## M4. Bosh sahifa [B4]

Yuqorida: do'kon tanlash, davr (Bugun, Kecha, 7 kun, 30 kun, Shu oy, O'tgan oy, Shu yil, Hammasi, tanlash),
"solishtirish" (oldingi davr / o'tgan yil shu davri), yangilanish holati.

Bloklar (joylashuvi 04-dizayn.md §7.2 desktop, §7.3 mobil):
1. **Hisob varag'i** (asosiy element): Tushum → − komissiya → − logistika → = Uzum to'lovi → − tannarx →
   − Uzum xarajatlari → − o'z xarajatlari → − soliq → **= Sof foyda** (ikki chiziq ostida). Har qator yonida
   oldingi davrga nisbatan o'zgarish. Har qator bosilsa — manba yozuvlar ro'yxati (drill-down).
2. **Davr chizig'i:** Bugun, Kecha, Shu oy, Oy prognozi (run-rate), O'tgan oy — har birida tushum, sof foyda,
   buyurtma (dona).
3. **Kunlik grafik:** tushum (ustun) va sof foyda (chiziq) bir o'qda; Uzum bonus davrlari (bepul logistika va h.k.,
   ADR-031) soya bilan.
4. **Diqqat talab qiladi** (ustuvorlik bo'yicha): tannarxsiz sotuvlar, tugayotgan tovar, zarar bilan sotilayotgan
   SKU, yangi jarimalar, kechikayotgan kargo, sinxron xatosi, Uzum to'lovi kutilmoqda.
5. **Eng foydali 5 / zarar 5 SKU.**
6. **Qo'shimcha ko'rsatkichlar:** marja (yonida tannarxsiz qism ulushi, F13), ROI, bekor %, qaytish %, reklama ulushi (DRR), muzlagan pul, yo'ldagi
   tovar qiymati, kutilayotgan foyda (F16).

Qabul mezonlari: 1 yillik, 50 000 sotuv qatori bilan javob p95 < 700 ms; davr va do'kon tanlovi URL'da
(havolani ulashsa shu ko'rinish ochiladi); 360 px kenglikda gorizontal skroll yo'q.

## M5. Foyda va zarar (P&L) [B4]

- Hisobot qatorlari: F3 → F4 → F5 → F6 → F7 → F8 → F9 (turlari alohida: reklama, saqlash, qaytim saqlash,
  jarimalar, fotostudiya, pul yechish xizmati, kompensatsiya) → F10 (toifalar bo'yicha) → F11 → **F12**.
- Ustunlar: tanlangan davr, tushumga nisbatan %, oldingi davr, farq. Ko'rinishlar: oylar bo'yicha (ustun = oy),
  do'konlar bo'yicha, SKU / toifa bo'yicha.
- Do'kon va SKU kesimlarida F9/F10 xarajatlari ikki qismda: **to'g'ridan-to'g'ri** (SKU'ga bog'langan) va
  **taqsimlangan** (do'kon / tashkilot xarajatining tushum ulushi); sotuvsiz kun xarajati — "Taqsimlanmagan" (ADR-026).
- Grafik: sharshara (waterfall) — tushumdan sof foydagacha.
- **Kutilayotgan** (Jarayondagi) sotuvlar alohida blok (F16), realizatsiya darajasi ko'rsatiladi.
- **Tannarx qamrovi** (F15) < 100% bo'lsa, qizil emas, sariq banner: "N ta sotuv (X so'm) tannarxsiz — foydaga
  kirmadi. [Tannarx kiritish]".
- Davrda Uzum bonusi bo'lsa (ADR-031): ma'lumot banneri — sabab, bepul turlar, sanalar; haqiqiy hisob o'zgarmaydi
  (bepul xarajat 0), "standart tarif bo'yicha foyda" qatori yo'q. Bonussiz baho — M6 (F40).
- Har qator → drill-down: shu summani tashkil qilgan sotuv / xarajat qatorlari (eksport bilan).
- Excel va PDF eksport.

Qabul mezonlari: P&L'dagi sof foyda = bosh sahifadagi sof foyda = SKU jadvali yig'indisi (bitta funksiya);
oylar yig'indisi = butun davr; har drill-down yig'indisi qator summasiga teng (avtomatik test).

## M6. Mahsulotlar (SKU va unit-iqtisod) [B4]

- Jadval: rasm, SKU, nom, do'kon, sotilgan dona, tushum, o'rtacha narx, komissiya %, logistika/dona,
  tannarx/dona (lot ma'lumoti bilan), reklama/dona, foyda/dona, me'yoriy (bonussiz) foyda/dona (F40, ADR-031),
  marja, ROI, qaytish %, qoldiq, zaxira kunlari,
  ABC (bizniki + Uzum `rankInfo`), holat belgisi (Zarar / Chegarada < 5% / Foydali / Ma'lumot yo'q).
- Qidiruv (lotin/kirill, apostrof turidan qat'i nazar), filtrlar, ustunlarni tanlash, saqlangan ko'rinishlar,
  Excel eksport.
- **SKU sahifasi:** sarlavha (rasm, nom, Uzum'dagi sahifaga havola), KPI'lar; narx va foyda tarixi; tannarx tarixi
  (lotlar vaqt chizig'ida); kunlik sotuv; qoldiq tarixi (snapshotlardan); qaytishlar va sabablari;
  **unit kalkulyator** (narx, reklama %, tannarx o'zgarsa nima bo'ladi) + zararsizlik narxi (F35) + maqsadli
  marja narxi (F36) — me'yoriy (bonussiz) tariflar bilan (F40); izohlar.
- **Tovar (item) va SKU:** bitta jismoniy tovar bir necha do'kon/marketplace SKU'siga bog'lanishi mumkin.
  Tannarx va ombor tovar darajasida yuritiladi. Standart: har SKU = alohida tovar; birlashtirish qo'lda.

Qabul mezonlari: 2 000 SKU'li jadval virtual skroll bilan silliq; har raqam yonidagi "?" formulani ochadi.

## M7. Buyurtmalar, bekor va qaytishlar [B4; FBS B5]

- Sotuv qatorlari ro'yxati: sana, holat, SKU, dona, narx, komissiya, logistika, Uzum to'lovi, tannarx, foyda;
  Uzum bonus davridagi buyurtma — "Bonus davri" belgisi (ADR-031).
- Bekor tahlili: ulush (F17), topshirilgandan keyin bekor, SKU bo'yicha, trend.
- Qaytish tahlili: ulush (F18), sabab (`returnCause`), SKU bo'yicha, qaytish xarajati (qaytim saqlash C000004).
- FBS (do'konda bo'lsa): faol buyurtmalar, `acceptUntil` / `deliverUntil` muddatlari, kechikish xavfi [B5].
  FBS buyurtmani tasdiqlash / yorliq chop etish [Keyin].

## M8. Xarajatlar [B4]

- **Uzum xarajatlari:** kod bo'yicha toifalar (reklama, saqlash, qaytim saqlash, jarimalar, fotostudiya,
  pul yechish xizmati, kompensatsiya, boshqa), trend, eng katta jarimalar ro'yxati.
- **O'z xarajatlarim:** toifalar (ish haqi, ijara, qadoq, internet, bank, transport, boshqa — tahrirlanadi),
  bir martalik / takroriy (har oy N-sanada), amortizatsiya (masalan, printer 12 oyga), taqsimot (tashkilot / do'kon /
  tovar / tushum ulushi bo'yicha), chek rasmi [B7].
- Excel'dan import [B7].

## M9. Xaridlar (partiyalar) va tannarx — asosiy ustunligimiz [B4 asos, B5 to'liq]

**Vazifasi.** Xitoydan (yoki boshqa joydan) buyurtma bergan kundan tovar Uzum omboriga yetguncha bo'lgan har bir
xarajatni to'g'ri yig'ish va tovarlarga to'g'ri bo'lish.

- **Yetkazib beruvchilar:** nomi, platforma (1688, Pinduoduo, Taobao, WeChat, mahalliy, boshqa), aloqa, valyuta,
  o'rtacha tayyorlash muddati (o'rganiladi), izoh.
- **Kargo kompaniyalari:** nomi, narx usuli (kg / m³ / dona / aralash), valyuta, o'rtacha yo'l muddati (o'rganiladi).
- **Xarid (partiya) hayoti:** Qoralama → Buyurtma berildi → To'landi → Xitoy omborida → Yo'lda → Toshkentga keldi →
  Qabul qilindi → Uzumga yuborildi → Yopildi. Har bosqich ixtiyoriy, sanasi yoziladi, vaqt chizig'ida ko'rinadi.
  Legacy'dagi kabi bosqichma-bosqich to'ldiriladi: avval faqat tovar summasi, keyin qatorlar, keyin kargo.
- **Qatorlar:** tovar/SKU yoki "yangi tovar" (vaqtinchalik nom, rasm, 1688 havolasi), variant (rang × o'lcham),
  buyurtma qilingan va qabul qilingan dona (qisman kelishi mumkin), dona narxi (valyutada), dona vazni va hajmi
  (taqsimot uchun, ixtiyoriy).
- **Xarajat komponentlari** (istalgancha): tovar, Xitoy ichki yetkazish, xarid komissiyasi (agent), kargo, bojxona,
  qadoqlash, shtrix-kod/yorliq, Uzum omboriga yetkazish, boshqa. Har birida: summa + valyuta, to'lov sanasi,
  hisob (karta/naqd), **kurs**, **taqsimot asosi**, qaysi qatorlarga tegishli.
  - Kurs rejimlari: (1) CBU kursi to'lov sanasi bo'yicha (standart); (2) qo'lda; (3) **"kartadan yechilgan summa"**:
    masalan 1 000 CNY uchun USD kartadan 142,50 $ yechildi → effektiv kurs avtomatik.
  - Taqsimot asosi: dona / vazn / hajm / qiymat / qo'lda. Kargo uchun standart: vazn (vazn kiritilmagan bo'lsa dona).
- **Birlik tannarx** (F20) jonli hisoblanadi, tarkibi ko'rinadi; kargo hali kiritilmagan bo'lsa "taxminiy" belgisi.
- Qabulda brak/kamomad: hisobdan chiqarish yoki yetkazib beruvchiga da'vo.
- "Qayta buyurtma" — eski xaridni nusxalash; zaxira rejasidan xarid yaratish [B5].
- **Kech kiritilgan xarajat** (masalan, kargo narxi 20 kundan keyin) kiritilganda o'tgan sotuvlar tannarxi
  avtomatik qayta hisoblanadi va P&L'da "qayta hisoblandi" belgisi chiqadi.
- Excel import [B7]. (Legacy partiyalarini ko'chirish bekor — ADR-032: qo'lda kiritiladi.)
- Eski partiyalar shart emas: boshlash sanasidan oldingisi — boshlang'ich holat (F41, ADR-033).

Qabul mezonlari: legacy'dagi har partiya ko'chirilgach birlik tannarx legacy bilan bir xil (o'rtacha usulda);
kargo vazn bo'yicha taqsimlanganda qatorlar yig'indisi kargo summasiga tiyinigacha teng (yaxlitlash qoldig'i
eng katta qatorga, F20); kurs o'zgarsa tannarx darhol yangilanadi.

## M10. Ombor va zaxira rejasi [B4 asos, B5 to'liq]

- **Joylar:** Xitoyda (buyurtma qilingan) → Yo'lda → O'z omborim → Uzum FBO (API) / FBS (API) → Brak → Qaytish yo'lida.
- **Qoldiq jadvali:** har tovar bo'yicha joylar, tannarxdagi qiymat, zaxira kunlari (F24), holat (F26), buyurtma sanasi,
  tavsiya miqdor (F27) va byudjet (CNY va so'm), "Xarid yaratish" tugmasi.
- **FBO yuborish rejasi:** o'z omborimdan Uzumga nima yuborish kerak (FBO zaxira maqsadi bo'yicha) + Excel [B5].
- **Postavkalar:** holat, e'lon qilingan va qabul qilingan dona, kamomad (F33), bog'liq C000007 jarimasi [B5].
- **Yo'qolgan tovar** (F31) va kompensatsiya taxmini (F32), "kabinetda tekshiring" ro'yxati bilan [B5].
- **Nelikvid** (F30), **muzlagan pul** (F29), **tugab qolishdan yo'qotilgan foyda** (F34) [B5].
- Qoldiq tarixi grafigi (snapshotlardan); o'z omborida inventarizatsiya (tuzatish yozuvi bilan).

Qabul mezonlari: Uzum FBO qoldig'i `quantityActive` + `quantityFbs` dan olinadi (faqat `/fbs/sku/stocks` emas);
tezlik hisobida qoldiq 0 bo'lgan kunlar chiqarib tashlanadi; yo'qolgan tovar ishonchsiz holatda ko'rsatilmaydi.

## M11. Pul oqimi [B5]

- **Hisoblar:** karta (so'm), USD karta, naqd, bank, Uzum balansi (virtual).
- **Kirim/chiqim:** xarid to'lovlari va o'z xarajatlari avtomatik, Uzum to'lovlari (prognozdan tasdiqlanadi),
  o'tkazmalar, qo'lda yozuv.
- **Uzum to'lov prognozi** (F38): jadval bo'yicha qachon qancha tushadi; tushgach "tushdi" deb belgilanadi.
- **90 kunlik to'lov kalendari** (F39): rejalashtirilgan kargo to'lovlari, takroriy xarajatlar, kutilayotgan Uzum
  to'lovlari → kunlik qoldiq prognozi; manfiy bo'lsa "kassa uzilishi" ogohlantirishi.

## M12. Reja-fakt [B5]

Oylik maqsadlar (tushum, sof foyda, dona) tashkilot / do'kon / tovar bo'yicha; bajarilish %; oy oxiri prognozi
(run-rate); og'ish 15% dan katta bo'lsa ogohlantirish.

## M13. Kalkulyator (xariddan oldin) [B5]

Kiritish: 1688 narxi (CNY) + Xitoy ichki yetkazish, dona, dona vazni (kg) va o'lchami (sm), kargo narxi ($/kg yoki
$/m³), qo'shimcha xarajat/dona, Uzum toifasi komissiyasi (%), mo'ljallangan narx.
Natija: tannarx/dona, Uzum logistika (F37), komissiya, soliq, foyda/dona, marja, ROI, zararsizlik narxi (F35),
maqsadli marja narxi (F36). Ssenariyni saqlash, xaridga aylantirish.
**Ochiq versiya** (ro'yxatdan o'tmasdan) landing sahifada — mijoz jalb qilish uchun [B8].

## M14. Hisobotlar va eksport [B7]

- Har jadval → Excel (formatlangan, so'm formatida).
- Oylik PDF hisobot: P&L, TOP SKU, ombor holati, keyingi oy rejasi.
- Buxgalter paketi: oy bo'yicha sotuvlar reyestri, xarajatlar reyestri, xaridlar.
- Rejalashtirilgan yuborish (har oyning 1-sanasi, Telegram).
- **To'liq eksport** (ZIP: CSV + JSON) — "ma'lumot sizniki".

## M15. Bildirishnomalar va Telegram bot [B6]

Kanallar: Telegram (asosiy), ilova ichida, web push (PWA); email [Keyin].

| Hodisa | Standart | Chegara (sozlanadi) |
|---|---|---|
| Kunlik xulosa (kechagi buyurtma, tushum, sof foyda, bekorlar) | yoqilgan, 09:00 | vaqt |
| Haftalik xulosa | yoqilgan, dushanba 09:00 | — |
| Qoldiq kritik (F26) | yoqilgan | holat |
| Zarar bilan sotuv | yoqilgan | foyda/dona < 0, ketma-ket 3 sotuv |
| Tannarxsiz sotuvlar paydo bo'ldi | yoqilgan | kuniga 1 marta |
| Yangi jarima | yoqilgan | summa > 0 |
| Qaytish keskin oshdi | yoqilgan | 7 kun ulushi 30 kunlikdan 2 barobar |
| Postavka kamomadi | yoqilgan | > 0 dona |
| Yo'qolgan tovar signali | yoqilgan | taxmin > 0 |
| Sinxron to'xtadi / kalit yaroqsiz / kvota tugayapti | yoqilgan | 2 soat |
| Uzum to'lovi kutilmoqda / tushmadi | yoqilgan | kutilgan + 4 ish kuni |
| Kargo kechikmoqda | yoqilgan | kutilgan sana + 5 kun |
| SKU komissiyasi o'zgardi | yoqilgan | har o'zgarish |
| FBS: `acceptUntil` yaqin | FBS bo'lsa | 2 soat qoldi |

- Tinch soatlar (standart 22:00–08:00, kritiklardan tashqari), har foydalanuvchi o'zi tanlaydi.
- Bot buyruqlari: `/bugun`, `/kecha`, `/hafta`, `/oy`, `/qoldiq`, `/sozlamalar`; har xabarda "Batafsil" tugmasi
  ilovaning kerakli sahifasini ochadi.
- Bog'lash: ilovadagi QR/havola (`t.me/<bot>?start=<bir martalik token>`).

Qabul mezonlari: kunlik xulosadagi raqamlar ilovadagi "Kecha" bilan bir xil; Uzum uzilishida "sotuv yo'q"
xabari yuborilmaydi; bitta hodisa takror yuborilmaydi (idempotent).

## M16. Sozlamalar [B4]

Tashkilot, do'konlar (nom, rang, hisobga olish/olmaslik), soliq profili (F11), tannarx usuli (FIFO / o'rtacha),
valyutalar va kurs manbasi, Uzum to'lov jadvali (F38), **Uzum bonuslari** (bepul xarajat davrlari: do'kon yoki
hammasi, sanalar, turlar, sabab; tizim takliflarini tasdiqlash — ADR-031), standart yetkazish muddatlari, ABC qamrov kunlari,
ogohlantirish chegaralari, Telegram, til, tarif va to'lovlar [B8], API kalitlar (Pro) [B10], to'liq eksport,
tashkilotni o'chirish (30 kunlik kutish bilan).

## M17. Admin panel (ichki) [B8]

Tashkilotlar, obunalar, to'lovlar; barcha akkauntlar bo'yicha sinxron holati va kvota; xatolar oqimi;
foydalanuvchi nomidan kirish (faqat audit va ekranda banner bilan); funksiya bayroqlari; xarajat kodlari lug'ati;
Uzum tariflari jadvali (sana bo'yicha); soliq jadvallari; hammaga e'lon (banner).

## M18. Yordam markazi [B3 asos, B8 to'liq]

Har ko'rsatkich yonida "?" (formula + izoh), yordam maqolalari (uz/ru), qisqa videolar, onboarding ro'yxati,
Telegram orqali yordam havolasi, "Yangiliklar" (changelog) sahifasi.

## M19. AI yordamchi [Keyin, B10]

Savol-javob o'z ma'lumoti bo'yicha ("O'tgan oy qaysi tovar zarar qildi?"). Claude API, faqat dastur API'sidan
olingan raqamlar bilan javob beradi (raqam manbasi ko'rsatiladi, taxmin qilmaydi). Pro tarifda MCP server
(sotuvchi o'z AI yordamchisini ulaydi).

## M20. Boshqa marketplace'lar [Keyin, B10]

Yandex Market (O'zbekiston), Wildberries, Ozon. B2 dan boshlab provayder interfeysi (03 §6) shu uchun qurilgan.

## M21. Narx boshqaruvi va FBS operatsiyalari [Keyin, B10]

Narxni `sendPriceData` orqali o'zgartirish (pastki chegara = F36), FBS buyurtmani tasdiqlash, yorliq va
topshirish akti.

---

## Formulalar lug'ati (yagona manba)

Umumiy qoidalar:
- Pul `Decimal`; so'm 2 xona; valyuta 4 xona; kurs 6 xona. Ko'rsatishda so'm butun songa yaxlitlanadi.
- Vaqt bazada UTC (`timestamptz`); biznes sanasi Asia/Tashkent bo'yicha.
- Tannarx noma'lum joyda raqam O'YLAB TOPILMAYDI: "ma'lumot yo'q" yoki "taxminiy" belgisi bilan ko'rsatiladi.

**F1. Davr.** Sotuv sanasi = `finance/orders.date` ning Toshkent sanasi. Davr [boshlanish 00:00; tugash 23:59:59.999].
Yakunlangan sana Open API'da yo'q (FBO uchun), shuning uchun yagona asos — buyurtma sanasi (ADR-017).

**F2. Holatlar.** Yakunlangan = `TO_WITHDRAW`; Jarayonda = `PROCESSING`; Bekor = `CANCELED`;
Qisman bekor = `PARTIALLY_CANCELLED` (qolgan `amount` yakunlangan sifatida; Temurning real ma'lumotida bunday qator
yo'q — taxmin, birinchi real qatorda `scripts/compare_staging.py` tekshiradi). Real ma'lumot (B2.11): Bekor qatorda
Uzum `amount` = 0, `commission`, `logisticDeliveryFee`, `sellerProfit` = 0 beradi, bekor qilingan dona — `amountReturns`.
`sellerProfit` hamma qatorda `amount` bilan F6 ga teng — `amount` doim qolgan (sof) dona.

**F3. Tushum** = Σ `sellPrice` × `amount` (Yakunlangan).

**F4. Uzum komissiyasi** = Σ `commission` (Yakunlangan).

**F5. Logistika** = Σ `logisticDeliveryFee` (Yakunlangan). Xarajatlardagi logistika kodlari qayta ayrilmaydi.

**F6. Uzum to'lovi** = F3 − F4 − F5. `sellerProfit` kelgan qatorlarda solishtiriladi; farq > 1 so'm bo'lsa log.

**F7. Tannarx (COGS)** = Σ (sotuvning birlik tannarxi F21) × `amount` (Yakunlangan, tannarxi ma'lum qatorlar).

**F8. Yalpi foyda** = F6 − F7.

**F9. Uzum xarajatlari** = reklama + saqlash + qaytim saqlash + jarimalar + fotostudiya + pul yechish xizmati +
boshqa Uzum xizmatlari − kompensatsiyalar. Manba `finance/expenses`, toifa `code` bo'yicha (birinchi harf kirill
yoki lotin keladi: С/C, У/U/Y variantlari bitta kodga keltiriladi — legacy У→U ni, qo'llanma Y ni ko'rsatadi; real
ma'lumotda B2.11 da tasdiqlanadi). `status` CANCELED/REFUNDED va `BALANCE_CORRECTION` hisobga
olinmaydi; summa `abs(paymentPrice)`, yo'nalish `type` dan; dublikat `id` bo'yicha olib tashlanadi; reklama matnidagi
aniq summa (legacy `AD_RE`) ishlatiladi.

**F10. O'z xarajatlari** = qo'lda kiritilgan xarajatlar, amortizatsiya bilan davrga to'g'ri keladigan qismi
(kunlik teng taqsimot).

**F11. Soliq** = soliq profili bo'yicha:
(a) aylanmadan %: stavka × baza (baza: Tushum F3 — standart, yoki Uzum to'lovi F6);
(b) Uzum soliq agenti sifatida ushlaydi: xarajatlardan olinadi, qayta hisoblanmaydi;
(c) QQS + foyda solig'i: QQS va foyda solig'i stavkalari sozlamada, oylik taxmin;
(d) yo'q.
Stavkalar bazada sana bo'yicha (2026: YaTT 1% yillik daromad 1 mlrd so'mgacha; e-tijorat yuridik shaxslari uchun
bazaviy 4% / 15% — 08-tadqiqot.md, buxgalter bilan tasdiqlanadi).

**F12. Sof foyda** = F8 − F9 − F10 − F11.

**F13. Marja** = F12 / (tannarxi ma'lum qatorlar tushumi) — F15 bilan bir asosda (ADR-024); qamrov 100% bo'lsa
F12 / F3. Marja yonida doim **tannarxsiz qism ulushi** = 1 − F15 alohida ko'rsatiladi (0% bo'lsa yashiriladi).
**F14. ROI** = F12 / F7.

**F15. Tannarx qamrovi** = (tannarxi ma'lum qatorlar tushumi) / F3. Qamrov < 100% bo'lsa sof foyda faqat ma'lum
qatorlar bo'yicha hisoblanadi; F9, F10, F11 qamrov ulushiga mutanosib qismi ayriladi; qolgani "tannarxsiz qism"
qatorida alohida ko'rsatiladi. (Legacy hamma xarajatni ayirib, foydani kam ko'rsatardi.)

**F16. Kutilayotgan foyda** = Σ (F6 − F7) Jarayondagi qatorlar × R. R = realizatsiya darajasi = do'konning oxirgi
90 kunida yakuniy holatga yetgan donalar ichida Yakunlangan ulushi. Ma'lumot kam bo'lsa (< 50 dona) R ko'rsatilmaydi.
(Legacy'dagi 0,75 doimiysi o'rniga.)

**F17. Bekor ulushi** = Bekor / (Yakunlangan + Bekor), dona bo'yicha. Bekor dona = `amount` + `amountReturns` (F2).

**F18. Qaytish ulushi** = qaytgan / (sotilgan + qaytgan) — Uzum ta'rifi (SKU `quantityReturned`, `quantitySold`);
davr bo'yicha esa Yakunlangan qatorlardagi `amountReturns` dan (Bekor qatorniki — bekor qilingan dona, qaytish emas).

**F19. Reklama ulushi (DRR)** = reklama / F3. SKU ACOS = SKU'ga bog'langan reklama (AD#id → sotuv qatori) /
SKU tushumi. Bog'lanmagan reklama SKU'larga tushum ulushi bo'yicha taqsimlanadi (sozlamada o'chirish mumkin).

**F20. Xarid (lot) birlik tannarxi.** Har komponent: summa × kurs → so'm; taqsimot asosiga ko'ra qatorlarga
bo'linadi (dona / vazn / hajm / qiymat / qo'lda); qatorning birlik tannarxi = qatorga tushgan komponentlar
yig'indisi / qabul qilingan dona (hali qabul qilinmagan bo'lsa buyurtma qilingan dona, "taxminiy"). Yaxlitlash
qoldig'i eng katta qatorga. Kurs: CBU (to'lov sanasi, dam olish kunida oxirgi ish kuni), qo'lda, yoki yechilgan
summadan effektiv kurs.

**F21. Sotuv tannarxi.** Hodisalar sana tartibida: lot kirimi (+), sotuv (−), sotuvga yaroqli qaytish (+, o'sha
lot narxida), brak / yo'qotish (−).
- **FIFO** (standart): sotuv eng eski ochiq lotdan.
- **O'rtacha** (harakatlanuvchi): yangi o'rtacha = (qoldiq qiymati + kirim qiymati) / (qoldiq + kirim).
- Lot sotuvga tayyor sanasi = qabul sanasi; yo'q bo'lsa kargo to'langan sana (Temurning jarayonida kargo tovar
  qo'lga olinganda to'lanadi). Ikkalasi ham yo'q lot — "yo'lda".
- Yo'ldagi lot sotuvga faqat tayyor lotlar tugaganda ishlatiladi ("qabul belgilanmagan" belgisi: sotuv bor — demak
  tovar kelgan). Shu bilan legacy qoidasi saqlanadi: yo'ldagi partiya eski tovar sotuvlarini buzmaydi.
- Sotuv birinchi lotdan oldin bo'lsa — birinchi lot narxi, "erta sotuv" belgisi.
- Hamma lot tugasa: oxirgi ma'lum lot narxi + "lot yetmadi"; tovarda lot umuman yo'q: tannarx yo'q.
- Har o'zgarishda tovarning eng erta o'zgargan sanasidan qayta hisoblanadi.
- Boshlang'ich holat (F41) bo'lsa — boshlash sanasigacha bo'lgan hodisalar lotlarga tegmaydi.

**F22. Taxminiy belgilar:** "kargo kiritilmagan", "erta sotuv" (sotuv lotdan oldin), "lot yetmadi", "tarixiy"
(boshlash sanasidan oldingi sotuv — F41),
"kurs qo'lda emas, CBU". UI'da `~` va izoh.

**F23. Sof sotuv tezligi** (dona/kun): oxirgi 14 kun, oxirgi 7 kun 2 barobar vazn bilan; qoldiq 0 bo'lgan kunlar
(snapshot) hisobdan chiqariladi; yangi tovar uchun kamida 7 kunga bo'linadi; × (1 − qaytish darajasi, 14 kun,
≤ 0,5); × trend koeffitsiyenti: r = v7/v30 → r ≥ 1,3: 1,20; 1,1 ≤ r < 1,3: 1,10; 0,9 < r < 1,1: 1,00;
0,7 < r ≤ 0,9: 0,93; r ≤ 0,7: 0,85.

**F24. Zaxira kunlari** = (FBO `quantityActive` + FBS `quantityFbs`) / F23.

**F25. To'liq muddat** = tayyorlash + Xitoy ichki + kargo yo'li + qabul/yorliq + Uzumga topshirish. Har biri
yetkazib beruvchi va kargo tarixidan o'rganiladi (oxirgi 5 xarid medianasi), yo'q bo'lsa sozlamadagi standart.

**F26. Holat:** Kritik (zaxira ≤ F25) · Yuqori (≤ F25 + 7) · O'rta (≤ F25 + 21) · Yaxshi · Harakatsiz
(tezlik 0, qoldiq > 0). Mahsulotning eng ko'p sotiladigan varianti (sotuvning ≥ 20%) kritik bo'lsa, butun mahsulot kritik.

**F27. Tavsiya miqdor** = max(0, F23 × (F25 + qamrov) − (qoldiq + yo'lda + buyurtma qilingan)), qamrov ABC bo'yicha
(A 60, B 30, C 14 kun, sozlanadi), odatiy partiya hajmiga yaxlitlanadi. Byudjet = miqdor × oxirgi lot narxi (CNY va so'm).
**Buyurtma sanasi** = bugun + (zaxira kunlari F24 − to'liq muddat F25), butun kunga pastga yaxlitlanadi; farq ≤ 0 (F26
"Kritik") bo'lsa — "hozir" (kechikkan). Tezlik 0 yoki muddat noma'lum bo'lsa sana yo'q. Qoldiq tarkibi (F27, F29):
Xitoyda (buyurtma, to'landi, Xitoy omborida), yo'lda (yo'lda, Toshkentga keldi), o'z omborim (qabul qilindi, Uzumga
yuborilmadi; inventarizatsiya tuzatishi va hisobdan chiqarish bilan) — xarid bosqichidan; Uzumga yuborilgani FBO'da.

**F28. ABC / XYZ.** ABC: oxirgi 30 kun tushumi (yoki foydasi — tanlanadi) kamayish tartibida, jamlangan ulush
0–80% A, 80–95% B, 95–100% C. XYZ: oxirgi 8 hafta haftalik sotuvlarning variatsiya koeffitsiyenti: ≤ 0,25 X,
≤ 0,5 Y, > 0,5 Z.

**F29. Muzlagan pul** = Σ qoldiq × lot narxi (joylar bo'yicha). O'rtacha sotilish muddati = Σ (zaxira kunlari ×
qiymat) / Σ qiymat.

**F30. Nelikvid** = qoldiq > 0, tezlik 0 va (hech sotilmagan yoki oxirgi sotuvdan > 180 kun). "Sekin" = 90–180 kun.

**F31. Yo'qolgan tovar** (SKU): kutilgan qoldiq = (FBO'ga qabul qilingan + FBS jo'natilgan) − sotilgan −
(qaytarilgan + FBS qaytgan + brak); farq = max(0, kutilgan − omborda); yo'qolgan = max(0, farq − min(qaytish
yo'lida, farq)). Faqat sotuv tarixi ishonchli bo'lsa va oxirgi 3 kunlik postavkalar chiqarib tashlangan holda.
Asos — *qabul qilingan* dona (e'lon qilingan emas): qabuldagi kamomad F33 da alohida, ikki marta sanalmaydi.

**F32. Kompensatsiya taxmini** = yo'qolgan × o'rtacha sotuv narxi (oxirgi 30 sotuv) × (1 − komissiya%).

**F33. Qabul kamomadi** = Σ (`quantityToStock` − `quantityAccepted`) postavka × SKU bo'yicha.

**F34. Tugab qolishdan yo'qotilgan foyda** = Σ (faol SKU qoldig'i 0 bo'lgan kunlar) × tugashdan oldingi F23 ×
o'rtacha foyda/dona (oxirgi 90 kun). Faqat snapshot bor kunlar uchun.

**F35. Zararsizlik narxi** = qat'iy / (1 − ulush/100); qat'iy = tannarx + logistika + qadoq/dona;
ulush = komissiya% + soliq% + reklama%. Ulush ≥ 100% → "hech qanday narx foyda bermaydi".

**F36. Maqsadli marja narxi** = qat'iy / (1 − (ulush + m)/100).
Narx `p` dagi foyda/dona = p × (1 − ulush/100) − qat'iy; F35 (foyda 0) va F36 (foyda = p × m/100) shu tenglamaning
ildizi — unit kalkulyator (`upcore.unit`) shuni ishlatadi.

**F37. Uzum logistika tarifi** (01.06.2026 dan, bazadagi jadval, sana bo'yicha): litr = (uzunlik × eni × balandlik,
mm) / 1 000 000, butun songa yaxlitlanadi; ≤ 1 l: 5 250 so'm; har qo'shimcha litr +250; maksimal 50 000;
o'lcham kiritilmagan: 50 000; SIM-karta: 20 000. Qaytishda qaytariladi.

**F38. Uzum to'lov prognozi.** Jadval: har ish kuni (1,5%), haftalik — 7, 14, 21, 28 (1%), 2 haftada — 7 va 21 (0%),
oylik — 7 (0%); shoshilinch yechish 2,5%. Kutilgan sana = jadvaldagi navbatdagi sana (dam olish kuni → keyingi
ish kuni), oraliq + 4 ish kuni (Uzum kechiktirishi mumkin). Summa = shu davrda Yakunlangan bo'lgan F6 − ushlanmalar.

**F39. Kassa prognozi** (90 kun) = boshlang'ich qoldiq + kutilgan kirimlar (F38) − rejalashtirilgan chiqimlar
(xarid to'lovlari, takroriy xarajatlar). Istalgan kunda < 0 → "kassa uzilishi" ogohlantirishi.

**F40. Me'yoriy (bonussiz) foyda/dona** (ADR-031; faqat SKU baholash va narx — M6, F35/F36, M13; P&L va hisob
varag'iga hech qachon qo'shilmaydi): foyda/dona − Uzum bonusi bilan tejalgan xarajatlarning me'yoriy qiymati/dona.
Bonus davrlari — `fee_waivers` (do'kon yoki hammasi, sanalar, bepul turlar, sabab; foydalanuvchi kiritadi yoki
tizim taklifini tasdiqlaydi; taklif: kunlik Yakunlangan qatorlarning ≥ 90% ida logistika 0). Me'yoriy qiymat tur
bo'yicha: sotuv logistikasi — SKU'ning bonus davridan tashqaridagi oxirgi pullik logistikasi, bo'lmasa do'konning
odatiy (eng ko'p) tarifi, SKU o'lchamlari bazada bo'lsa (tovar o'lchamlarini tahrirlash — B4.6) — F37 (SKU'ning o'z tarifidan keyin, do'kon tarifidan oldin; kodda hozircha qo'llanmaydi); saqlash — SKU `storage_price` × kunlar; baholovchisi yo'q tur —
"me'yoriy baho yo'q". Haqiqiy foyda (F3–F16) o'zgarmaydi: bonus davrida bepul xarajat 0.

**F41. Boshlang'ich holat** (ADR-033). Boshlash sanasi S (tashkilot sozlamasi, ixtiyoriy), tovar bo'yicha tarixiy
narxlar {(sana dan, dona narxi)} (sana yo'q — boshidan) va S kunidagi qoldiq Q = Uzumda (FBO + FBS; taklif — S dan
oldingi kun snapshoti, S bugun bo'lsa joriy qoldiq) + o'z omborimda (sotuvchi tasdiqlaydi, son qotadi).
- Narx kun bo'yicha: `sana dan ≤ kun` bo'lgan eng oxirgi narx; kun hamma narxdan oldin bo'lsa — eng birinchisi.
- Sotuv kuni < S: tannarx = shu kungi narx × dona, "tarixiy" belgisi (F22), lotlarga tegmaydi; narx yo'q — tannarxsiz.
- S kunida "boshlang'ich qoldiq" loti: Q dona × S kungi narx; FIFO'da shu kungi partiyalardan ham oldin ishlatiladi,
  o'rtachada hovuzning boshlang'ich qiymati. Q = 0 yoki narx yo'q — lot yo'q.
- Tayyor sanasi < S bo'lgan partiyalar ishlatilmaydi (qoldiqqa kirgan); yo'ldagi (sanasiz) va S dan keyingilari — F21.
- Ombor qiymati (F27, F29): S dan keyin tayyor partiya bo'lmasa — S kungi narx.
- Qamrov (sahifada): S gacha bo'lgan tushumning narx yozilgan turlarga to'g'ri keladigan ulushi — shu narx qo'llanadigan
  sotuvlar bo'yicha (doimiy oyna yo'q, tamoyil 2).
- Unit kalkulyator (F35/F36) tannarxi: oxirgi tayyor partiya, bo'lmasa davr o'rtachasi (narx keyingi donalar uchun).
