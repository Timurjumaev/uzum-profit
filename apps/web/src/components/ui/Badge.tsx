// Holat belgisi (04 §5, §11): holat hech qachon faqat rang bilan emas — ikon + matn.
import { Circle, CircleAlert, CircleCheck, Info, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cx } from "./cx";

export type Tone = "neutral" | "positive" | "negative" | "warning" | "info";

export const TONE_ICON: Record<Tone, LucideIcon> = {
  neutral: Circle,
  positive: CircleCheck,
  negative: CircleAlert,
  warning: TriangleAlert,
  info: Info,
};

export function StatusPill({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  const Icon = TONE_ICON[tone];
  return (
    <span className={cx("ui-pill", `ui-tone--${tone}`)}>
      <Icon size={14} aria-hidden />
      {children}
    </span>
  );
}

/** Kichik yorliq (soni, "Taxminiy" va h.k.) — matnli, ikon ixtiyoriy. */
export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={cx("ui-badge", `ui-tone--${tone}`)}>{children}</span>;
}
