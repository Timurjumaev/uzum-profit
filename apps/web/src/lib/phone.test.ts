import { describe, expect, it } from "vitest";

import { formatPhone, normalizePhone } from "./phone";

describe("normalizePhone", () => {
  it.each([
    ["+998 90 123 45 67", "+998901234567"],
    ["998901234567", "+998901234567"],
    ["90 123-45-67", "+998901234567"],
    ["(90) 1234567", "+998901234567"],
    ["901234567", "+998901234567"],
    ["+998-90-123-45-67", "+998901234567"],
    ["  +998901234567  ", "+998901234567"],
    ["+99890 123 45 67", "+998901234567"],
  ])("%s → %s", (input, expected) => {
    expect(normalizePhone(input)).toBe(expected);
  });

  it.each(["", "abc", "+998 90 123", "90123456", "9012345678", "+7 912 345 67 89", "+998901234567890", "+99890123456"])(
    "noto'g'ri: %s",
    (input) => {
      expect(normalizePhone(input)).toBeNull();
    },
  );

  it("faqat raqamlar hisobga olinadi (boshqa belgilar tashlanadi)", () => {
    expect(normalizePhone("tel: 90.123.45.67")).toBe("+998901234567");
  });
});

describe("formatPhone", () => {
  it("o'qiladigan ko'rinish; noto'g'ri bo'lsa o'zgarishsiz", () => {
    expect(formatPhone("+998901234567")).toBe("+998 90 123 45 67");
    expect(formatPhone("90 123 45 67")).toBe("+998 90 123 45 67");
    expect(formatPhone("abc")).toBe("abc");
  });
});
