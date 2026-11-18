// Raqam "sanab chiqish" animatsiyasi (D1, ADR-070): qiymat 0 dan oxirgisigacha ~0,9 s da o'sadi. Faqat bezak: oxirida
// aynan API qiymati ko'rsatiladi; `prefers-reduced-motion`, jsdom va qiymat o'zgarmaganda — animatsiyasiz.
import { useEffect, useRef, useState } from "react";

const DURATION = 900;

function reduced(): boolean {
  return globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? true;
}

/** `value` (Decimal matn) uchun ko'rsatiladigan oraliq qiymat (matn); oxirida `value` ning o'zi. */
export function useCountUp(value: string): string {
  const [shown, setShown] = useState(value);
  const first = useRef(true);
  useEffect(() => {
    const target = Number(value);
    if (!first.current || reduced() || !Number.isFinite(target) || target === 0 || typeof requestAnimationFrame !== "function") {
      first.current = false;
      setShown(value);
      return;
    }
    first.current = false;
    let frame = 0;
    const start = performance.now();
    const tick = (now: number) => {
      const p = Math.min((now - start) / DURATION, 1);
      const eased = 1 - (1 - p) ** 3;
      setShown(p >= 1 ? value : String(Math.round(target * eased)));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    setShown("0");
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [value]);
  return shown;
}
