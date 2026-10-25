// "?" (04 §5, tamoyil 1 — "har raqam tushuntiriladi"): formula F-raqami bilan, qaysi ma'lumotdan, taxminiy bo'lsa
// sababi. Matnlar chaqiruvchidan (i18n).
import { CircleHelp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Badge } from "./Badge";
import { Popover } from "./Popover";

export type FormulaPopoverProps = {
  /** Ko'rsatkich nomi (tugma yorlig'i uchun). */
  metric: string;
  /** F-raqam, masalan "F12". */
  code: string;
  formula: string;
  source?: string;
  estimatedReason?: string;
};

export function FormulaPopover({ metric, code, formula, source, estimatedReason }: FormulaPopoverProps) {
  const { t } = useTranslation();
  return (
    <Popover
      trigger={<CircleHelp size={16} aria-hidden />}
      label={`${t("ui.formula")}: ${metric}`}
      triggerClassName="ui-icon-btn"
    >
      <div className="ui-formula">
        <p className="label">
          {metric} · {code}
        </p>
        <p className="ui-formula__expr">{formula}</p>
        {source && (
          <p className="caption">
            {t("ui.source")}: {source}
          </p>
        )}
        {estimatedReason && (
          <p className="caption">
            <Badge tone="warning">{t("ui.estimated")}</Badge> {estimatedReason}
          </p>
        )}
      </div>
    </Popover>
  );
}
