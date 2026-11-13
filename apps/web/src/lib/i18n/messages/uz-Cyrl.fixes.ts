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
  "dispatch.noBarcode": "Штрих-коди йўқ {{count}} та SKU Excelʼга кирмайди",
  "dispatch.save": "Excel юклаб олиш ({{count}} дона)",
  "dispatch.excel": "Excel",
  "dispatch.emptyText": "Excel юклаб олинганда жўнатма шу ерда кўринади.",
  "dispatch.lead":
    "Дўконни танланг — Омборимдаги унинг ҳамма SKUʼлари тўлиқ сони билан чиқади. Сонни камайтириш ёки қаторни олиб ташлаш мумкин. Excel Uzum кабинети шаблонида; юклаб олингач доналар \"Жўнатилмоқда\" бўлади, поставка кабинетда яратилгач ўзи боғланади.",
  // Sayt manzili lotinda qoladi.
  "onboarding.key.howto.1": "seller.uzum.uz кабинетига киринг.",
};
