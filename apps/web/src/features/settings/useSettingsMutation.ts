// Sozlama yozuvlari: javob — yangi butun sozlama (keshga qo'yiladi); boshqa hisobotlar (P&L, ombor, xaridlar ...) eskiradi,
// chunki soliq, tannarx usuli, muddat va qamrov ularning raqamlariga ta'sir qiladi.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { settingsKey } from "../../app/query";
import { useToast } from "../../components/ui";
import type { Settings } from "../../lib/api/types";

export function useSettingsMutation<V>(orgId: string, fn: (value: V) => Promise<Settings>, done: string, onDone?: () => void) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (data) => {
      client.setQueryData(settingsKey(orgId), data);
      await client.invalidateQueries({ queryKey: ["orgs", orgId], predicate: (q) => q.queryKey[2] !== "settings" });
      toast.show(t(done), "positive");
      onDone?.();
    },
    onError: (error) => toast.show(errorText(error, t), "negative"),
  });
}
