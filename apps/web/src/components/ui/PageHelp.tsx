// Sahifa haqida qisqa yordam (B4.11, M18): sarlavha yonidagi "?" — sahifa nima ko'rsatishi, 3 ta qisqa satr
// (04 §3: satr ≤ 75 belgi). Matnlar i18n'da (`help.pages.<sahifa>`); ko'rsatkich formulalari — FormulaPopover.
import { CircleHelp } from "lucide-react";
import { useTranslation } from "react-i18next";

import { Popover } from "./Popover";

export const HELP_PAGES = ["home", "pnl", "products", "orders", "expenses", "purchases", "inventory", "settings", "opening"] as const;
export type HelpPage = (typeof HELP_PAGES)[number];

export function PageHelp({ page }: { page: HelpPage }) {
  const { t } = useTranslation();
  return (
    <Popover trigger={<CircleHelp size={16} aria-hidden />} label={t("help.label", { page: t(`help.pages.${page}.title`) })} triggerClassName="ui-icon-btn">
      <div className="ui-page-help">
        <p className="label">{t(`help.pages.${page}.title`)}</p>
        <ul>
          {(["a", "b", "c"] as const).map((line) => (
            <li key={line}>{t(`help.pages.${page}.${line}`)}</li>
          ))}
        </ul>
      </div>
    </Popover>
  );
}
