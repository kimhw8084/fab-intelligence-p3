import { useEffect, useRef } from "react";
import { init, use } from "echarts/core";
import type { EChartsOption } from "echarts";
import { ScatterChart } from "echarts/charts";
import { AriaComponent, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import type { SpatialMapV2 } from "../../contracts/spatial-map.v2";
import { spatialAxisBounds } from "./spatialAxisBounds";

const PALETTE = ["#1769aa", "#a34493", "#c26b16", "#2a7f62", "#7655a5", "#a13f3f", "#467b91", "#825b35"];

use([ScatterChart, GridComponent, LegendComponent, TooltipComponent, VisualMapComponent, AriaComponent, CanvasRenderer]);

export function SpatialMapRenderer({ model }: { model: SpatialMapV2 }) {
  const element = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!element.current) return;
    const chart = init(element.current, undefined, { renderer: "canvas", useDirtyRect: true });
    const numeric = model.observations.filter((row) => row.observation_kind === "NUMERIC_MEASUREMENT");
    const categorical = model.observations.filter((row) => row.observation_kind === "CATEGORICAL_MEASUREMENT");
    const defects = model.observations.filter((row) => row.observation_kind === "DEFECT_EVENT");
    const missing = model.observations.filter((row) => row.observation_kind === "MISSING_MEASUREMENT");
    const catValues = [...new Set(categorical.map((row) => `${typeof row.value}:${String(row.value)}`))].sort();
    const defectValues = [...new Set(defects.map((row) => `${typeof row.value}:${String(row.value)}`))].sort();
    const catCodes = new Map(catValues.map((value, index) => [value, index]));
    const defectCodes = new Map(defectValues.map((value, index) => [value, index]));
    const rows = (items: typeof model.observations, code: (value: string | number | null) => number) =>
      items.map((row) => [row.x, row.y, code(row.value), String(row.value ?? "(unlabeled event)"), row.site_id, row.observation_kind]);
    const values = numeric.map((row) => row.value as number);
    const low = values.length ? Math.min(...values) : 0;
    const high = values.length ? Math.max(...values) : 1;
    const bounds = spatialAxisBounds(model.geometry);
    const option: EChartsOption = {
      animation: false,
      grid: { left: 54, right: 24, top: 24, bottom: 48, containLabel: true },
      tooltip: { trigger: "item", confine: true },
      legend: { bottom: 0, type: "scroll" },
      xAxis: { type: "value", name: `X (${model.coordinate_unit})`, min: bounds.x.min, max: bounds.x.max, scale: false },
      yAxis: { type: "value", name: `Y (${model.coordinate_unit})`, min: bounds.y.min, max: bounds.y.max, scale: false },
      series: [
        { name: `Numeric (${model.measurement_unit})`, type: "scatter", symbolSize: 13,
          data: numeric.map((row) => [row.x, row.y, row.value, row.site_id, row.standard_uncertainty ?? null]),
          encode: { tooltip: [0, 1, 2, 3, 4] } },
        { name: "Categorical value", type: "scatter", symbol: "rect", symbolSize: 15,
          data: rows(categorical, (value) => catCodes.get(`${typeof value}:${String(value)}`) ?? 0),
          encode: { tooltip: [0, 1, 3, 4, 5] } },
        { name: "Defect event", type: "scatter", symbol: "diamond", symbolSize: 16,
          data: rows(defects, (value) => defectCodes.get(`${typeof value}:${String(value)}`) ?? 0),
          encode: { tooltip: [0, 1, 3, 4, 5] } },
        { name: "Explicitly missing", type: "scatter", symbol: "circle", symbolSize: 11,
          itemStyle: { color: "#777777", borderColor: "#ffffff", borderWidth: 1 },
          data: missing.map((row) => [row.x, row.y, "Missing", row.site_id]), encode: { tooltip: [0, 1, 2, 3] } },
      ],
      visualMap: [
        { type: "continuous", show: numeric.length > 0, min: low, max: high, dimension: 2, seriesIndex: 0,
          calculable: false, orient: "horizontal", left: "center", top: 0,
          inRange: { color: ["#3e79a8", "#f2c14e", "#ae3935"] } },
        { type: "piecewise", show: catValues.length > 0, dimension: 2, seriesIndex: 1,
          pieces: catValues.map((_value, index) => ({ value: index, label: catValues[index].replace(/^(number|string):/, ""), color: PALETTE[index % PALETTE.length] })) },
        { type: "piecewise", show: defectValues.length > 0, dimension: 2, seriesIndex: 2,
          pieces: defectValues.map((_value, index) => ({ value: index, label: defectValues[index].replace(/^(number|string):/, ""), color: PALETTE[index % PALETTE.length] })) },
      ],
    };
    chart.setOption(option);
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(() => chart.resize());
    observer?.observe(element.current);
    window.addEventListener("resize", onResize);
    function onResize() { chart.resize(); }
    return () => { observer?.disconnect(); window.removeEventListener("resize", onResize); chart.dispose(); };
  }, [model]);

  return <div className="spatial-chart" ref={element} role="img" aria-label={`Measured wafer observations for ${model.wafer_id}. The accompanying table contains each typed value.`} />;
}
