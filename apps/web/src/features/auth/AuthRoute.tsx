// Kirish talab qiladigan hamma sahifalar uchun umumiy: profil tilini qo'llash (yangi qurilmada).
import { useSuspenseQuery } from "@tanstack/react-query";
import { Outlet } from "@tanstack/react-router";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";

import { meQuery } from "../../app/query";
import { syncProfileLanguage } from "./language";

export function AuthRoute() {
  const { i18n } = useTranslation();
  const { data: me } = useSuspenseQuery(meQuery);
  const profile = me.user.language;
  useEffect(() => {
    // Qo'lda tanlangan til bo'lmasa (yangi qurilma) — profil tili; bo'lsa tegilmaydi.
    void syncProfileLanguage(i18n, profile, { push: false });
  }, [i18n, profile]);
  return <Outlet />;
}
