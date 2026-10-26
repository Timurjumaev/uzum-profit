// Onboarding (M2, 04 §7.4): markazda bitta ustun, chapda qadamlar ro'yxati (desktop) / tepada progress (mobil). Holat
// serverdan olinadi (tashkilot, do'konlar) — istalgan joyda to'xtab, keyin davom etish mumkin; joriy qadam URL'da
// (`?step=`), oldingi qadam yetishmasa — eng yaqin mumkin bo'lganiga qaytariladi.
// Soliq, tannarx, Telegram qadamlari (M2 4–6) tegishli endpointlar (B4.8, B5, B6) bilan keladi.
import { useQuery, useSuspenseQuery } from "@tanstack/react-query";
import { useNavigate, useSearch } from "@tanstack/react-router";
import { LogOut } from "lucide-react";
import { useTranslation } from "react-i18next";

import { currentOrg, meQuery, shopsQuery } from "../../app/query";
import { ONBOARDING_STEPS, onboardingSearch, type OnboardingStep } from "../../app/search";
import { Logo } from "../../components/shell/Logo";
import { Button, ProgressBar, Skeleton, Stepper } from "../../components/ui";
import { useSignOut } from "../../components/shell/UserMenu";
import { HistoryStep } from "./HistoryStep";
import { KeyStep } from "./KeyStep";
import { OrgStep } from "./OrgStep";
import { ShopsStep } from "./ShopsStep";

/** Qaysi qadamga o'tish mumkin: keyingisi oldingisining natijasiga tayanadi. */
export function allowedStep(requested: OnboardingStep | undefined, state: { hasOrg: boolean; hasShops: boolean }): OnboardingStep {
  const reachable: OnboardingStep[] = ["org"];
  if (state.hasOrg) reachable.push("key");
  if (state.hasShops) reachable.push("shops", "history");
  if (requested && reachable.includes(requested)) return requested;
  return state.hasShops ? "shops" : state.hasOrg ? "key" : "org";
}

export function Onboarding() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const signOut = useSignOut();
  const { step: requested } = onboardingSearch(useSearch({ from: "/auth/onboarding" }));
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me);
  const shops = useQuery({ ...shopsQuery(org?.id ?? ""), enabled: org !== null });
  const loading = org !== null && shops.isPending;
  const hasShops = (shops.data?.length ?? 0) > 0;
  const step = allowedStep(requested, { hasOrg: org !== null, hasShops });
  const go = (next: OnboardingStep) => void navigate({ to: "/onboarding", search: { step: next } });
  const index = ONBOARDING_STEPS.indexOf(step);
  const steps = ONBOARDING_STEPS.map((id, i) => ({
    label: t(`onboarding.steps.${id}`),
    state: i < index ? ("done" as const) : i === index ? ("current" as const) : ("upcoming" as const),
  }));
  return (
    <div className="onb">
      <header className="onb__bar">
        <span className="auth__brand">
          <Logo />
          <span>{t("app.name")}</span>
        </span>
        <Button variant="ghost" size="sm" icon={<LogOut size={16} aria-hidden />} loading={signOut.isPending} onClick={() => signOut.mutate()}>
          {t("shell.signOut")}
        </Button>
      </header>
      <main className="onb__body">
        <aside className="onb__steps">
          <Stepper steps={steps} label={t("onboarding.stepsLabel")} />
        </aside>
        <div className="onb__progress">
          <ProgressBar
            label={t("onboarding.stepOf", { current: index + 1, total: ONBOARDING_STEPS.length })}
            value={index + 1}
            max={ONBOARDING_STEPS.length}
          />
        </div>
        <section className="onb__main" aria-live="polite">
          <h1 className="ui-visually-hidden">{t("onboarding.title")}</h1>
          {loading ? (
            <Skeleton label={t("common.loading")} lines={4} />
          ) : step === "org" ? (
            <OrgStep onDone={() => go("key")} />
          ) : step === "key" && org ? (
            <KeyStep orgId={org.id} isOwner={org.role === "owner"} onDone={() => go("shops")} />
          ) : step === "shops" && org ? (
            <ShopsStep key={shops.data?.map((s) => s.id).join()} orgId={org.id} shops={shops.data ?? []} onDone={() => go("history")} />
          ) : step === "history" && org ? (
            <HistoryStep orgId={org.id} onDone={() => void navigate({ to: "/" })} />
          ) : null}
        </section>
      </main>
    </div>
  );
}

