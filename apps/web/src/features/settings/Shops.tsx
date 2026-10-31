// Do'konlar (M16): qisqa nom, rang va sinxronga kiradimi. O'zgartirish — faqat egasi (server ham shunday); kamida bitta
// do'kon faol bo'lishi kerak. Do'kon qo'shish/olib tashlash — Uzum kaliti orqali (Ulanishlar, B5).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { shopsQuery, syncQuery, updateShop } from "../../app/query";
import { Badge, Banner, Button, DataTable, Dialog, EmptyState, Skeleton, TextInput, useToast, type Column } from "../../components/ui";
import type { components } from "../../lib/api/schema";
import { ColorPicker } from "../onboarding/ColorPicker";
import { shopChanges } from "../onboarding/ShopsStep";

type Shop = components["schemas"]["ShopOut"];

export function Shops({ orgId, canEdit }: { orgId: string; canEdit: boolean }) {
  const { t } = useTranslation();
  const shops = useQuery(shopsQuery(orgId));
  const [editing, setEditing] = useState<Shop | null>(null);
  const columns: Column<Shop>[] = [
    {
      key: "shop",
      header: t("settings.shops.col.shop"),
      render: (s) => (
        <span className="settings-shop">
          <span className="settings-shop__swatch" style={{ background: s.color ?? "transparent" }} aria-hidden />
          <span>
            <strong>{s.alias ?? s.name}</strong>
            {s.alias && <span className="caption"> · {s.name}</span>}
          </span>
        </span>
      ),
    },
    { key: "id", header: t("settings.shops.col.id"), numeric: true, render: (s) => s.external_id },
    { key: "active", header: t("settings.shops.col.active"), render: (s) => <Badge tone={s.active ? "positive" : "neutral"}>{t(s.active ? "settings.shops.on" : "settings.shops.off")}</Badge> },
    ...(canEdit
      ? [
          {
            key: "actions",
            header: t("settings.col.actions"),
            render: (s: Shop) => (
              <Button size="sm" variant="ghost" onClick={() => setEditing(s)}>
                {t("settings.edit")}
              </Button>
            ),
          },
        ]
      : []),
  ];
  return (
    <section className="settings-section" aria-labelledby="settings-shops">
      <h2 id="settings-shops" className="h3">
        {t("settings.shops.title")}
      </h2>
      <p className="caption">{t("settings.shops.lead")}</p>
      {shops.isError ? (
        <Banner tone="negative" title={errorText(shops.error, t)} />
      ) : !shops.data ? (
        <Skeleton label={t("common.loading")} lines={2} />
      ) : shops.data.length === 0 ? (
        <EmptyState title={t("settings.shops.empty")} />
      ) : (
        <DataTable caption={t("settings.shops.title")} columns={columns} rows={shops.data} rowKey={(s) => s.id} />
      )}
      {editing && shops.data && <ShopForm orgId={orgId} shop={editing} onlyActive={shops.data.filter((s) => s.active).length <= 1 && editing.active} onClose={() => setEditing(null)} />}
    </section>
  );
}

function ShopForm({ orgId, shop, onlyActive, onClose }: { orgId: string; shop: Shop; onlyActive: boolean; onClose: () => void }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const [draft, setDraft] = useState({ active: shop.active, alias: shop.alias ?? "", color: shop.color });
  const changes = shopChanges(shop, draft);
  const clearsAlias = draft.alias.trim() === "" && shop.alias !== null;
  const save = useMutation({
    mutationFn: () => updateShop(orgId, shop.id, { ...changes, ...(clearsAlias ? { alias: null } : {}) }),
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: shopsQuery(orgId).queryKey }), client.invalidateQueries({ queryKey: syncQuery(orgId).queryKey })]);
      toast.show(t("settings.shops.saved"), "positive");
      onClose();
    },
  });
  const dirty = Object.keys(changes).length > 0 || clearsAlias;
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (dirty) save.mutate();
  };
  return (
    <Dialog
      open
      title={t("settings.shops.editTitle", { name: shop.name })}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("settings.cancel")}
          </Button>
          <Button type="submit" form="shop-form" disabled={!dirty} loading={save.isPending}>
            {t("settings.save")}
          </Button>
        </>
      }
    >
      <form id="shop-form" className="settings-form" onSubmit={submit}>
        {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
        <label className="settings-check">
          <input type="checkbox" checked={draft.active} disabled={onlyActive} onChange={(e) => setDraft((d) => ({ ...d, active: e.target.checked }))} /> {t("settings.shops.activeLabel")}
        </label>
        {onlyActive && <p className="caption">{t("settings.shops.lastActive")}</p>}
        <TextInput label={t("settings.shops.alias")} help={t("settings.shops.aliasHelp")} optional placeholder={shop.name} value={draft.alias} onValueChange={(alias) => setDraft((d) => ({ ...d, alias }))} maxLength={40} />
        <ColorPicker label={t("settings.shops.color")} value={draft.color} onChange={(color) => setDraft((d) => ({ ...d, color }))} />
      </form>
    </Dialog>
  );
}
