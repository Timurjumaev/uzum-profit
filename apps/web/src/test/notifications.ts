// Namunaviy `/notifications/settings` javobi (B6.1). Vitest'ga bog'liq emas (e2e ham ishlatadi).
import type { NotificationEvent, NotificationSettings } from "../lib/api/types";

/** Bildirishnoma sozlamalari (B6.1): katalog standartlari bilan. */
export function notificationSettings(over: Partial<NotificationSettings> = {}): NotificationSettings {
  const ev = (event: NotificationEvent["event"], extra: Partial<NotificationEvent> = {}): NotificationEvent => ({ event, enabled: true, params: {}, critical: false, available: true, stage: null, ...extra });
  return {
    events: [
      ev("daily_summary", { params: { at: "09:00" } }),
      ev("weekly_summary", { params: { at: "09:00" } }),
      ev("stock_critical"),
      ev("ship_needed"),
      ev("loss_sales", { params: { streak: 3 } }),
      ev("new_fine"),
      ev("sync_stopped", { critical: true, params: { hours: 2 } }),
      ev("payout_late", { available: false, stage: "B5.7" }),
      ev("returns_spike", { params: { level: null, min_returns: null } }),
    ],
    quiet_from: "22:00:00",
    quiet_to: "08:00:00",
    telegram_linked: false,
    ...over,
  };
}

