// Grafik ma'lumotlari (04 §5.1). Pul va nisbatlar — satr (API: "123456.00"): tooltip, jadval va aria matni asl satrdan
// formatlanadi (aniq); songa aylantirish faqat chizish (joylashuv) uchun. Hisob-kitob (yig'indi, ulush) grafikda
// yo'q — tayyor qiymatlar API'dan keladi (tamoyil 4).
export type ColorKey = number | "ink" | "other"; // kategoriya slot 1–8 (04 §4.3 rollari), siyoh (natija chizig'i), "Boshqa"
export type Unit = "money" | "count";
export type XKind = "day" | "month" | "text";
export type Value = string | null;

export type SeriesInput = {
  key: string;
  name: string;
  color: ColorKey;
  /** LineBar: ustun yoki chiziq (standart — ustun). */
  kind?: "bar" | "line";
  /** LineBar: bir xil `stack` dagi ustunlar ustma-ust (masalan, Yakunlangan + Jarayonda tushum). */
  stack?: string;
  values: Value[];
};

/** Annotatsiya (04 §5.1): `shade` — davr belgisi (soya), `hatch` — sinxron uzilgan kunlar (shtrix). */
export type Band = { from: string; to: string; kind: "shade" | "hatch"; label: string };

export type LegendItem = { key: string; name: string; color: ColorKey | "gradient"; shape: "bar" | "line" | "shade" | "hatch" };

/** Jadval ko'rinishi: birinchi ustun — qator sarlavhasi, qolganlari raqam. */
export type TableSpec = { head: string[]; rows: string[][]; foot?: string[] };
