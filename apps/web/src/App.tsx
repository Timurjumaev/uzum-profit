// Ilova ildizi: til (B3.2) → xato chegarasi → Query → marshrutlovchi (B3.1).
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider, type RouterHistory } from "@tanstack/react-router";
import type { i18n as I18n } from "i18next";
import { useState } from "react";
import { I18nextProvider } from "react-i18next";

import { AppErrorBoundary } from "./app/errors";
import { ToastProvider } from "./components/ui";
import { makeQueryClient } from "./app/query";
import { createAppRouter, type AppRouter } from "./app/router";
import { createI18n, type Lang } from "./lib/i18n";

export type AppState = { queryClient: QueryClient; router: AppRouter; i18n: I18n };

/** Query mijozi va marshrutlovchi. Sessiya tugasa (401): kesh tozalanadi, joriy sahifa manzili bilan /login ga. */
export function createAppState(history?: RouterHistory, lang?: Lang): AppState {
  const ref: { router?: AppRouter } = {};
  const queryClient = makeQueryClient(() => {
    const location = ref.router?.state.location;
    queryClient.clear();
    void ref.router?.navigate({
      to: "/login",
      search: !location || location.pathname === "/login" ? {} : { redirect: location.href },
    });
  });
  ref.router = createAppRouter(queryClient, history);
  return { queryClient, router: ref.router, i18n: createI18n(lang) };
}

export function App({ state }: { state?: AppState }) {
  const [{ queryClient, router, i18n }] = useState(() => state ?? createAppState());
  return (
    <I18nextProvider i18n={i18n}>
      <AppErrorBoundary>
        <QueryClientProvider client={queryClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </QueryClientProvider>
      </AppErrorBoundary>
    </I18nextProvider>
  );
}
