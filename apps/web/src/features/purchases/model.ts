// Xaridlar (M9) sahifasi uchun sof yordamchilar: bosqichlar tartibi va guruhlari, Partiya yo'li → Timeline, taxminiy
// belgilar (F22). Hisob yo'q — birlik tannarx, kurs va kutilgan sana API'dan (tamoyil 4).
import type { Stage } from "../../components/ui";
import type { PurchaseGroup } from "../../app/search";
import type { AllocationBase, ComponentKind, PurchaseStage, StageMark } from "../../lib/api/types";

/** Sanasi bor bosqichlar tartib bilan (qoralamadan keyin). */
export const DATED_STAGES: PurchaseStage[] = ["ordered", "paid", "cn_warehouse", "shipped", "arrived", "received", "sent_to_uzum", "closed"];

/** Ro'yxat guruhlari → API `stage` filtri. */
export const GROUP_STAGES: Record<PurchaseGroup, PurchaseStage[]> = {
  active: ["ordered", "paid", "cn_warehouse", "shipped", "arrived", "received", "sent_to_uzum"],
  draft: ["draft"],
  transit: ["cn_warehouse", "shipped", "arrived"],
  closed: ["closed"],
};

export const COMPONENT_KINDS: ComponentKind[] = ["goods", "cn_delivery", "agent_fee", "cargo", "customs", "packaging", "labeling", "uzum_delivery", "other"];
export const ALLOCATIONS: AllocationBase[] = ["units", "weight", "volume", "value", "manual"];
export const CURRENCIES = ["CNY", "USD", "UZS", "EUR", "RUB"] as const;
export type CurrencyCode = (typeof CURRENCIES)[number];

/** Taxminiy (F22): kargo kiritilmagan, qabul qilinmagan (buyurtma donasi bilan), vazn/hajm yo'q — dona bo'yicha. */
export const ESTIMATE_FLAGS = ["cargo_missing", "not_received", "base_fallback"] as const;

export function isEstimated(flags: readonly string[]): boolean {
  return flags.some((f) => (ESTIMATE_FLAGS as readonly string[]).includes(f));
}

/** Ko'rsatiladigan belgilar tartib bilan (kurs CBU — ma'lumot uchun, oxirida). */
export function visibleFlags(flags: readonly string[]): string[] {
  const order = [...ESTIMATE_FLAGS, "cbu_rate"];
  return order.filter((f) => flags.includes(f));
}

/** Keyingi belgilanadigan bosqich: joriydan keyingi birinchisi (yopilgan — yo'q). */
export function nextStage(current: PurchaseStage): PurchaseStage | null {
  if (current === "draft") return "ordered";
  const i = DATED_STAGES.indexOf(current);
  return DATED_STAGES[i + 1] ?? null;
}

/** API Partiya yo'li → `Timeline` (sana faqat bajarilgan va joriy bosqichda). */
export function timelineStages(marks: StageMark[], label: (stage: PurchaseStage) => string): Stage[] {
  return marks.map((m) => ({
    label: label(m.stage),
    state: m.state === "done" ? "done" : m.state === "current" ? "current" : "upcoming",
    date: m.on ?? undefined,
    days: m.state === "current" ? (m.days ?? undefined) : undefined,
    expected: m.expected ?? undefined,
    delayed: m.delayed,
  }));
}

/** Bosqich sanalari shaklidan API'ga: faqat o'zgarganlari (bo'sh — `null`, sanani o'chirish). */
export function changedDates(before: Partial<Record<PurchaseStage, string | null>>, draft: Partial<Record<PurchaseStage, string>>) {
  const out: Partial<Record<PurchaseStage, string | null>> = {};
  for (const s of DATED_STAGES) {
    const next = draft[s] ? draft[s]! : null;
    if ((before[s] ?? null) !== next) out[s] = next;
  }
  return out;
}

/** Sanalar tartibi (keyingi bosqich oldingisidan oldin emas) — API ham tekshiradi; shaklda oldindan aytish uchun. */
export function datesInOrder(dates: Partial<Record<PurchaseStage, string | null | undefined>>): boolean {
  let last = "";
  for (const s of DATED_STAGES) {
    const d = dates[s];
    if (!d) continue;
    if (d < last) return false;
    last = d;
  }
  return true;
}
