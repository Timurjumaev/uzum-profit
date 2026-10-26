// Qayta yuborish kutish vaqti: `since` (ms) dan `seconds` soniya; har soniyada yangilanadi, 0 da to'xtaydi.
import { useEffect, useState } from "react";

export function useCountdown(since: number, seconds: number): number {
  const left = () => Math.max(0, Math.ceil(seconds - (Date.now() - since) / 1000));
  const [value, setValue] = useState(left);
  useEffect(() => {
    // Yangi `since` — darhol qayta hisoblash (interval kutmasdan).
    const tick = () => setValue(left());
    const id = setInterval(tick, 1000);
    tick();
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [since, seconds]);
  return value;
}
