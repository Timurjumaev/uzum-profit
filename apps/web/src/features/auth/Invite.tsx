// Taklif (M1): `/invite?token=...` — kirgan foydalanuvchi taklifni qabul qiladi (kirmagan bo'lsa marshrut avval
// /login ga yuboradi va qaytaradi). Muddati o'tgan, ishlatilgan yoki boshqa raqamga yuborilgan taklif — API `code` bo'yicha
// tushunarli xabar bilan.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useRouter, useSearch } from "@tanstack/react-router";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { acceptInvite, meQuery } from "../../app/query";
import { inviteSearch } from "../../app/search";
import { Banner, Button } from "../../components/ui";
import { AuthLayout } from "./AuthLayout";

export function Invite() {
  const { t } = useTranslation();
  const router = useRouter();
  const client = useQueryClient();
  const { token } = inviteSearch(useSearch({ from: "/auth/invite" })); // xom qidiruv ham kelishi mumkin
  const accept = useMutation({
    mutationFn: () => acceptInvite(token!),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: meQuery.queryKey }); // yangi tashkilot ro'yxatga tushsin
      await router.navigate({ to: "/" });
    },
  });
  return (
    <AuthLayout title={t("pages.invite.title")} lead={token ? t("pages.invite.lead") : undefined}>
      {!token ? (
        <Banner tone="negative" title={t("pages.invite.missing")} />
      ) : (
        <div className="auth__form">
          {accept.isError && <Banner tone="negative" title={errorText(accept.error, t)} />}
          <Button variant="primary" size="lg" loading={accept.isPending} onClick={() => accept.mutate()}>
            {t("pages.invite.accept")}
          </Button>
        </div>
      )}
    </AuthLayout>
  );
}
