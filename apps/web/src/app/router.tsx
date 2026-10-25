// Marshrutlar (03 §9). Har sahifa alohida bo'lak (`lazyRouteComponent`). Kirish talab qiladigan sahifalar `app`
// tartibi ostida: sessiya yo'q (401) — `/login?redirect=...`. Sahifalarning o'zi B3.5–B4 da.
import type { QueryClient } from "@tanstack/react-query";
import {
  createRootRouteWithContext,
  createRoute,
  createRouter,
  lazyRouteComponent,
  Outlet,
  redirect,
  type RouterHistory,
} from "@tanstack/react-router";

import { ApiError } from "../lib/api/client";
import { NotFound, Pending, RouteError } from "./errors";
import { meQuery } from "./query";

export type RouterContext = { queryClient: QueryClient };

const root = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
});

/** Kirish talab qiladigan sahifalar: foydalanuvchi va tashkilotlari kontekstga. */
const app = createRoute({
  getParentRoute: () => root,
  id: "app",
  beforeLoad: async ({ context, location }) => {
    try {
      return { me: await context.queryClient.ensureQueryData(meQuery) };
    } catch (error) {
      if (error instanceof ApiError && error.status === 401) {
        throw redirect({ to: "/login", search: { redirect: location.href } });
      }
      throw error;
    }
  },
  component: Outlet,
});

const home = createRoute({
  getParentRoute: () => app,
  path: "/",
  component: lazyRouteComponent(() => import("../routes/home"), "Home"),
});

const status = createRoute({
  getParentRoute: () => app,
  path: "/status",
  component: lazyRouteComponent(() => import("../routes/status"), "Status"),
});

export type LoginSearch = { redirect?: string };

/** Kirishdan keyin qaytish manzili — faqat o'z saytimiz ichidagi yo'l (ochiq qayta yo'naltirish yo'q). */
export function loginSearch(search: Record<string, unknown>): LoginSearch {
  const target = search.redirect;
  return typeof target === "string" && /^\/(?![/\\])/.test(target) ? { redirect: target } : {};
}

const login = createRoute({
  getParentRoute: () => root,
  path: "/login",
  validateSearch: loginSearch,
  component: lazyRouteComponent(() => import("../routes/login"), "Login"),
});

// Komponentlar katalogi (04 §5) — kirishsiz, ma'lumotsiz (sintetik namunalar).
const uiKit = createRoute({
  getParentRoute: () => root,
  path: "/ui-kit",
  component: lazyRouteComponent(() => import("../routes/ui-kit"), "UiKit"),
});

export const routeTree = root.addChildren([app.addChildren([home, status]), login, uiKit]);

export type AppRouter = ReturnType<typeof createAppRouter>;

export function createAppRouter(queryClient: QueryClient, history?: RouterHistory) {
  return createRouter({
    routeTree,
    history,
    context: { queryClient },
    defaultErrorComponent: RouteError,
    defaultNotFoundComponent: NotFound,
    defaultPendingComponent: Pending,
    defaultPreload: "intent",
    // Ma'lumot keshini Query boshqaradi — marshrut o'zi keshlamaydi.
    defaultPreloadStaleTime: 0,
    scrollRestoration: true,
  });
}

declare module "@tanstack/react-router" {
  interface Register {
    router: ReturnType<typeof createAppRouter>;
  }
}
