"use client";

import { useMemo } from "react";
import type { PlayerHistoryPoint } from "@/lib/api";
import { formatPpg } from "@/lib/format";

type OvrTrendSparklineProps = {
  points: PlayerHistoryPoint[];
};

function parseSnapshotDate(isoDate: string): Date {
  const [year, month, day] = isoDate.split("-").map(Number);
  return new Date(year, month - 1, day);
}

function formatSnapshotDate(isoDate: string, includeYear = false): string {
  const date = parseSnapshotDate(isoDate);
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    ...(includeYear ? { year: "numeric" } : {}),
  });
}

function deltaClass(delta: number | null): string {
  if (delta == null || delta === 0) return "text-bb-muted";
  return delta > 0 ? "text-emerald-400" : "text-red-300";
}

function formatDelta(delta: number | null): string {
  if (delta == null || delta === 0) return "—";
  return `${delta > 0 ? "+" : ""}${delta}`;
}

/** Keep the first snapshot and any later snapshot where OVR changed. */
function filterOvrChangePoints(points: PlayerHistoryPoint[]): PlayerHistoryPoint[] {
  if (points.length === 0) return [];

  const filtered: PlayerHistoryPoint[] = [points[0]];
  for (let i = 1; i < points.length; i++) {
    const prev = filtered[filtered.length - 1];
    const curr = points[i];
    if (curr.ovr !== prev.ovr) {
      filtered.push(curr);
    }
  }
  return filtered;
}

export function OvrTrendSparkline({ points }: OvrTrendSparklineProps) {
  const changePoints = useMemo(() => filterOvrChangePoints(points), [points]);

  const rows = useMemo(() => {
    return changePoints.map((point, index) => {
      const prev = index > 0 ? changePoints[index - 1] : null;
      const ovrDelta =
        point.ovr != null && prev?.ovr != null ? point.ovr - prev.ovr : null;
      const formulaChanged =
        prev != null && point.formula_version !== prev.formula_version;
      return { point, index, ovrDelta, formulaChanged };
    });
  }, [changePoints]);

  if (points.length < 2) {
    return (
      <p className="text-sm text-bb-muted">
        Trend appears after two syncs. Run sync again to accumulate history.
      </p>
    );
  }

  const first = changePoints[0];
  const latest = changePoints[changePoints.length - 1];
  const observationStart = points[0];
  const observationEnd = points[points.length - 1];
  const totalDelta =
    latest.ovr != null && first.ovr != null ? latest.ovr - first.ovr : null;
  const hasFormulaChange = changePoints.some((point, index) => {
    if (index === 0) return false;
    return point.formula_version !== changePoints[index - 1].formula_version;
  });
  const skippedSnapshots = points.length - changePoints.length;

  if (changePoints.length < 2) {
    return (
      <div className="space-y-2">
        <p className="text-lg font-semibold tabular-nums text-white">
          Held at {latest.ovr ?? "—"}
        </p>
        <p className="text-xs text-bb-muted">
          No grade changes between{" "}
          {formatSnapshotDate(observationStart.snapshot_date, true)}
          {" and "}
          {formatSnapshotDate(observationEnd.snapshot_date, true)}
          {skippedSnapshots > 0
            ? ` · ${skippedSnapshots} unchanged snapshot${skippedSnapshots === 1 ? "" : "s"} hidden`
            : ""}
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <p className="text-2xl font-semibold tabular-nums text-white sm:text-3xl">
          {first.ovr ?? "—"}
          <span className="mx-2 text-bb-muted">→</span>
          {latest.ovr ?? "—"}
          {totalDelta != null ? (
            <span className={`ml-1 text-base font-medium sm:text-lg ${deltaClass(totalDelta)}`}>
              ({formatDelta(totalDelta)})
            </span>
          ) : null}
        </p>
        <p className="mt-1 text-xs text-bb-muted sm:text-sm">
          {changePoints.length} change{changePoints.length === 1 ? "" : "s"} ·{" "}
          {formatSnapshotDate(observationStart.snapshot_date, true)}
          {" – "}
          {formatSnapshotDate(observationEnd.snapshot_date, true)}
          {skippedSnapshots > 0
            ? ` · ${skippedSnapshots} flat day${skippedSnapshots === 1 ? "" : "s"} hidden`
            : ""}
          {hasFormulaChange ? " · includes formula changes" : ""}
        </p>
      </div>

      {/* Desktop: horizontal step path */}
      <div className="hidden sm:block">
        <div className="flex items-stretch">
          {rows.map(({ point, index, ovrDelta, formulaChanged }, stepIndex) => {
            const isFirst = index === 0;
            const isLatest = index === rows.length - 1;
            return (
              <div key={point.snapshot_date} className="flex min-w-0 flex-1 items-stretch">
                {stepIndex > 0 ? (
                  <div className="flex w-10 shrink-0 flex-col items-center justify-center self-center">
                    <div className="h-px w-full bg-bb-gold/40" />
                    <span
                      className={`my-1 text-xs font-semibold tabular-nums ${deltaClass(ovrDelta)}`}
                    >
                      {formatDelta(ovrDelta)}
                    </span>
                  </div>
                ) : null}
                <div className="min-w-0 flex-1 rounded-xl bg-black/25 px-3 py-3 ring-1 ring-inset ring-white/8">
                  <p className="text-3xl font-bold tabular-nums text-bb-gold">{point.ovr ?? "—"}</p>
                  <p className="mt-1 text-sm text-white">
                    {formatSnapshotDate(point.snapshot_date, true)}
                  </p>
                  <p className="mt-0.5 text-xs text-bb-muted">
                    HPPG {formatPpg(point.hppg)}
                  </p>
                  <div className="mt-2">
                    {formulaChanged ? (
                      <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                        Formula
                      </span>
                    ) : isLatest ? (
                      <span className="text-[10px] font-medium uppercase tracking-wider text-bb-gold">
                        Latest
                      </span>
                    ) : isFirst ? (
                      <span className="text-[10px] font-medium uppercase tracking-wider text-bb-muted">
                        Baseline
                      </span>
                    ) : null}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Mobile: vertical timeline */}
      <ol className="space-y-0 sm:hidden">
        {rows.map(({ point, index, ovrDelta, formulaChanged }, stepIndex) => {
          const isFirst = index === 0;
          const isLatest = index === rows.length - 1;
          return (
            <li key={point.snapshot_date}>
              <div className="flex gap-3">
                <div className="flex w-8 shrink-0 flex-col items-center">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-bb-gold/15 ring-2 ring-bb-gold/50">
                    <span className="text-xs font-bold tabular-nums text-bb-gold">
                      {point.ovr ?? "—"}
                    </span>
                  </div>
                  {stepIndex < rows.length - 1 ? (
                    <div className="my-1 w-px flex-1 bg-bb-gold/30" />
                  ) : null}
                </div>
                <div className="min-w-0 flex-1 pb-4">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                    <p className="text-sm font-medium text-white">
                      {formatSnapshotDate(point.snapshot_date, true)}
                    </p>
                    {ovrDelta != null && ovrDelta !== 0 ? (
                      <span className={`text-xs font-semibold tabular-nums ${deltaClass(ovrDelta)}`}>
                        {formatDelta(ovrDelta)}
                      </span>
                    ) : null}
                    {formulaChanged ? (
                      <span className="rounded-full bg-amber-400/10 px-2 py-0.5 text-[10px] font-medium text-amber-300">
                        Formula
                      </span>
                    ) : isLatest ? (
                      <span className="text-[10px] font-medium uppercase tracking-wider text-bb-gold">
                        Latest
                      </span>
                    ) : isFirst ? (
                      <span className="text-[10px] font-medium uppercase tracking-wider text-bb-muted">
                        Baseline
                      </span>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-xs text-bb-muted">
                    HPPG {formatPpg(point.hppg)}
                  </p>
                </div>
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
