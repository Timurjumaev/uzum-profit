// Kirish (M1): telefon raqam → Telegram'dan 6 xonali kod → kirish. Parol yo'q. Kod to'liq yozilgach o'zi yuboriladi.
// Xato matnlari — API `code` bo'yicha (nima bo'ldi + nima qilish kerak, 04 §8.1). Kirgach: qaytish manzili
// (faqat ichki yo'l, `loginSearch`), bo'lmasa bosh sahifa; tashkilot yo'q bo'lsa — onboarding.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearch } from "@tanstack/react-router";
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { loginWithCode, meQuery, requestOtp } from "../../app/query";
import { loginSearch } from "../../app/search";
import { Button, TextInput } from "../../components/ui";
import { formatPhone, normalizePhone } from "../../lib/phone";
import { AuthLayout } from "./AuthLayout";
import { syncProfileLanguage } from "./language";
import { useCountdown } from "./useCountdown";

export const RESEND_SECONDS = 30;
export const CODE_LENGTH = 6;

export function Login() {
  const { t, i18n } = useTranslation();
  const router = useRouter();
  const client = useQueryClient();
  // Xom qidiruv ham kelishi mumkin — qaytish manzili ishlatilishidan oldin qayta tekshiriladi (ochiq qayta yo'naltirish).
  const { redirect } = loginSearch(useSearch({ from: "/login" }));
  const [phoneText, setPhoneText] = useState("");
  const [phone, setPhone] = useState<string | null>(null); // kod yuborilgan raqam (normallashgan) — kod bosqichi
  const [sentAt, setSentAt] = useState(0);
  const [expiresIn, setExpiresIn] = useState(0);
  const [code, setCode] = useState("");
  const [attempt, setAttempt] = useState(0); // xatodan keyin kod maydoni qayta fokus olsin
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [codeError, setCodeError] = useState<string | null>(null);
  const cooldown = useCountdown(sentAt, RESEND_SECONDS);

  const send = useMutation({
    mutationFn: requestOtp,
    onSuccess: (sent, number) => {
      setPhone(number);
      setSentAt(Date.now());
      setExpiresIn(sent.expires_in);
      setCode("");
      setCodeError(null);
      setPhoneError(null);
    },
    onError: (error) => (phone ? setCodeError : setPhoneError)(errorText(error, t)),
  });

  const login = useMutation({
    mutationFn: ({ number, value }: { number: string; value: string }) => loginWithCode(number, value),
    onSuccess: async (result) => {
      client.setQueryData(meQuery.queryKey, { user: result.user, orgs: result.orgs });
      await syncProfileLanguage(i18n, result.user.language, { push: true });
      if (redirect) router.history.push(redirect);
      else await router.navigate({ to: result.orgs.length > 0 ? "/" : "/onboarding" });
    },
    onError: (error) => {
      setCodeError(errorText(error, t));
      setCode("");
      setAttempt((n) => n + 1);
    },
  });

  const submitPhone = (e: FormEvent) => {
    e.preventDefault();
    const number = normalizePhone(phoneText);
    if (!number) return setPhoneError(t("errors.codes.invalid_phone"));
    setPhoneError(null);
    send.mutate(number);
  };

  const submitCode = (value: string) => {
    if (phone && value.length === CODE_LENGTH && !login.isPending) {
      setCodeError(null);
      login.mutate({ number: phone, value });
    }
  };

  const onCode = (raw: string) => {
    const digits = raw.replace(/\D/g, "").slice(0, CODE_LENGTH);
    setCode(digits);
    submitCode(digits);
  };

  if (phone === null) {
    return (
      <AuthLayout title={t("pages.login.title")} lead={t("pages.login.lead")}>
        <form className="auth__form" onSubmit={submitPhone} noValidate>
          <TextInput
            label={t("pages.login.phone")}
            help={t("pages.login.phoneHelp")}
            error={phoneError}
            value={phoneText}
            onValueChange={setPhoneText}
            type="tel"
            inputMode="tel"
            autoComplete="tel"
            placeholder="+998 90 123 45 67"
            autoFocus
          />
          <Button type="submit" variant="primary" size="lg" loading={send.isPending}>
            {t("pages.login.send")}
          </Button>
        </form>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={t("pages.login.codeTitle")}
      lead={t("pages.login.codeLead", { phone: formatPhone(phone), minutes: Math.max(1, Math.round(expiresIn / 60)) })}
    >
      <form
        className="auth__form"
        onSubmit={(e) => {
          e.preventDefault();
          submitCode(code);
        }}
        noValidate
      >
        <TextInput
          key={attempt}
          label={t("pages.login.code")}
          error={codeError}
          value={code}
          onValueChange={onCode}
          inputMode="numeric"
          autoComplete="one-time-code"
          maxLength={CODE_LENGTH}
          placeholder="000000"
          className="auth__code"
          autoFocus
        />
        <Button type="submit" variant="primary" size="lg" loading={login.isPending} disabled={code.length !== CODE_LENGTH}>
          {t("pages.login.submit")}
        </Button>
        <div className="auth__links">
          <Button variant="ghost" size="sm" loading={send.isPending} disabled={cooldown > 0} onClick={() => send.mutate(phone)}>
            {cooldown > 0 ? t("pages.login.resendIn", { seconds: cooldown }) : t("pages.login.resend")}
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => {
              setPhone(null);
              setCode("");
              setCodeError(null);
            }}
          >
            {t("pages.login.change")}
          </Button>
        </div>
      </form>
    </AuthLayout>
  );
}
