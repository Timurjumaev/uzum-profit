// uz-Cyrl: avtomatik transliteratsiya (uz-Latn → kirill) qoidaga tushmagan joylari uchun qo'lda tuzatishlar —
// kalit yo'li → to'liq matn. So'z darajasidagi istisnolar (sentabr → сентябр) — `translit.ts` `WORDS` da.
export const uzCyrlFixes: Record<string, string> = {
  // Brend nomi har tilda lotinda (ADR-030).
  "app.name": "SellerMax",
  // Til nomi o'z yozuvida qoladi.
  "languages.uz-Latn": "Oʻzbekcha",
  "languages.ru": "Русский",
  // Sayt manzili lotinda qoladi.
  "onboarding.key.howto.1": "seller.uzum.uz кабинетига киринг.",
  // Fayl nomi (uzum.db) va kompyuter (Mac) lotinda qoladi (B4.9).
  "errors.codes.bad_legacy_file":
    "Файл эски дастур базаси эмас ёки бузилган. Эски дастур папкасидаги uzum.db файлини танланг.",
  "settings.legacy.lead":
    "Локал дастурдаги партиялар (uzum.db) харид бўлиб кўчирилади: қаторлар, товар суммаси, карго ва қўшимча чиқимлар курслари билан. Сотувлар Uzumʼдан қайта олинади. Аввал кўриб чиқилади — ҳеч нарса ёзилмайди.",
  "settings.legacy.hint":
    "Macʼда: эски дастур папкасидаги uzum.db файли. Қайта юклаш хавфсиз — кўчирилган партия қайта яратилмайди.",
};
