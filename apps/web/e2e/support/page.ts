import type { Page } from "@playwright/test";

/** Sahifa ochiladi va shrift, tarmoq tinchigunicha kutiladi (skrinshot va axe barqaror bo'lsin). */
export async function open(page: Page, path: string): Promise<void> {
  await page.goto(path);
  await page.waitForLoadState("networkidle");
  await page.evaluate(() => document.fonts.ready);
}

export const isMobile = (project: string) => project === "mobile";
