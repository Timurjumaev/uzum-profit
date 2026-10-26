// "Hozir yangilash" (M3): ustuvor navbat, daqiqada bir marta. SyncIndicator va "Ma'lumotlar holati" sahifasi ishlatadi.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { useToast } from "../components/ui";
import { errorText } from "./errors";
import { refreshSync, syncQuery } from "./query";

export function useRefreshSync(orgId: string) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => refreshSync(orgId),
    onSuccess: () => {
      toast.show(t("sync.refreshStarted"));
      void client.invalidateQueries({ queryKey: syncQuery(orgId).queryKey });
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
}
