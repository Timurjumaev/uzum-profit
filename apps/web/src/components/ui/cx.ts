/** Sinf nomlarini birlashtirish (yolg'on qiymatlar tashlanadi). */
export function cx(...names: Array<string | false | null | undefined>): string {
  return names.filter(Boolean).join(" ");
}
