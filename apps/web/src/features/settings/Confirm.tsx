// Tasdiqlash oynasi (o'chirish va tannarx usulini almashtirish).
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import { Button, Dialog } from "../../components/ui";

export function Confirm({ title, children, action, loading, destructive = true, onConfirm, onClose }: { title: string; children: ReactNode; action: string; loading?: boolean; destructive?: boolean; onConfirm: () => void; onClose: () => void }) {
  const { t } = useTranslation();
  return (
    <Dialog
      open
      title={title}
      onClose={onClose}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            {t("settings.cancel")}
          </Button>
          <Button variant={destructive ? "destructive" : "primary"} loading={loading} onClick={onConfirm}>
            {action}
          </Button>
        </>
      }
    >
      <p>{children}</p>
    </Dialog>
  );
}
