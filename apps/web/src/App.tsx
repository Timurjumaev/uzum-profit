// Ilova ildizi (B3.1): xato chegarasi → Query → marshrutlovchi.
import { QueryClientProvider, type QueryClient } from "@tanstack/react-query";
import { RouterProvider, type RouterHistory } from "@tanstack/react-router";
import { useState } from "react";

import { AppErrorBoundary } from "./app/errors";
import { makeQueryClient } from "./app/query";
import { createAppRouter, type AppRouter } from "./app/router";

export type AppState = { queryClient: QueryClient; router: AppRouter };

/** Query mijozi va marshrutlovchi. Sessiya tugasa (401): kesh tozalanadi, joriy sahifa manzili bilan /login ga. */
export function createAppState(history?: RouterHistory): AppState {
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
  return { queryClient, router: ref.router };
}

export function App({ state }: { state?: AppState }) {
  const [{ queryClient, router }] = useState(() => state ?? createAppState());
  return (
    <AppErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </AppErrorBoundary>
  );
}
