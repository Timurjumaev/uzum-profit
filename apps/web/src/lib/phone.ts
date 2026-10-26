// Telefon raqami (M1: kirish telefon + kod bilan). Foydalanuvchi turlicha yozadi: "+998 90 123 45 67", "90 123-45-67",
// "998901234567", "(90) 1234567". API ga yagona ko'rinish yuboriladi: `+998XXXXXXXXX` (E.164, O'zbekiston).

const UZ = "998";

/** `+998901234567` yoki `null` (O'zbekiston raqami emas / to'liq emas). Faqat yozilgan raqamlar hisobga olinadi. */
export function normalizePhone(input: string): string | null {
  const digits = input.replace(/\D/g, "");
  const national = digits.startsWith(UZ) && digits.length === 12 ? digits.slice(3) : digits.length === 9 ? digits : null;
  return national && /^\d{9}$/.test(national) ? `+${UZ}${national}` : null;
}

/** Ko'rinish uchun: `+998 90 123 45 67`; noto'g'ri bo'lsa — kiritilgan matn o'zgarishsiz. */
export function formatPhone(phone: string): string {
  const normalized = normalizePhone(phone);
  if (!normalized) return phone;
  const n = normalized.slice(4);
  return `+${UZ} ${n.slice(0, 2)} ${n.slice(2, 5)} ${n.slice(5, 7)} ${n.slice(7)}`;
}
