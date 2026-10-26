// Oldingi davrga nisbatan o'zgarish (04 §5 KPI qoidasi): ishora + foiz, rang = yo'nalish × yaxshimi (xarajat o'sishi —
// yomon). Ulush API'dan (`RowOut.change`, farq / |oldingi|); xarajat qatorida kattalik bo'yicha ko'rsatiladi.
import { useTranslation } from "react-i18next";

import { changeTone } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";
import { negate, type Direction } from "./model";

export function Change({ value, direction }: { value: string | null; direction: Direction }) {
  const { t } = useTranslation();
  const f = useFormat();
  if (value === null) return null;
  const shown = direction === "cost" ? negate(value) : value;
  const tone = changeTone(shown, direction === "cost" ? "down" : "up");
  return (
    <span className={cx("home-change", `ui-text--${tone}`)} title={t("home.ledger.changeAria")}>
      {f.change(shown)}
    </span>
  );
}
