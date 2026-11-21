// "Sozlash: N/6" (B8.12): 6 ta qadam holati sof funksiyada — soliq "rejimsiz" hisoblanmaydi, tannarx faqat sotuv bor va
// tannarxsiz qator yo'q bo'lsa tayyor.
import { describe, expect, it } from "vitest";

import { settingsData } from "../../test/settings";
import { setupItems } from "./SetupProgress";

const base = { shops: 1, historyLoaded: true, uncosted: 0, lines: 10, telegram: true };
const done = (items: ReturnType<typeof setupItems>) => items.filter((i) => i.done).map((i) => i.id);

describe("setupItems", () => {
  it("hammasi tayyor", () => {
    expect(done(setupItems({ ...base, settings: settingsData() }))).toEqual(["shops", "history", "tax", "payout", "costs", "telegram"]);
  });

  it("soliq faqat 'rejimsiz' bo'lsa, to'lov jadvali yo'q va tannarxsiz qator bor — tugamagan", () => {
    const settings = settingsData({
      tax_profiles: [{ id: "a", valid_from: "2026-01-01", regime: "none", rate_pct: "0", base: "revenue", vat_pct: "0", profit_pct: "0", lines: [], taxpayer: null }],
      payout_schedules: [],
    });
    expect(done(setupItems({ ...base, settings, uncosted: 3 }))).toEqual(["shops", "history", "telegram"]);
  });

  it("sotuv yo'q — tannarx hali 'tayyor' emas; do'kon va tarix yo'q", () => {
    const items = setupItems({ shops: 0, historyLoaded: false, settings: settingsData(), uncosted: 0, lines: 0, telegram: false });
    expect(done(items)).toEqual(["tax", "payout"]);
  });
});
