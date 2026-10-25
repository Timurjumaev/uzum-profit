// Dialog va Drawer (04 §5): modal, `aria-modal`, Esc va fon bosilsa yopiladi, fokus ichida qoladi.
// Drawer — o'ngdan (drill-down: summani tashkil qilgan yozuvlar), mobilda pastdan to'liq kenglikda.
import { X } from "lucide-react";
import { useId, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { cx } from "./cx";
import { useFocusTrap } from "./useFocusTrap";

type OverlayProps = {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
};

function Layer({ open, onClose, title, children, footer, kind }: OverlayProps & { kind: "dialog" | "drawer" }) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);
  const titleId = useId();
  useFocusTrap(panel, open, onClose);
  if (!open) return null;
  return createPortal(
    <div className={cx("ui-layer", `ui-layer--${kind}`)}>
      <div className="ui-layer__backdrop" onClick={onClose} aria-hidden />
      <div
        ref={panel}
        className={cx("ui-layer__panel", `ui-${kind}`)}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        <header className="ui-layer__head">
          <h2 id={titleId}>{title}</h2>
          <button type="button" className="ui-icon-btn" onClick={onClose} aria-label={t("ui.close")}>
            <X size={20} aria-hidden />
          </button>
        </header>
        <div className="ui-layer__body">{children}</div>
        {footer && <footer className="ui-layer__foot">{footer}</footer>}
      </div>
    </div>,
    document.body,
  );
}

export function Dialog(props: OverlayProps) {
  return <Layer {...props} kind="dialog" />;
}

export function Drawer(props: OverlayProps) {
  return <Layer {...props} kind="drawer" />;
}
