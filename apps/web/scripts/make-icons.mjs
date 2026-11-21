// PWA ikonkalari (B6.3): `public/icon.svg` dan PNG'lar. Bir marta ishga tushiriladi, natija repoga kiradi:
//   node scripts/make-icons.mjs
// Brend belgisi — Logo.tsx / favicon.svg bilan bir xil ustunlar, jonli gradient fonda (ADR-070).
import { writeFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const out = (name) => fileURLToPath(new URL(`../public/${name}`, import.meta.url));

// `pad` — belgi atrofidagi bo'sh joy ulushi: maskable ikonkada xavfsiz zona (ichki 80%) uchun kattaroq.
const svg = (size, { radius, pad }) => {
  const inner = size * (1 - pad * 2);
  const o = size * pad;
  const bar = (x, y, w, h) => `<rect x="${o + (x / 24) * inner}" y="${o + (y / 24) * inner}" width="${(w / 24) * inner}" height="${(h / 24) * inner}" rx="${(1 / 24) * inner}" fill="#fff"/>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
  <defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2A78D6"/><stop offset="0.55" stop-color="#7C5CFF"/><stop offset="1" stop-color="#FF8C42"/></linearGradient></defs>
  <rect width="${size}" height="${size}" rx="${radius}" fill="url(#g)"/>
  ${bar(3, 13, 4, 8)}${bar(10, 8, 4, 13)}${bar(17, 3, 4, 18)}
</svg>`;
};

const icons = [
  { file: "icon-192.png", size: 192, radius: 44, pad: 0.2 },
  { file: "icon-512.png", size: 512, radius: 118, pad: 0.2 },
  { file: "icon-maskable-512.png", size: 512, radius: 0, pad: 0.3 }, // to'liq fon: tizim o'zi kesadi
  { file: "apple-touch-icon.png", size: 180, radius: 0, pad: 0.22 }, // iOS o'zi yumaloqlaydi
];

const browser = await chromium.launch();
const page = await browser.newPage();
for (const { file, size, radius, pad } of icons) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(`<body style="margin:0;background:transparent">${svg(size, { radius, pad })}</body>`);
  writeFileSync(out(file), await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } }));
}
await browser.close();
writeFileSync(out("icon.svg"), svg(512, { radius: 118, pad: 0.2 }));
console.log("ok", icons.map((i) => i.file).join(", "));
