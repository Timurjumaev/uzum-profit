// "Shundan jarayonda" (ADR-036): sotuvlar Yakunlangan + Jarayonda hisobga kiradi; bu izoh qaysi qismi hali yakuniy
// emasligini ko'rsatadi (mijoz olib ketmasa yoki 10 kun ichida qaytarsa kamayadi). Raqamlar API'dan, hisob yo'q.
import { useTranslation } from "react-i18next";

import { FormulaPopover } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";

type Props = {
  units: number;
  revenue: string;
  /** Davr kartochkasi uchun: "?" siz, qisqa. */
  compact?: boolean;
  className?: string;
};

export function ProcessingNote({ units, revenue, compact = false, className }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  if (units <= 0) return null;
  const text = t(compact ? "home.processing.short" : "home.processing.text", {
    units: f.number(units),
    revenue: f.money(revenue),
  });
  return (
    <p className={cx("caption processing-note", className)}>
      {text}
      {!compact && (
        <>
          {" "}
          <FormulaPopover
            metric={t("home.processing.metric")}
            code={t("home.formula.processing.code")}
            formula={t("home.formula.processing.formula")}
            source={t("home.formula.processing.source")}
            estimatedReason={t("home.formula.processing.estimated")}
          />
        </>
      )}
    </p>
  );
}
