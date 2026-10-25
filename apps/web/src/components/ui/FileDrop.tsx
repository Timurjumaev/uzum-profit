// Fayl tashlash (04 §5): Excel import — sudrab tashlash yoki tanlash; shablon havolasi.
import { Upload } from "lucide-react";
import { useId, useRef, useState, type DragEvent } from "react";
import { useTranslation } from "react-i18next";

import { cx } from "./cx";

export type FileDropProps = {
  accept?: string;
  onFiles: (files: File[]) => void;
  templateHref?: string;
  hint?: string;
};

export function FileDrop({ accept, onFiles, templateHref, hint }: FileDropProps) {
  const { t } = useTranslation();
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const id = useId();
  const pick = (list: FileList | null) => list && list.length > 0 && onFiles([...list]);
  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setOver(false);
    pick(e.dataTransfer.files);
  };
  return (
    <div
      className={cx("ui-filedrop", over && "is-over")}
      onDragOver={(e) => {
        e.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={onDrop}
    >
      <Upload size={20} aria-hidden />
      <p>{t("ui.fileDrop")}</p>
      {hint && <p className="caption">{hint}</p>}
      <input
        ref={input}
        id={id}
        type="file"
        accept={accept}
        className="ui-visually-hidden"
        onChange={(e) => pick(e.target.files)}
      />
      <label htmlFor={id} className="ui-btn ui-btn--secondary ui-btn--md">
        {t("ui.fileChoose")}
      </label>
      {templateHref && (
        <a href={templateHref} download>
          {t("ui.fileTemplate")}
        </a>
      )}
    </div>
  );
}
