// Hisobdan chiqarish va inventarizatsiya tuzatishi (M10, B4.7): tovar bo'yicha. Hisobdan chiqarish — brak, yo'qotish,
// kamomad (musbat dona); tuzatish — ishorali dona (omborni sanab chiqqandan keyin). Yozuv tannarx dvigatelida lotdan
// chiqim (F21) — o'tgan sotuvlar tannarxi qayta hisoblanadi. Eski yozuvni o'chirib, qaytarish mumkin (sotuvchi
// kiritgani jim o'zgarmaydi: har o'zgarish ko'rinadi va qaytariladi).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createStockMove, deleteStockMove, stockMovesQuery } from "../../app/query";
import { Banner, Button, Dialog, NumberInput, Select, TextInput, useToast } from "../../components/ui";
import { todayTashkent } from "../../lib/dates";
import { useFormat } from "../../lib/i18n";

type Kind = "writeoff" | "adjust";

export function StockMoveForm({ orgId, itemId, title, onClose }: { orgId: string; itemId: string; title: string; onClose: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const moves = useQuery(stockMovesQuery(orgId, itemId));
  const today = todayTashkent();
  const [kind, setKind] = useState<Kind>("writeoff");
  const [qty, setQty] = useState<string | null>(null);
  const [day, setDay] = useState(today);
  const [note, setNote] = useState("");
  const amount = qty === null ? null : Number(qty);
  const valid = amount !== null && Number.isInteger(amount) && (kind === "writeoff" ? amount > 0 : amount !== 0) && day !== "" && day <= today;
  const refresh = async () => {
    await client.invalidateQueries({ queryKey: ["orgs", orgId, "inventory"] });
    await client.invalidateQueries({ queryKey: ["orgs", orgId, "stock-moves", itemId] });
  };
  const save = useMutation({
    mutationFn: () => createStockMove(orgId, { item_id: itemId, kind, qty: amount!, day, note: note.trim() || null }),
    onSuccess: async () => {
      await refresh();
      toast.show(t("inventory.move.saved"), "positive");
      setQty(null);
      setNote("");
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => deleteStockMove(orgId, id),
    onSuccess: async () => {
      await refresh();
      toast.show(t("inventory.move.removed"), "positive");
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (valid) save.mutate();
  };
  const error = save.error ?? remove.error;
  return (
    <Dialog
      open
      title={t("inventory.move.title", { name: title })}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("inventory.move.close")}
          </Button>
          <Button type="submit" form="stock-move-form" disabled={!valid} loading={save.isPending}>
            {t("inventory.move.save")}
          </Button>
        </>
      }
    >
      <form id="stock-move-form" className="inventory-move" onSubmit={submit}>
        {error && <Banner tone="negative" title={errorText(error, t)} />}
        <p className="caption">{t("inventory.move.hint")}</p>
        <Select
          label={t("inventory.move.kind")}
          value={kind}
          onValueChange={(v) => setKind(v as Kind)}
          options={[
            { value: "writeoff", label: t("inventory.move.kinds.writeoff") },
            { value: "adjust", label: t("inventory.move.kinds.adjust") },
          ]}
        />
        <NumberInput label={t("inventory.move.qty")} help={t(`inventory.move.qtyHint.${kind}`)} value={qty} onValueChange={setQty} digits={0} suffix={t("inventory.unit")} />
        <TextInput label={t("inventory.move.day")} type="date" max={today} value={day} onValueChange={setDay} />
        <TextInput label={t("inventory.move.note")} optional value={note} onValueChange={setNote} maxLength={500} />
      </form>
      <h3 className="h3 inventory-move__history-title">{t("inventory.move.history")}</h3>
      {moves.isError ? (
        <Banner tone="negative" title={errorText(moves.error, t)} />
      ) : !moves.data ? (
        <p className="caption">{t("common.loading")}</p>
      ) : moves.data.items.length === 0 ? (
        <p className="caption">{t("inventory.move.empty")}</p>
      ) : (
        <ul className="inventory-move__history" aria-label={t("inventory.move.history")}>
          {moves.data.items.map((m) => (
            <li key={m.id}>
              <span>
                {f.date(m.day)} · {t(`inventory.move.kinds.${m.kind as Kind}`)} · <strong>{m.kind === "adjust" && m.qty > 0 ? `+${f.number(m.qty)}` : f.number(m.kind === "writeoff" ? -m.qty : m.qty)}</strong>
                {m.note && <span className="caption"> — {m.note}</span>}
              </span>
              <button
                type="button"
                className="ui-icon-btn"
                aria-label={t("inventory.move.remove", { date: f.date(m.day) })}
                disabled={remove.isPending}
                onClick={() => remove.mutate(m.id)}
              >
                <Trash2 size={16} aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Dialog>
  );
}
