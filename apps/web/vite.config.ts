import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Dev serverda /api va /health so'rovlari backend'ga uzatiladi (compose'da http://api:8000).
const apiTarget = process.env.API_PROXY_TARGET ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": apiTarget,
      "/health": apiTarget,
    },
  },
  test: {
    environment: "jsdom",
  },
});
