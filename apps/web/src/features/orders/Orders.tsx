// Buyurtmalar (M7, B4.4): sotuv qatorlari ro'yxati ("Bonus davri" belgisi bilan) va bekor / qaytish tahlili.
// Bo'lim (`tab`) va ro'yxat holati filtri (`group`) — URL'da. Hamma raqam API'dan (`/sales`, `/orders/analysis`):
// ulushlar (F17, F18) serverda hisoblanadi, bu yerda qayta hisoblanmaydi (tamoyil 4).
import { useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { useFilters } from "../../app/filters";
import { currentOrg, meQuery } from "../../app/query";
import { ORDER_TABS, ordersSearch, type OrderTab } from "../../app/search";
import { PageHelp } from "../../components/ui";
import { cx } from "../../components/ui/cx";
import { useFormat } from "../../lib/i18n";
import { Analysis } from "./Analysis";
import { OrdersList } from "./OrdersList";

export function Orders() {
  const { t } = useTranslation();
  const f = useFormat();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!; // `app` marshruti tashkilotsiz foydalanuvchini onboarding'ga yuboradi
  const { filters } = useFilters();
  const navigate = useNavigate();
  // Bola marshrutga ota marshrutning xom qidiruvi ham keladi — qiymat shu yerda ham tekshiriladi (app/search).
  const search = ordersSearch(useSearch({ strict: false }) as Record<string, unknown>);
  const tab: OrderTab = search.tab ?? "list";
  const params = { shops: filters.shops, start: filters.range.start, end: filters.range.end };
  const setTab = (next: OrderTab) =>
    void navigate({ to: "/orders", search: (prev) => ({ ...prev, tab: next === "list" ? undefined : next, group: undefined }), replace: true });
  return (
    <section className="orders">
      <header className="orders__head">
        <div className="page-title">
          <h1 className="h2">{t("orders.title", { period: f.period(params.start, params.end) })}</h1>
          <PageHelp page="orders" />
        </div>
      </header>
      <div role="tablist" aria-label={t("orders.tabsLabel")} className="orders-tabs">
        {ORDER_TABS.map((id) => (
          <button
            key={id}
            type="button"
            role="tab"
            id={`orders-tab-${id}`}
            aria-selected={tab === id}
            aria-controls="orders-panel"
            className={cx("orders-tab", tab === id && "is-active")}
            onClick={() => setTab(id)}
          >
            {t(`orders.tabs.${id}`)}
          </button>
        ))}
      </div>
      <div id="orders-panel" role="tabpanel" aria-labelledby={`orders-tab-${tab}`}>
        {tab === "list" ? <OrdersList orgId={org.id} params={params} group={search.group} /> : <Analysis orgId={org.id} params={params} kind={tab} />}
      </div>
    </section>
  );
}
