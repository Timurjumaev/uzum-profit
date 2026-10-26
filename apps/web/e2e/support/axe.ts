// axe-core haqiqiy brauzerda — jsdom'dan farqi: KONTRAST ham tekshiriladi (04 §4.4, §11). Jiddiy (serious/critical)
// xato bo'lmasligi shart.
import { createRequire } from "node:module";

import type { Page } from "@playwright/test";

const require = createRequire(import.meta.url);

type AxeResult = { violations: Array<{ id: string; impact: string | null; nodes: Array<{ target: unknown[]; failureSummary?: string }> }> };

export async function seriousViolations(page: Page): Promise<string[]> {
  await page.addScriptTag({ path: require.resolve("axe-core/axe.min.js") });
  const result = await page.evaluate(() => (globalThis as unknown as { axe: { run: (c: Document) => Promise<AxeResult> } }).axe.run(document));
  return result.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} — ${(n.failureSummary ?? "").split("\n").slice(1, 2).join("").trim()}`).join(" | ")}`);
}
