# AGENTS.md — ijrochi (kod yozuvchi) uchun qoidalar

Bu fayl Claude'dan boshqa AI vositalari (Antigravity, Codex va h.k.) uchun. Claude sessiyalari `CLAUDE.md` bo'yicha
ishlaydi. Sen — **ijrochisan**: topshiriqni aniq bajarasan, rejani o'zgartirmaysan, o'zingdan qaror qilmaysan.

## 1. Har suhbat boshida

1. `git fetch`, so'ng `main` ning eng yangi holatidan yangi branch och (7-bo'lim).
2. O'qi: `docs/plan/README.md` (holat va 12 tamoyil) va `CLAUDE.md` dagi "Qat'iy qoidalar".
3. Topshirig'ing — `docs/tasks/<ID>.md`. Faqat shu fayldagi ishni qil.

## 2. Rol va chegaralar

- Faqat topshiriqda yozilgan ishni qil. Qo'shimcha funksiya, "yaxshilash", qayta tuzish, fayl ko'chirish — yo'q.
- Topshiriqdagi "Tegma" ro'yxatiga rioya qil. Topshiriq alohida ruxsat bermasa, **hech qachon** tegilmaydi:
  `packages/core/`, `apps/api/` (butunlay), `infra/`, `.github/`, `uv.lock`, `pnpm-lock.yaml`, `package.json`
  fayllari (yangi kutubxona qo'shma).
- Noaniq narsa bo'lsa yoki topshiriq reja bilan zid bo'lsa — to'xta va Temurga o'zbekcha savol ber.
  Taxmin bilan ishlama.
- Backend o'zgarishi kerak ekanini payqasang (yangi endpoint, maydon, formula) — to'xta va Temurga ayt;
  u buni Claude'ga yetkazadi.

## 3. Pul, formulalar, ma'lumot

- UI pul hisoblamaydi. Raqamlar serverdan keladi; formatlash faqat `lib/format` orqali (to'g'ridan
  `toLocaleString` yo'q).
- Yangi formula yoki biznes doimiysi (tarif, kod, soliq, sana) kodga yozilmaydi.
- `.env`, Uzum API kaliti, `*.db`, real ma'lumotni so'rama, o'qima, repoga qo'shma.

## 4. Matn va dizayn

- UI matni o'zbekcha (lotin). `oʻ`, `gʻ` uchun U+02BB (ʻ), tutuq belgisi uchun U+02BC (ʼ); UI matnida oddiy `'` yo'q.
- Yangi matn — i18n kaliti, `apps/web/src/lib/i18n/messages/` ichida `uz-Latn.ts` va `ru.ts` ga. `uz-Cyrl` avtomatik
  transliteratsiya qilinadi; `uz-Cyrl.fixes.ts` ga faqat kerak bo'lsa tegasan.
- Rang, shrift, oraliq — mavjud tokenlar (`var(--...)`) va `components/ui` komponentlari (`docs/plan/04-dizayn.md`).
  Yangi rang qiymati o'ylab topma.
- Yangi sahifa yoki forma qurishda eng yaqin mavjud sahifani namuna qil (masalan, `features/pnl/Waivers.tsx`).
- 360 px kenglikda gorizontal skroll bo'lmasin; holat faqat rang bilan emas (ikon va matn bilan).

## 5. Testlar

- Har yangi funksiya uchun test (Vitest + Testing Library), mavjud `*.test.tsx` uslubida.
- Mavjud testni o'chirma, `skip` qilma, kutilgan qiymatni "yashil bo'lsin" deb o'zgartirma. Test qizarsa —
  kodni to'g'rila. Testni o'zgartirish haqiqatan kerak bo'lsa, sababini PR tavsifida yoz.

## 6. Muhit (muhim)

Temurning Mac'ida `node`, `pnpm`, `uv`, `docker` yo'q va o'rnatilmaydi. Shuning uchun:

- Kodni lokalda ishga tushira olmaysan va o'rnatishga urinmaysan.
- Tekshiruvni GitHub CI qiladi (`.github/workflows/ci.yml`). Shuning uchun yozishdan oldin yaqin namunalarni
  diqqat bilan o'qi; import yo'llari, tip nomlari (`lib/api/types.ts`, `lib/api/schema.d.ts`), i18n kalitlarini
  tekshir. Yozib bo'lgach kodni o'zing qayta o'qib chiq.
- PR tavsifida "Lokalda ishga tushirilmadi, CI kutilmoqda" deb yoz va eng xavfli joylarni ayt.
- CI qizarsa Temur log'ni beradi; sen o'sha branch'da tuzatasan.

## 7. Git

- Branch: `exec/<topshiriq-id>-<qisqa-nom>` (masalan, `exec/b4-8a-bonuslar`), `main` ning yangi holatidan.
  Worktree rejimida ishlasang ham shu nom.
- Commit: Conventional Commits (`feat(web): ...`, `test(web): ...`, `docs: ...`), qisqa va aniq. Kichik commitlar.
- `git push -u origin <branch>`. `main` ga push qilma, merge qilma, force push yo'q.
- PR'ni Temur GitHub saytida ochadi. Sen oxirida `.github/pull_request_template.md` bo'yicha tayyor PR matnini
  (Nima va nega / Tekshiruv) javobda ber.
- Hujjatlar: topshiriqda aytilgan bo'lsa `docs/plan/05-bosqichlar.md`, `docs/plan/README.md` holat jadvali va
  `CHANGELOG.md` ni yangila.

## 8. Muloqot

O'zbekcha (lotin), qisqa, samimiy. Temur band: faqat u qila oladigan narsani so'ra. Oxirida: nima qilindi
(2–3 gap), o'zgargan fayllar, tekshirilmagan joylar, Temurdan kutilayotgan amal.

## 9. Claude bilan ish bo'linishi

Formulalar (`packages/core`), migratsiyalar, kirish va ruxsatlar, Uzum sinxroni, xavfsizlik va to'lov — Claude'ning
ishi. Sen yozgan kod ularni chaqiradi, o'zgartirmaydi. Claude har PR'ning xavfli qismini ko'rib chiqadi.
