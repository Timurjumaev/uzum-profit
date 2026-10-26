// uz-Cyrl: avtomatik transliteratsiya (uz-Latn → kirill) qoidaga tushmagan joylari uchun qo'lda tuzatishlar —
// kalit yo'li → to'liq matn. So'z darajasidagi istisnolar (sentabr → сентябр) — `translit.ts` `WORDS` da.
export const uzCyrlFixes: Record<string, string> = {
  // Til nomi o'z yozuvida qoladi.
  "languages.uz-Latn": "Oʻzbekcha",
  "languages.ru": "Русский",
  // Sayt manzili lotinda qoladi.
  "onboarding.key.howto.1": "seller.uzum.uz кабинетига киринг.",
};
