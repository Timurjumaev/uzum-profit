import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";

import { App } from "./App";

test("sarlavha ko'rinadi", () => {
  render(<App />);
  expect(screen.getByRole("heading", { name: "Uzum Profit" })).toBeTruthy();
});
