// Bosh sahifa (M4) — B4.1. Hozircha karkas: kim kirgani va tashkilotlar.
import { useSuspenseQuery } from "@tanstack/react-query";

import { meQuery } from "../app/query";

export function Home() {
  const { data } = useSuspenseQuery(meQuery);
  return (
    <main>
      <h1>Uzum Profit</h1>
      <p>Bosh sahifa qurilmoqda. Hozircha legacy dasturdan foydalaning.</p>
      <ul aria-label="Tashkilotlar">
        {data.orgs.map((org) => (
          <li key={org.id}>{org.name}</li>
        ))}
      </ul>
    </main>
  );
}
