// Marshrutlar (03 §9). Har sahifa alohida bo'lak (`lazyRouteComponent`). Kirish talab qiladigan sahifalar `app`
// tartibi ostida: sessiya yo'q (401) — `/login?redirect=...`; ular `AppShell` karkasida (B3.5). Sahifalarning o'zi B4 da.
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

import { AppShell } from "../components/shell";
import { ApiError } from "../lib/api/client";
import { NotFound, Pending, RouteError } from "./errors";
import { AuthRoute } from "../features/auth/AuthRoute";
import { filterSearch } from "./filters";
import { inviteSearch, loginSearch, onboardingSearch, pnlSearch, productsSearch } from "./search";

export { inviteSearch, loginSearch };
import { meQuery } from "./query";

export type RouterContext = { queryClient: QueryClient };

const root = createRootRouteWithContext<RouterContext>()({
  component: Outlet,
});

/** Kirish talab qiladigan hamma sahifalar: foydalanuvchi va tashkilotlari kontekstga; sessiya yo'q (401) — /login. */
const auth = createRoute({
  getParentRoute: () => root,
  id: "auth",
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
  component: AuthRoute,
});

/** Karkas ostidagi sahifalar. Tashkilotsiz foydalanuvchi — avval onboarding (M2). */
const app = createRoute({
  getParentRoute: () => auth,
  id: "app",
  // Umumiy filtrlar (do'kon, davr, solishtirish) — URL'da, hamma sahifada (app/filters).
  validateSearch: filterSearch,
  beforeLoad: ({ context }) => {
    if (context.me.orgs.length === 0) throw redirect({ to: "/onboarding" });
  },
  component: AppShell,
});

const home = createRoute({
  getParentRoute: () => app,
  path: "/",
  component: lazyRouteComponent(() => import("../routes/home"), "Home"),
});

/** Foyda va zarar (M5, B4.2): kesim (`view`) — URL'da. */
const pnl = createRoute({
  getParentRoute: () => app,
  path: "/pnl",
  validateSearch: pnlSearch,
  component: lazyRouteComponent(() => import("../routes/pnl"), "Pnl"),
});

/** Mahsulotlar (M6, B4.3): jadval (qidiruv, saralash, filtrlar — URL'da) va SKU sahifasi. */
const products = createRoute({
  getParentRoute: () => app,
  path: "/products",
  validateSearch: productsSearch,
  component: lazyRouteComponent(() => import("../routes/products"), "Products"),
});

const product = createRoute({
  getParentRoute: () => app,
  path: "/products/$skuId",
  component: lazyRouteComponent(() => import("../routes/products"), "SkuPage"),
});

const status = createRoute({
  getParentRoute: () => app,
  path: "/status",
  component: lazyRouteComponent(() => import("../routes/status"), "Status"),
});

// Sahifalari hali yo'q bo'limlar (B4+): menyu ishlaydi, sahifa "qurilmoqda".
const soon = <const P extends string>(path: P, name: keyof typeof import("../routes/soon")) =>
  createRoute({
    getParentRoute: () => app,
    path,
    component: lazyRouteComponent(() => import("../routes/soon"), name),
  });
const orders = soon("/orders", "Orders");
const expenses = soon("/expenses", "Expenses");
const purchases = soon("/purchases", "Purchases");
const inventory = soon("/inventory", "Inventory");
const cash = soon("/cash", "Cash");
const reports = soon("/reports", "Reports");
const settings = soon("/settings", "Settings");

const login = createRoute({
  getParentRoute: () => root,
  path: "/login",
  validateSearch: loginSearch,
  component: lazyRouteComponent(() => import("../routes/login"), "Login"),
});

/** Birinchi ulanish (M2): markazda bitta ustun, karkassiz. */
const onboarding = createRoute({
  getParentRoute: () => auth,
  path: "/onboarding",
  validateSearch: onboardingSearch,
  component: lazyRouteComponent(() => import("../routes/onboarding"), "Onboarding"),
});

const invite = createRoute({
  getParentRoute: () => auth,
  path: "/invite",
  validateSearch: inviteSearch,
  component: lazyRouteComponent(() => import("../routes/invite"), "Invite"),
});

// Komponentlar katalogi (04 §5) — kirishsiz, ma'lumotsiz (sintetik namunalar).
const uiKit = createRoute({
  getParentRoute: () => root,
  path: "/ui-kit",
  component: lazyRouteComponent(() => import("../routes/ui-kit"), "UiKit"),
});

export const routeTree = root.addChildren([
  auth.addChildren([
    app.addChildren([home, status, pnl, products, product, orders, expenses, purchases, inventory, cash, reports, settings]),
    onboarding,
    invite,
  ]),
  login,
  uiKit,
]);

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
