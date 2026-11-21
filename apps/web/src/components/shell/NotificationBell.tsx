// Bildirishnomalar markazi (B6.3, ADR-064): qo'ng'iroq + o'qilmaganlar soni + ro'yxat. Manba — `GET /notifications` (Telegram
// ulanmagan a'zoning qatorlari ham shu yerda). Yetkazish holati (Telegram'ga yuborildi / yuborilmadi) o'qilganlikdan alohida
// ko'rsatiladi. Qator bosilsa — o'qilgan va o'sha hodisaning sahifasi ochiladi ("Batafsil"). Web push va oflayn kesh yo'q (Keyinga).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { Bell } from "lucide-react";
import { useTranslation } from "react-i18next";

import { markNotificationsRead, notificationsQuery } from "../../app/query";
import type { NotificationItem } from "../../lib/api/types";
import { useFormat } from "../../lib/i18n";
import { Badge, Button, Popover, type Tone } from "../ui";
import type { NavTo } from "./nav";

/** Hodisa → "Batafsil" sahifasi (botdagi bilan bir xil; 02 M15). */
export const EVENT_PATH: Record<string, NavTo> = {
  daily_summary: "/",
  weekly_summary: "/pnl",
  stock_critical: "/inventory",
  ship_needed: "/inventory",
  loss_sales: "/products",
  uncosted_sales: "/products",
  new_fine: "/expenses",
  returns_spike: "/orders",
  receiving_shortage: "/inventory",
  lost_goods: "/inventory",
  sync_stopped: "/status",
  payout_late: "/cash",
  cargo_late: "/purchases",
  commission_changed: "/products",
  fbs_deadline: "/inventory",
  uncounted_purchase: "/purchases",
  goal_behind: "/goals",
};

const DELIVERY_TONE: Record<string, Tone> = { sent: "positive", pending: "neutral", failed: "negative" };

export function NotificationBell({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const f = useFormat();
  const client = useQueryClient();
  const navigate = useNavigate();
  const query = useQuery(notificationsQuery(orgId));
  const items = query.data?.items ?? [];
  const unread = query.data?.unread ?? 0;
  const read = useMutation({
    mutationFn: (ids?: string[]) => markNotificationsRead(orgId, ids),
    onSuccess: (data) => client.setQueryData(notificationsQuery(orgId).queryKey, data),
  });
  const open = (item: NotificationItem, close: () => void) => {
    if (item.read_at === null) read.mutate([item.id]);
    close();
    const to = EVENT_PATH[item.event];
    if (to) void navigate({ to });
  };
  const count = typeof unread === "number" && unread > 99 ? "99+" : String(unread);
  return (
    <Popover
      align="end"
      label={unread > 0 ? t("notifCenter.labelUnread", { count: unread }) : t("notifCenter.label")}
      triggerClassName="ui-icon-btn topbar__bell"
      trigger={
        <span className="bell">
          <Bell size={20} aria-hidden />
          {unread > 0 && (
            <span className="bell__count" data-testid="bell-count" aria-hidden>
              {count}
            </span>
          )}
        </span>
      }
    >
      {(close) => (
        <div className="notif" role="region" aria-label={t("notifCenter.title")}>
          <div className="notif__head">
            <strong>{t("notifCenter.title")}</strong>
            <Button variant="ghost" size="sm" disabled={unread === 0 || read.isPending} onClick={() => read.mutate(undefined)}>
              {t("notifCenter.markAll")}
            </Button>
          </div>
          {items.length === 0 ? (
            <p className="muted notif__empty">{t("notifCenter.empty")}</p>
          ) : (
            <ul className="notif__list">
              {items.map((item) => (
                <li key={item.id}>
                  <button type="button" className={`notif__item${item.read_at === null ? " notif__item--unread" : ""}`} onClick={() => open(item, close)}>
                    <span className="notif__title">{t(`settings.notifications.event.${item.event}`, { defaultValue: item.event })}</span>
                    <span className="caption notif__meta">
                      {f.relative(item.created_at)}
                      <Badge tone={DELIVERY_TONE[item.status] ?? "neutral"}>{t(`notifCenter.delivery.${item.status}`, { defaultValue: item.status })}</Badge>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </Popover>
  );
}
