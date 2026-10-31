// Excel eksport tugmasi (B4.10, 03 §8): server `.xlsx` yig'adi (ro'yxat bilan bir xil filtr), brauzer faylni yuklaydi.
// Kirish cookie orqali; xato — toast (fayl o'rniga JSON ochilmaydi). Yuklanayotganda tugma band.
import { Download } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "./Button";
import { useToast } from "./Toast";

export type ExportQuery = Record<string, string | string[] | undefined | null>;

/** `/api/v1/orgs/{org}/exports/{table}.xlsx?...` — bo'sh qiymatlar tushiriladi, massiv takrorlanadi (`shop=a&shop=b`). */
export function exportUrl(orgId: string, table: string, query: ExportQuery = {}): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    for (const v of Array.isArray(value) ? value : [value]) params.append(key, v);
  }
  const qs = params.toString();
  return `/api/v1/orgs/${orgId}/exports/${table}.xlsx${qs ? `?${qs}` : ""}`;
}

/** `Content-Disposition: attachment; filename="x.xlsx"` → `x.xlsx` (yo'q bo'lsa `fallback`). */
export function fileName(header: string | null, fallback: string): string {
  const match = header ? /filename="([^"]+)"/.exec(header) : null;
  return match?.[1] ?? fallback;
}

type Props = { orgId: string; table: string; query?: ExportQuery; disabled?: boolean };

export function ExportButton({ orgId, table, query, disabled }: Props) {
  const { t } = useTranslation();
  const toast = useToast();
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    try {
      const response = await fetch(new Request(new URL(exportUrl(orgId, table, query), globalThis.location.origin).href, { credentials: "include" }));
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      const link = document.createElement("a");
      const href = URL.createObjectURL(blob);
      link.href = href;
      link.download = fileName(response.headers.get("Content-Disposition"), `${table}.xlsx`);
      document.body.append(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(href);
    } catch {
      toast.show(t("ui.exportFailed"), "negative");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Button variant="secondary" size="sm" icon={<Download size={16} aria-hidden />} loading={busy} disabled={disabled} onClick={() => void run()}>
      {t("ui.exportExcel")}
    </Button>
  );
}
