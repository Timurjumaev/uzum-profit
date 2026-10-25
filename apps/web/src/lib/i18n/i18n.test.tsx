import { render } from "@testing-library/react";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";

import { buildCyrillic, createI18n, currentLang, detectLang, LANGS, resources, setLanguage, useFormat } from ".";
import { term } from "./glossary";
import { uzLatn } from "./messages/uz-Latn";
import { searchKey, toCyrillic, toLatin, uzApostrophes } from "./translit";

type Tree = { [key: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): Array<[string, string]> {
  return Object.entries(tree).flatMap(([key, value]) =>
    typeof value === "string" ? [[`${prefix}${key}`, value] as [string, string]] : leaves(value, `${prefix}${key}.`),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  localStorage.clear();
});

describe("transliteratsiya (04 §8.3)", () => {
  it("lotin → kirill: harflar, juftliklar, e/э, tutuq, katta harf", () => {
    expect(toCyrillic("Oʻzbekiston")).toBe("Ўзбекистон");
    expect(toCyrillic("gʻalla shahar choy")).toBe("ғалла шаҳар чой");
    expect(toCyrillic("yoʻq yangi yoz yuz")).toBe("йўқ янги ёз юз");
    expect(toCyrillic("eski ega mehr")).toBe("эски эга меҳр");
    expect(toCyrillic("maʼlumot")).toBe("маълумот");
    expect(toCyrillic("SHAHAR Shahar")).toBe("ШАҲАР Шаҳар");
    expect(toCyrillic("qoʻshiq xabar")).toBe("қўшиқ хабар");
  });

  it("istisnolar: o'zlashmalar, nomlar, o'zgaruvchilar", () => {
    expect(toCyrillic("23-oktabr, sentabr, iyun")).toBe("23-октябр, сентябр, июн");
    expect(toCyrillic("Kompensatsiya")).toBe("Компенсация");
    expect(toCyrillic("Uzum ROI SKU")).toBe("Uzum ROI SKU");
    expect(toCyrillic("Telegramʼda Uzumʼning")).toBe("Telegramʼда Uzumʼнинг");
    expect(toCyrillic("Soʻrov ID: {{id}} <b>qalin</b>")).toBe("Сўров ID: {{id}} <b>қалин</b>");
    expect(toCyrillic("+998 XX XXX")).toBe("+998 XX XXX");
  });

  it("kirill → lotin va qidiruv kaliti", () => {
    expect(toLatin("Ўзбекистон Ғалла Шаҳар")).toBe("Oʻzbekiston Gʻalla Shahar");
    expect(toLatin("маълумот ёз юз яна")).toBe("maʼlumot yoz yuz yana");
    expect(toLatin("Цех щётка подъезд")).toBe("Tsex shyotka podʼezd");
    const keys = ["Ғалла", "G'alla", "gʻalla", "G‘ALLA", "  gʼalla  "].map(searchKey);
    expect(new Set(keys).size).toBe(1);
    expect(searchKey("Ma'lumot   bor")).toBe(searchKey("Маълумот бор"));
  });

  it("oddiy apostrof → UI yozuvi", () => {
    expect(uzApostrophes("O'zbek bo'sh ma'lumot g'alla")).toBe("Oʻzbek boʻsh maʼlumot gʻalla");
  });
});

describe("tarjimalar", () => {
  const latin = leaves(uzLatn as Tree);
  const cyr = leaves(resources["uz-Cyrl"].translation as Tree);
  const ru = leaves(resources.ru.translation as Tree);

  it("hamma tilda kalitlar bir xil", () => {
    const keys = latin.map(([k]) => k);
    expect(cyr.map(([k]) => k)).toEqual(keys);
    expect(ru.map(([k]) => k).sort()).toEqual([...keys].sort());
  });

  it("uz-Latn: oddiy apostrof yo'q, oʻ/gʻ — U+02BB (04 §8.3)", () => {
    for (const [key, text] of latin) {
      expect(text, key).not.toMatch(/['‘’`]/);
      expect(text, key).not.toMatch(/[oOgG]ʼ/); // oʻ/gʻ tutuq bilan yozilmagan
    }
  });

  it("uz-Cyrl: lotin harflari faqat nomlarda va o'zgaruvchilarda", () => {
    const allowed = /\{\{[^}]*\}\}|Uzum|Profit|Telegram|ROI|DRR|SKU|ID|X+|Oʻzbekcha/g;
    for (const [key, text] of cyr) {
      if (key === "languages.uz-Latn") continue;
      expect(text.replace(allowed, ""), key).not.toMatch(/[A-Za-zʻ]/);
    }
  });

  it("qo'lda tuzatish ustun", () => {
    const out = buildCyrillic(uzLatn, { "common.retry": "Яна уриниш" });
    expect(out.common.retry).toBe("Яна уриниш");
    expect(out.common.loading).toBe("Юкланмоқда…");
  });
});

describe("til tanlash", () => {
  it("saqlangan → brauzer → uz-Latn", () => {
    expect(detectLang()).toBe("uz-Latn");
    vi.stubGlobal("navigator", { language: "ru-RU" });
    expect(detectLang()).toBe("ru");
    localStorage.setItem("up.lang", "uz-Cyrl");
    expect(detectLang()).toBe("uz-Cyrl");
    localStorage.setItem("up.lang", "en");
    expect(detectLang()).toBe("ru");
  });

  it("localStorage yopiq bo'lsa ham ishlaydi", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => {
        throw new Error("SecurityError");
      },
      setItem: () => {
        throw new Error("SecurityError");
      },
    });
    expect(detectLang()).toBe("uz-Latn");
    const i18n = createI18n("uz-Latn");
    return setLanguage(i18n, "ru").then(() => expect(currentLang(i18n)).toBe("ru"));
  });

  it("tarjima, almashtirish, <html lang>, formatlovchi", async () => {
    const i18n = createI18n("uz-Latn");
    expect(i18n.t("errors.codes.otp_invalid")).toContain("Kod notoʻgʻri");
    expect(i18n.t("common.requestId", { id: "r1" })).toBe("Soʻrov ID: r1");
    expect(document.documentElement.lang).toBe("uz-Latn");
    await setLanguage(i18n, "uz-Cyrl");
    expect(i18n.t(term("netProfit"))).toBe("Соф фойда");
    expect(document.documentElement.lang).toBe("uz-Cyrl");
    expect(localStorage.getItem("up.lang")).toBe("uz-Cyrl");
    expect(LANGS).toEqual(["uz-Latn", "uz-Cyrl", "ru"]);

    function Money() {
      const f = useFormat();
      return <span>{f.money(1500)}</span>;
    }
    await setLanguage(i18n, "ru");
    const { container } = render(
      <I18nextProvider i18n={i18n}>
        <Money />
      </I18nextProvider>,
    );
    expect(container.textContent).toBe("1\u00A0500\u00A0сум");
  });
});
