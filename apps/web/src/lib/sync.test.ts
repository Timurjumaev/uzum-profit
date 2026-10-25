import { describe, expect, it } from "vitest";

import { syncStatus } from "../test/api";
import { lastSync, STALE_AFTER_MS, syncSummary } from "./sync";

const NOW = new Date("2026-10-25T12:00:00Z");
const ago = (ms: number) => new Date(NOW.getTime() - ms).toISOString();

describe("lastSync", () => {
  it("eng yangi muvaffaqiyatli sinxron; null'lar hisobga olinmaydi", () => {
    const status = syncStatus({ freshness: { orders: ago(10 * 60_000), expenses: ago(5 * 60_000), returns: null } });
    expect(lastSync(status)).toBe(ago(5 * 60_000));
  });

  it("birorta ham yo'q — null", () => {
    expect(lastSync(syncStatus({ freshness: { orders: null } }))).toBeNull();
    expect(lastSync(syncStatus({ freshness: {} }))).toBeNull();
  });
});

describe("syncSummary (tamoyil 8: 'ma'lumot yo'q' ≠ 'sinxron ishlamayapti')", () => {
  const fresh = { orders: ago(3 * 60_000) };

  it("yangi — yashil", () => {
    expect(syncSummary(syncStatus({ freshness: fresh }), NOW)).toEqual({ state: "fresh", tone: "positive", at: fresh.orders });
  });

  it("bir soatdan eski — sariq (aniq chegara: soat o'zi hali yangi)", () => {
    expect(syncSummary(syncStatus({ freshness: { orders: ago(STALE_AFTER_MS) } }), NOW).state).toBe("fresh");
    expect(syncSummary(syncStatus({ freshness: { orders: ago(STALE_AFTER_MS + 1000) } }), NOW)).toMatchObject({ state: "stale", tone: "warning" });
  });

  it("hech qachon sinxron bo'lmagan — neytral", () => {
    expect(syncSummary(syncStatus({ freshness: {} }), NOW)).toEqual({ state: "never", tone: "neutral", at: null });
  });

  it("xato bor — sariq; uzilish — qizil va boshqalardan ustun", () => {
    expect(syncSummary(syncStatus({ healthy: false, freshness: fresh }), NOW)).toMatchObject({ state: "errors", tone: "warning" });
    const outage = { active: true, since: ago(60_000), paused_until: null, recovered_from: null, recovered_at: null };
    expect(syncSummary(syncStatus({ healthy: false, outage, freshness: {} }), NOW)).toMatchObject({ state: "outage", tone: "negative" });
  });
});
