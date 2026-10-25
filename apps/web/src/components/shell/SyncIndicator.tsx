// SyncIndicator (04 §5; M3 "Ma'lumot yangiligi"): "Yangilandi: 3 daqiqa oldin" + holat belgisi (ikon + matn, rang
// yolg'iz emas). Bosilsa — ma'lumot turlari bo'yicha oxirgi sinxron, "Hozir yangilash" va "Ma'lumotlar holati".
// Uzilish banneri ham shu so'rovdan (`OutageBanner`).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { RefreshCw } from "lucide-react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { refreshSync, syncQuery } from "../../app/query";
import { useFormat } from "../../lib/i18n";
import { syncSummary, type SyncState } from "../../lib/sync";
import { TONE_ICON } from "../ui/Badge";
import { Banner, Button, Popover, useToast } from "../ui";
import { cx } from "../ui/cx";

const STATE_TEXT: Record<SyncState, string> = {
  outage: "sync.outage",
  errors: "sync.errors",
  never: "sync.never",
  stale: "sync.stale",
  fresh: "sync.updated",
};

const STATE_HELP: Partial<Record<SyncState, string>> = {
  outage: "sync.outageText",
  errors: "sync.errorsText",
  never: "sync.neverText",
  stale: "sync.staleText",
};

export function SyncIndicator({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuery(syncQuery(orgId));
  const refresh = useMutation({
    mutationFn: () => refreshSync(orgId),
    onSuccess: () => {
      toast.show(t("sync.refreshStarted"));
      void client.invalidateQueries({ queryKey: syncQuery(orgId).queryKey });
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const status = query.data;
  const summary = status ? syncSummary(status) : null;
  const tone = summary?.tone ?? "warning";
  const Icon = TONE_ICON[tone];
  const ago = summary?.at ? f.relative(summary.at) : "";
  const text = !summary ? t("sync.unknown") : t(STATE_TEXT[summary.state], { ago });
  const help = summary && STATE_HELP[summary.state];
  return (
    <Popover
      align="end"
      label={`${t("sync.title")}: ${text}`}
      triggerClassName={cx("ui-btn ui-btn--ghost ui-btn--md sync", `sync--${tone}`)}
      trigger={
        <>
          <Icon size={16} aria-hidden />
          <span className="sync__text">{text}</span>
        </>
      }
    >
      <div className="syncpanel">
        <h3>{t("sync.title")}</h3>
        {help && <p className="muted">{t(help)}</p>}
        {query.isError && <p role="alert">{errorText(query.error, t)}</p>}
        {status && (
          <dl className="syncpanel__kinds">
            {Object.entries(status.freshness).map(([kind, at]) => (
              <div key={kind}>
                <dt>{t(`sync.kinds.${kind}`, { defaultValue: kind })}</dt>
                <dd>{at ? f.relative(at) : t("sync.kindNever")}</dd>
              </div>
            ))}
          </dl>
        )}
        <div className="syncpanel__actions">
          <Button
            size="sm"
            icon={<RefreshCw size={16} aria-hidden />}
            loading={refresh.isPending}
            disabled={status?.outage.active}
            onClick={() => refresh.mutate()}
          >
            {t("sync.refresh")}
          </Button>
          <Link to="/status" search={(prev) => prev} className="ui-btn ui-btn--ghost ui-btn--sm">
            {t("sync.details")}
          </Link>
        </div>
      </div>
    </Popover>
  );
}

/** Uzum uzilishi (M3): sariq banner — "sotuv yo'q" ga ishonmaslik haqida. */
export function OutageBanner({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const { data } = useQuery(syncQuery(orgId));
  if (!data?.outage.active) return null;
  return (
    <div className="app__banner">
      <Banner tone="warning" title={t("sync.outageTitle")}>
        {t("sync.outageText")}
      </Banner>
    </div>
  );
}
