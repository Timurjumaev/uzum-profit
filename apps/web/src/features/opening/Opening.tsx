// Boshlang'ich holat (B4.12, ADR-033, F41): eski partiyalarni kiritmasdan boshlash. Sotuvchi boshlash sanasini
// tanlaydi, har tovarga bitta tannarx va qoldiqni (Uzumdagi — taklif, o'z omborim — qo'lda) yozadi. Sanagacha bo'lgan
// sotuvlar shu narxda ("Taxminiy"), keyingilari partiyalardan. Qatorlar tushum bo'yicha: avval eng muhimlari.
import { useMutation, useQuery, useQueryClient, useSuspenseQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import { currentOrg, meQuery, openingQuery, saveOpening } from "../../app/query";
import { Banner, Button, EmptyState, MoneyInput, NumberInput, PageHelp, ProgressBar, Skeleton, TextInput, useToast } from "../../components/ui";
import type { OpeningRow } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { searchKey } from "../../lib/i18n/translit";
import { applyGroupPrice, draftOf, filled, groupPrice, groupRows, hasPeriods, invalid, openingBody, rowKey, type Edit } from "./model";

const MANAGE_ROLES = ["owner", "manager"];
const PAGE = 50;

export function Opening() {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me)!;
  const canManage = MANAGE_ROLES.includes(org.role);
  const [start, setStart] = useState<string | null>(null); // null — saqlangan (yoki bugun)
  const { filters } = useFilters(); // do'kon filtri — tanlangan do'konda sotiladigan tovarlar
  const query = useQuery(openingQuery(org.id, start, filters.shops));
  const [edits, setEdits] = useState<Record<string, Edit>>({});
  const [needle, setNeedle] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const data = query.data;
  const startValue = start ?? data?.start_on ?? data?.as_of ?? "";
  const save = useMutation({
    mutationFn: (off: boolean) => saveOpening(org.id, off ? { start_on: null, rows: [] } : openingBody(startValue || null, data?.rows ?? [], edits), filters.shops),
    onSuccess: async (body, off) => {
      setEdits({});
      setStart(null);
      client.setQueryData(openingQuery(org.id, null, filters.shops).queryKey, body);
      await client.invalidateQueries({ queryKey: ["orgs", org.id], predicate: (q) => q.queryKey[2] !== "opening" });
      toast.show(t(off ? "opening.offDone" : "opening.saved"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const groups = useMemo(() => {
    const key = searchKey(needle.trim());
    return groupRows((data?.rows ?? []).filter((r) => !key || searchKey([r.name, r.product ?? "", ...r.skus].join(" ")).includes(key)));
  }, [data, needle]);
  const anyInvalid = (data?.rows ?? []).some((r) => invalid(draftOf(r, edits[rowKey(r)])));
  const patch = (r: OpeningRow, e: Edit) => setEdits((all) => ({ ...all, [rowKey(r)]: { ...all[rowKey(r)], ...e } }));
  // Bitta tur (yoki tovar) qatori; `variant` — mahsulot guruhi ichida (sarlavha — SKU, mahsulot nomi guruhda).
  // Funksiya (komponent emas): har chizishda qayta o'rnatilmaydi — yozayotganda maydon fokusni yo'qotmaydi.
  const row = (r: OpeningRow, title: string, variant = false) => {
    const d = draftOf(r, edits[rowKey(r)]);
    return (
      <li key={rowKey(r)} className={variant ? "opening-row opening-row--variant" : "opening-row"}>
        <div className="opening-row__name">
          <p className="label">{title}</p>
          <p className="caption">
            {!variant && `${r.skus.join(", ")} · `}
            {t("opening.revenue", { sum: f.money(r.revenue) })}
          </p>
          {r.shared && <p className="caption">{t("opening.shared")}</p>}
          {r.last_lot_cost !== null && <p className="caption">{t("opening.lastLot", { sum: f.money(r.last_lot_cost) })}</p>}
          {r.lots_before > 0 && <p className="caption opening-row__warn">{t("opening.lotsBefore", { n: r.lots_before })}</p>}
        </div>
        {hasPeriods(r) ? (
          <p className="caption">{t("opening.periods", { list: r.prices.map((p) => `${p.valid_from ? f.date(p.valid_from) : t("opening.fromStart")}: ${f.money(p.unit_cost)}`).join("; ") })}</p>
        ) : (
          <MoneyInput label={t("opening.price")} optional disabled={!canManage} value={d.price} onValueChange={(price) => patch(r, { price })} />
        )}
        <NumberInput label={t("opening.uzum")} help={r.uzum_suggested !== null ? t("opening.suggested", { n: r.uzum_suggested }) : undefined} digits={0} disabled={!canManage} value={d.uzum} onValueChange={(uzum) => patch(r, { uzum })} />
        <NumberInput label={t("opening.own")} optional digits={0} disabled={!canManage} value={d.own} onValueChange={(own) => patch(r, { own })} />
      </li>
    );
  };

  return (
    <section className="opening">
      <header className="settings__head">
        <div className="page-title">
          <h1 className="h2">{t("opening.title")}</h1>
          <PageHelp page="opening" />
        </div>
        <p className="caption">{t("opening.lead")}</p>
      </header>
      {query.isError ? (
        <Banner tone="negative" title={errorText(query.error, t)} action={<Button onClick={() => void query.refetch()}>{t("common.retry")}</Button>} />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={8} />
      ) : (
        <>
          {!canManage && <Banner tone="info" title={t("settings.readOnly")}>{t("settings.readOnlyText")}</Banner>}
          {data.start_on === null && <Banner tone="info" title={t("opening.offTitle")}>{t("opening.offText")}</Banner>}
          <div className="opening__top">
            <TextInput
              label={t("opening.start")}
              help={t("opening.startHelp")}
              type="date"
              disabled={!canManage}
              value={startValue}
              onValueChange={(v) => setStart(v || null)}
            />
            <div className="opening__coverage">
              <ProgressBar
                value={Number(data.coverage ?? 0) * 100}
                max={100}
                label={t("opening.coverage", { pct: data.coverage === null ? "—" : f.percent(data.coverage) })}
                detail={t("opening.filled", { n: filled(data.rows, edits), total: data.rows.length })}
              />
            </div>
          </div>
          {data.stock_source !== "current" && (
            <Banner tone={data.stock_source === "none" ? "warning" : "info"} title={t(`opening.stock.${data.stock_source}`, { day: f.date(data.as_of) })} />
          )}
          {data.rows.length === 0 ? (
            <EmptyState title={t("opening.empty")} text={t("opening.emptyText")} />
          ) : (
            <>
              <TextInput label={t("opening.search")} type="search" value={needle} onValueChange={setNeedle} />
              <ul className="opening__list" aria-label={t("opening.title")}>
                {groups.slice(0, limit).map((g) =>
                  g.rows.length === 1 ? (
                    row(g.rows[0]!, g.rows[0]!.name)
                  ) : (
                    <li key={g.key} className="opening-group">
                      <div className="opening-group__head">
                        <div className="opening-row__name">
                          <p className="label">{g.title}</p>
                          <p className="caption">{t("opening.variants", { n: g.rows.length })}</p>
                        </div>
                        <MoneyInput
                          label={t("opening.groupPrice")}
                          help={t("opening.groupPriceHelp")}
                          optional
                          disabled={!canManage}
                          value={groupPrice(g, edits)}
                          onValueChange={(price) => setEdits((all) => applyGroupPrice(g, price, all))}
                        />
                      </div>
                      <ul className="opening__list" aria-label={g.title}>
                        {g.rows.map((r) => row(r, r.skus.join(", "), true))}
                      </ul>
                    </li>
                  ),
                )}
              </ul>
              {groups.length > limit && (
                <Button variant="ghost" onClick={() => setLimit((n) => n + PAGE)}>
                  {t("opening.more", { n: groups.length - limit })}
                </Button>
              )}
            </>
          )}
          {anyInvalid && <Banner tone="warning" title={t("opening.invalid")} />}
          {canManage && (
            <div className="settings-section__row">
              <Button variant="primary" disabled={anyInvalid || !startValue} loading={save.isPending && !save.variables} onClick={() => save.mutate(false)}>
                {t("opening.save")}
              </Button>
              {data.start_on !== null && (
                <Button variant="ghost" loading={save.isPending && save.variables} onClick={() => save.mutate(true)}>
                  {t("opening.off")}
                </Button>
              )}
              <Link to="/purchases" className="opening__link">
                {t("opening.toPurchases")}
              </Link>
            </div>
          )}
        </>
      )}
    </section>
  );
}
