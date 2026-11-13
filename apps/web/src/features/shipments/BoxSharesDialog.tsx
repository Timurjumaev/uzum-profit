// Kodli quti ulushlarini tahrirlash (TM3, ADR-061 §3): har xaridga tushgan kargo puli — dona bo'yicha (server, F20)
// tayyor turadi; sotuvchi istalganini o'zgartiradi, qolgani dona bo'yicha qayta bo'linadi. Yig'indi summaga teng bo'lishi
// shart (qoldiq ko'rinadi). Saqlanganda faqat o'zgartirilgan ulushlar yoziladi (sanashda dona o'zgarsa qolganlari o'zi
// qayta bo'linadi).
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { previewBoxShares, setBoxShares } from "../../app/query";
import { Banner, Button, Dialog, MoneyInput } from "../../components/ui";
import type { CostComponent, ShipmentPurchase } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { boxRest } from "../cargo/CargoPool";
import type { CurrencyCode } from "../purchases/model";

export function BoxSharesDialog({ orgId, shipmentId, component, purchases, onClose, onSaved }: { orgId: string; shipmentId: string; component: CostComponent; purchases: ShipmentPurchase[]; onClose: () => void; onSaved: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const [fixed, setFixed] = useState<Record<string, string | null>>(() => ({ ...component.purchase_shares }));
  const clean = Object.fromEntries(Object.entries(fixed).filter(([, v]) => v !== null && v !== "")) as Record<string, string>;
  const currency = component.currency as CurrencyCode;
  const ids = purchases.map((p) => p.id);
  const preview = useQuery({
    queryKey: ["orgs", orgId, "purchases", "cargo-pool", "shares", component.id, clean],
    queryFn: () => previewBoxShares(orgId, { amount: component.amount, currency, purchase_ids: ids, fixed: clean }),
    placeholderData: keepPreviousData,
    retry: false,
  });
  const shareOf = (id: string) => (fixed[id] !== undefined && fixed[id] !== null ? fixed[id] : (preview.data?.shares[id] ?? null));
  const rest = boxRest(
    component.amount,
    ids.map((id) => shareOf(id)),
  );
  const save = useMutation({ mutationFn: () => setBoxShares(orgId, shipmentId, component.id, clean), onSuccess: onSaved });
  const valid = !preview.isError && rest === 0;
  return (
    <Dialog
      open
      title={t("shipments.shares.title")}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("purchases.cancel")}
          </Button>
          <Button variant="primary" disabled={!valid} loading={save.isPending} onClick={() => save.mutate()}>
            {t("shipments.shares.save")}
          </Button>
        </>
      }
    >
      <div className="purchase-form">
        <p className="caption">{t("shipments.shares.hint", { amount: f.number(component.amount), currency })}</p>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        {preview.isError && <Banner tone="negative" title={errorText(preview.error, t)} />}
        {rest !== null && rest !== 0 && !preview.isError && <Banner tone="warning" title={t("cargo.boxRest", { rest: f.number(rest) })} />}
        {purchases.map((p) => (
          <MoneyInput
            key={p.id}
            label={`${p.title ?? t("purchases.untitled")} · ${t("cargo.units", { count: preview.data?.units[p.id] ?? p.units })}`}
            currency={currency}
            value={shareOf(p.id)}
            onValueChange={(v) => setFixed((x) => ({ ...x, [p.id]: v }))}
          />
        ))}
        {Object.keys(clean).length > 0 && (
          <Button variant="ghost" onClick={() => setFixed({})}>
            {t("cargo.resetShares")}
          </Button>
        )}
      </div>
    </Dialog>
  );
}
