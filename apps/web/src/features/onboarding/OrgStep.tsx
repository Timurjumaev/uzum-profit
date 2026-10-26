// 0-qadam: tashkilot (biznes) nomi. Foydalanuvchi birinchi marta kirganda tashkilot yo'q — shu yerda ochiladi (M1).
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { createOrg, meQuery } from "../../app/query";
import { Banner, Button, TextInput } from "../../components/ui";

export function OrgStep({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation();
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [inn, setInn] = useState("");
  const [errors, setErrors] = useState<{ name?: string; inn?: string }>({});
  const create = useMutation({
    mutationFn: () => createOrg({ name: name.trim(), inn: inn.trim() || null }),
    // Yangi tashkilot `me` ro'yxatiga tushguncha kutamiz — keyingi qadamlar uni ko'radi.
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: meQuery.queryKey });
      onDone();
    },
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const next: typeof errors = {};
    if (!name.trim()) next.name = t("onboarding.org.nameRequired");
    if (inn.trim() && !/^\d{9}$/.test(inn.trim())) next.inn = t("onboarding.org.innInvalid");
    setErrors(next);
    if (Object.keys(next).length === 0) create.mutate();
  };
  return (
    <form className="onb__form" onSubmit={submit} noValidate>
      <h2>{t("onboarding.org.title")}</h2>
      <p className="muted">{t("onboarding.org.lead")}</p>
      {create.isError && <Banner tone="negative" title={errorText(create.error, t)} />}
      <TextInput label={t("onboarding.org.name")} value={name} onValueChange={setName} error={errors.name} maxLength={100} autoComplete="organization" autoFocus />
      <TextInput
        label={t("onboarding.org.inn")}
        help={t("onboarding.org.innHelp")}
        optional
        value={inn}
        onValueChange={(v) => setInn(v.replace(/\D/g, "").slice(0, 9))}
        error={errors.inn}
        inputMode="numeric"
      />
      <div className="onb__actions">
        <Button type="submit" variant="primary" size="lg" loading={create.isPending}>
          {t("common.next")}
        </Button>
      </div>
    </form>
  );
}
