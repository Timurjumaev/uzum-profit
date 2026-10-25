import { describe, expect, it } from "vitest";
import type { ApiPaths, PnlRow, Statement } from "./types";

describe("API tiplari", () => {
  it("pul qiymatlari satr (03 §8)", () => {
    const row: PnlRow = {
      code: "revenue",
      amount: "1800000.00",
      share_of_revenue: "1.000000",
      previous: "400000.00",
      diff: "1400000.00",
    };
    const revenue: Statement["revenue"] = row.amount;
    expect(revenue).toBe("1800000.00");
  });

  it("o'qish API'lari yo'llari sxemada", () => {
    type Pnl = ApiPaths["/api/v1/orgs/{org_id}/pnl"]["get"];
    const params: Pnl["parameters"]["query"] = { start: "2026-10-01", end: "2026-10-20", view: "sku" };
    expect(params?.view).toBe("sku");
  });
});
