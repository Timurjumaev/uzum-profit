// Sotuv qatori tannarxi katagi (M7): qiymat va uning ishonchliligi. "Taxminiy" yoki "Tannarxsiz" belgisi sababi bilan
// ko'rsatiladi — F22 belgilari matnga aylantiriladi (tamoyil 9: taxmin yashirilmaydi, lekin sababi ham aytiladi).
import { Info } from "lucide-react";
import { useId, useState } from "react";
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

/** Sotuvchi o'zi kiritgan narx (boshlang'ich holat, F41) aniq tannarx: "tarixiy" belgisi taxmin emas, "Taxminiy" qo'yilmaydi. */
const EXACT = new Set(["historical"]);

type Props = { cogs: string | null; flags: readonly string[] };

/** Belgi bosilsa sabablar katak ichida ochiladi (qalqib chiqmaydi: jadval skroll konteynerida kesilmasin, telefonda ham ishlasin). */
export function CostCell({ cogs, flags: all }: Props) {
  const { t } = useTranslation();
  const flags = all.filter((x) => !EXACT.has(x));
  const f = useFormat();
  const [open, setOpen] = useState(false);
  const id = useId();
  const reasons = sortFlags(flags).map((x) => t(`orders.flag.${x}`, { defaultValue: x }));
  const value = cogs === null ? "—" : f.money(cogs, { unit: false });
  if (flags.length === 0) return <>{value}</>;
  const text = t(cogs === null ? "orders.uncosted" : "orders.estimated");
  return (
    <>
      <button type="button" className="cost-flag" aria-expanded={open} aria-controls={id} title={reasons.join("; ")} onClick={() => setOpen(!open)}>
        <Badge tone={cogs === null ? "negative" : "warning"}>
          {text} <Info size={12} aria-hidden />
        </Badge>
      </button>{" "}
      {value}
      {open && (
        <ul id={id} className="cost-flag__reasons caption">
          {reasons.map((x) => (
            <li key={x}>{x}</li>
          ))}
        </ul>
      )}
    </>
  );
}
