// Legacy import (B4.9, 03 §16): eski lokal dasturning `uzum.db` fayli → xaridlar. Fayl tanlanganda avval ko'rib chiqish
// (`dry_run`, server hech narsa yozmaydi, lekin hisobot haqiqiy hisob yo'li bilan) — har partiya legacy va yangi birlik
// tannarxi bilan solishtiriladi; "Import qilish" xuddi shuni yozadi. Qayta yuklash xavfsiz: ko'chirilgan partiya
// qayta yaratilmaydi. Hamma raqam serverdan (tamoyil 4); faqat egasi va menejer.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { importLegacy } from "../../app/query";
import { Badge, Banner, Button, DataTable, FileDrop, useToast, type Column, type Tone } from "../../components/ui";
import type { LegacyBatchReport, LegacyImport as Report } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

const STATUS_TONE: Record<string, Tone> = { created: "info", exists: "neutral", error: "negative" };

export function LegacyImport({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const [file, setFile] = useState<File | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const run = useMutation({
    mutationFn: ({ blob, dryRun }: { blob: File; dryRun: boolean }) => importLegacy(orgId, blob, dryRun),
    onSuccess: async (data) => {
      setReport(data);
      if (!data.dry_run) {
        // Xaridlar, ombor, tovarlar va (hisob ishidan keyin) foyda raqamlari o'zgaradi.
        await client.invalidateQueries({ queryKey: ["orgs", orgId], predicate: (q) => q.queryKey[2] !== "settings" });
        toast.show(t("settings.legacy.done", { count: data.created }), "positive");
      }
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const pick = (files: File[]) => {
    const next = files[0];
    if (!next) return;
    setFile(next);
    setReport(null);
    run.mutate({ blob: next, dryRun: true });
  };
  const money = (v: string | null | undefined) => (v == null ? "—" : f.money(v));
  const columns: Column<LegacyBatchReport>[] = [
    {
      key: "batch",
      header: t("settings.legacy.col.batch"),
      render: (b) => (
        <span>
          {b.purchase_id ? (
            <Link to="/purchases/$purchaseId" params={{ purchaseId: b.purchase_id }}>
              {b.title}
            </Link>
          ) : (
            <strong>{b.title}</strong>
          )}
          <span className="caption">
            {" "}
            · #{b.legacy_id}
            {b.day && ` · ${f.day(b.day)}`}
            {b.shop && ` · ${b.shop}`}
          </span>
        </span>
      ),
    },
    { key: "status", header: t("settings.legacy.col.status"), render: (b) => <Badge tone={STATUS_TONE[b.status] ?? "neutral"}>{t(`settings.legacy.status.${b.status}`)}</Badge> },
    { key: "units", header: t("settings.legacy.col.units"), numeric: true, render: (b) => f.number(b.units) },
    { key: "legacy", header: t("settings.legacy.col.legacy"), numeric: true, render: (b) => money(b.total_legacy) },
    { key: "new", header: t("settings.legacy.col.new"), numeric: true, render: (b) => money(b.total_new) },
    { key: "diff", header: t("settings.legacy.col.diff"), numeric: true, render: (b) => (b.worst_difference == null ? "—" : f.money(b.worst_difference)) },
    {
      key: "match",
      header: t("settings.legacy.col.match"),
      render: (b) =>
        b.match == null ? (
          "—"
        ) : (
          <Badge tone={b.match ? "positive" : "negative"}>{t(b.match ? "settings.legacy.match.yes" : "settings.legacy.match.no")}</Badge>
        ),
    },
  ];
  const notes = (report?.batches ?? []).flatMap((b) => [
    ...b.warnings.map((w) => ({ id: b.legacy_id, text: w })),
    ...(b.unmatched.length > 0 ? [{ id: b.legacy_id, text: t("settings.legacy.unmatched", { skus: b.unmatched.join(", ") }) }] : []),
    ...(b.new_items > 0 ? [{ id: b.legacy_id, text: t("settings.legacy.newItems", { count: b.new_items }) }] : []),
  ]);
  const offline = (report?.shops ?? []).filter((s) => !s.connected);
  return (
    <section className="settings-section" aria-labelledby="settings-legacy">
      <h2 id="settings-legacy" className="h3">
        {t("settings.legacy.title")}
      </h2>
      <p className="caption">{t("settings.legacy.lead")}</p>
      <FileDrop accept=".db,.sqlite,.sqlite3,application/octet-stream,application/x-sqlite3" onFiles={pick} hint={t("settings.legacy.hint")} />
      {run.isPending && <p role="status">{t(run.variables?.dryRun ? "settings.legacy.checking" : "settings.legacy.importing")}</p>}
      {report && (
        <>
          {report.dry_run ? (
            <Banner
              tone={report.mismatched > 0 || report.errors > 0 ? "warning" : "info"}
              title={t("settings.legacy.previewTitle", { file: file?.name ?? "uzum.db" })}
              action={
                <Button variant="primary" disabled={report.created === 0 || !file} loading={run.isPending && !run.variables?.dryRun} onClick={() => file && run.mutate({ blob: file, dryRun: false })}>
                  {t("settings.legacy.import", { count: report.created })}
                </Button>
              }
            >
              {t("settings.legacy.summary", { created: report.created, existing: report.existing, errors: report.errors, mismatched: report.mismatched })}
            </Banner>
          ) : (
            <Banner tone="positive" title={t("settings.legacy.done", { count: report.created })} action={<Link to="/purchases">{t("settings.legacy.toPurchases")}</Link>}>
              {t("settings.legacy.doneText")}
            </Banner>
          )}
          {offline.length > 0 && (
            <Banner tone="warning" title={t("settings.legacy.offline", { shops: offline.map((s) => `${s.name} (${s.legacy_id})`).join(", ") })} />
          )}
          <DataTable caption={t("settings.legacy.table")} columns={columns} rows={report.batches} rowKey={(b) => String(b.legacy_id)} density="compact" empty={t("settings.legacy.empty")} />
          {notes.length > 0 && (
            <div>
              <h3 className="label">{t("settings.legacy.notes")}</h3>
              <ul className="caption">
                {notes.map((n, i) => (
                  <li key={i}>
                    #{n.id}: {n.text}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </section>
  );
}
