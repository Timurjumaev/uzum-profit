// F50 (B4.80, ADR-058): yillik tushum chegarasi — hisob serverda (`upcore.tax.revenue_limit_status`), bu yerda faqat
// ko'rsatish. 80% dan — ogohlantirish (warning), 100% dan — oshdi (negative); rejim o'zi almashmaydi.
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Banner } from "../../components/ui";
import type { Settings } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";

type Limit = Settings["revenue_limit"];

function useParts(limit: NonNullable<Limit>) {
  const { t } = useTranslation();
  const f = useFormat();
  return {
    year: limit.year,
    revenue: f.money(limit.revenue),
    limit: f.money(limit.limit),
    share: f.percent(limit.share, { digits: 0 }),
    taxpayer: t(`settings.tax.taxpayer.${limit.taxpayer}`),
  };
}

/** Bosh sahifa va Sozlamalar: faqat chegaraga yaqin (≥ 80%) yoki oshgan bo'lsa. */
export function RevenueLimitBanner({ limit, action }: { limit: Limit; action?: ReactNode }) {
  if (!limit || limit.level === "ok") return null;
  return <Warning limit={limit} action={action} />;
}

function Warning({ limit, action }: { limit: NonNullable<Limit>; action?: ReactNode }) {
  const { t } = useTranslation();
  const parts = useParts(limit);
  const over = limit.level === "over";
  return (
    <Banner tone={over ? "negative" : "warning"} title={t(over ? "settings.tax.limit.overTitle" : "settings.tax.limit.nearTitle", parts)} action={action}>
      {t("settings.tax.limit.text", parts)}
    </Banner>
  );
}

/** Sozlamalar → Soliq profili: joriy holat (doim), yaqin yoki oshgan bo'lsa — ogohlantirish bilan. */
export function RevenueLimitStatus({ limit }: { limit: Limit }) {
  const { t } = useTranslation();
  return (
    <section className="settings-limit" aria-labelledby="settings-limit">
      <h3 id="settings-limit" className="label">
        {t("settings.tax.limit.title")}
      </h3>
      {limit ? <Known limit={limit} /> : <p className="caption">{t("settings.tax.limit.none")}</p>}
    </section>
  );
}

function Known({ limit }: { limit: NonNullable<Limit> }) {
  const { t } = useTranslation();
  const parts = useParts(limit);
  return (
    <>
      <p>{t("settings.tax.limit.status", parts)}</p>
      <p className="caption">{t("settings.tax.limit.note")}</p>
      <RevenueLimitBanner limit={limit} />
    </>
  );
}
