// "Qurilmoqda" sahifalari: menyu B3.5 da to'liq, sahifalarning o'zi B4+ da (05-bosqichlar). Har biri o'z marshrutida —
// B4 da faqat shu yerdagi bittasi haqiqiy sahifa bilan almashtiriladi.
import { useTranslation } from "react-i18next";

import type { NavKey } from "../components/shell/nav";

function Soon({ page }: { page: NavKey }) {
  const { t } = useTranslation();
  return (
    <section>
      <h1>{t(`nav.${page}`)}</h1>
      <p>{t("pages.soon")}</p>
    </section>
  );
}

export const Products = () => <Soon page="products" />;
export const Orders = () => <Soon page="orders" />;
export const Expenses = () => <Soon page="expenses" />;
export const Purchases = () => <Soon page="purchases" />;
export const Inventory = () => <Soon page="inventory" />;
export const Cash = () => <Soon page="cash" />;
export const Reports = () => <Soon page="reports" />;
export const Settings = () => <Soon page="settings" />;
