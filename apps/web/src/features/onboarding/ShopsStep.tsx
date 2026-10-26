// 2-qadam: do'konlarni tanlash (hammasi belgilangan), har biriga qisqa nom va rang (M2). Faqat o'zgargan do'konlar
// saqlanadi; kamida bittasi faol bo'lishi kerak.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { shopsQuery, syncQuery, updateShop } from "../../app/query";
import { Banner, Button, TextInput } from "../../components/ui";
import type { components } from "../../lib/api/schema";
import { ColorPicker, defaultColor } from "./ColorPicker";

type Shop = components["schemas"]["ShopOut"];
type Draft = { active: boolean; alias: string; color: string | null };

const initial = (shops: Shop[]): Record<string, Draft> =>
  Object.fromEntries(shops.map((s, i) => [s.id, { active: s.active, alias: s.alias ?? "", color: s.color ?? defaultColor(i) }]));

/** Serverga yuboriladigan o'zgarishlar (faqat farq; bo'sh nom — o'zgarmagan). */
export function shopChanges(shop: Shop, draft: Draft): { active?: boolean; alias?: string; color?: string } {
  const out: { active?: boolean; alias?: string; color?: string } = {};
  if (draft.active !== shop.active) out.active = draft.active;
  const alias = draft.alias.trim();
  if (alias && alias !== (shop.alias ?? "")) out.alias = alias;
  if (draft.color && draft.color.toLowerCase() !== (shop.color ?? "").toLowerCase()) out.color = draft.color;
  return out;
}

export function ShopsStep({ orgId, shops, onDone }: { orgId: string; shops: Shop[]; onDone: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [drafts, setDrafts] = useState(() => initial(shops));
  const [none, setNone] = useState(false);
  const patch = (id: string, change: Partial<Draft>) => setDrafts((d) => ({ ...d, [id]: { ...d[id], ...change } }));
  const save = useMutation({
    mutationFn: async () => {
      await Promise.all(
        shops.map((shop) => {
          const changes = shopChanges(shop, drafts[shop.id]);
          return Object.keys(changes).length > 0 ? updateShop(orgId, shop.id, changes) : null;
        }),
      );
    },
    onSuccess: async () => {
      await Promise.all([client.invalidateQueries({ queryKey: shopsQuery(orgId).queryKey }), client.invalidateQueries({ queryKey: syncQuery(orgId).queryKey })]);
      onDone();
    },
  });
  const submit = () => {
    const anyActive = shops.some((s) => drafts[s.id].active);
    setNone(!anyActive);
    if (anyActive) save.mutate();
  };
  return (
    <div className="onb__form">
      <h2>{t("onboarding.shops.title")}</h2>
      <p className="muted">{t("onboarding.shops.lead")}</p>
      {none && <Banner tone="negative" title={t("onboarding.shops.noneActive")} />}
      {save.isError && <Banner tone="negative" title={errorText(save.error, t)} />}
      <ul className="onb__shops">
        {shops.map((shop) => {
          const draft = drafts[shop.id];
          return (
            <li key={shop.id} className="onb__shop">
              <label className="onb__shop-check">
                <input type="checkbox" checked={draft.active} onChange={(e) => patch(shop.id, { active: e.target.checked })} />
                <span>
                  <strong>{shop.name}</strong>
                  <span className="caption"> · {t("onboarding.shops.uzumId", { id: shop.external_id })}</span>
                </span>
              </label>
              {draft.active && (
                <div className="onb__shop-fields">
                  <TextInput
                    label={t("onboarding.shops.alias")}
                    help={t("onboarding.shops.aliasHelp")}
                    placeholder={shop.name}
                    value={draft.alias}
                    onValueChange={(alias) => patch(shop.id, { alias })}
                    maxLength={40}
                  />
                  <ColorPicker label={t("onboarding.shops.color")} value={draft.color} onChange={(color) => patch(shop.id, { color })} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      <div className="onb__actions">
        <Button variant="primary" size="lg" loading={save.isPending} onClick={submit}>
          {t("common.next")}
        </Button>
      </div>
    </div>
  );
}
