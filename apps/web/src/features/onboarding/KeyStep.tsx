// 1-qadam: Uzum API kaliti (M2). Kalit faqat shu maydonda va so'rov tanasida: URL'ga, jurnalga, xato matniga, holatga
// (muvaffaqiyatdan keyin) tushmaydi; javobda faqat oxirgi 4 belgi. Parol so'ralmaydi (tamoyil 5).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { connectAccount, shopsQuery, syncQuery } from "../../app/query";
import { Banner, Button, TextInput } from "../../components/ui";

export function KeyStep({ orgId, isOwner, onDone }: { orgId: string; isOwner: boolean; onDone: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [token, setToken] = useState("");
  const [empty, setEmpty] = useState(false);
  const connect = useMutation({
    mutationFn: () => connectAccount(orgId, token),
    onSuccess: async () => {
      setToken(""); // kalit endi serverda (shifrlangan) — brauzerda qolmasin
      await Promise.all([client.invalidateQueries({ queryKey: shopsQuery(orgId).queryKey }), client.invalidateQueries({ queryKey: syncQuery(orgId).queryKey })]);
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const empty = token.trim().length === 0;
    setEmpty(empty);
    if (!empty) connect.mutate();
  };
  return (
    <form className="onb__form" onSubmit={submit} noValidate>
      <h2>{t("onboarding.key.title")}</h2>
      <p className="muted">{t("onboarding.key.lead")}</p>
      <ol className="onb__howto">
        {(["1", "2", "3", "4"] as const).map((n) => (
          <li key={n}>{t(`onboarding.key.howto.${n}`)}</li>
        ))}
      </ol>
      {!isOwner && <Banner tone="info" title={t("onboarding.key.ownerOnly")} />}
      {connect.isError && <Banner tone="negative" title={errorText(connect.error, t)} />}
      <TextInput
        label={t("onboarding.key.label")}
        help={t("onboarding.key.help")}
        error={empty ? t("onboarding.key.required") : null}
        value={token}
        onValueChange={setToken}
        type="password"
        autoComplete="off"
        spellCheck={false}
        autoCapitalize="off"
        disabled={!isOwner}
      />
      <div className="onb__actions">
        <Button type="submit" variant="primary" size="lg" loading={connect.isPending} disabled={!isOwner}>
          {t("onboarding.key.connect")}
        </Button>
      </div>
    </form>
  );
}
