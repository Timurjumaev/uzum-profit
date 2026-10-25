// Mahsulot rasmi (04 §5, §10): Uzum CDN'dan, lazy; yo'q yoki yuklanmasa — nomning birinchi harfi.
import { useState } from "react";

import { cx } from "./cx";

export function ProductThumb({ src, name, size = 40 }: { src?: string | null; name: string; size?: 32 | 40 | 64 }) {
  const [failed, setFailed] = useState(false);
  const letter = name.trim().charAt(0).toUpperCase() || "?";
  return (
    <span className={cx("ui-thumb", `ui-thumb--${size}`)}>
      {src && !failed ? (
        <img src={src} alt={name} loading="lazy" decoding="async" width={size} height={size} onError={() => setFailed(true)} />
      ) : (
        <span role="img" aria-label={name}>
          {letter}
        </span>
      )}
    </span>
  );
}
