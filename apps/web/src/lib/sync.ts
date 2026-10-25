// Ma'lumot yangiligi (M3, tamoyil 8: "ma'lumot yo'q" ≠ "sinxron ishlamayapti"): holat — uzilish, xato, eskirgan yoki
// yangi; matn — oxirgi muvaffaqiyatli sinxron vaqti. Hamma sahifa shu bitta hisobdan foydalanadi.
import type { Tone } from "../components/ui";
import type { components } from "./api/schema";

export type SyncStatus = components["schemas"]["SyncStatusOut"];
export type SyncState = "outage" | "errors" | "never" | "stale" | "fresh";

/** Buyurtmalar 10–15 daqiqada yangilanadi (M3) — bir soatdan eski ma'lumot "eskirgan". */
export const STALE_AFTER_MS = 60 * 60_000;

/** Eng yangi muvaffaqiyatli sinxron (ISO) yoki `null` (hali birorta ham yo'q). */
export function lastSync(status: Pick<SyncStatus, "freshness">): string | null {
  const times = Object.values(status.freshness).filter((v): v is string => v !== null);
  return times.reduce<string | null>((latest, t) => (latest === null || Date.parse(t) > Date.parse(latest) ? t : latest), null);
}

export function syncSummary(status: SyncStatus, now: Date = new Date()): { state: SyncState; tone: Tone; at: string | null } {
  const at = lastSync(status);
  if (status.outage.active) return { state: "outage", tone: "negative", at };
  if (!status.healthy) return { state: "errors", tone: "warning", at };
  if (at === null) return { state: "never", tone: "neutral", at };
  if (now.getTime() - Date.parse(at) > STALE_AFTER_MS) return { state: "stale", tone: "warning", at };
  return { state: "fresh", tone: "positive", at };
}
