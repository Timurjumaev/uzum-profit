// Sahifa karkasi (B3.5, 04 §7.1): sidebar (desktop), topbar, mobil tab bar, Ctrl+K. Faqat kirgan foydalanuvchi uchun
// (`app` marshruti). Sahifalar `<main>` ni o'zlari ochmaydi — u shu yerda (bitta landmark).
import { useSuspenseQuery } from "@tanstack/react-query";
import { Outlet } from "@tanstack/react-router";
import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";

import { currentOrg, meQuery } from "../../app/query";
import { CommandPalette, isPaletteShortcut } from "./CommandPalette";
import { MobileTabBar } from "./MobileTabBar";
import { Sidebar } from "./Sidebar";
import { OutageBanner } from "./SyncIndicator";
import { TopBar } from "./TopBar";
import { usePaletteItems } from "./usePaletteItems";
import type { Account } from "./UserMenu";

export const SIDEBAR_KEY = "up.sidebar";

function readCollapsed(): boolean {
  try {
    return globalThis.localStorage?.getItem(SIDEBAR_KEY) === "collapsed";
  } catch {
    return false;
  }
}

/** Sidebar yig'ilganligi — brauzerda saqlanadi (maxfiy oynada saqlanmasa ham ishlaydi). */
export function useSidebarCollapsed(): [boolean, () => void] {
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const toggle = useCallback(() => {
    setCollapsed((was) => {
      try {
        globalThis.localStorage?.setItem(SIDEBAR_KEY, was ? "expanded" : "collapsed");
      } catch {
        // saqlanmasa — faqat shu sahifada
      }
      return !was;
    });
  }, []);
  return [collapsed, toggle];
}

export function AppShell() {
  const { t } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const org = currentOrg(me);
  const account: Account = { name: me.user.name, phone: me.user.phone, org: org?.name ?? null };
  const [collapsed, toggleSidebar] = useSidebarCollapsed();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const items = usePaletteItems();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (!isPaletteShortcut(e)) return;
      e.preventDefault(); // brauzerning qidiruv satri ochilmasin
      setPaletteOpen((open) => !open);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
  const skip = (e: MouseEvent) => {
    e.preventDefault();
    document.getElementById("content")?.focus();
  };
  return (
    <div className="app" data-collapsed={collapsed || undefined}>
      <a className="skip-link" href="#content" onClick={skip}>
        {t("shell.skip")}
      </a>
      <Sidebar collapsed={collapsed} onToggle={toggleSidebar} />
      <div className="app__col">
        <TopBar orgId={org?.id ?? null} account={account} onSearch={() => setPaletteOpen(true)} />
        {org && <OutageBanner orgId={org.id} />}
        <main id="content" tabIndex={-1} className="app__main">
          <Outlet />
        </main>
      </div>
      <MobileTabBar account={account} />
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} items={items} />
    </div>
  );
}
