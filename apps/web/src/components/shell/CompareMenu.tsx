// Solishtirish (04 §5, §7.1): topbar'da ixcham tugma, ichida CompareToggle.
import { ArrowLeftRight } from "lucide-react";
import { useTranslation } from "react-i18next";

import { CompareToggle, Popover, type CompareMode } from "../ui";

export function CompareMenu({ value, onChange }: { value: CompareMode; onChange: (mode: CompareMode) => void }) {
  const { t } = useTranslation();
  const text = value === "none" ? t("ui.compare.label") : `${t("ui.compare.label")}: ${t(`ui.compare.${value}`)}`;
  return (
    <Popover
      label={text}
      triggerClassName="ui-btn ui-btn--secondary ui-btn--md topbar__compare"
      trigger={
        <>
          <ArrowLeftRight size={16} aria-hidden />
          <span className="topbar__compare-text">{text}</span>
        </>
      }
    >
      {(close) => (
        <CompareToggle
          value={value}
          onChange={(mode) => {
            onChange(mode);
            close();
          }}
        />
      )}
    </Popover>
  );
}
