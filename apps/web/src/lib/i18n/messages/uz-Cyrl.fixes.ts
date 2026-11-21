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
  "onboarding.history.next": "Таннархни ҳозироқ Excel орқали киритишингиз мумкин; солиқ созламалари — Созламалар саҳифасида.",
  "opening.excel.title": "Таннархни Excel орқали киритиш",
  "opening.excel.file": "Excel файл",
  "dispatch.noBarcode": "Штрих-коди йўқ {{count}} та SKU Excelʼга кирмайди",
  "dispatch.save": "Excel юклаб олиш ({{count}} дона)",
  "dispatch.excel": "Excel",
  "dispatch.emptyText": "Excel юклаб олинганда жўнатма шу ерда кўринади.",
  "dispatch.lead":
    "Дўконни танланг — Омборимдаги унинг ҳамма SKUʼлари тўлиқ сони билан чиқади. Сонни камайтириш ёки қаторни олиб ташлаш мумкин. Excel Uzum кабинети шаблонида; юклаб олингач доналар \"Жўнатилмоқда\" бўлади, поставка кабинетда яратилгач ўзи боғланади.",
  // To'liq eksport (B7.5): fayl turlari va Telegram chat id lotinda qoladi → kirillda yozilmaydi.
  "settings.fullExport.title": "Тўлиқ экспорт (архив)",
  "settings.fullExport.lead":
    "Маълумот — сизники. Киритган ҳамма нарсангиз (харидлар, харажатлар, таннарх, омбор ҳаракатлари, созламалар) ва Уздан олинган фактлар (сотувлар, харажатлар, маҳсулотлар, поставкалар, қайтаришлар) — жадвал ва матн кўринишида битта архив файлда. Файл тайёр бўлганда билдиришнома келади; ҳавола бир марта ишлайди ва 24 соат амал қилади.",
  "settings.fullExport.excluded": "Узум калити, сеанслар, Телеграм чат рақами ва бошқа аъзоларнинг телефонлари файлга кирмайди. Кунига бир марта.",
  // Sayt manzili lotinda qoladi.
  "onboarding.key.howto.1": "seller.uzum.uz кабинетига киринг.",
};
