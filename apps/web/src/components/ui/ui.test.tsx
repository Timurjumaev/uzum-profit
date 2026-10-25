import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState, type ReactNode } from "react";
import { I18nextProvider } from "react-i18next";
import { afterEach, describe, expect, it, vi } from "vitest";

import { parseNumber } from "../../lib/format";
import { createI18n } from "../../lib/i18n";
import type { Range } from "../../lib/dates";
import {
  Banner,
  Button,
  changeTone,
  Combobox,
  CompareToggle,
  DataTable,
  DateRangePicker,
  Dialog,
  Drawer,
  filterOptions,
  FormulaPopover,
  Kpi,
  LedgerTable,
  MoneyInput,
  NumberInput,
  ProductThumb,
  ProgressBar,
  Skeleton,
  StatusPill,
  Timeline,
  ToastProvider,
  Tooltip,
  useToast,
  type CompareMode,
} from ".";

const i18n = createI18n("uz-Latn");
const wrap = (node: ReactNode) => render(<I18nextProvider i18n={i18n}>{node}</I18nextProvider>);

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("parseNumber (MoneyInput)", () => {
  it.each([
    ["1 234,5", "1234.5"],
    ["1234.5", "1234.5"],
    ["1 234 567", "1234567"],
    ["1 234 567", "1234567"],
    ["−312 400", "-312400"],
    ["1.234.567", "1234567"],
    ["1.234.567,50", "1234567.50"],
    ["1,234,567.5", "1234567.5"],
    ["0,5", "0.5"],
    [",5", "0.5"],
    ["-0", "0"],
    ["007", "7"],
  ])("%s → %s", (input, expected) => expect(parseNumber(input)).toBe(expected));

  it.each(["", "  ", "abc", "1,2,3.4.5", "1-2", "--1", "1e5"])("%s → null", (input) =>
    expect(parseNumber(input)).toBeNull(),
  );
});

describe("tugma va maydonlar", () => {
  it("Button: yuklanishda matn qoladi, bosilmaydi, aria-busy", () => {
    const onClick = vi.fn();
    wrap(
      <Button variant="primary" loading onClick={onClick}>
        Saqlash
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Saqlash" });
    expect(button.getAttribute("aria-busy")).toBe("true");
    expect((button as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(button);
    expect(onClick).not.toHaveBeenCalled();
    expect(button.className).toContain("ui-btn--primary");
  });

  it("MoneyInput: '1 234,5' → '1234.5', blur'da formatlanadi, xato matni", () => {
    const seen: Array<string | null> = [];
    function Demo() {
      const [value, setValue] = useState<string | null>(null);
      return (
        <MoneyInput
          label="Summa"
          value={value}
          onValueChange={(v) => {
            seen.push(v);
            setValue(v);
          }}
        />
      );
    }
    wrap(<Demo />);
    const input = screen.getByLabelText("Summa") as HTMLInputElement;
    expect(input.getAttribute("inputmode")).toBe("decimal");
    fireEvent.change(input, { target: { value: "1 234,5" } });
    expect(seen.at(-1)).toBe("1234.5");
    fireEvent.blur(input);
    expect(input.value).toBe("1 234,5");
    expect(screen.getByText("soʻm")).toBeTruthy();
    fireEvent.change(input, { target: { value: "12abc" } });
    expect(seen.at(-1)).toBe("1234.5"); // noto'g'ri qiymat yuborilmaydi
    expect(screen.getByRole("alert").textContent).toContain("Son notoʻgʻri");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    fireEvent.change(input, { target: { value: "" } });
    expect(seen.at(-1)).toBeNull();
  });

  it("NumberInput: yorliq, yordam matni aria-describedby orqali", () => {
    wrap(<NumberInput label="Dona" help="Butun son" value="5" onValueChange={() => {}} />);
    const input = screen.getByLabelText("Dona");
    const help = document.getElementById(input.getAttribute("aria-describedby")!);
    expect(help?.textContent).toBe("Butun son");
  });
});

describe("Combobox (04 §8.3)", () => {
  const options = [
    { value: "1", label: "Gʻalla sumka", hint: "SKU-101" },
    { value: "2", label: "Oʻyinchoq ayiq", hint: "SKU-102" },
    { value: "3", label: "Чарм ҳамён", hint: "SKU-104" },
  ];

  it("lotin/kirill va apostrof turlaridan qat'i nazar", () => {
    expect(filterOptions(options, "galla").map((o) => o.value)).toEqual(["1"]);
    expect(filterOptions(options, "ғалла").map((o) => o.value)).toEqual(["1"]);
    expect(filterOptions(options, "G'ALLA").map((o) => o.value)).toEqual(["1"]);
    expect(filterOptions(options, "charm hamyon").map((o) => o.value)).toEqual(["3"]); // ё → yo
    expect(filterOptions(options, "charm").map((o) => o.value)).toEqual(["3"]);
    expect(filterOptions(options, "sku-102").map((o) => o.value)).toEqual(["2"]);
    expect(filterOptions(options, "  ")).toHaveLength(3);
  });

  it("klaviatura: ↓ ↓ Enter tanlaydi, Esc yopadi", () => {
    const onChange = vi.fn();
    wrap(<Combobox label="Mahsulot" options={options} value={null} onValueChange={onChange} />);
    const input = screen.getByRole("combobox", { name: "Mahsulot" });
    fireEvent.focus(input);
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getAllByRole("option")).toHaveLength(3);
    fireEvent.keyDown(input, { key: "ArrowDown" });
    expect(input.getAttribute("aria-activedescendant")).toBe(screen.getAllByRole("option")[1].id);
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith("2");
    fireEvent.change(input, { target: { value: "yoq-narsa" } });
    expect(screen.getByText("Hech narsa topilmadi")).toBeTruthy();
    fireEvent.keyDown(input, { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});

describe("qatlamlar", () => {
  it("Dialog: fokus ichida, Esc va fon bilan yopiladi, fokus qaytadi", () => {
    function Demo() {
      const [open, setOpen] = useState(false);
      return (
        <>
          <button onClick={() => setOpen(true)}>Ochish</button>
          <Dialog open={open} onClose={() => setOpen(false)} title="Oʻchirish" footer={<button>Ha</button>}>
            <p>Matn</p>
          </Dialog>
        </>
      );
    }
    wrap(<Demo />);
    const opener = screen.getByRole("button", { name: "Ochish" });
    opener.focus();
    fireEvent.click(opener);
    const dialog = screen.getByRole("dialog", { name: "Oʻchirish" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const close = screen.getByRole("button", { name: "Yopish" });
    expect(document.activeElement).toBe(close);
    const yes = screen.getByRole("button", { name: "Ha" });
    yes.focus();
    fireEvent.keyDown(dialog, { key: "Tab" });
    expect(document.activeElement).toBe(close); // oxiridan boshiga
    fireEvent.keyDown(dialog, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(yes);
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(opener);
  });

  it("Drawer: fon bosilsa yopiladi", () => {
    const onClose = vi.fn();
    wrap(
      <Drawer open onClose={onClose} title="Tushum">
        <p>yozuvlar</p>
      </Drawer>,
    );
    fireEvent.click(document.querySelector(".ui-layer__backdrop")!);
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("FormulaPopover: F-raqam, manba, taxminiy sababi; Esc yopadi", () => {
    wrap(<FormulaPopover metric="Sof foyda" code="F12" formula="F8 − F9 − F10 − F11" source="sotuvlar" estimatedReason="tannarx yoʻq" />);
    const trigger = screen.getByRole("button", { name: "Qanday hisoblanadi: Sof foyda" });
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("Sof foyda · F12")).toBeTruthy();
    expect(screen.getByText("Manba: sotuvlar")).toBeTruthy();
    expect(screen.getByText("Taxminiy")).toBeTruthy();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    fireEvent.click(trigger);
    fireEvent.mouseDown(document.body);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
  });

  it("Tooltip: fokusda ko'rinadi, aria-describedby", () => {
    wrap(
      <Tooltip text="Izoh">
        <button>Savol</button>
      </Tooltip>,
    );
    const button = screen.getByRole("button", { name: "Savol" });
    const tip = screen.getByRole("tooltip", { hidden: true });
    expect(button.getAttribute("aria-describedby")).toBe(tip.id);
    fireEvent.focus(button);
    expect(tip.className).toContain("is-shown");
    fireEvent.keyDown(button, { key: "Escape" });
    expect(tip.className).not.toContain("is-shown");
  });

  it("Toast: matn, aria-live, 5 s da yo'qoladi", () => {
    vi.useFakeTimers();
    function Demo() {
      const toast = useToast();
      return <button onClick={() => toast.show("Xarid saqlandi")}>Saqlash</button>;
    }
    wrap(
      <ToastProvider>
        <Demo />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Saqlash" }));
    expect(screen.getByText("Xarid saqlandi")).toBeTruthy();
    expect(document.querySelector(".ui-toasts")?.getAttribute("aria-live")).toBe("polite");
    act(() => vi.advanceTimersByTime(5000));
    expect(screen.queryByText("Xarid saqlandi")).toBeNull();
  });

  it("useToast provayder'siz — tushunarli xato", () => {
    function Bad() {
      useToast();
      return null;
    }
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => wrap(<Bad />)).toThrow(/ToastProvider/);
  });
});

describe("davr va solishtirish", () => {
  it("DateRangePicker: tayyor davr nomi, preset va kalendar bilan tanlash", () => {
    const changes: Range[] = [];
    function Demo() {
      const [range, setRange] = useState<Range>({ start: "2026-10-01", end: "2026-10-25" });
      return (
        <DateRangePicker
          value={range}
          today="2026-10-25"
          first="2026-07-14"
          onChange={(r) => {
            changes.push(r);
            setRange(r);
          }}
        />
      );
    }
    wrap(<Demo />);
    const trigger = screen.getByRole("button", { name: /Davr: Shu oy · 1–25-oktabr/ });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Oʻtgan oy" }));
    expect(changes.at(-1)).toEqual({ start: "2026-09-01", end: "2026-09-30" });
    expect(trigger.textContent).toContain("Oʻtgan oy");
    expect(document.activeElement).toBe(trigger);

    fireEvent.click(trigger);
    expect(screen.getByText("sentabr 2026")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Keyingi oy" }));
    fireEvent.click(screen.getByRole("button", { name: "20-oktabr" }));
    fireEvent.click(screen.getByRole("button", { name: "5-oktabr" })); // teskari tartib ham to'g'ri
    expect(changes.at(-1)).toEqual({ start: "2026-10-05", end: "2026-10-20" });
    fireEvent.click(trigger);
    expect((screen.getByRole("button", { name: "26-oktabr" }) as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Hammasi" }));
    expect(changes.at(-1)).toEqual({ start: "2026-07-14", end: "2026-10-25" });
  });

  it("CompareToggle: radio guruh", () => {
    function Demo() {
      const [mode, setMode] = useState<CompareMode>("none");
      return <CompareToggle value={mode} onChange={setMode} />;
    }
    wrap(<Demo />);
    const lastYear = screen.getByRole("radio", { name: "Oʻtgan yil" }) as HTMLInputElement;
    fireEvent.click(lastYear);
    expect(lastYear.checked).toBe(true);
    expect(screen.getByRole("group", { name: "Solishtirish" })).toBeTruthy();
  });
});

describe("raqamli komponentlar", () => {
  it("KPI: rang = yo'nalish × yaxshimi; ▲/▼ va nom bilan davr", () => {
    expect(changeTone("0.12", "up")).toBe("positive");
    expect(changeTone("0.12", "down")).toBe("negative");
    expect(changeTone("-0.05", "down")).toBe("positive");
    expect(changeTone("0", "up")).toBe("neutral");
    const { container } = wrap(
      <Kpi label="Xarajat" value="100" change="0.081" good="down" changeLabel="oldingi davrga nisbatan" spark={[1, 2, 3]} />,
    );
    const change = container.querySelector(".ui-kpi__change")!;
    expect(change.className).toContain("ui-text--negative");
    expect(change.textContent).toBe("▲ 8,1% oldingi davrga nisbatan");
    expect(container.querySelector("svg")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("LedgerTable: operator, tabular summa, oraliq va yakun, drill-down", () => {
    const onRow = vi.fn();
    const { container } = wrap(
      <LedgerTable
        caption="Hisob"
        onRowClick={onRow}
        rows={[
          { key: "r", label: "Tushum", amount: "186420000.00" },
          { key: "c", label: "Komissiya", amount: "-37284000.00", op: "−" },
          { key: "p", label: "Uzum toʻlovi", amount: "149136000.00", op: "=", kind: "subtotal" },
          { key: "n", label: "Sof foyda", amount: "48357200", op: "=", kind: "total" },
        ]}
      />,
    );
    const rows = container.querySelectorAll("tbody tr");
    expect(rows[1].textContent).toBe("−Komissiya−37 284 000");
    expect(rows[2].className).toBe("is-subtotal");
    expect(rows[3].className).toBe("is-total");
    expect(screen.getByRole("table", { name: "Hisob" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sof foyda" }));
    expect(onRow).toHaveBeenCalledWith(expect.objectContaining({ key: "n" }));
  });

  it("DataTable: sarlavha, raqam ustunlari, jami, bo'sh holat", () => {
    const columns = [
      { key: "name", header: "Mahsulot", render: (r: { n: string; v: string }) => r.n },
      { key: "v", header: "Tushum", numeric: true, render: (r: { n: string; v: string }) => r.v },
    ];
    const { container, rerender } = wrap(
      <DataTable caption="SKU" columns={columns} rows={[{ n: "A", v: "1 000" }]} rowKey={(r) => r.n} total={{ name: "Jami", v: "1 000" }} />,
    );
    expect(screen.getByRole("region", { name: "SKU" })).toBeTruthy();
    expect(screen.getByRole("columnheader", { name: "Tushum" }).className).toBe("num");
    expect(screen.getByRole("rowheader", { name: "A" })).toBeTruthy();
    expect(container.querySelector("tfoot")?.textContent).toBe("Jami1 000");
    rerender(
      <I18nextProvider i18n={i18n}>
        <DataTable caption="SKU" columns={columns} rows={[]} rowKey={(r) => r.n} empty="Hali sotuv yoʻq" />
      </I18nextProvider>,
    );
    expect(screen.getByText("Hali sotuv yoʻq")).toBeTruthy();
  });
});

describe("holat va qolganlari", () => {
  it("StatusPill va Banner: ikon + matn, xato — alert", () => {
    const { container } = wrap(<StatusPill tone="negative">Xato</StatusPill>);
    expect(container.querySelector("svg")).toBeTruthy();
    expect(container.textContent).toBe("Xato");
    const onDismiss = vi.fn();
    wrap(
      <Banner tone="negative" title="Kalit rad etildi" onDismiss={onDismiss}>
        <p>Yangi kalit kiriting</p>
      </Banner>,
    );
    expect(screen.getByRole("alert").textContent).toContain("Kalit rad etildi");
    fireEvent.click(screen.getByRole("button", { name: "Yopish" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("Skeleton 300 ms dan keyin ko'rinadi", () => {
    vi.useFakeTimers();
    const { container } = wrap(<Skeleton label="Yuklanmoqda" />);
    expect(container.querySelectorAll(".ui-skeleton__line")).toHaveLength(0);
    act(() => vi.advanceTimersByTime(300));
    expect(container.querySelectorAll(".ui-skeleton__line")).toHaveLength(3);
    expect(screen.getByRole("status", { name: "Yuklanmoqda" })).toBeTruthy();
  });

  it("ProgressBar: aria qiymatlari, chegaralangan", () => {
    wrap(<ProgressBar label="Sotuvlar" value={150} max={100} />);
    const bar = screen.getByRole("progressbar", { name: "Sotuvlar" });
    expect([bar.getAttribute("aria-valuenow"), bar.getAttribute("aria-valuemax")]).toEqual(["150", "100"]);
    expect((bar.firstChild as HTMLElement).style.inlineSize).toBe("100%");
  });

  it("ProductThumb: rasm yuklanmasa — harf", () => {
    wrap(<ProductThumb src="https://cdn/x.jpg" name="sumka" />);
    const img = screen.getByRole("img", { name: "sumka" });
    expect(img.getAttribute("loading")).toBe("lazy");
    fireEvent.error(img);
    expect(screen.getByRole("img", { name: "sumka" }).textContent).toBe("S");
  });

  it("Timeline: joriy bosqich, kunlar, kutilgan sana, kechikish", () => {
    const { container } = wrap(
      <Timeline
        label="Partiya yoʻli"
        stages={[
          { label: "Buyurtma", state: "done", date: "2026-10-02" },
          { label: "Yoʻlda", state: "current", days: 11, delayed: true },
          { label: "Toshkent", state: "upcoming", expected: "2026-10-28" },
        ]}
      />,
    );
    const current = container.querySelector('[aria-current="step"]')!;
    expect(current.textContent).toContain("11 kun");
    expect(current.textContent).toContain("Kechikmoqda");
    expect(container.textContent).toContain("kutilmoqda ~28.10");
    expect(container.textContent).toContain("02.10");
  });
});
