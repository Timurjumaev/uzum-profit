// Xato chegaralari (B3.1): marshrut xatosi — `RouteError` (qayta urinish, so'rov ID), topilmagan sahifa — `NotFound`,
// marshrutdan tashqaridagi render xatosi — `AppErrorBoundary`. Matn — i18n: avval `errors.codes.<ApiError.code>`,
// bo'lmasa HTTP holati bo'yicha (B3.2).
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { Link, useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import type { TFunction } from "i18next";
import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";
import { useTranslation, withTranslation, type WithTranslation } from "react-i18next";

import { ApiError } from "../lib/api/client";

export function errorText(error: unknown, t: TFunction): string {
  if (error instanceof ApiError) {
    const key = `errors.codes.${error.code}`;
    const text = t(key);
    if (text !== key) return text;
    if (error.status === 0) return t("errors.network");
    if (error.status === 403) return t("errors.forbidden");
    if (error.status === 404) return t("errors.notFound");
    if (error.status === 429) return t("errors.rateLimited");
    if (error.status >= 500) return t("errors.server");
  }
  return t("errors.unknown");
}

function RequestId({ error }: { error: unknown }) {
  const { t } = useTranslation();
  if (!(error instanceof ApiError) || !error.requestId) return null;
  return <p className="muted">{t("common.requestId", { id: error.requestId })}</p>;
}

export function RouteError({ error, reset }: ErrorComponentProps) {
  const { t } = useTranslation();
  const router = useRouter();
  const queryReset = useQueryErrorResetBoundary();
  useEffect(() => queryReset.reset(), [queryReset]);
  return (
    <section role="alert" className="state">
      <h1>{t("errors.title")}</h1>
      <p>{errorText(error, t)}</p>
      <RequestId error={error} />
      <button
        type="button"
        onClick={() => {
          reset();
          void router.invalidate();
        }}
      >
        {t("common.retry")}
      </button>
    </section>
  );
}

export function NotFound() {
  const { t } = useTranslation();
  return (
    <section className="state">
      <h1>{t("notFound.title")}</h1>
      <p>{t("notFound.text")}</p>
      <Link to="/">{t("common.backHome")}</Link>
    </section>
  );
}

export function Pending() {
  const { t } = useTranslation();
  return (
    <p className="state" role="status" aria-live="polite">
      {t("common.loading")}
    </p>
  );
}

type BoundaryProps = WithTranslation & {
  children: ReactNode;
  onError?: (error: unknown, info: ErrorInfo) => void;
};

/** Marshrutlovchidan tashqaridagi (provayderlar, karkas) xato — oq ekran o'rniga tushunarli sahifa. */
class Boundary extends Component<BoundaryProps, { error: unknown }> {
  state = { error: null as unknown };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  render() {
    const { t, children } = this.props;
    if (this.state.error === null) return children;
    return (
      <main className="state" role="alert">
        <h1>{t("errors.title")}</h1>
        <p>{errorText(this.state.error, t)}</p>
        <button type="button" onClick={() => window.location.reload()}>
          {t("common.reload")}
        </button>
      </main>
    );
  }
}

export const AppErrorBoundary = withTranslation()(Boundary);
