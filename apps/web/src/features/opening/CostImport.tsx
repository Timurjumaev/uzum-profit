// Tannarxni Excel orqali kiritish (B7.1, ADR-065): jadvalni yuklab oling → "Tannarx, so'm" ustunini to'ldiring → qayta yuklang →
// AVVAL ko'rib chiqish (yangi / ustidan yoziladi eski → yangi / xato — qator va sabab) → tasdiqdan keyin saqlash. Bo'sh katak
// tegilmaydi; o'sha faylni qayta yuklash hech narsani o'zgartirmaydi. Hisob va tekshiruv serverda; fayl brauzerdan diskka yozilmaydi.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { applyCosts, previewCosts } from "../../app/query";
import { fileName } from "../../components/ui/ExportButton";
import { Badge, Banner, Button, Dialog, useToast } from "../../components/ui";
import type { CostPreview } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

const SHOWN = 100; // jadvalda ko'rsatiladigan eng ko'p qator (saqlashga hammasi ketadi)

export function CostImport({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const input = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState<CostPreview | null>(null);
  const [busy, setBusy] = useState(false);
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");

  const download = async () => {
    setBusy(true);
    try {
      const response = await fetch(new Request(new URL(`/api/v1/orgs/${orgId}/opening/costs.xlsx`, globalThis.location.origin).href, { credentials: "include" }));
      if (!response.ok) throw new Error(String(response.status));
      const blob = await response.blob();
      const link = document.createElement("a");
      const href = URL.createObjectURL(blob);
      link.href = href;
      link.download = fileName(response.headers.get("Content-Disposition"), "tannarx.xlsx");
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
  const upload = useMutation({ mutationFn: (file: File) => previewCosts(orgId, file), onSuccess: setPreview, onError: fail });
  const apply = useMutation({
    mutationFn: () => applyCosts(orgId, (preview?.changes ?? []).map((c) => ({ key: c.key, unit_cost: c.new }))),
    onSuccess: async (out) => {
      toast.show(t("opening.excel.saved", { n: out.saved }), "positive");
      setPreview(null);
      await client.invalidateQueries({ queryKey: ["orgs", orgId] });
    },
    onError: fail,
  });
  const pick = (file: File | undefined) => {
    if (input.current) input.current.value = ""; // o'sha faylni qayta tanlash ham ishlasin
    if (file) upload.mutate(file);
  };
  const close = () => setPreview(null);
  const total = preview ? preview.new + preview.changed : 0;
  return (
    <section className="cost-import" aria-label={t("opening.excel.title")}>
      <div className="cost-import__text">
        <h2 className="h3">{t("opening.excel.title")}</h2>
        <p className="caption">{t("opening.excel.lead")}</p>
      </div>
      <div className="cost-import__actions">
        <Button variant="secondary" icon={<Download size={16} aria-hidden />} loading={busy} onClick={() => void download()}>
          {t("opening.excel.download")}
        </Button>
        <Button variant="primary" icon={<Upload size={16} aria-hidden />} loading={upload.isPending} onClick={() => input.current?.click()}>
          {t("opening.excel.upload")}
        </Button>
        <input ref={input} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" className="ui-visually-hidden" tabIndex={-1} aria-label={t("opening.excel.file")} onChange={(e) => pick(e.target.files?.[0])} />
      </div>
      <Dialog
        open={preview !== null}
        onClose={close}
        title={t("opening.excel.previewTitle")}
        footer={
          <>
            <Button variant="ghost" onClick={close}>
              {t("opening.excel.cancel")}
            </Button>
            <Button variant="primary" disabled={total === 0} loading={apply.isPending} onClick={() => apply.mutate()}>
              {t("opening.excel.apply", { n: total })}
            </Button>
          </>
        }
      >
        {preview && (
          <div className="cost-import__preview">
            <ul className="cost-import__stats" aria-label={t("opening.excel.stats")}>
              <li>
                <Badge tone="positive">{t("opening.excel.new", { n: preview.new })}</Badge>
              </li>
              <li>
                <Badge tone={preview.changed > 0 ? "warning" : "neutral"}>{t("opening.excel.changed", { n: preview.changed })}</Badge>
              </li>
              <li>
                <Badge tone="neutral">{t("opening.excel.same", { n: preview.same })}</Badge>
              </li>
              <li>
                <Badge tone="neutral">{t("opening.excel.empty", { n: preview.empty })}</Badge>
              </li>
              <li>
                <Badge tone={preview.error_count > 0 ? "negative" : "neutral"}>{t("opening.excel.errors", { n: preview.error_count })}</Badge>
              </li>
            </ul>
            {preview.changed > 0 && (
              <Banner tone="warning" title={t("opening.excel.overwriteTitle", { n: preview.changed })}>
                {t("opening.excel.overwriteText")}
              </Banner>
            )}
            {total === 0 && preview.error_count === 0 && <p className="muted">{t("opening.excel.nothing")}</p>}
            {preview.changes.length > 0 && (
              <table className="cost-import__table">
                <caption className="ui-visually-hidden">{t("opening.excel.changesCaption")}</caption>
                <thead>
                  <tr>
                    <th scope="col">{t("opening.excel.row")}</th>
                    <th scope="col">{t("opening.excel.name")}</th>
                    <th scope="col">{t("opening.excel.was")}</th>
                    <th scope="col">{t("opening.excel.now")}</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.changes.slice(0, SHOWN).map((c) => (
                    <tr key={c.key}>
                      <td>{c.row}</td>
                      <th scope="row">{c.name}</th>
                      <td>{c.old === null ? <Badge tone="positive">{t("opening.excel.newBadge")}</Badge> : f.money(c.old)}</td>
                      <td>
                        <strong>{f.money(c.new)}</strong>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            {preview.changes.length > SHOWN && <p className="caption">{t("opening.excel.more", { n: preview.changes.length - SHOWN })}</p>}
            {preview.error_count > 0 && (
              <div className="cost-import__errors" role="alert">
                <h3 className="h4">{t("opening.excel.errorsTitle", { n: preview.error_count })}</h3>
                <ul>
                  {preview.errors.map((e) => (
                    <li key={e.row}>{t("opening.excel.errorRow", { row: e.row, reason: e.reason })}</li>
                  ))}
                </ul>
                {preview.error_count > preview.errors.length && <p className="caption">{t("opening.excel.more", { n: preview.error_count - preview.errors.length })}</p>}
              </div>
            )}
          </div>
        )}
      </Dialog>
    </section>
  );
}
