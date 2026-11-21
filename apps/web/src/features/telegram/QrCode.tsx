// QR kod (B6.6): qrcode-generator moduli → SVG yo'l (innerHTML yo'q). Skaner ishonchli o'qishi uchun har doim oq fonda qora —
// mavzuga bog'liq emas; atrofida 4 modullik jim zona.
import qrcode from "qrcode-generator";
import { useMemo } from "react";

const QUIET = 4;

export function QrCode({ text, label, size = 176 }: { text: string; label: string; size?: number }) {
  const { n, path } = useMemo(() => {
    const qr = qrcode(0, "M");
    qr.addData(text);
    qr.make();
    const count = qr.getModuleCount();
    let d = "";
    for (let r = 0; r < count; r++) for (let c = 0; c < count; c++) if (qr.isDark(r, c)) d += `M${c + QUIET},${r + QUIET}h1v1h-1z`;
    return { n: count, path: d };
  }, [text]);
  const side = n + QUIET * 2;
  return (
    <svg className="qr" role="img" aria-label={label} width={size} height={size} viewBox={`0 0 ${side} ${side}`} shapeRendering="crispEdges">
      <rect width={side} height={side} fill="#fff" />
      <path d={path} fill="#0E121A" />
    </svg>
  );
}
