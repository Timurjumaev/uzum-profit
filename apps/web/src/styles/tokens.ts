// Dizayn tokenlari (04 §2–4) — yagona manba. CSS o'zgaruvchilari (`tokens.css`) shu qiymatlar bilan bir xil bo'lishi
// test bilan tekshiriladi; grafiklar (ECharts, B3.6) ranglarni shu yerdan oladi. Qorong'i rejim avtomatik inversiya
// emas — har token alohida (04 §4.2).

export type Theme = "light" | "dark";

/** 04 §4.2 — `--<nom>` CSS o'zgaruvchilari. */
export const colors = {
  light: {
    "bg-page": "#F5F6F8",
    "bg-surface": "#FFFFFF",
    "bg-raised": "#F0F2F5",
    "text-primary": "#121826",
    "text-secondary": "#4B5160",
    "text-muted": "#7C8291",
    "border-hairline": "#E3E6EB",
    "border-rule": "#121826",
    "border-input": "#858A96",
    accent: "#256ABF",
    "accent-hover": "#1C5CAB",
    "accent-text": "#256ABF",
    "on-accent": "#FFFFFF",
    "focus-ring": "#256ABF",
    "positive-text": "#006300",
    "positive-bg": "#E3F4E3",
    "negative-text": "#B42F2F",
    "negative-bg": "#FBE9E9",
    "warning-text": "#8A5A00",
    "warning-bg": "#FDF1D6",
    "info-text": "#1C5CAB",
    "info-bg": "#E7F0FB",
  },
  dark: {
    "bg-page": "#0E121A",
    "bg-surface": "#161B24",
    "bg-raised": "#1E2430",
    "text-primary": "#EEF0F4",
    "text-secondary": "#B4BAC6",
    "text-muted": "#8A91A0",
    "border-hairline": "#2A3140",
    "border-rule": "#EEF0F4",
    "border-input": "#6B7282",
    accent: "#256ABF",
    "accent-hover": "#3987E5",
    "accent-text": "#6DA7EC",
    "on-accent": "#FFFFFF",
    "focus-ring": "#6DA7EC",
    "positive-text": "#3FBF3F",
    "positive-bg": "#13301A",
    "negative-text": "#EF8A8A",
    "negative-bg": "#3A1C1C",
    "warning-text": "#FAB219",
    "warning-bg": "#3A2C0E",
    "info-text": "#86B6EF",
    "info-bg": "#16263D",
  },
} as const satisfies Record<Theme, Record<string, string>>;

export type ColorToken = keyof (typeof colors)["light"];

/** 04 §4.3 — kategoriya slotlari (qat'iy tartib; 9-chi — "Boshqa"). */
export const chartSlots = {
  light: ["#2A78D6", "#EB6834", "#1BAF7A", "#EDA100", "#E87BA4", "#008300", "#6250D6", "#E34948"],
  dark: ["#3987E5", "#D95926", "#199E70", "#C98500", "#D55181", "#008300", "#9085E9", "#E66767"],
} as const satisfies Record<Theme, readonly string[]>;

/** 04 §4.3 — holat ranglari (faqat holat uchun, doim ikon + matn bilan), ketma-ket va ikki qutbli shkalalar. */
export const chartStatus = { good: "#0CA30C", warning: "#FAB219", serious: "#EC835A", critical: "#D03B3B" } as const;
export const chartSequential = ["#CDE2FB", "#0D366B"] as const;
export const chartDivergingMid = { light: "#F0EFEC", dark: "#383835" } as const;

/** Rollar (ob'ekt → slot, hamma grafikda bir xil; 1 dan). Sof foyda — slot emas, `text-primary` 2 px. */
export const chartRoles = {
  revenue: 1,
  commission: 2,
  logistics: 3,
  cogs: 4,
  ads: 5,
  storage: 6,
  fines: 7,
  other: 8,
} as const;

/** 04 §2.1 — tipografik shkala: [o'lcham px, qator px, og'irlik, harf oralig'i em]. */
export const typeScale = {
  hero: [48, 52, 600, -0.02],
  display: [36, 44, 600, 0],
  h1: [24, 32, 600, -0.01],
  h2: [18, 26, 600, 0],
  h3: [15, 22, 600, 0],
  body: [14, 20, 400, 0],
  "body-strong": [14, 20, 500, 0],
  table: [13, 18, 400, 0],
  label: [12, 16, 500, 0],
  kpi: [28, 34, 600, 0],
  caption: [12, 16, 400, 0],
} as const satisfies Record<string, readonly [number, number, number, number]>;

/** 04 §3. */
export const space = [4, 8, 12, 16, 20, 24, 32, 40, 48, 64] as const;
export const radius = { control: 6, panel: 10 } as const;
export const breakpoints = { xs: 360, sm: 640, md: 768, lg: 1024, xl: 1280, xxl: 1440 } as const;
export const shadowFloat = "0 8px 24px rgb(18 24 38 / 0.12)";

export const fontSans = 'Inter, "Noto Sans", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif';
export const fontMono = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace";
