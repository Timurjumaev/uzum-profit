// Ctrl+K (04 §5): sahifa va amalga tez o'tish. Qidiruv — `filterOptions` (lotin/kirill va apostrof turlaridan qat'i
// nazar, §8.3), klaviatura: ↑ ↓ Enter Esc, ARIA combobox + listbox, fokus ichida. Manba — `PaletteItem` ro'yxati:
// SKU va xaridlar guruhlari tegishli sahifalar bilan keladi (B4.3, B4.6) — palitra o'zgarmaydi.
import { Search, type LucideIcon } from "lucide-react";
import { useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { filterOptions } from "../ui/Combobox";
import { cx } from "../ui/cx";
import { useFocusTrap } from "../ui/useFocusTrap";

export type PaletteItem = {
  id: string;
  group: "page" | "action";
  label: string;
  /** Qo'shimcha qidiruv so'zlari (masalan, boshqa tildagi nom). */
  keywords?: string;
  icon?: LucideIcon;
  run: () => void;
};

/** `Ctrl K` yoki `⌘K` — qurilmaga qarab. */
export function shortcutLabel(): string {
  const platform = globalThis.navigator?.platform ?? "";
  return /Mac|iPhone|iPad/.test(platform) ? "⌘K" : "Ctrl K";
}

export function isPaletteShortcut(e: Pick<KeyboardEvent, "key" | "code" | "ctrlKey" | "metaKey" | "altKey" | "shiftKey">): boolean {
  return (e.ctrlKey || e.metaKey) && !e.altKey && !e.shiftKey && (e.key.toLowerCase() === "k" || e.code === "KeyK");
}

export function searchItems(items: PaletteItem[], query: string): PaletteItem[] {
  const byId = new Map(items.map((i) => [i.id, i]));
  return filterOptions(
    items.map((i) => ({ value: i.id, label: i.label, keywords: i.keywords })),
    query,
  ).map((o) => byId.get(o.value)!);
}

export function CommandPalette({ open, onClose, items }: { open: boolean; onClose: () => void; items: PaletteItem[] }) {
  if (!open) return null; // yopilganda qidiruv va tanlov tozalanadi
  return <Palette onClose={onClose} items={items} />;
}

function Palette({ onClose, items }: { onClose: () => void; items: PaletteItem[] }) {
  const { t } = useTranslation();
  const panel = useRef<HTMLDivElement>(null);
  const listId = useId();
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const shown = useMemo(() => searchItems(items, query), [items, query]);
  const current = Math.min(active, shown.length - 1);
  useFocusTrap(panel, true, onClose);
  const choose = (item: PaletteItem) => {
    onClose();
    item.run();
  };
  const optionId = (i: number) => `${listId}-${i}`;
  return createPortal(
    <div className="ui-layer palette">
      <div className="ui-layer__backdrop" onClick={onClose} aria-hidden />
      <div ref={panel} className="ui-layer__panel palette__panel" role="dialog" aria-modal="true" aria-label={t("shell.search")} tabIndex={-1}>
        <div className="palette__field">
          <Search size={18} aria-hidden />
          <input
            className="palette__input"
            role="combobox"
            aria-expanded={shown.length > 0}
            aria-controls={shown.length > 0 ? listId : undefined}
            aria-autocomplete="list"
            aria-label={t("shell.searchLabel")}
            aria-activedescendant={shown[current] ? optionId(current) : undefined}
            placeholder={t("shell.searchPlaceholder")}
            autoComplete="off"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setActive(0);
            }}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") {
                e.preventDefault();
                setActive(Math.min(current + 1, shown.length - 1));
              } else if (e.key === "ArrowUp") {
                e.preventDefault();
                setActive(Math.max(current - 1, 0));
              } else if (e.key === "Enter" && shown[current]) {
                e.preventDefault();
                choose(shown[current]);
              }
            }}
          />
        </div>
        {shown.length === 0 ? (
          <p className="palette__empty" role="status">
            {t("shell.searchEmpty")}
          </p>
        ) : (
          <ul id={listId} role="listbox" className="palette__list" aria-label={t("shell.search")}>
          {shown.map((item, i) => {
            const Icon = item.icon;
            return (
              <li
                key={item.id}
                id={optionId(i)}
                role="option"
                aria-selected={i === current}
                className={cx("palette__option", i === current && "is-active")}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => choose(item)}
                onMouseEnter={() => setActive(i)}
              >
                {Icon && <Icon size={18} aria-hidden />}
                <span className="palette__label">{item.label}</span>
                <span className="palette__group">{t(`shell.group.${item.group}`)}</span>
              </li>
            );
          })}
          </ul>
        )}
      </div>
    </div>,
    document.body,
  );
}
