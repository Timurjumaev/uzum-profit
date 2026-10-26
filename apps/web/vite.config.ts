import react from "@vitejs/plugin-react";
import type { Plugin } from "vite";
import { defineConfig } from "vitest/config";

/** Asosiy shrift fayli (Inter, lotin) — `<link rel="preload">` (04 §2): matn zaxira shriftda sakramaydi. */
function preloadFont(): Plugin {
  return {
    name: "preload-inter",
    apply: "build",
    transformIndexHtml: {
      order: "post",
      handler(_html, ctx) {
        const file = Object.keys(ctx.bundle ?? {}).find((f) => /inter-latin-opsz-normal.*\.woff2$/.test(f));
        if (!file) throw new Error("Inter lotin shrifti build'da topilmadi");
        return [
          {
            tag: "link",
            attrs: { rel: "preload", href: `/${file}`, as: "font", type: "font/woff2", crossorigin: "" },
            injectTo: "head",
          },
        ];
      },
    },
  };
}

// Dev serverda /api va /health so'rovlari backend'ga uzatiladi (compose'da http://api:8000).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), preloadFont()],
  server: {
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
    exclude: ["e2e/**", "node_modules/**", "dist/**"], // e2e — Playwright (`pnpm e2e`), vitest emas
  },
});
