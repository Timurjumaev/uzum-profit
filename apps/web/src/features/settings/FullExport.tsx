// To'liq eksport (B7.5, faqat egasi): "ma'lumot sizniki" — hamma kiritilgan va Uzumdan olingan ma'lumot ZIP'da (CSV + JSON).
// Tartib: so'rov → fon ishi (holat har 5 soniyada yangilanadi) → bir martalik 24 soatlik havola → yuklash. Kuniga bir marta.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, PackageOpen } from "lucide-react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { fullExportLink, fullExportsQuery, requestFullExport } from "../../app/query";
import { Button, StatusPill, useToast, type Tone } from "../../components/ui";
import { formatDate } from "../../lib/format";
import type { FullExport as Item } from "../../lib/api/types";

const TONE: Record<string, Tone> = { pending: "info", running: "info", ready: "positive", failed: "negative", expired: "neutral" };

export function megabytes(bytes: number | null): string {
  return `${((bytes ?? 0) / (1024 * 1024)).toFixed(1)} MB`;
}

export function FullExport({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuery(fullExportsQuery(orgId));
  const refresh = () => client.invalidateQueries({ queryKey: ["orgs", orgId, "exports-full"] });
  const request = useMutation({
    mutationFn: () => requestFullExport(orgId),
    onSuccess: async () => {
      toast.show(t("settings.fullExport.requested"), "positive");
      await refresh();
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const download = useMutation({
    mutationFn: (item: Item) => fullExportLink(orgId, item.id),
    onSuccess: async (link) => {
      const a = document.createElement("a");
      a.href = link.url;
      document.body.append(a);
      a.click();
      a.remove();
      await refresh();
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const items = query.data ?? [];
  const busy = items.some((e) => e.status === "pending" || e.status === "running");
  return (
    <section className="settings-section full-export" aria-labelledby="settings-full-export">
      <h2 id="settings-full-export" className="h3">
        <PackageOpen size={20} aria-hidden className="full-export__icon" /> {t("settings.fullExport.title")}
      </h2>
      <p className="caption">{t("settings.fullExport.lead")}</p>
      <p className="caption">{t("settings.fullExport.excluded")}</p>
      <div className="settings-section__row">
        <Button variant="primary" loading={request.isPending || busy} disabled={busy} onClick={() => request.mutate()}>
          {t("settings.fullExport.request")}
        </Button>
      </div>
      {items.length > 0 && (
        <ul className="full-export__list">
          {items.map((e) => (
            <li key={e.id} className="full-export__item">
              <StatusPill tone={TONE[e.status] ?? "neutral"}>{t(`settings.fullExport.status.${e.status}`)}</StatusPill>
              <span className="caption">{formatDate(e.created_at)}</span>
              {e.status === "ready" && <span className="caption">{megabytes(e.size_bytes)}</span>}
              {e.status === "ready" && e.expires_at && <span className="caption">{t("settings.fullExport.until", { when: formatDate(e.expires_at) })}</span>}
              {e.status === "ready" && e.downloaded && <span className="caption">{t("settings.fullExport.downloaded")}</span>}
              {e.status === "ready" && (
                <Button size="sm" variant="secondary" icon={<Download size={16} aria-hidden />} loading={download.isPending} onClick={() => download.mutate(e)}>
                  {t("settings.fullExport.download")}
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
