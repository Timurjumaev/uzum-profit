// Tashkilotni o'chirish (B8.13, faqat egasi): so'rov → 30 kun kutish (bekor qilsa bo'ladi) → butunlay o'chadi.
// Oldin to'liq eksport tavsiya qilinadi (yuqoridagi bo'lim). Tasdiq oynasi — qaytarib bo'lmaydigan oqibat haqida.
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { cancelOrgDeletion, orgDeletionKey, orgDeletionQuery, requestOrgDeletion } from "../../app/query";
import { Banner, Button, useToast } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { Confirm } from "./Confirm";

export function OrgDeletion({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const query = useQuery(orgDeletionQuery(orgId));
  const [asking, setAsking] = useState(false);
  const done = async (message: string) => {
    await client.invalidateQueries({ queryKey: orgDeletionKey(orgId) });
    toast.show(message, "positive");
  };
  const request = useMutation({
    mutationFn: () => requestOrgDeletion(orgId),
    onSuccess: async () => {
      setAsking(false);
      await done(t("settings.orgDeletion.requested"));
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const cancel = useMutation({
    mutationFn: () => cancelOrgDeletion(orgId),
    onSuccess: () => done(t("settings.orgDeletion.cancelled")),
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const data = query.data;
  const pending = data?.requested_at != null;
  return (
    <section className="settings-section org-deletion" aria-labelledby="settings-org-deletion">
      <h2 id="settings-org-deletion" className="h3">
        <Trash2 size={20} aria-hidden className="org-deletion__icon" /> {t("settings.orgDeletion.title")}
      </h2>
      <p className="caption">{t("settings.orgDeletion.lead")}</p>
      {pending && data?.delete_on ? (
        <Banner tone="warning" title={t("settings.orgDeletion.pendingTitle", { date: formatDate(data.delete_on), days: data.days_left ?? 0 })}>
          {t("settings.orgDeletion.pendingText")}
        </Banner>
      ) : null}
      <div className="settings-section__row">
        {pending ? (
          <Button variant="primary" loading={cancel.isPending} onClick={() => cancel.mutate()}>
            {t("settings.orgDeletion.cancel")}
          </Button>
        ) : (
          <Button variant="destructive" disabled={!data} onClick={() => setAsking(true)}>
            {t("settings.orgDeletion.request")}
          </Button>
        )}
      </div>
      {asking && (
        <Confirm title={t("settings.orgDeletion.confirmTitle")} action={t("settings.orgDeletion.request")} loading={request.isPending} onConfirm={() => request.mutate()} onClose={() => setAsking(false)}>
          {t("settings.orgDeletion.confirmText")}
        </Confirm>
      )}
    </section>
  );
}
