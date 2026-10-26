// ECharts o'rami: bo'lak birinchi grafik so'ralganda yuklanadi (`lib/echarts`), SVG renderer, o'lcham o'zgarsa
// (`ResizeObserver`) qayta chizadi, mavzu/til o'zgarsa yangi parametr bilan to'liq almashtiradi, olib tashlanganda
// `dispose`. Yuklanmasa (tarmoq) — matn va "Qayta urinish" (jadval ko'rinishi baribir ishlaydi).
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { loadEcharts, type ECharts, type EChartsCoreOption } from "../../lib/echarts";
import { Button } from "../ui/Button";
import { Skeleton } from "../ui/Feedback";

export function EChart({ option, height = 280 }: { option: EChartsCoreOption; height?: number }) {
  const { t } = useTranslation();
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<ECharts | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "failed">("loading");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    let disposed = false;
    let observer: ResizeObserver | undefined;
    loadEcharts().then(
      (echarts) => {
        if (disposed) return;
        const instance = echarts.init(el, null, { renderer: "svg" });
        chart.current = instance;
        if (typeof ResizeObserver !== "undefined") {
          observer = new ResizeObserver(() => instance.resize());
          observer.observe(el);
        }
        setState("ready");
      },
      () => !disposed && setState("failed"),
    );
    return () => {
      disposed = true;
      observer?.disconnect();
      chart.current?.dispose();
      chart.current = null;
    };
  }, [attempt]);

  useEffect(() => {
    if (state === "ready") chart.current?.setOption(option, { notMerge: true });
  }, [state, option]);

  return (
    <div className="chart" style={{ blockSize: height }}>
      <div ref={host} className="chart__canvas" />
      {state === "loading" && (
        <div className="chart__overlay">
          <Skeleton label={t("charts.loading")} lines={4} />
        </div>
      )}
      {state === "failed" && (
        <div className="chart__overlay" role="alert">
          <p>{t("charts.failed")}</p>
          <Button
            size="sm"
            onClick={() => {
              setState("loading");
              setAttempt((n) => n + 1);
            }}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}
    </div>
  );
}
