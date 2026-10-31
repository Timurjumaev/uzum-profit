// uz-Cyrl: avtomatik transliteratsiya (uz-Latn → kirill) qoidaga tushmagan joylari uchun qo'lda tuzatishlar —
// kalit yo'li → to'liq matn. So'z darajasidagi istisnolar (sentabr → сентябр) — `translit.ts` `WORDS` da.
export const uzCyrlFixes: Record<string, string> = {
  // Brend nomi har tilda lotinda (ADR-030).
  "app.name": "SellerMax",
  // Til nomi o'z yozuvida qoladi.
  "languages.uz-Latn": "Oʻzbekcha",
  "languages.ru": "Русский",
  // Dastur nomi lotinda qoladi.
  "help.pages.expenses.c": "Excel тугмаси жорий фильтр бўйича файл беради.",
  "ui.exportExcel": "Excel юклаб олиш",
  // Sayt manzili lotinda qoladi.
  "onboarding.key.howto.1": "seller.uzum.uz кабинетига киринг.",
};
