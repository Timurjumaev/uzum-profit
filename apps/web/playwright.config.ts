// E2E va vizual testlar (03 §14): production build (`vite preview`) brauzerda, API — `e2e/support/api.ts` dagi soxta
// (marshrut darajasida), shuning uchun backend va baza kerak emas va natija deterministik. Haqiqiy backend bilan
// e2e (staging) — B8. Ikki o'lcham: 1440 (desktop) va 390 px (mobil) — 04 §11; yorug'/qorong'i — testlarda.
import { defineConfig, devices } from "@playwright/test";

const PORT = 4173;

export default defineConfig({
  testDir: "e2e",
  // Skrinshot asoslari (baseline) repoda: `e2e/__screenshots__/<loyiha>/<fayl>/<nom>.png`.
  snapshotPathTemplate: "{testDir}/__screenshots__/{projectName}/{testFilePath}/{arg}{ext}",
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [["list"], ["html", { open: "never" }]] : "list",
  use: {
    baseURL: `http://localhost:${PORT}`,
    locale: "uz-UZ",
    timezoneId: "Asia/Tashkent",
    reducedMotion: "reduce", // animatsiyasiz: grafiklar va o'tishlar skrinshotda barqaror
    trace: "retain-on-failure",
    // Mashinalar orasida bir xil matn shakllanishi: hinting va LCD antialiasing o'chiq (aks holda runner va lokal
    // skrinshotlar matnda 2–4% farq qiladi). Asoslarni (baseline) ham shu rejimda olish shart.
    launchOptions: { args: ["--font-render-hinting=none", "--disable-lcd-text", "--disable-font-subpixel-positioning"] },
  },
  expect: {
    // Shrift antialiasing farqlari uchun kichik bag'ishlash; haqiqiy o'zgarish (rang, joylashuv) undan katta.
    toHaveScreenshot: { maxDiffPixelRatio: 0.01, animations: "disabled" },
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    { name: "mobile", use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true } },
  ],
  webServer: {
    command: `pnpm exec vite preview --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
