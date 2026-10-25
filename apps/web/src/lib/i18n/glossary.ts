// Atamalar lug'ati (04 §8.2): matnlar `messages/*.ts` dagi `terms` bo'limida (hamma tilda bir xil kalit),
// komponentlar atamani shu kalit orqali oladi — `t(term("netProfit"))`.
import type { Messages } from "./messages/uz-Latn";

export type Term = keyof Messages["terms"];

export function term(name: Term): `terms.${Term}` {
  return `terms.${name}`;
}
