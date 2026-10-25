// /ui-kit (04 §5): hamma komponentlar holatlari bilan — dizayn ko'rigi va vizual testlar (B3.8) uchun ichki sahifa.
// Ma'lumot sintetik (04 §6.1, §6.2 namunalari). Matnlar namunaviy — sahifalar o'z matnlarini i18n'dan oladi.
import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";

import {
  Badge,
  Banner,
  Button,
  Combobox,
  CompareToggle,
  DataTable,
  DateRangePicker,
  Dialog,
  Drawer,
  EmptyState,
  FileDrop,
  FormulaPopover,
  Kpi,
  LedgerTable,
  MoneyInput,
  NumberInput,
  ProductThumb,
  ProgressBar,
  Select,
  Skeleton,
  StatusPill,
  Stepper,
  TextInput,
  Timeline,
  Tooltip,
  useToast,
  type ComboOption,
  type CompareMode,
  type LedgerRow,
} from "../components/ui";
import type { Range } from "../lib/dates";
import { LANGS, setLanguage, useFormat, type Lang } from "../lib/i18n";
import { useTheme, type ThemeChoice } from "../lib/theme";
import "./ui-kit.css";

const TODAY = "2026-10-25";

const LEDGER: LedgerRow[] = [
  { key: "revenue", label: "Tushum", amount: "186420000.00" },
  { key: "commission", label: "Uzum komissiyasi", amount: "-37284000.00", op: "−" },
  { key: "logistics", label: "Logistika", amount: "-9135750.00", op: "−" },
  { key: "payout", label: "Uzum toʻlovi", amount: "140000250.00", op: "=", kind: "subtotal" },
  { key: "cogs", label: "Tannarx (partiyalar)", amount: "-78112050.00", op: "−" },
  { key: "uzum", label: "Reklama, saqlash, jarima", amount: "-11631000.00", op: "−" },
  { key: "own", label: "Oʻz xarajatlarim", amount: "0", op: "−" },
  { key: "tax", label: "Soliq (1%)", amount: "-1864200.00", op: "−" },
  { key: "net", label: "Sof foyda", amount: "48357200.00", op: "=", kind: "total" },
];

type Sku = { id: string; name: string; units: number; revenue: string; profit: string; margin: string };
const SKUS: Sku[] = [
  { id: "1", name: "Ayollar sumkasi, qora", units: 412, revenue: "24720000", profit: "6180000", margin: "0.25" },
  { id: "2", name: "Ryukzak, kulrang", units: 238, revenue: "16422000", profit: "2463300", margin: "0.15" },
  { id: "3", name: "Hamyon, jigarrang", units: 57, revenue: "1938000", profit: "-212400", margin: "-0.109" },
];

const OPTIONS: ComboOption[] = [
  { value: "1", label: "Gʻalla sumka", hint: "SKU-101", keywords: "qop" },
  { value: "2", label: "Oʻyinchoq ayiq", hint: "SKU-102" },
  { value: "3", label: "Shaharcha ryukzak", hint: "SKU-103" },
  { value: "4", label: "Чарм ҳамён", hint: "SKU-104" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="kit-section" aria-labelledby={`kit-${title}`}>
      <h2 id={`kit-${title}`}>{title}</h2>
      <div className="kit-row">{children}</div>
    </section>
  );
}

export function UiKit() {
  const { t, i18n } = useTranslation();
  const f = useFormat();
  const toast = useToast();
  const { choice, setTheme } = useTheme();
  const [text, setText] = useState("byDurii");
  const [qty, setQty] = useState<string | null>("1234.5");
  const [money, setMoney] = useState<string | null>("48357200");
  const [usd, setUsd] = useState<string | null>("142.5");
  const [shop, setShop] = useState("a");
  const [sku, setSku] = useState<string | null>(null);
  const [range, setRange] = useState<Range>({ start: "2026-10-01", end: TODAY });
  const [compare, setCompare] = useState<CompareMode>("previous");
  const [dialog, setDialog] = useState(false);
  const [drawer, setDrawer] = useState<LedgerRow | null>(null);
  const [loading, setLoading] = useState(false);

  return (
    <main className="kit">
      <header className="kit-head">
        <h1>UI-kit</h1>
        <div className="kit-row">
          <Select
            label="Mavzu"
            value={choice}
            onValueChange={(v) => setTheme(v as ThemeChoice)}
            options={[
              { value: "system", label: "Tizim" },
              { value: "light", label: "Yorugʻ" },
              { value: "dark", label: "Qorongʻi" },
            ]}
          />
          <Select
            label={t("common.language")}
            value={i18n.language}
            onValueChange={(v) => void setLanguage(i18n, v as Lang)}
            options={LANGS.map((l) => ({ value: l, label: t(`languages.${l}`) }))}
          />
        </div>
      </header>

      <Section title="Button">
        <Button variant="primary">Xaridni saqlash</Button>
        <Button>Bekor qilish</Button>
        <Button variant="ghost">Batafsil</Button>
        <Button variant="destructive">Oʻchirish</Button>
        <Button variant="primary" size="sm">
          Kichik
        </Button>
        <Button variant="primary" size="lg">
          Katta
        </Button>
        <Button variant="primary" disabled>
          Faol emas
        </Button>
        <Button
          variant="primary"
          loading={loading}
          onClick={() => {
            setLoading(true);
            setTimeout(() => setLoading(false), 1500);
          }}
        >
          Saqlash
        </Button>
      </Section>

      <Section title="Input, NumberInput, MoneyInput">
        <TextInput label="Doʻkon taxallusi" value={text} onValueChange={setText} help="Roʻyxatlarda koʻrinadi" />
        <NumberInput label="Dona" value={qty} onValueChange={setQty} help="1 234,5 yoki 1234.5" />
        <MoneyInput label="Xarid summasi" value={money} onValueChange={setMoney} />
        <MoneyInput label="Kargo" currency="USD" value={usd} onValueChange={setUsd} optional />
        <TextInput label="Telefon" value="+99890" onValueChange={() => {}} error={t("errors.codes.invalid_phone")} />
        <TextInput label="Faol emas" value="—" onValueChange={() => {}} disabled />
      </Section>

      <Section title="Select, Combobox">
        <Select
          label="Doʻkon"
          value={shop}
          onValueChange={setShop}
          options={[
            { value: "a", label: "byDurii" },
            { value: "b", label: "EL-ONE" },
          ]}
        />
        <Combobox
          label="Mahsulot"
          help="Lotin yoki kirillda, apostrofsiz ham topiladi: galla, ғалла"
          options={OPTIONS.map((o) => ({ ...o, thumb: <ProductThumb name={o.label} size={32} /> }))}
          value={sku}
          onValueChange={setSku}
        />
      </Section>

      <Section title="DateRangePicker, CompareToggle">
        <DateRangePicker value={range} onChange={setRange} today={TODAY} first="2026-07-14" />
        <CompareToggle value={compare} onChange={setCompare} />
      </Section>

      <Section title="KPI, FormulaPopover">
        <div className="kit-grid">
          <Kpi
            label="Sof foyda"
            value={f.money("48357200")}
            change="0.124"
            changeLabel={t("ui.vsPrevious")}
            spark={[12, 14, 13, 17, 16, 19, 18, 22, 21, 24, 23, 27]}
            help={
              <FormulaPopover
                metric="Sof foyda"
                code="F12"
                formula="Yalpi foyda − Uzum xarajatlari − Oʻz xarajatlarim − Soliq"
                source="sotuvlar, xarajatlar, partiyalar"
                estimatedReason="12 ta sotuvda tannarx yoʻq"
              />
            }
          />
          <Kpi
            label="Uzum xarajatlari"
            value={f.money("11631000")}
            change="0.081"
            good="down"
            changeLabel={t("ui.vsPrevious")}
            spark={[9, 9, 10, 10, 11, 10, 11, 12, 11, 12, 12, 13]}
          />
          <Kpi label="Marja" value={f.percent("0.259")} change="-0.031" changeLabel={t("ui.vsLastYear")} />
        </div>
      </Section>

      <Section title="LedgerTable (Hisob varagʻi)">
        <div className="kit-ledger">
          <p className="label">Sof foyda, oktabr</p>
          <p className="hero">{f.money("48357200")}</p>
          <LedgerTable caption="Hisob varagʻi, oktabr" rows={LEDGER} onRowClick={setDrawer} />
          <p className="caption">
            <Badge tone="warning">Taxminiy</Badge> Tannarxsiz 12 ta sotuv ({f.money("1240000")}) hisobga kirmadi
          </p>
        </div>
      </Section>

      <Section title="DataTable">
        <DataTable
          caption="Mahsulotlar"
          rows={SKUS}
          rowKey={(r) => r.id}
          columns={[
            {
              key: "name",
              header: "Mahsulot",
              render: (r) => (
                <span className="kit-sku">
                  <ProductThumb name={r.name} size={32} />
                  {r.name}
                </span>
              ),
            },
            { key: "units", header: "Dona", numeric: true, render: (r) => f.number(r.units) },
            { key: "revenue", header: "Tushum", numeric: true, render: (r) => f.money(r.revenue, { unit: false }) },
            {
              key: "profit",
              header: "Foyda",
              numeric: true,
              render: (r) => (
                <span className={Number(r.profit) < 0 ? "ui-text--negative" : undefined}>
                  {f.money(r.profit, { unit: false })}
                </span>
              ),
            },
            { key: "margin", header: "Marja", numeric: true, render: (r) => f.percent(r.margin) },
          ]}
          total={{ name: "Jami", units: f.number(707), revenue: f.money("43080000", { unit: false }), profit: f.money("8430900", { unit: false }), margin: f.percent("0.196") }}
        />
      </Section>

      <Section title="Badge, StatusPill">
        <StatusPill tone="positive">Sinxron ishlayapti</StatusPill>
        <StatusPill tone="warning">Kalit muddati tugaydi</StatusPill>
        <StatusPill tone="negative">Uzum javob bermayapti</StatusPill>
        <StatusPill tone="info">Tarix yuklanmoqda</StatusPill>
        <StatusPill>Faol emas</StatusPill>
        <Badge tone="warning">Taxminiy</Badge>
        <Badge>12</Badge>
      </Section>

      <Section title="Banner">
        <div className="kit-stack">
          <Banner tone="negative" title="Uzum kalitni rad etdi" action={<Button variant="primary">Kalitni almashtirish</Button>}>
            <p>Kabinetda yangi kalit yarating va shu yerga qoʻying.</p>
          </Banner>
          <Banner tone="warning" title="Tannarx qamrovi 82%" onDismiss={() => {}}>
            <p>18% sotuvda tannarx yoʻq — foyda taxminiy.</p>
          </Banner>
          <Banner tone="info" title="Uzumʼda uzilish">
            <p>Tiklangach maʼlumot avtomatik toʻldiriladi.</p>
          </Banner>
        </div>
      </Section>

      <Section title="Dialog, Drawer, Popover, Tooltip, Toast">
        <Button onClick={() => setDialog(true)}>Dialog</Button>
        <Button onClick={() => setDrawer(LEDGER[1])}>Drawer</Button>
        <Tooltip text="Uzum bergan sotuv summasi">
          <Button variant="ghost">Tooltip</Button>
        </Tooltip>
        <Button onClick={() => toast.show("Xarid saqlandi")}>Toast</Button>
        <Dialog
          open={dialog}
          onClose={() => setDialog(false)}
          title="Xaridni oʻchirish"
          footer={
            <>
              <Button onClick={() => setDialog(false)}>Bekor qilish</Button>
              <Button variant="destructive" onClick={() => setDialog(false)}>
                Oʻchirish
              </Button>
            </>
          }
        >
          <p>Partiya va unga bogʻliq tannarxlar qayta hisoblanadi.</p>
        </Dialog>
        <Drawer open={drawer !== null} onClose={() => setDrawer(null)} title={drawer?.label ?? ""}>
          <p>Shu summani tashkil qilgan yozuvlar (B4.2).</p>
        </Drawer>
      </Section>

      <Section title="Stepper, Timeline (Partiya yoʻli)">
        <div className="kit-stack">
          <Stepper
            label="Onboarding"
            steps={[
              { label: "Kalit", state: "done" },
              { label: "Doʻkonlar", state: "done" },
              { label: "Tarix", state: "current" },
              { label: "Tannarx", state: "upcoming" },
            ]}
          />
          <Timeline
            label="Partiya yoʻli"
            stages={[
              { label: "Buyurtma", state: "done", date: "2026-10-02" },
              { label: "Toʻlandi", state: "done", date: "2026-10-03" },
              { label: "Xitoy ombori", state: "done", date: "2026-10-09" },
              { label: "Yoʻlda", state: "current", date: "2026-10-12", days: 11, delayed: true },
              { label: "Toshkent", state: "upcoming", expected: "2026-10-28" },
              { label: "Qabul", state: "upcoming" },
              { label: "Uzum", state: "upcoming" },
            ]}
          />
        </div>
      </Section>

      <Section title="EmptyState, Skeleton, ProgressBar">
        <div className="kit-grid">
          <EmptyState
            title="Hali xarid yoʻq"
            text="Birinchi partiyani kiriting — tannarx va foyda shundan hisoblanadi."
            action={<Button variant="primary">Xarid qoʻshish</Button>}
          />
          <Skeleton label={t("ui.loading")} delay={0} lines={4} />
          <div className="kit-stack">
            <ProgressBar label="byDurii · sotuvlar" value={1830} max={2465} detail={t("ui.progress", { done: f.number(1830), total: f.number(2465) })} />
            <ProgressBar label="EL-ONE · xarajatlar" value={203} max={203} detail={t("ui.progress", { done: 203, total: 203 })} />
          </div>
        </div>
      </Section>

      <Section title="ProductThumb, FileDrop">
        <ProductThumb name="Sumka" />
        <ProductThumb name="Ryukzak" size={64} />
        <FileDrop accept=".xlsx,.xls,.csv" onFiles={(files) => toast.show(`${files[0].name}`, "info")} templateHref="#" hint="Excel (.xlsx), 5 MB gacha" />
      </Section>
    </main>
  );
}
