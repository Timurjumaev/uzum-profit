// Xato chegaralari (B3.1): marshrut xatosi — `RouteError` (qayta urinish, so'rov ID), topilmagan sahifa — `NotFound`,
// marshrutdan tashqaridagi render xatosi — `AppErrorBoundary`. Matnlar B3.2 da i18n'ga ko'chadi (ApiError.code bo'yicha).
import { useQueryErrorResetBoundary } from "@tanstack/react-query";
import { Link, useRouter, type ErrorComponentProps } from "@tanstack/react-router";
import { Component, useEffect, type ErrorInfo, type ReactNode } from "react";

import { ApiError } from "../lib/api/client";

export function errorText(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 0) return "Internet aloqasi yoʻq. Ulanishni tekshirib, qayta urining.";
    if (error.status === 403) return "Bu sahifaga ruxsatingiz yoʻq.";
    if (error.status === 404) return "Maʼlumot topilmadi.";
    if (error.status === 429) return "Soʻrovlar juda koʻp. Birozdan soʻng qayta urining.";
    if (error.status >= 500) return "Server javob bermadi. Birozdan soʻng qayta urining.";
  }
  return "Kutilmagan xatolik yuz berdi.";
}

function RequestId({ error }: { error: unknown }) {
  if (!(error instanceof ApiError) || !error.requestId) return null;
  return <p className="muted">Soʻrov ID: {error.requestId}</p>;
}

export function RouteError({ error, reset }: ErrorComponentProps) {
  const router = useRouter();
  const queryReset = useQueryErrorResetBoundary();
  useEffect(() => queryReset.reset(), [queryReset]);
  return (
    <section role="alert" className="state">
      <h1>Xatolik yuz berdi</h1>
      <p>{errorText(error)}</p>
      <RequestId error={error} />
      <button
        type="button"
        onClick={() => {
          reset();
          void router.invalidate();
        }}
      >
        Qayta urinish
      </button>
    </section>
  );
}

export function NotFound() {
  return (
    <section className="state">
      <h1>Sahifa topilmadi</h1>
      <p>Manzil notoʻgʻri yoki sahifa koʻchirilgan.</p>
      <Link to="/">Bosh sahifaga qaytish</Link>
    </section>
  );
}

export function Pending() {
  return (
    <p className="state" role="status" aria-live="polite">
      Yuklanmoqda…
    </p>
  );
}

type BoundaryProps = { children: ReactNode; onError?: (error: unknown, info: ErrorInfo) => void };

/** Marshrutlovchidan tashqaridagi (provayderlar, karkas) xato — oq ekran o'rniga tushunarli sahifa. */
export class AppErrorBoundary extends Component<BoundaryProps, { error: unknown }> {
  state = { error: null as unknown };

  static getDerivedStateFromError(error: unknown) {
    return { error };
  }

  componentDidCatch(error: unknown, info: ErrorInfo) {
    this.props.onError?.(error, info);
  }

  render() {
    if (this.state.error === null) return this.props.children;
    return (
      <main className="state" role="alert">
        <h1>Xatolik yuz berdi</h1>
        <p>{errorText(this.state.error)}</p>
        <button type="button" onClick={() => window.location.reload()}>
          Sahifani yangilash
        </button>
      </main>
    );
  }
}
