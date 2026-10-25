// Tezlik byudjeti (03 §9): boshlang'ich JS (index.html dagi kirish skripti va uning modulepreload'lari) ≤ 250 KB gzip.
// `pnpm build` dan keyin: `pnpm size`. Marshrut bo'laklari (lazy) bu hisobga kirmaydi.
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { gzipSync } from "node:zlib";

const LIMIT_KB = Number(process.env.WEB_INITIAL_JS_KB ?? 250);
const dist = join(import.meta.dirname, "..", "dist");
const html = readFileSync(join(dist, "index.html"), "utf8");
const files = [
  ...html.matchAll(/<script[^>]+src="\/([^"]+\.js)"/g),
  ...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\/([^"]+\.js)"/g),
].map((m) => m[1]);
if (files.length === 0) {
  console.error("index.html da kirish skripti topilmadi");
  process.exit(1);
}
const kb = files.reduce((sum, f) => sum + gzipSync(readFileSync(join(dist, f))).length, 0) / 1024;
console.log(`Boshlang'ich JS: ${kb.toFixed(1)} KB gzip (chegara ${LIMIT_KB} KB): ${files.join(", ")}`);
if (kb > LIMIT_KB) {
  console.error("Byudjet oshdi — og'ir kutubxonani lazy marshrutga ko'chiring (03 §9).");
  process.exit(1);
}
