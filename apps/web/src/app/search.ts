// URL qidiruv parametrlari: tekshiruvchilar (router) va iste'molchilar (komponentlar) bir joyda. MUHIM: TanStack
// Router bola marshrutga ota marshrutning xom qidiruvini ham beradi (`useSearch` tekshirilmagan qiymatni qaytarishi
// mumkin), shuning uchun xavfsizlik uchun muhim qiymat (qaytish manzili, taklif tokeni) ISHLATILGAN joyda ham shu
// funksiyalardan o'tkaziladi.

export type LoginSearch = { redirect?: string };

/** Kirishdan keyin qaytish manzili — faqat o'z saytimiz ichidagi yo'l (ochiq qayta yo'naltirish yo'q). */
export function loginSearch(search: Record<string, unknown>): LoginSearch {
  const target = search.redirect;
  return typeof target === "string" && /^\/(?![/\\])/.test(target) ? { redirect: target } : {};
}

export type InviteSearch = { token?: string };

/** Taklif havolasi tokeni: faqat harf, raqam, `_` va `-`. */
export function inviteSearch(search: Record<string, unknown>): InviteSearch {
  return typeof search.token === "string" && /^[\w-]{8,200}$/.test(search.token) ? { token: search.token } : {};
}

export const ONBOARDING_STEPS = ["org", "key", "shops", "history"] as const;
export type OnboardingStep = (typeof ONBOARDING_STEPS)[number];
export type OnboardingSearch = { step?: OnboardingStep };

export function onboardingSearch(search: Record<string, unknown>): OnboardingSearch {
  return (ONBOARDING_STEPS as readonly unknown[]).includes(search.step) ? { step: search.step as OnboardingStep } : {};
}
