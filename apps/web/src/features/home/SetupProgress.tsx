// "Sozlash: N/6" (B8.12, 09 R3 d): yangi foydalanuvchiga nima qolganini ko'rsatadigan jonli kartochka — Bosh sahifada, hammasi
// tugaguncha. Hisob — serverdan kelgan ma'lumotlardan (sozlama, sinxron, tannarxsiz qatorlar, Telegram); faqat egasi va menejerga.
import { useQuery } from "@tanstack/react-query";
import { Link } from "@tanstack/react-router";
import { CircleCheck, Circle, Rocket } from "lucide-react";
import { useTranslation } from "react-i18next";

import { notificationSettingsQuery, settingsQuery } from "../../app/query";
import { ProgressBar } from "../../components/ui";
import type { Settings } from "../../lib/api/types";

export type SetupItem = { id: "shops" | "history" | "tax" | "payout" | "costs" | "telegram"; done: boolean; to: "/settings" | "/status" | "/products" | "/opening" };

/** 6 ta qadam holati (sof funksiya — testlanadi). `uncosted` — tannarxsiz qatorlar soni, `lines` — davrdagi jami qatorlar. */
export function setupItems(input: { shops: number; historyLoaded: boolean; settings: Settings; uncosted: number; lines: number; telegram: boolean }): SetupItem[] {
  const { settings } = input;
  return [
    { id: "shops", done: input.shops > 0, to: "/settings" },
    { id: "history", done: input.historyLoaded, to: "/status" },
    { id: "tax", done: settings.tax_profiles.some((p) => p.regime !== "none"), to: "/settings" },
    { id: "payout", done: settings.payout_schedules.length > 0, to: "/settings" },
    { id: "costs", done: input.lines > 0 && input.uncosted === 0, to: "/opening" },
    { id: "telegram", done: input.telegram, to: "/settings" },
  ];
}

export function SetupProgress({ orgId, shops, historyLoaded, uncosted, lines }: { orgId: string; shops: number; historyLoaded: boolean; uncosted: number; lines: number }) {
  const { t } = useTranslation();
  const settings = useQuery(settingsQuery(orgId));
  const notify = useQuery(notificationSettingsQuery(orgId));
  if (!settings.data || notify.data === undefined) return null;
  const items = setupItems({ shops, historyLoaded, settings: settings.data, uncosted, lines, telegram: notify.data.telegram_linked });
  const done = items.filter((i) => i.done).length;
  if (done === items.length) return null;
  return (
    <aside className="setup-progress" aria-label={t("home.setup.title", { done, total: items.length })}>
      <span className="setup-progress__icon" aria-hidden>
        <Rocket size={22} />
      </span>
      <div className="setup-progress__body">
        <strong>{t("home.setup.title", { done, total: items.length })}</strong>
        <ProgressBar label={t("home.setup.title", { done, total: items.length })} value={done} max={items.length} />
        <ul className="setup-progress__list">
          {items.map((item) => (
            <li key={item.id} className={item.done ? "is-done" : undefined}>
              {item.done ? <CircleCheck size={16} aria-hidden /> : <Circle size={16} aria-hidden />}
              {item.done ? (
                <span>{t(`home.setup.items.${item.id}`)}</span>
              ) : (
                <Link to={item.to}>{t(`home.setup.items.${item.id}`)}</Link>
              )}
            </li>
          ))}
        </ul>
      </div>
    </aside>
  );
}
