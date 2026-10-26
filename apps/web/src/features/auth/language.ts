// Til va profil (M1, B3.2 qoldig'i): foydalanuvchining tili profilda (`user.language`) saqlanadi. Qoida:
// qo'lda tanlangan til (brauzerda) ustun — kirishda profilga yoziladi; hali tanlanmagan bo'lsa (yangi qurilma) profil
// tili qo'llanadi. Profilga yozish xatosi jim: til baribir shu qurilmada o'zgargan.
import type { i18n as I18n } from "i18next";

import { updateProfile } from "../../app/query";
import { currentLang, isLang, setLanguage, storedLang, type Lang } from "../../lib/i18n";

export async function syncProfileLanguage(instance: I18n, profile: string, { push }: { push: boolean }): Promise<void> {
  const stored = storedLang();
  if (stored) {
    if (push && stored !== profile) await updateProfile({ language: stored }).catch(() => undefined);
    return;
  }
  if (isLang(profile) && profile !== currentLang(instance)) await setLanguage(instance, profile);
}

/** Til almashtirish: shu qurilmada darhol, profilga — fonda. */
export async function changeLanguage(instance: I18n, lang: Lang): Promise<void> {
  await setLanguage(instance, lang);
  await updateProfile({ language: lang }).catch(() => undefined);
}
