"use client";

import type { PlayerHistoryPoint } from "@/lib/api";

type OvrTrendSparklineProps = {
  points: PlayerHistoryPoint[];
  width?: number;
  height?: number;
};

function scaleSeries(values: number[], height: number, pad: number): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const inner = height - pad * 2;
  return values.map((v) => pad + inner - ((v - min) / span) * inner);
}

export function OvrTrendSparkline({
  points,
  width = 320,
  height = 96,
}: OvrTrendSparklineProps) {
  const ovrValues = points
    .map((p) => p.ovr)
    .filter((v): v is number => v != null);
  const hppgValues = points
    .map((p) => p.hppg)
    .filter((v): v is number => v != null);

  if (ovrValues.length < 2 && hppgValues.length < 2) {
    return (
      <p className="text-sm text-bb-muted">
        Trend appears after two syncs. Run sync again to accumulate history.
      </p>
    );
  }

  const pad = 8;
  const ovrYs = scaleSeries(ovrValues, height, pad);
  const hppgYs = scaleSeries(hppgValues, height, pad);

  const seriesLength = Math.max(ovrValues.length, hppgValues.length);
  const step = seriesLength > 1 ? (width - pad * 2) / (seriesLength - 1) : 0;

  const toPath = (ys: number[]) =>
    ys
      .map((y, i) => `${i === 0 ? "M" : "L"} ${pad + i * step} ${y}`)
      .join(" ");

  const latest = points[points.length - 1];
  const first = points[0];
  const ovrDelta =
    latest.ovr != null && first.ovr != null ? latest.ovr - first.ovr : null;

  return (
    <div>
      <div className="mb-3 flex flex-wrap items-center gap-4 text-sm">
        <span className="flex items-center gap-2 text-white">
          <span className="inline-block h-0.5 w-4 bg-bb-gold" />
          OVR
          {ovrDelta != null ? (
            <span
              className={
                ovrDelta > 0
                  ? "text-emerald-400"
                  : ovrDelta < 0
                    ? "text-red-300"
                    : "text-bb-muted"
              }
            >
              {ovrDelta > 0 ? "+" : ""}
              {ovrDelta}
            </span>
          ) : null}
        </span>
        {hppgValues.length >= 2 ? (
          <span className="flex items-center gap-2 text-bb-muted">
            <span className="inline-block h-0.5 w-4 bg-sky-400/80" />
            HPPG
          </span>
        ) : null}
      </div>

      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full max-w-md text-bb-gold"
        role="img"
        aria-label="OVR and HPPG trend"
      >
        {hppgYs.length >= 2 ? (
          <path
            d={toPath(hppgYs)}
            fill="none"
            stroke="rgb(56 189 248 / 0.65)"
            strokeWidth="2"
            strokeLinejoin="round"
          />
        ) : null}
        {ovrYs.length >= 2 ? (
          <path
            d={toPath(ovrYs)}
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinejoin="round"
          />
        ) : null}
      </svg>

      <p className="mt-2 text-xs text-bb-muted">
        {points.length} daily point{points.length === 1 ? "" : "s"}
        {latest.formula_version !== first.formula_version
          ? " · includes formula changes"
          : ""}
      </p>
    </div>
  );
}
