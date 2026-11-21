// QR kod (B6.6): matndan deterministik SVG yo'l, aria-label, oq fon; bir xil matn — bir xil rasm; boshqa matn — boshqa.
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { QrCode } from "./QrCode";

afterEach(cleanup);

const pathOf = () => screen.getByRole("img").querySelector("path")!.getAttribute("d")!;

describe("QrCode", () => {
  it("yo'l bor, label va oq fon; deterministik", () => {
    render(<QrCode text="https://t.me/sellermax_bot?start=abc" label="QR" />);
    const first = pathOf();
    expect(first.length).toBeGreaterThan(100);
    expect(screen.getByRole("img", { name: "QR" }).querySelector("rect")!.getAttribute("fill")).toBe("#fff");
    cleanup();
    render(<QrCode text="https://t.me/sellermax_bot?start=abc" label="QR" />);
    expect(pathOf()).toBe(first);
    cleanup();
    render(<QrCode text="https://t.me/sellermax_bot?start=abd" label="QR" />);
    expect(pathOf()).not.toBe(first);
  });
});
