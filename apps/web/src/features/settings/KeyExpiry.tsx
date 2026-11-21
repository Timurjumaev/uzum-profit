// Uzum kaliti muddati (B8.16, faqat egasi): Uzum muddatni API orqali bermaydi — sotuvchi kiritadi; muddatidan 5 va 1 kun oldin
// ogohlantirish keladi. Bo'sh qoldirilsa — cheklanmagan/noma'lum. Kalitning o'zi ko'rsatilmaydi (faqat oxirgi 4 belgi).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { accountsKey, accountsQuery, setKeyExpiry } from "../../app/query";
import { Badge, Button, TextInput, useToast } from "../../components/ui";
import type { Account } from "../../lib/api/types";

function Row({ orgId, account }: { orgId: string; account: Account }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const [value, setValue] = useState(account.key_expires_on ?? "");
  const save = useMutation({
    mutationFn: () => setKeyExpiry(orgId, account.id, value || null),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: accountsKey(orgId) });
      toast.show(t("settings.keyExpiry.saved"), "positive");
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
  const left = account.key_days_left;
  return (
    <li className="full-export__item">
      <strong>{account.key_hint ?? t("settings.keyExpiry.noKey")}</strong>
      {left !== null && <Badge tone={left <= 5 ? "warning" : "neutral"}>{t("settings.keyExpiry.daysLeft", { count: left })}</Badge>}
      <TextInput label={t("settings.keyExpiry.date")} type="date" value={value} onValueChange={setValue} />
      <Button size="sm" variant="secondary" loading={save.isPending} disabled={value === (account.key_expires_on ?? "")} onClick={() => save.mutate()}>
        {t("settings.save")}
      </Button>
    </li>
  );
}

export function KeyExpiry({ orgId }: { orgId: string }) {
  const { t } = useTranslation();
  const query = useQuery(accountsQuery(orgId));
  const accounts = (query.data ?? []).filter((a) => a.key_hint !== null);
  if (accounts.length === 0) return null;
  return (
    <section className="settings-section" aria-labelledby="settings-key-expiry">
      <h2 id="settings-key-expiry" className="h3">
        <KeyRound size={20} aria-hidden className="full-export__icon" /> {t("settings.keyExpiry.title")}
      </h2>
      <p className="caption">{t("settings.keyExpiry.lead")}</p>
      <ul className="full-export__list">
        {accounts.map((a) => (
          <Row key={a.id} orgId={orgId} account={a} />
        ))}
      </ul>
    </section>
  );
}
