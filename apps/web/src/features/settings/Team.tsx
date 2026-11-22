// "Jamoa" (M1, B8.0b; faqat egasi): aʼzolar (rol almashtirish, chiqarish) va telefon raqam bo'yicha takliflar. Taklif havolasi
// bir marta ko'rsatiladi — egasi uni o'zi yuboradi. Oxirgi egani kamaytirish/chiqarishni server rad etadi (`last_owner`).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Copy, Users } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { errorText } from "../../app/errors";
import { changeMemberRole, createInvite, invitesKey, invitesQuery, membersKey, membersQuery, removeMember, revokeInvite, type MemberRole } from "../../app/query";
import { Badge, Button, Dialog, EmptyState, Select, TextInput, useToast } from "../../components/ui";
import { formatDate } from "../../lib/format";
import { formatPhone, normalizePhone } from "../../lib/phone";
import { Confirm } from "./Confirm";

const ROLES: MemberRole[] = ["owner", "manager", "accountant", "warehouse"];
const INVITE_ROLES: MemberRole[] = ["manager", "accountant", "warehouse"];

export function Team({ orgId, userId }: { orgId: string; userId?: string }) {
  const { t } = useTranslation();
  const toast = useToast();
  const client = useQueryClient();
  const members = useQuery(membersQuery(orgId));
  const invites = useQuery(invitesQuery(orgId));
  const [removing, setRemoving] = useState<{ id: string; who: string } | null>(null);
  const [phone, setPhone] = useState("");
  const [phoneError, setPhoneError] = useState<string | null>(null);
  const [role, setRole] = useState<MemberRole>("manager");
  const [link, setLink] = useState<{ url: string; phone: string } | null>(null);
  const fail = (error: unknown) => toast.show(errorText(error, t), "negative");
  const refresh = async () => {
    await Promise.all([client.invalidateQueries({ queryKey: membersKey(orgId) }), client.invalidateQueries({ queryKey: invitesKey(orgId) })]);
  };
  const change = useMutation({
    mutationFn: (v: { id: string; role: MemberRole }) => changeMemberRole(orgId, v.id, v.role),
    onSuccess: async () => {
      toast.show(t("settings.team.roleChanged"), "positive");
      await refresh();
    },
    onError: async (error) => {
      fail(error);
      await refresh();
    },
  });
  const remove = useMutation({
    mutationFn: (id: string) => removeMember(orgId, id),
    onSuccess: async () => {
      setRemoving(null);
      toast.show(t("settings.team.removed"), "positive");
      await refresh();
    },
    onError: (error) => {
      setRemoving(null);
      fail(error);
    },
  });
  const revoke = useMutation({
    mutationFn: (id: string) => revokeInvite(orgId, id),
    onSuccess: async () => {
      toast.show(t("settings.team.revoked"), "positive");
      await refresh();
    },
    onError: fail,
  });
  const invite = useMutation({
    mutationFn: (number: string) => createInvite(orgId, number, role),
    onSuccess: async (created) => {
      setLink({ url: created.url, phone: created.phone });
      setPhone("");
      await refresh();
    },
    onError: (error) => setPhoneError(errorText(error, t)),
  });
  const submit = () => {
    const number = normalizePhone(phone);
    if (!number) return setPhoneError(t("errors.codes.invalid_phone"));
    setPhoneError(null);
    invite.mutate(number);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(link!.url);
      toast.show(t("settings.team.copied"), "positive");
    } catch {
      // Nusxalash ruxsati yo'q — havola oynada ko'rinib turadi, qo'lda belgilanadi.
    }
  };
  const roleOptions = (list: MemberRole[]) => list.map((r) => ({ value: r, label: t(`settings.team.roles.${r}`) }));
  const people = members.data ?? [];
  const pending = invites.data ?? [];
  return (
    <section className="settings-section team" aria-labelledby="settings-team">
      <h2 id="settings-team" className="h3">
        <Users size={20} aria-hidden className="full-export__icon" /> {t("settings.team.title")}
      </h2>
      <p className="caption">{t("settings.team.lead")}</p>
      {people.length > 0 && (
        <ul className="full-export__list">
          {people.map((m) => {
            const who = m.name ?? formatPhone(m.phone);
            const self = m.user_id === userId;
            return (
              <li key={m.user_id} className="full-export__item team__member">
                <strong>{m.name ?? t("settings.team.unnamed")}</strong>
                <span className="caption">{formatPhone(m.phone)}</span>
                {self && <Badge tone="positive">{t("settings.team.you")}</Badge>}
                <span className="caption">{t("settings.team.since", { when: formatDate(m.joined_at) })}</span>
                <Select label={t("settings.team.role")} options={roleOptions(ROLES)} value={m.role} onValueChange={(r) => change.mutate({ id: m.user_id, role: r as MemberRole })} disabled={change.isPending} />
                <Button size="sm" variant="secondary" onClick={() => setRemoving({ id: m.user_id, who })} aria-label={`${t("settings.team.remove")}: ${who}`}>
                  {t("settings.team.remove")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      <h3 className="h4">{t("settings.team.invitesTitle")}</h3>
      {pending.length === 0 ? (
        <EmptyState title={t("settings.team.noInvites")} />
      ) : (
        <ul className="full-export__list">
          {pending.map((i) => (
            <li key={i.id} className="full-export__item">
              <strong>{formatPhone(i.phone)}</strong>
              <Badge tone="info">{t(`settings.team.roles.${i.role}`)}</Badge>
              <span className="caption">{t("settings.team.expires", { when: formatDate(i.expires_at) })}</span>
              <Button size="sm" variant="secondary" loading={revoke.isPending && revoke.variables === i.id} onClick={() => revoke.mutate(i.id)}>
                {t("settings.team.revoke")}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <form
        className="team__invite"
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
      >
        <TextInput label={t("settings.team.phone")} help={t("settings.team.phoneHelp")} error={phoneError} inputMode="tel" autoComplete="off" value={phone} onValueChange={setPhone} />
        <Select label={t("settings.team.role")} help={t(`settings.team.roleHelp.${role}`)} options={roleOptions(INVITE_ROLES)} value={role} onValueChange={(r) => setRole(r as MemberRole)} />
        <Button type="submit" loading={invite.isPending}>
          {t("settings.team.send")}
        </Button>
      </form>
      {removing && (
        <Confirm title={t("settings.team.removeTitle")} action={t("settings.team.remove")} loading={remove.isPending} onConfirm={() => remove.mutate(removing.id)} onClose={() => setRemoving(null)}>
          {t("settings.team.removeText", { who: removing.who })}
        </Confirm>
      )}
      {link && (
        <Dialog
          open
          title={t("settings.team.created")}
          onClose={() => setLink(null)}
          footer={
            <>
              <Button variant="ghost" onClick={() => setLink(null)}>
                {t("settings.team.close")}
              </Button>
              <Button onClick={() => void copy()}>
                <Copy size={16} aria-hidden /> {t("settings.team.copy")}
              </Button>
            </>
          }
        >
          <p>{t("settings.team.createdText", { phone: formatPhone(link.phone) })}</p>
          <p className="team__link" data-testid="invite-url">
            {link.url}
          </p>
        </Dialog>
      )}
    </section>
  );
}
