// Tovar ↔ SKU bog'lash (M6): tannarx va ombor tovar darajasida yuritiladi. SKU: tovarsiz, mavjud tovarga, yangi tovar
// sifatida yoki ajratilgan. O'zgartirish — egasi va menejer (`manage_purchases`); tannarx qayta hisoblash navbatiga
// tushadi (bir necha daqiqada yangilanadi).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { itemsQuery, linkItem } from "../../app/query";
import { Button, Combobox, Dialog, TextInput, useToast } from "../../components/ui";
import type { ItemLinkIn, SkuDetail } from "../../lib/api/types";

type Mode = ItemLinkIn["mode"];

export function LinkItem({ orgId, detail, canManage }: { orgId: string; detail: SkuDetail; canManage: boolean }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const [open, setOpen] = useState(false);
  const sku = detail.sku;
  const linked = detail.linked;
  const done = useMutation({
    mutationFn: (body: ItemLinkIn) => linkItem(orgId, sku.sku_id, body),
    onSuccess: async () => {
      await Promise.all(["sku", "skus", "pnl", "dashboard"].map((key) => client.invalidateQueries({ queryKey: ["orgs", orgId, key] })));
      toast.show(t("products.link.saved"), "positive");
      setOpen(false);
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  return (
    <section className="sku-link" aria-labelledby="sku-link-title">
      <h2 id="sku-link-title" className="h3">
        {t("products.link.title")}
      </h2>
      {linked ? (
        <>
          <p>
            <strong>{linked.name}</strong>
          </p>
          <ul className="sku-link__skus">
            {linked.skus.map((s) => (
              <li key={s.sku_id}>
                {s.sku_id === sku.sku_id ? (
                  <span>{s.title ?? t("home.sku.unnamed")}</span>
                ) : (
                  <Link to="/products/$skuId" params={{ skuId: s.sku_id }} search={(prev) => ({ shop: prev.shop, from: prev.from, to: prev.to, cmp: prev.cmp })}>
                    {s.title ?? t("home.sku.unnamed")}
                  </Link>
                )}
              </li>
            ))}
          </ul>
          <p className="caption">{t("products.link.linkedNote")}</p>
        </>
      ) : (
        <p>{t("products.link.none")}</p>
      )}
      {canManage && (
        <div className="sku-link__actions">
          <Button variant="secondary" onClick={() => setOpen(true)}>
            {linked ? t("products.link.change") : t("products.link.add")}
          </Button>
          {linked && (
            <Button variant="ghost" loading={done.isPending && done.variables?.mode === "none"} onClick={() => done.mutate({ mode: "none" })}>
              {t("products.link.detach")}
            </Button>
          )}
        </div>
      )}
      {open && <LinkForm orgId={orgId} detail={detail} pending={done.isPending} onSubmit={(body) => done.mutate(body)} onClose={() => setOpen(false)} />}
    </section>
  );
}

function LinkForm({ orgId, detail, pending, onSubmit, onClose }: { orgId: string; detail: SkuDetail; pending: boolean; onSubmit: (body: ItemLinkIn) => void; onClose: () => void }) {
  const { t } = useTranslation();
  const items = useQuery(itemsQuery(orgId, ""));
  const [mode, setMode] = useState<Exclude<Mode, "none">>("existing");
  const [item, setItem] = useState<string | null>(detail.linked?.item_id ?? null);
  const [name, setName] = useState(detail.sku.title ?? detail.sku.product_title ?? "");
  const valid = mode === "existing" ? item !== null : name.trim() !== "";
  return (
    <Dialog
      open
      onClose={onClose}
      title={t("products.link.formTitle")}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("products.link.cancel")}
          </Button>
          <Button variant="primary" disabled={!valid} loading={pending} onClick={() => onSubmit(mode === "existing" ? { mode, item_id: item } : { mode, name: name.trim() })}>
            {t("products.link.save")}
          </Button>
        </>
      }
    >
      <p className="caption">{t("products.link.formLead")}</p>
      <fieldset className="sku-link__modes">
        <legend className="ui-visually-hidden">{t("products.link.formTitle")}</legend>
        {(["existing", "new"] as const).map((m) => (
          <label key={m}>
            <input type="radio" name="link-mode" checked={mode === m} onChange={() => setMode(m)} /> {t(`products.link.mode.${m}`)}
          </label>
        ))}
      </fieldset>
      {mode === "existing" ? (
        <Combobox
          label={t("products.link.item")}
          options={(items.data?.items ?? []).map((i) => ({ value: i.id, label: i.name, hint: t("products.link.skuCount", { value: i.sku_count }) }))}
          value={item}
          onValueChange={setItem}
          placeholder={t("products.link.itemPlaceholder")}
        />
      ) : (
        <TextInput label={t("products.link.name")} value={name} onValueChange={setName} maxLength={200} />
      )}
    </Dialog>
  );
}
