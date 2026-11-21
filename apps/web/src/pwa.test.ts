// O'rnatiladigan ilova (B6.3): manifest to'liq (nom, start_url, standalone, ranglar, ikonkalar), ko'rsatilgan fayllar bor,
// ikonkalar haqiqiy PNG (o'lchami to'g'ri) va index.html ularga havola beradi. Service worker yo'q.
import { existsSync, readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const root = resolve(__dirname, "..");
const manifest = JSON.parse(readFileSync(resolve(root, "public/manifest.webmanifest"), "utf8")) as {
  name: string;
  short_name: string;
  start_url: string;
  display: string;
  theme_color: string;
  background_color: string;
  icons: { src: string; sizes: string; type: string; purpose: string }[];
};

function pngSize(file: string): [number, number] {
  const b = readFileSync(file);
  expect(b.subarray(1, 4).toString()).toBe("PNG");
  return [b.readUInt32BE(16), b.readUInt32BE(20)];
}

describe("PWA", () => {
  it("manifest: o'rnatish uchun zarur maydonlar", () => {
    expect(manifest.short_name).toBe("SellerMax");
    expect(manifest.start_url).toBe("/");
    expect(manifest.display).toBe("standalone");
    expect(manifest.theme_color).toMatch(/^#[0-9A-Fa-f]{6}$/);
    expect(manifest.background_color).toMatch(/^#[0-9A-Fa-f]{6}$/);
    const purposes = manifest.icons.map((i) => `${i.sizes}:${i.purpose}`);
    expect(purposes).toEqual(expect.arrayContaining(["192x192:any", "512x512:any", "512x512:maskable"]));
  });

  it("ikonkalar fayli bor va PNG o'lchami e'lon qilinganiga teng", () => {
    for (const icon of manifest.icons) {
      const file = resolve(root, "public", icon.src.slice(1));
      expect(existsSync(file), icon.src).toBe(true);
      if (icon.type === "image/png") {
        const [w, h] = icon.sizes.split("x").map(Number);
        expect(pngSize(file), icon.src).toEqual([w, h]);
      }
    }
    expect(pngSize(resolve(root, "public/apple-touch-icon.png"))).toEqual([180, 180]);
  });

  it("index.html manifest, apple-touch-icon va favicon'ga havola beradi; service worker ro'yxatdan o'tmaydi", () => {
    const html = readFileSync(resolve(root, "index.html"), "utf8");
    expect(html).toContain('rel="manifest" href="/manifest.webmanifest"');
    expect(html).toContain('rel="apple-touch-icon" href="/apple-touch-icon.png"');
    expect(html).toContain('rel="icon" href="/favicon.svg"');
    const main = readFileSync(resolve(root, "src/main.tsx"), "utf8");
    expect(main).not.toContain("serviceWorker");
  });
});
