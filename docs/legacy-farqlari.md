# Legacy va yangi yadro farqlari (B1.9)

Raqamlar Temurning real ma'lumotida `scripts/compare_legacy.py` bilan olinadi (lokal, faqat standart kutubxona):

```bash
python3 scripts/compare_legacy.py --db uzum.db --history uzum_history.json
```

Skript `legacy_farqlari.md` faylini yozadi (repozitoriyga kirmaydi). Quyida — farqlar ro'yxati va sabablari;
real natija kelgach har bandga summa qo'shiladi.

## Bir xil bo'lishi shart (majburiy tekshiruv)

| Ko'rsatkich | Shart | Holat |
|---|---|---|
| Partiya birlik tannarxi (F20) | 1 tiyingacha | sintetik ma'lumotda ✓; real — kutilmoqda |
| Dona, tushum, komissiya, logistika (`TO_WITHDRAW`, oylar bo'yicha) | 1 so'mgacha | sintetik ✓; real — kutilmoqda |

## Kutilgan farqlar (tuzatilgan xatolar va yangi qoidalar)

| # | Farq | Legacy | Yangi | Manba |
|---|---|---|---|---|
| 1 | Sotuv tannarxi usuli | sanagacha kelgan hamma partiyalar o'rtachasi (kumulyativ) | FIFO (Temur tashkiloti, ADR-025) yoki harakatlanuvchi o'rtacha | F21 |
| 2 | Tannarxsiz qism | hamma xarajat ayiriladi — foyda kam ko'rinadi | xarajat qamrov ulushida, qolgani "tannarxsiz qism" | F15, ADR-026 |
| 3 | Marja maxraji | tannarxi ma'lum tushum | xuddi shunday + tannarxsiz ulush alohida | F13, ADR-024 |
| 4 | Xarajat toifalari | faqat reklama, saqlash, jarima, kompensatsiya | + fotostudiya, pul yechish, pullik jo'natish, boshqa | F9, B1.3 |
| 5 | Xarajat kodlari | faqat `У→U` varianti, `U000120` | hamma kirill/lotin variantlari, `Y000119`, `Y000050` | B1.3 |
| 6 | Xarajat statuslari | filtrlanmaydi | CANCELED/REFUNDED, `BALANCE_CORRECTION` chiqariladi | F9 |
| 7 | Uzum to'lovi (F6) | Uzum `sellerProfit` | F3 − F4 − F5, farq > 1 so'm bo'lsa log | F6 |
| 8 | `PARTIALLY_CANCELLED` | hisobga olinmaydi | qolgan `amount` yakunlangan | F2 (B2.11 da tasdiqlanadi) |
| 9 | Kutilayotgan foyda | doimiy 0,75 | do'konning 90 kunlik realizatsiya darajasi R (< 50 dona — ko'rsatilmaydi) | F16 |
| 10 | Bepul logistika davri | `.env` sanalari | ma'lumotdan aniqlanadi, admin tasdiqlaydi | F40 |
| 11 | Yo'ldagi partiya | boshqa to'liq partiya bo'lsa aralashmaydi | xuddi shunday: tayyor lotlar tugagach "qabul belgilanmagan" | F21 |
