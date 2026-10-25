// Do'kon filtri (04 §7.1): "Hammasi" yoki bir nechta do'kon. Bo'sh tanlov = hammasi (URL'da `shop` yo'q). Kamida
// bitta do'kon tanlangan bo'lishi kerak; hammasi belgilansa — yana "Hammasi".
import { useQuery } from "@tanstack/react-query";
import { Store } from "lucide-react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { shopsQuery } from "../../app/query";
import type { components } from "../../lib/api/schema";
import { Popover } from "../ui";

type Shop = components["schemas"]["ShopOut"];

export const shopName = (shop: Pick<Shop, "alias" | "name">) => shop.alias || shop.name;

/** Rang belgisi faqat to'g'ri HEX bo'lsa (stilga tashqi satr qo'yilmaydi). */
const COLOR = /^#[0-9a-f]{6}$/i;

/** Tanlov ro'yxatdagi do'konlar bilan kesishadi: o'chirilgan yoki begona ID jim tashlanadi. */
export function effectiveShops(selected: string[], shops: Shop[]): string[] {
  const known = new Set(shops.map((s) => s.id));
  const kept = selected.filter((id) => known.has(id));
  return kept.length === shops.length ? [] : kept;
}

export function toggleShop(selected: string[], id: string, shops: Shop[]): string[] {
  const all = shops.map((s) => s.id);
  const current = selected.length === 0 ? all : selected;
  const next = current.includes(id) ? current.filter((x) => x !== id) : [...current, id];
  if (next.length === 0) return selected; // hech bo'lmasa bittasi
  return next.length === all.length ? [] : next;
}

export function ShopFilter({ orgId, selected, onChange }: { orgId: string; selected: string[]; onChange: (ids: string[]) => void }) {
  const { t } = useTranslation();
  const query = useQuery(shopsQuery(orgId));
  const shops = (query.data ?? []).filter((s) => s.active);
  const chosen = effectiveShops(selected, shops);
  const only = chosen.length === 1 ? shops.find((s) => s.id === chosen[0]) : undefined;
  const text = only ? shopName(only) : chosen.length > 1 ? t("shell.shopsCount", { count: chosen.length }) : t("shell.allShops");
  const label = `${t("shell.shop")}: ${text}`;
  return (
    <Popover
      label={label}
      triggerClassName="ui-btn ui-btn--secondary ui-btn--md topbar__shop"
      trigger={
        <>
          <Store size={16} aria-hidden />
          <span className="topbar__shop-prefix">{t("shell.shop")}:</span>
          <span className="topbar__shop-text">{text}</span>
        </>
      }
    >
      <div className="shopfilter">
        {query.isError && (
          <p role="alert" className="shopfilter__note">
            {t("shell.shopsFailed")} {errorText(query.error, t)}
          </p>
        )}
        {query.isSuccess && shops.length === 0 && <p className="shopfilter__note">{t("shell.noShops")}</p>}
        {shops.length > 0 && (
          <fieldset className="shopfilter__list">
            <legend className="ui-visually-hidden">{t("shell.shop")}</legend>
            <button type="button" className="ui-btn ui-btn--ghost ui-btn--sm" disabled={chosen.length === 0} onClick={() => onChange([])}>
              {t("shell.allShops")}
            </button>
            {shops.map((shop) => (
              <label key={shop.id} className="shopfilter__item">
                <input
                  type="checkbox"
                  checked={chosen.length === 0 || chosen.includes(shop.id)}
                  onChange={() => onChange(toggleShop(chosen, shop.id, shops))}
                />
                {shop.color && COLOR.test(shop.color) && <span className="shopfilter__dot" style={{ background: shop.color }} aria-hidden />}
                {shopName(shop)}
              </label>
            ))}
          </fieldset>
        )}
      </div>
    </Popover>
  );
}
