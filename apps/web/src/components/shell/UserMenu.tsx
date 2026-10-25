// Foydalanuvchi menyusi: kim kirgan, tashkilot, ko'rinish (mavzu, til), chiqish.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "@tanstack/react-router";
import { CircleUser, LogOut } from "lucide-react";
import { useTranslation } from "react-i18next";

import { logout } from "../../app/query";
import { Button, Popover, useToast } from "../ui";
import { Appearance } from "./Appearance";

export type Account = { name: string | null; phone: string; org: string | null };

/** Chiqish: sessiya bekor, /login ga, kesh tozalanadi (boshqa foydalanuvchi ma'lumoti qolmasin). */
export function useSignOut() {
  const { t } = useTranslation();
  const client = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  return useMutation({
    mutationFn: logout,
    onSuccess: async () => {
      // Avval sahifadan chiqamiz — aks holda karkasning faol so'rovlari tozalangan keshni qayta to'ldiradi.
      await navigate({ to: "/login", search: {} });
      client.clear();
    },
    onError: () => toast.show(t("shell.signOutFailed"), "negative"),
  });
}

export function AccountPanel({ account }: { account: Account }) {
  const { t } = useTranslation();
  const signOut = useSignOut();
  return (
    <div className="account">
      <div className="account__who">
        <p className="account__name">{account.name ?? account.phone}</p>
        {account.name && <p className="muted">{account.phone}</p>}
        {account.org && <p className="muted">{account.org}</p>}
      </div>
      <Appearance />
      <Button icon={<LogOut size={16} aria-hidden />} loading={signOut.isPending} onClick={() => signOut.mutate()}>
        {t("shell.signOut")}
      </Button>
    </div>
  );
}

export function UserMenu({ account }: { account: Account }) {
  const { t } = useTranslation();
  const label = `${t("shell.account")}: ${account.name ?? account.phone}`;
  return (
    <Popover
      align="end"
      label={label}
      triggerClassName="ui-icon-btn topbar__user"
      trigger={<CircleUser size={22} aria-hidden />}
    >
      <AccountPanel account={account} />
    </Popover>
  );
}
