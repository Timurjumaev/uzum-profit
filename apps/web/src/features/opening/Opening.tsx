// Boshlang'ich holat (B4.12, ADR-033, F41): eski partiyalarni kiritmasdan boshlash. Sotuvchi boshlash sanasini
// tanlaydi, har tovarga bitta tannarx va qoldiqni (Uzumdagi — taklif, o'z omborim — qo'lda) yozadi. Sanagacha bo'lgan
// sotuvlar shu narxda ("Taxminiy"), keyingilari partiyalardan. Qatorlar tushum bo'yicha: avval eng muhimlari.
// Ko'rinish — Uzum kabinetidagi SKU jadvali: har Uzum mahsuloti — ixcham jadval (turlari — rang, model), "Tannarx"
// ustuni sarlavhasidagi tugma — "Barcha turlar uchun qo'llash" (keyin istalgan turini alohida o'zgartirish mumkin).
import {
  useMutation,
  useQuery,
  useQueryClient,
  useSuspenseQuery,
} from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { Check, ListChevronsUpDown } from "lucide-react";
import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { useFilters } from "../../app/filters";
import {
  currentOrg,
  meQuery,
  openingQuery,
  saveOpening,
} from "../../app/query";
import {
  Banner,
  Button,
  EmptyState,
  MoneyInput,
  NumberInput,
  PageHelp,
  Popover,
  ProgressBar,
  Skeleton,
  TextInput,
  useToast,
} from "../../components/ui";
import type { OpeningRow } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { searchKey } from "../../lib/i18n/translit";
import {
  applyGroupPrice,
  draftOf,
  filled,
  groupRows,
  hasPeriods,
  invalid,
  openingBody,
  rowKey,
  type Edit,
  type Group,
} from "./model";

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
    mutationFn: (off: boolean) =>
      saveOpening(
        org.id,
        off
          ? { start_on: null, rows: [] }
          : openingBody(startValue || null, data?.rows ?? [], edits),
        filters.shops,
      ),
    onSuccess: async (body, off) => {
      setEdits({});
      setStart(null);
      client.setQueryData(
        openingQuery(org.id, null, filters.shops).queryKey,
        body,
      );
      await client.invalidateQueries({
        queryKey: ["orgs", org.id],
        predicate: (q) => q.queryKey[2] !== "opening",
      });
      toast.show(t(off ? "opening.offDone" : "opening.saved"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const groups = useMemo(() => {
    const key = searchKey(needle.trim());
    return groupRows(
      (data?.rows ?? []).filter(
        (r) =>
          !key ||
          searchKey([r.name, r.product ?? "", ...r.skus].join(" ")).includes(
            key,
          ),
      ),
    );
  }, [data, needle]);
  const anyInvalid = (data?.rows ?? []).some((r) =>
    invalid(draftOf(r, edits[rowKey(r)])),
  );
  const patch = (r: OpeningRow, e: Edit) =>
    setEdits((all) => ({ ...all, [rowKey(r)]: { ...all[rowKey(r)], ...e } }));
  // Jadval qatori. Funksiya (komponent emas): har chizishda qayta o'rnatilmaydi — yozayotganda fokus yo'qolmaydi.
  const row = (r: OpeningRow) => {
    const d = draftOf(r, edits[rowKey(r)]);
    const sku = r.skus.join(", ");
    return (
      <tr key={rowKey(r)}>
        <th scope="row">
          <div className="opening-table__cell">
            <span className="opening-table__sku">{sku}</span>
            {r.shared && <span className="caption">{t("opening.shared")}</span>}
            {r.last_lot_cost !== null && (
              <span className="caption">
                {t("opening.lastLot", { sum: f.money(r.last_lot_cost) })}
              </span>
            )}
            {r.lots_before > 0 && (
              <span className="caption opening-row__warn">
                {t("opening.lotsBefore", { n: r.lots_before })}
              </span>
            )}
          </div>
        </th>
        <td className="opening-table__num opening-table__rev">
          {f.money(r.revenue)}
        </td>
        <td>
          {hasPeriods(r) ? (
            <span className="caption">
              {t("opening.periods", {
                list: r.prices
                  .map(
                    (p) =>
                      `${p.valid_from ? f.date(p.valid_from) : t("opening.fromStart")}: ${f.money(p.unit_cost)}`,
                  )
                  .join("; "),
              })}
            </span>
          ) : (
            <MoneyInput
              label={`${t("opening.price")} — ${sku}`}
              disabled={!canManage}
              value={d.price}
              onValueChange={(price) => patch(r, { price })}
            />
          )}
        </td>
        <td>
          <NumberInput
            label={`${t("opening.uzum")} — ${sku}`}
            help={
              r.uzum_suggested !== null
                ? t("opening.suggested", { n: r.uzum_suggested })
                : undefined
            }
            digits={0}
            disabled={!canManage}
            value={d.uzum}
            onValueChange={(uzum) => patch(r, { uzum })}
          />
        </td>
        <td>
          <NumberInput
            label={`${t("opening.own")} — ${sku}`}
            digits={0}
            disabled={!canManage}
            value={d.own}
            onValueChange={(own) => patch(r, { own })}
          />
        </td>
      </tr>
    );
  };
  const card = (g: Group) => (
    <section key={g.key} className="opening-card" aria-label={g.title}>
      <header className="opening-card__head">
        <p className="label">{g.title}</p>
        {g.rows.length > 1 && (
          <span className="caption">
            {t("opening.variants", { n: g.rows.length })}
          </span>
        )}
      </header>
      <div className="opening-table__wrap">
        <table className="opening-table">
          <thead>
            <tr>
              <th scope="col">{t("opening.col.sku")}</th>
              <th scope="col" className="opening-table__num opening-table__rev">
                {t("opening.col.revenue")}
              </th>
              <th scope="col">
                <span className="opening-table__th">
                  {t("opening.col.price")}
                  {canManage && g.rows.length > 1 && (
                    <ApplyAll
                      title={g.title}
                      onApply={(price) =>
                        setEdits((all) => applyGroupPrice(g, price, all))
                      }
                    />
                  )}
                </span>
              </th>
              <th scope="col">{t("opening.col.uzum")}</th>
              <th scope="col">{t("opening.col.own")}</th>
            </tr>
          </thead>
          <tbody>{g.rows.map(row)}</tbody>
        </table>
      </div>
    </section>
  );
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
        <Banner
          tone="negative"
          title={errorText(query.error, t)}
          action={
            <Button onClick={() => void query.refetch()}>
              {t("common.retry")}
            </Button>
          }
        />
      ) : !data ? (
        <Skeleton label={t("common.loading")} lines={8} />
      ) : (
        <>
          {!canManage && (
            <Banner tone="info" title={t("settings.readOnly")}>
              {t("settings.readOnlyText")}
            </Banner>
          )}
          {data.start_on === null && (
            <Banner tone="info" title={t("opening.offTitle")}>
              {t("opening.offText")}
            </Banner>
          )}
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
                label={t("opening.coverage", {
                  pct: data.coverage === null ? "—" : f.percent(data.coverage),
                })}
                detail={t("opening.filled", {
                  n: filled(data.rows, edits),
                  total: data.rows.length,
                })}
              />
            </div>
          </div>
          {data.stock_source !== "current" && (
            <Banner
              tone={data.stock_source === "none" ? "warning" : "info"}
              title={t(`opening.stock.${data.stock_source}`, {
                day: f.date(data.as_of),
              })}
            />
          )}
          {data.rows.length === 0 ? (
            <EmptyState
              title={t("opening.empty")}
              text={t("opening.emptyText")}
            />
          ) : (
            <>
              <TextInput
                label={t("opening.search")}
                type="search"
                value={needle}
                onValueChange={setNeedle}
              />
              <div className="opening__list">
                {groups.slice(0, limit).map(card)}
              </div>
              {groups.length > limit && (
                <Button
                  variant="ghost"
                  onClick={() => setLimit((n) => n + PAGE)}
                >
                  {t("opening.more", { n: groups.length - limit })}
                </Button>
              )}
            </>
          )}
          {anyInvalid && <Banner tone="warning" title={t("opening.invalid")} />}
          {canManage && (
            <div className="settings-section__row">
              <Button
                variant="primary"
                disabled={anyInvalid || !startValue}
                loading={save.isPending && !save.variables}
                onClick={() => save.mutate(false)}
              >
                {t("opening.save")}
              </Button>
              {data.start_on !== null && (
                <Button
                  variant="ghost"
                  loading={save.isPending && save.variables}
                  onClick={() => save.mutate(true)}
                >
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

/** "Tannarx" ustuni sarlavhasidagi tugma (Uzum kabinetidagi kabi): narx yoziladi → ✓ → guruhning hamma turiga. */
function ApplyAll({
  title,
  onApply,
}: {
  title: string;
  onApply: (price: string | null) => void;
}) {
  const { t } = useTranslation();
  const [price, setPrice] = useState<string | null>(null);
  return (
    <Popover
      trigger={<ListChevronsUpDown size={16} aria-hidden />}
      label={t("opening.applyAllFor", { name: title })}
      triggerClassName="ui-icon-btn opening-table__apply"
    >
      {(close) => (
        <form
          className="opening-apply"
          onSubmit={(e) => {
            e.preventDefault();
            if (price === null) return;
            onApply(price);
            setPrice(null);
            close();
          }}
        >
          <MoneyInput
            label={t("opening.applyAll")}
            value={price}
            onValueChange={setPrice}
            autoFocus
          />
          <button
            type="submit"
            className="ui-icon-btn opening-apply__ok"
            aria-label={t("opening.apply")}
            disabled={price === null}
          >
            <Check size={18} aria-hidden />
          </button>
        </form>
      )}
    </Popover>
  );
}
