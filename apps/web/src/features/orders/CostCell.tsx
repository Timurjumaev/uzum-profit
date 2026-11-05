// Sotuv qatori tannarxi katagi (M7): qiymat va uning ishonchliligi. "Taxminiy" yoki "Tannarxsiz" belgisi sababi bilan
// ko'rsatiladi — F22 belgilari matnga aylantiriladi (tamoyil 9: taxmin yashirilmaydi, lekin sababi ham aytiladi).
import { useTranslation } from "react-i18next";

import { Badge } from "../../components/ui";
import { useFormat } from "../../lib/i18n";

/** Belgilar muhimlik tartibida: avval tannarx qiymatiga ta'sir qiluvchilar, oxirida ma'lumot uchun (kurs CBU). */
const ORDER = [
  "no_item",
  "no_lots",
  "lot_shortage",
  "early_sale",
  "not_received_marked",
  "return_unmatched",
  "historical",
  "not_received",
  "cargo_missing",
  "base_fallback",
  "market_rate",
  "cbu_rate",
];

export function sortFlags(flags: readonly string[]): string[] {
  const rank = (x: string) => (ORDER.includes(x) ? ORDER.indexOf(x) : ORDER.length);
  return [...flags].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

type Props = { cogs: string | null; flags: readonly string[] };

export function CostCell({ cogs, flags }: Props) {
  const { t } = useTranslation();
  const f = useFormat();
  const reasons = sortFlags(flags)
    .map((x) => t(`orders.flag.${x}`, { defaultValue: x }))
    .join("; ");
  const value = cogs === null ? "—" : f.money(cogs, { unit: false });
  if (flags.length === 0) return <>{value}</>;
  return (
    <>
      <Badge tone={cogs === null ? "negative" : "warning"} title={reasons}>
        {t(cogs === null ? "orders.uncosted" : "orders.estimated")}
      </Badge>
      <span className="ui-visually-hidden">: {reasons}.</span> {value}
    </>
  );
}
