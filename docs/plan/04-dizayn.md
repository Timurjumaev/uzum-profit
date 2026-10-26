# 04. Dizayn tizimi

Hamma sahifa shu fayl bo'yicha quriladi. Rang va kontrast qiymatlari taxmin emas: 2026-10-23 da
dataviz validatori (`validate_palette.js`) va WCAG/APCA hisobi bilan tekshirilgan (natijalar §4.4).

## 1. Yo'nalish

**Mavzu.** Dastur sotuvchining qog'oz daftarini (hisob daftari) almashtiradi. Vizual til shu yerdan olinadi:
toza qog'oz, ko'k-qora siyoh, buxgalteriya qoidalari (summa ustidan chiziq, yakuniy summa ostida ikki chiziq),
shtrix-kod (sotuvchi har kuni yopishtiradi). Bezak yo'q — raqamlar asosiy.

**Kim uchun.** Band sotuvchi, ko'pincha telefonda, Telegram'da yashaydi; buxgalter emas. O'zbek (lotin/kirill) va
rus tilida o'qiydi.

**Asosiy vazifa.** 5 soniyada "qancha sof foyda qildim va nimani buyurtma qilishim kerak" degan savolga javob.

**Bitta esda qoladigan element — "Hisob varag'i".** Bosh sahifa va P&L tushumdan sof foydagacha bo'lgan vertikal
hisob bilan ochiladi: har qator ayiriladi, oraliq summa ustida bitta chiziq, **Sof foyda** ostida ikki chiziq.
Bu ham chiroyli, ham vazifaviy: foyda qayerdan kelganini ko'rsatadi (raqobatchilarda yo'q shaffoflik).
Qolgan hamma narsa sokin va intizomli.

**Ikkinchi xos element — "Partiya yo'li"**: xaridning Xitoydan Uzumgacha bosqichlari vaqt chizig'ida (§6.2).

**Ataylab qilinmaydigan narsalar** (shablon belgilari): bir xil yumaloq kartochkalar to'ri va bir xil soya;
gradient bezaklar; KATTA HARFLI yorliqlar; sarlavhalarni nuqta bilan ulangan meta satrlar; havola matniga "→"
qo'shish; har bo'limga paydo bo'lish animatsiyasi; Uzum'ning binafsha rangi va uzum/uzum shingili motivlari.

Tekshiruv (dizayn rejasini shablon bilan solishtirish): oddiy "SaaS dashboard" yo'li — 4 ta KPI kartochka qatori,
gradient aksent, Inter + ko'k. Bizda: shrift xuddi shu sababli emas, glif tekshiruvi bilan tanlandi (§2); asosiy
blok kartochkalar emas, hisob varag'i; rang mavzudan (siyoh); tuzilma chiziqlari buxgalteriya ma'nosiga ega.

## 2. Shrift

**Qaror: Inter (variable, `opsz` + `wght`), butun ilova uchun bitta oila.**

Tekshiruv (google/fonts fayllari, fontTools + Chromium skrinshoti, 2026-10-23):

| Shrift | oʻ gʻ (U+02BB) | ʼ (U+02BC) | Oʻzbek kirill (Ў Қ Ғ Ҳ) | U+202F | `tnum` | Natija |
|---|---|---|---|---|---|---|
| **Inter** | bor, to'g'ri oraliq | bor | bor | bor | bor | **tanlandi** |
| Onest | bor | bor | bor | bor | bor | yaxshi, lekin minus (−) defisdek qisqa, raqamlar kengroq |
| IBM Plex Sans | bor, lekin "o ʻ" orasida katta bo'shliq | bor | bor | bor | yo'q | rad |
| Noto Sans | bor | bor | bor | bor | bor | keng, zaxira sifatida |
| Geist, Geologica, Golos Text, Rubik, Open Sans | **yo'q** | — | — | — | — | rad (oʻ zaxira shriftda chiqadi) |
| Manrope, JetBrains Mono | **yo'q** | yo'q | Қ Ғ Ҳ yo'q | — | — | rad |

- Fayl: o'zimizda (CDN emas), woff2, subset: lotin + lotin-ext + kirill + kirill-ext + U+02BB U+02BC U+00A0
  U+202F U+2212 U+2116; `font-display: swap`; asosiy fayl `preload`.
- Zaxira steki: `Inter, "Noto Sans", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif`.
- `font-optical-sizing: auto` (katta o'lchamda Inter Display shakli o'zi yoqiladi).
- Raqamlar: **jadval ustunlari, o'q yozuvlari, hisob varag'i summalari** — `font-variant-numeric: tabular-nums`;
  **katta yolg'iz raqamlar** (hero, KPI) — proportsional (standart).
- Kod va kalitlar (API kalitining oxirgi 4 belgisi, IDlar): `ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`.

### 2.1 Tipografik shkala

| Token | O'lcham / qator | Og'irlik | Qayerda |
|---|---|---|---|
| `hero` | 48/52 (mobil 36/40), −0,02em | 600 | sahifadagi yagona asosiy raqam (Sof foyda) |
| `display` | 36/44 | 600 | landing sarlavhalari |
| `h1` | 24/32, −0,01em | 600 | sahifa sarlavhasi |
| `h2` | 18/26 | 600 | bo'lim sarlavhasi |
| `h3` | 15/22 | 600 | blok sarlavhasi |
| `body` | 14/20 (mobil 15/22) | 400 | asosiy matn |
| `body-strong` | 14/20 | 500 | tugmalar, menyu |
| `table` | 13/18 | 400 | jadval qatorlari |
| `label` | 12/16 | 500 | yorliqlar, jadval sarlavhalari (gap harfida, katta harf emas) |
| `kpi` | 28/34 | 600 | KPI qiymati |
| `caption` | 12/16 | 400 | izohlar |

Matn satri ≤ 75 belgi (yordam matnlari, tavsiflar). Hamma matn chapga tekislanadi; raqamlar o'ngga.

## 3. Oraliq, shakl, chiziqlar

- Oraliq qadami 4 px: 4, 8, 12, 16, 20, 24, 32, 40, 48, 64.
- Radius: 6 px (tugma, input), 10 px (panel, drawer, dialog); jadvallar va hisob varag'ida radius yo'q.
- Chiziqlar: `hairline` (1 px, ajratuvchi), `rule` (1 px, hisobdagi oraliq summa ustida — siyoh rangida),
  `rule-double` (3 px double, faqat yakuniy summa ostida).
- Soya: faqat suzib chiqadigan qatlamlarda (menyu, popover, dialog): `0 8px 24px rgb(18 24 38 / 0.12)`.
  Statik bloklarda soya yo'q — ajratish oq maydon va hairline bilan.
- Breakpointlar: 360 (eng kichik), 640, 768, 1024, 1280, 1440. Kontent maksimal kengligi 1440 px; chekka oraliq
  16 px (mobil) / 24 px (desktop).

## 4. Ranglar

### 4.1 Asosiy palitra (nomlangan)

| Nomi | Yorug' | Qorong'i | Vazifasi |
|---|---|---|---|
| **Qog'oz** (sahifa) | `#F5F6F8` | `#0E121A` | sahifa foni |
| **Varaq** (yuza) | `#FFFFFF` | `#161B24` | panel, jadval, grafik foni |
| **Siyoh** (asosiy matn) | `#121826` | `#EEF0F4` | matn, hisob chiziqlari, sof foyda chizig'i |
| **Ko'k siyoh** (aksent) | `#256ABF` | `#6DA7EC` (matn) / `#256ABF` (tugma) | asosiy tugma, havola, fokus, tanlangan holat |
| **Daftar chizig'i** | `#E3E6EB` | `#2A3140` | hairline, jadval qatorlari |
| **Foyda** | `#006300` | `#3FBF3F` | musbat natija matni |
| **Zarar** | `#B42F2F` | `#EF8A8A` | manfiy natija matni |

### 4.2 Barcha tokenlar

| Token | Yorug' | Qorong'i |
|---|---|---|
| `bg-page` | `#F5F6F8` | `#0E121A` |
| `bg-surface` | `#FFFFFF` | `#161B24` |
| `bg-raised` (hover, tanlangan qator) | `#F0F2F5` | `#1E2430` |
| `text-primary` | `#121826` | `#EEF0F4` |
| `text-secondary` | `#4B5160` | `#B4BAC6` |
| `text-muted` (faqat ≥ 14 px yoki ikkinchi darajali) | `#7C8291` | `#8A91A0` |
| `border-hairline` | `#E3E6EB` | `#2A3140` |
| `border-rule` | `#121826` | `#EEF0F4` |
| `border-input` (≥ 3:1) | `#858A96` | `#6B7282` |
| `accent` (tugma foni) | `#256ABF` | `#256ABF` |
| `accent-hover` | `#1C5CAB` | `#3987E5` |
| `accent-text` (havola) | `#256ABF` | `#6DA7EC` |
| `on-accent` | `#FFFFFF` | `#FFFFFF` |
| `focus-ring` | `#256ABF` | `#6DA7EC` |
| `positive-text` / `positive-bg` | `#006300` / `#E3F4E3` | `#3FBF3F` / `#13301A` |
| `negative-text` / `negative-bg` | `#B42F2F` / `#FBE9E9` | `#EF8A8A` / `#3A1C1C` |
| `warning-text` / `warning-bg` | `#8A5A00` / `#FDF1D6` | `#FAB219` / `#3A2C0E` |
| `info-text` / `info-bg` | `#1C5CAB` / `#E7F0FB` | `#86B6EF` / `#16263D` |

Qorong'i rejim avtomatik inversiya emas: har token alohida tanlangan. Tizim sozlamasiga ergashadi, foydalanuvchi
qo'lda tanlay oladi (`data-theme`).

### 4.3 Grafik ranglari (dataviz usuli)

- **Kategoriyalar** (do'konlar, xarajat turlari) — qat'iy tartib, hech qachon aylanib takrorlanmaydi; 9-chi seriya
  "Boshqa"ga qo'shiladi. Rang ob'ektga ergashadi (do'kon 1 doim 1-rang), tartib yoki filtr bo'yicha qayta bo'yalmaydi.

| Slot | Yorug' | Qorong'i |
|---|---|---|
| 1 ko'k | `#2A78D6` | `#3987E5` |
| 2 to'q sariq | `#EB6834` | `#D95926` |
| 3 zangori-yashil | `#1BAF7A` | `#199E70` |
| 4 sariq | `#EDA100` | `#C98500` |
| 5 pushti | `#E87BA4` | `#D55181` |
| 6 yashil | `#008300` | `#008300` |
| 7 binafsha | `#6250D6` | `#9085E9` |
| 8 qizil | `#E34948` | `#E66767` |

- **Ketma-ket (miqdor):** bitta ko'k shkala `#CDE2FB` → `#0D366B` (issiqlik xaritasi, kalendar).
  Qorong'i rejimda shkala teskari (eng ko'p qiymat — `#CDE2FB`, eng kam — `#0D366B`): qorong'i fonda "ko'p" yorug' ko'rinadi
  (B3.6; `#0D366B` `bg-surface` bilan deyarli bir xil bo'lgani uchun eng kam qiymat ham ko'rinadigan chegarada qoladi).
- **Ikki qutbli (+/−):** ko'k ↔ qizil, o'rtasi kulrang (yorug' `#F0EFEC`, qorong'i `#383835`) — sharshara
  grafigidagi qo'shiluvchi va ayriluvchi qadamlar.
- **Holat ranglari (faqat holat uchun, hech qachon "4-seriya" emas):** yaxshi `#0CA30C`, ogohlantirish `#FAB219`,
  jiddiy `#EC835A`, kritik `#D03B3B` — doim ikon + matn bilan.
- **Rollar (ob'ekt → slot, hamma grafikda bir xil):** Tushum 1; komissiya 2; logistika 3; tannarx 4; reklama 5;
  saqlash 6; jarima 7; boshqa 8 — xarajatlar tarkibi doim ketma-ket slotlar (2–8), oraliq tashlanmaydi (validator
  faqat qo'shni slotlar juftini tekshirgan). Natija chizig'i (Sof foyda) — kategoriya emas, alohida rol: siyoh
  (`text-primary`), 2 px.
- **Do'konlar:** slot do'kon qo'shilgan tartibda. 1–3 slot har qanday juftlikda ajraladi (validator: "hamma juftlik"
  3 tagacha), shuning uchun do'kon bo'yicha grafikda ko'pi bilan 3 ta do'kon + "Boshqa" (kulrang) yoki kichik
  grafiklar (small multiples).
- **Sharshara:** qo'shiluvchi qadam — slot 1 ko'k, ayiriluvchi — slot 8 qizil (`#E34948` / `#E66767`), yakuniy
  ustun — siyoh. (Holat qizili `#D03B3B` bu yerda ishlatilmaydi.)
- **Matn hech qachon seriya rangida bo'lmaydi** — yorliq va qiymatlar matn tokenlarida, yonida rangli belgi.

### 4.4 Tekshiruv natijalari (2026-10-23)

- Kategoriya palitrasi, yorug' (`#FFFFFF` fonda): yorqinlik, xroma, CVD (eng yomon qo'shni ΔE 9,1), oddiy ko'z
  (19,6) — PASS; 3 slot (`#1BAF7A`, `#EDA100`, `#E87BA4`) fonga < 3:1 → **majburiy yengillik**: bu ranglar ishlatilgan
  grafikda to'g'ridan-to'g'ri yorliqlar yoki jadval ko'rinishi bo'ladi (har grafikda "Jadval" tugmasi bor).
- Qorong'i (`#161B24` fonda): hammasi PASS (CVD 8,4, oddiy ko'z 19,3, kontrast ≥ 3:1).
- Scatter/xarita kabi "hamma juftlik" grafiklarida ko'pi bilan 3 seriya.
- Matn kontrastlari (WCAG): siyoh 17,3; ikkinchi darajali 7,7; muted 3,75 (shuning uchun kichik matnda ishlatilmaydi);
  havola 5,4; oq matn aksent tugmada 5,4; foyda 7,5; zarar 6,2; ogohlantirish 5,9; input chegarasi 3,5 (≥ 3:1;
  2026-10-25, B3.3: `#8B909C` → `#858A96` — eskisi qog'oz va hover fonida 2,9 edi, endi hamma fonda ≥ 3,08).
  Kontrastlar `apps/web/src/styles/tokens.test.ts` da avtomatik tekshiriladi.
  Qorong'i: matn 15,1; ikkinchi 8,9; muted 5,5; havola 6,9; foyda 7,2; zarar 7,1; input chegarasi 3,6.

Palitra o'zgartirilsa — validator qayta ishlatiladi (`validate_palette.js`, ikkala rejim).

## 5. Komponentlar

Hammasi `apps/web/src/components/ui` da, tokenlar bilan, holatlari bilan (default, hover, focus, disabled,
loading, error). `/ui-kit` ichki sahifasida hammasi ko'rinadi (yorug'/qorong'i, desktop/mobil skrinshotlari bilan).

| Komponent | Muhim qoidalar |
|---|---|
| Button | primary (aksent), secondary (hairline chegara), ghost, destructive; 32/36/40 px; yuklanishda matn saqlanadi + spinner |
| Input, NumberInput, **MoneyInput** | yorliq tepada, yordam matni pastda; pul o'ngga tekislanadi, valyuta qo'shimchasi; "1 234,5", "1234.5", "1 234 567" qabul qilinadi |
| Select, **Combobox** | qidiruvda apostrof turlari va lotin/kirill farqi yo'q (§8.3); SKU qidiruvida rasm kichik ko'rinishi |
| **DateRangePicker** | tayyor davrlar (Bugun, Kecha, 7/30 kun, Shu oy, O'tgan oy, Shu yil, Hammasi) + kalendar; tanlov URL'da |
| CompareToggle | "oldingi davr" / "o'tgan yil" |
| **KPI** | yorliq, qiymat (proportsional raqam), o'zgarish (ishora, nom bilan davr, rang = yo'nalish × yaxshimi), 12 nuqtali sparkline |
| **LedgerTable** (Hisob varag'i) | operator ustuni (−, =), summa tabular, oraliq summa ustida `rule`, yakun ostida `rule-double`; qator bosilsa drill-down drawer |
| **DataTable** | sarlavha 12/500, qator 13 px, balandlik 36 (zich 32, keng 44); raqamlar o'ngga, tabular, **hech qachon qatorga bo'linmaydi**; birinchi ustun skrollda qotadi; jami qatori `rule` bilan; ustun tanlash; saqlangan ko'rinish; eksport; 500+ qatorda virtual |
| **FormulaPopover** | har ko'rsatkich yonidagi "?": formula (F-raqam bilan), qaysi ma'lumotdan, "taxminiy" sababi |
| Badge / StatusPill | holat ikon + matn bilan (rang yolg'iz emas) |
| Drawer, Dialog, Popover, Tooltip | Esc bilan yopiladi, fokus ichida qoladi |
| Toast | amal nomi bilan: "Xaridni saqlash" → "Xarid saqlandi" |
| **Stepper**, **Timeline** | onboarding, Partiya yo'li |
| EmptyState | nima bo'lishi kerak + bitta harakat tugmasi |
| Skeleton | sahifa shaklida, 300 ms dan uzoq yuklanishda |
| Banner | sinxron xatosi, Uzum uzilishi, sinov tugashi, tannarx qamrovi |
| ProgressBar | tarix yuklanishi (do'kon × ma'lumot turi) |
| SyncIndicator | "Yangilandi: 3 daqiqa oldin" + holat nuqtasi |
| Sidebar, TopBar, MobileTabBar, **CommandPalette** (Ctrl+K) | SKU, xarid, sahifaga tez o'tish |
| ProductThumb | Uzum rasmi, lazy, yo'q bo'lsa harf-belgi |
| FileDrop | Excel import, shablon yuklab olish havolasi bilan |
| Charts | Line+Bar (bitta o'q), Waterfall, Heatmap (hafta kuni × soat), CalendarHeatmap, StackedBar, Sparkline; har birida tooltip va "Jadval" ko'rinishi |

### 5.1 Grafik qoidalari

- **Bitta o'q.** Ikki o'qli grafik yo'q. Turli o'lchovlar (so'm va dona) — ikki alohida grafik.
- Ustun ≤ 24 px, uchi 4 px yumaloq, asosi to'g'ri; chiziq 2 px; marker ≥ 8 px, 2 px fon halqasi bilan;
  qo'shni ustunlar orasida 2 px fon oralig'i; to'r chiziqlari hairline, yaxlit (punktir emas).
- ≥ 2 seriya — legenda doim; ≤ 4 seriya — qo'shimcha to'g'ridan-to'g'ri yorliq (faqat oxirgi nuqta yoki ekstremum).
- Hover: chiziqda crosshair + tooltip (hamma seriyalar qiymati), ustunda shu ustun tooltip'i.
- O'q raqamlari ixcham: 0 / 500 ming / 1 mln / 1,5 mln.
- Annotatsiya: Uzum bepul logistika davrlari — soya; sinxron uzilgan kunlar — shtrix.
- Pirog/donut ishlatilmaydi — ulushlar uchun yotiq ustunlar.

## 6. Xos komponentlar

### 6.1 Hisob varag'i

```
Sof foyda, oktabr                         ▲ 12,4% o'tgan oyga nisbatan
48 357 200 soʻm
──────────────────────────────────────────────────────
  Tushum                               186 420 000
− Uzum komissiyasi                      −37 284 000
− Logistika                              −9 135 750
──────────────────────────────────────────────────────
= Uzum toʻlovi                          140 000 250
− Tannarx (partiyalar)                  −78 112 050
− Reklama, saqlash, jarima              −11 631 000
− Oʻz xarajatlarim                               0
− Soliq (1%)                             −1 864 200
══════════════════════════════════════════════════════
= Sof foyda                              48 357 200
  Tannarxsiz 12 ta sotuv (1 240 000 soʻm) hisobga kirmadi   [Tannarx kiritish]
```
Har qator bosiladi → o'ng tomondan drawer: shu summani tashkil qilgan yozuvlar + "?" formula.

### 6.2 Partiya yo'li

```
Buyurtma ─● To'landi ─● Xitoy ombori ─● Yo'lda ─◐ Toshkent ─○ Qabul ─○ Uzum ─○
 02.10        03.10        09.10         12.10 (11 kun)  kutilmoqda ~28.10
```
To'ldirilgan nuqta — bajarilgan bosqich (sanasi bilan), yarim — joriy, bo'sh — kelajak; joriy bosqichda necha kun
o'tgani va kutilgan sana (F25). Mobilda vertikal. Kechikish bo'lsa joriy nuqta yonida ogohlantirish ikonasi va matni.

## 7. Sahifa maketlari

### 7.1 Umumiy karkas

```
┌──────────┬───────────────────────────────────────────────────────────────┐
│ Logo     │ [Do'kon: Hammasi ▾] [Oktabr ▾] [Solishtirish]   ● 3 daq oldin 🔔 👤│
│          ├───────────────────────────────────────────────────────────────┤
│ Asosiy   │                                                               │
│ Foyda    │                     sahifa kontenti                           │
│ Mahsulot │                                                               │
│ Buyurtma │                                                               │
│ Xarajat  │                                                               │
│ Xaridlar │                                                               │
│ Ombor    │                                                               │
│ Pul      │                                                               │
│ Hisobot  │                                                               │
│ ──────── │                                                               │
│ Sozlama  │                                                               │
└──────────┴───────────────────────────────────────────────────────────────┘
```
Sidebar 232 px (yig'ilganda 64 px). Mobil: yuqorida ixcham panel (do'kon, davr), pastda tab bar:
Asosiy · Foyda · Ombor · Xaridlar · Yana.

### 7.2 Bosh sahifa (desktop)

```
┌──────────────────────────────┬───────────────────────────────────────────┐
│ HISOB VARAG'I (§6.1)         │ Bugun | Kecha | Shu oy | Oy prognozi | O'tgan│
│ hero: Sof foyda              │───────────────────────────────────────────│
│ qatorlar ...                 │ Kunlik tushum (ustun) + sof foyda (chiziq) │
│ ════════                     │                                           │
├──────────────────────────────┴───────────────────────────────────────────┤
│ Diqqat talab qiladi (ro'yxat, ustuvorlik bo'yicha)                        │
├────────────────────────────────────┬─────────────────────────────────────┤
│ Eng foydali 5                      │ Zarar qilayotgan 5                  │
├────────────────────────────────────┴─────────────────────────────────────┤
│ Marja · ROI · Bekor % · Qaytish % · DRR · Muzlagan pul · Yo'ldagi tovar   │
└──────────────────────────────────────────────────────────────────────────┘
```
(Oxirgi qatordagi ko'rsatkichlar alohida KPI elementlari, nuqta bilan ulangan matn emas.)

### 7.3 Bosh sahifa (mobil, 390 px)

```
Sof foyda, oktabr
48 357 200 soʻm      ▲12,4%
[Hisob varag'i — yig'ilgan, 3 qator + "Hammasi"]
[Bugun | Kecha | Oy prognozi] (gorizontal skroll)
[Kunlik grafik]
[Diqqat talab qiladi]
[Eng foydali / Zarar — tab]
```

### 7.4 Boshqa sahifalar (qisqa)

- **Foyda va zarar:** yuqorida hisob varag'i to'liq; ostida sharshara; keyin oylar bo'yicha jadval (ustun = oy).
- **Mahsulotlar:** filtrlar qatori → DataTable; mobilda ro'yxat (rasm, nom, foyda/dona, zaxira kunlari) + bosilsa SKU sahifasi.
- **SKU sahifasi:** sarlavha (rasm, nom, holat) → KPI qatori → unit kalkulyator (o'ngda) + grafiklar (chapda) →
  lotlar vaqt chizig'i → qaytishlar.
- **Xaridlar:** ro'yxat (Partiya yo'li ixcham ko'rinishda) → xarid sahifasi: Partiya yo'li, qatorlar jadvali,
  xarajat komponentlari, birlik tannarx tarkibi (o'ngda doim ko'rinadi).
- **Ombor:** holat bo'yicha guruhlar (Kritik → Yaxshi), har qatorda joylar bo'yicha qoldiq; tepada muzlagan pul
  va yo'ldagi tovar.
- **Pul oqimi:** 90 kunlik prognoz grafigi (bitta o'q, so'm) + to'lov kalendari ro'yxati.
- **Onboarding:** markazda bitta ustun, chapda qadamlar ro'yxati (desktop) / tepada progress (mobil).

## 8. Matn, til va formatlash

### 8.1 Ovoz

"Siz" bilan, qisqa, aniq, ishbilarmon. Fe'l bilan tugmalar: "Xaridni saqlash", "Tannarx kiritish".
Xato: nima bo'ldi + nima qilish kerak ("Uzum kalitni rad etdi. Kabinetda yangi kalit yarating va shu yerga qo'ying.").
Bo'sh holat: harakatga taklif. Kechirim so'ralmaydi, noaniq gap yo'q.

### 8.2 Atamalar lug'ati (hamma joyda bir xil)

Tushum · Uzum komissiyasi · Logistika · Uzum to'lovi · Tannarx · Yalpi foyda · Uzum xarajatlari ·
O'z xarajatlarim · Soliq · Sof foyda · Marja · ROI · Reklama ulushi (DRR) · Kutilayotgan foyda ·
Yakunlangan / Jarayonda / Bekor qilingan / Qaytarilgan · Xarid (partiya) · Kargo · Yo'lda · Qoldiq ·
Zaxira kunlari · Muzlagan pul · Postavka · Kamomad · Jarima · Kompensatsiya · Taxminiy.
(Rus tilida mos ravishda: Выручка, Комиссия Uzum, Логистика, Выплата Uzum, Себестоимость, ...; lug'at
`lib/i18n/glossary` faylida.)

### 8.3 O'zbek yozuvi

- UI matnlarida: **oʻ, gʻ — U+02BB (ʻ)**, tutuq belgisi — **U+02BC (ʼ)**. Oddiy `'` ishlatilmaydi.
- Qidiruv va solishtirishda normallashtirish: `' ‘ ’ ʻ ʼ ``` → bitta belgi; kichik harf; kirill ↔ lotin
  transliteratsiya (Ўў→Oʻoʻ, Ққ→Qq, Ғғ→Gʻgʻ, Ҳҳ→Hh, Шш→Sh, Чч→Ch, Ёё→Yo, Юю→Yu, Яя→Ya, Ъ→ʼ ...).
- uz-Cyrl tarjima uz-Latn'dan avtomatik transliteratsiya + qo'lda tuzatishlar lug'ati (testlar bilan).

### 8.4 Formatlash (faqat `lib/format`)

| Tur | uz | ru |
|---|---|---|
| Butun son | `1 234 567` (guruh ajratgich U+00A0, satrga bo'linmaydi) | `1 234 567` |
| Kasr | `1 234,5` (vergul) | `1 234,5` |
| Manfiy | `−312 400` (U+2212) | `−312 400` |
| Pul | `48 357 200 soʻm`; jadvalda valyutasiz | `48 357 200 сум` |
| Valyuta | `142,50 $`, `1 000 ¥` (CNY) | `142,50 $`, `1 000 ¥` |
| Ixcham | `850 ming`, `1,2 mln`, `3,4 mlrd` | `850 тыс.`, `1,2 млн`, `3,4 млрд` |
| Foiz | `12,5%`; o'zgarish `▲ 12,4%` / `▼ 3,1%` | xuddi shunday |
| Sana | `23.10.2026`; matnda `23-oktabr` | `23.10.2026`; `23 октября` |
| Davr | `1–31-oktabr` | `1–31 октября` |
| Nisbiy vaqt | `3 daqiqa oldin` | `3 минуты назад` |

Oy nomlari (uz): yanvar, fevral, mart, aprel, may, iyun, iyul, avgust, sentabr, oktabr, noyabr, dekabr.
Hafta kunlari (qisqa): Du, Se, Ch, Pa, Ju, Sh, Ya.

## 9. Harakat (motion)

- Faqat foydalanuvchi amaliga javob: drawer ochilishi (200 ms), qator yoyilishi (150 ms), saqlash tasdig'i.
- Bitta rejalashtirilgan lahza: onboarding'da tarix yuklanib bo'lgach hisob varag'i qatorlari bir marta ketma-ket
  to'ladi.
- Sinxrondan keyin o'zgargan raqam fonida 600 ms yengil ta'kid.
- `prefers-reduced-motion` da hammasi o'chadi.

## 10. Ikon va rasmlar

Lucide (1,5 px chiziq, 16/20 px). Mahsulot rasmlari Uzum CDN'dan, lazy. Illyustratsiya o'rniga bo'sh holatlarda
yengil "daftar katagi" foni (faqat onboarding va bo'sh holatlarda).

## 11. Kirish imkoniyati (WCAG 2.2 AA)

Kontrast §4.4 bo'yicha tekshirilgan; fokus halqasi 2 px aksent + 2 px oraliq; hamma narsa klaviatura bilan;
mobil bosish maydoni ≥ 44 px; har grafikda jadval ko'rinishi va `aria` tavsifi; holat hech qachon faqat rang bilan
emas (ikon + matn, +/− ishorasi); `lang` atributi tilga mos; axe-core testi CI'da.

## 12. Brend (Q1 qaroridan keyin)

- Nom: Temur tanlaydi (07-qarorlar.md Q1). "Uzum" so'zi nomda ishlatilmaydi (tovar belgisi xavfi).
- Logo yo'nalishi: so'z belgisi (Inter Display 600) + belgi: **o'sib boruvchi shtrix-kod chiziqlari**
  (sotuvchining kundalik ishi + o'sish), ko'k siyoh rangida. Binafsha va uzum motivlari yo'q.
- Favicon: 3 ta chiziqli soddalashtirilgan belgi. OG rasm: hisob varag'i parchasi.
