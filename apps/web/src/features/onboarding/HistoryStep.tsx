// 3-qadam: tarix yuklanmoqda (M2). Har faol do'kon × ma'lumot turi bo'yicha progress; foydalanuvchi kutmaydi — istalgan
// payt bosh sahifaga o'tadi (yuklash fonda davom etadi, uzilsa qolgan joydan). Holat har 5 soniyada yangilanadi.
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { syncQuery } from "../../app/query";
import { Banner, Button, ProgressBar, Skeleton, StatusPill } from "../../components/ui";
import { useFormat } from "../../lib/i18n";
import type { SyncStatus } from "../../lib/sync";

export const HISTORY_POLL_MS = 5000;

type ShopStatus = SyncStatus["shops"][number];

/** Hamma tur yakunlangan (davom etayotgani yo'q) va buyurtmalar tarixi yozilgan. */
export function shopLoaded(shop: ShopStatus): boolean {
  return shop.history_status !== null && shop.kinds.every((k) => k.status !== "running");
}

export function HistoryStep({ orgId, onDone }: { orgId: string; onDone: () => void }) {
  const { t } = useTranslation();
  const f = useFormat();
  const query = useQuery({ ...syncQuery(orgId), refetchInterval: HISTORY_POLL_MS });
  const shops = (query.data?.shops ?? []).filter((s) => s.active);
  const loaded = shops.length > 0 && shops.every(shopLoaded);
  const failed = shops.some((s) => s.kinds.some((k) => k.status === "error"));
  return (
    <div className="onb__form">
      <h2>{t("onboarding.history.title")}</h2>
      <p className="muted">{t("onboarding.history.lead")}</p>
      {query.isError && <Banner tone="negative" title={errorText(query.error, t)} />}
      {query.isPending && <Skeleton label={t("common.loading")} lines={4} />}
      {loaded ? (
        <Banner tone="info" title={t("onboarding.history.done")}>
          {t("onboarding.history.doneText")}
        </Banner>
      ) : (
        failed && (
          <Banner tone="warning" title={t("onboarding.history.failed")}>
            <p>{t("onboarding.history.failedText")}</p>
          </Banner>
        )
      )}
      <ul className="onb__history">
        {shops.map((shop) => (
          <li key={shop.id}>
            <h3>{shop.alias || shop.name}</h3>
            <div className="onb__history-kinds">
              {shop.kinds
                .filter((k) => k.status !== null)
                .map((k) => {
                  const label = t(`sync.kinds.${k.kind}`, { defaultValue: k.kind });
                  const done = k.written ?? k.fetched ?? 0;
                  if (k.status === "error") {
                    return (
                      <div key={k.kind} className="onb__history-row">
                        <span>{label}</span>
                        <StatusPill tone="negative">{k.error ?? t("status.run.error")}</StatusPill>
                      </div>
                    );
                  }
                  if (k.total) {
                    return <ProgressBar key={k.kind} label={label} value={done} max={k.total} detail={t("ui.progress", { done: f.number(done), total: f.number(k.total) })} />;
                  }
                  return (
                    <div key={k.kind} className="onb__history-row">
                      <span>{label}</span>
                      {k.status === "running" ? (
                        <StatusPill tone="info">{t("onboarding.history.running", { value: f.number(done) })}</StatusPill>
                      ) : (
                        <StatusPill tone="positive">{t("status.run.ok")}</StatusPill>
                      )}
                    </div>
                  );
                })}
            </div>
          </li>
        ))}
      </ul>
      <p className="muted">{t("onboarding.history.next")}</p>
      <div className="onb__actions">
        <Link to="/status" className="ui-btn ui-btn--ghost ui-btn--lg">
          {t("sync.details")}
        </Link>
        <Button variant={loaded ? "primary" : "secondary"} size="lg" onClick={onDone}>
          {loaded ? t("onboarding.history.finish") : t("onboarding.history.skip")}
        </Button>
      </div>
    </div>
  );
}
