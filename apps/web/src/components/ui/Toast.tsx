// Toast (04 §5, §8.1): amal nomi bilan ("Xarid saqlandi"), `aria-live`, 5 s da yo'qoladi, yopish tugmasi bilan.
import { X } from "lucide-react";
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { TONE_ICON, type Tone } from "./Badge";
import { cx } from "./cx";

type Item = { id: number; text: string; tone: Tone };
type ToastApi = { show: (text: string, tone?: Tone) => void };

const ToastContext = createContext<ToastApi | null>(null);
export const TOAST_MS = 5000;

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [items, setItems] = useState<Item[]>([]);
  const next = useRef(1);
  const dismiss = useCallback((id: number) => setItems((list) => list.filter((i) => i.id !== id)), []);
  const show = useCallback(
    (text: string, tone: Tone = "positive") => {
      const id = next.current++;
      setItems((list) => [...list.slice(-2), { id, text, tone }]);
      setTimeout(() => dismiss(id), TOAST_MS);
    },
    [dismiss],
  );
  const api = useMemo(() => ({ show }), [show]);
  return (
    <ToastContext.Provider value={api}>
      {children}
      <div className="ui-toasts" aria-live="polite" role="status">
        {items.map((item) => {
          const Icon = TONE_ICON[item.tone];
          return (
            <div key={item.id} className={cx("ui-toast", `ui-tone--${item.tone}`)}>
              <Icon size={16} aria-hidden />
              <span>{item.text}</span>
              <button type="button" className="ui-icon-btn" onClick={() => dismiss(item.id)} aria-label={t("ui.close")}>
                <X size={14} aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastApi {
  const api = useContext(ToastContext);
  if (!api) throw new Error("useToast: ToastProvider yo'q");
  return api;
}
