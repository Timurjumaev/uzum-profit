// Banner (04 §5): sinxron xatosi, Uzum uzilishi, sinov tugashi, tannarx qamrovi. Nima bo'ldi + nima qilish kerak.
import { X } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { TONE_ICON, type Tone } from "./Badge";
import { cx } from "./cx";

export type BannerProps = {
  tone?: Tone;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
  onDismiss?: () => void;
};

export function Banner({ tone = "info", title, children, action, onDismiss }: BannerProps) {
  const { t } = useTranslation();
  const Icon = TONE_ICON[tone];
  return (
    <div className={cx("ui-banner", `ui-tone--${tone}`)} role={tone === "negative" ? "alert" : "status"}>
      <Icon className="ui-banner__icon" size={20} aria-hidden />
      <div className="ui-banner__body">
        <p className="ui-banner__title">{title}</p>
        {children && <div className="ui-banner__text">{children}</div>}
      </div>
      {action && <div className="ui-banner__action">{action}</div>}
      {onDismiss && (
        <button type="button" className="ui-icon-btn" onClick={onDismiss} aria-label={t("ui.dismiss")}>
          <X size={16} aria-hidden />
        </button>
      )}
    </div>
  );
}
