import type { PlayerGameLogEntry } from "@/lib/api";
import { formatPpg } from "@/lib/format";

type GameLogMobileProps = {
  entries: PlayerGameLogEntry[];
};

function ptsClass(pts: number, included: boolean): string {
  if (!included) return "text-bb-muted";
  if (pts >= 20) return "text-emerald-400";
  if (pts >= 15) return "text-emerald-300/80";
  if (pts >= 8) return "text-white";
  return "text-amber-400/80";
}

export function GameLogMobile({ entries }: GameLogMobileProps) {
  return (
    <div className="divide-y divide-bb-border/30 md:hidden">
      {entries.map((entry) => {
        const snapPct =
          entry.offense_pct != null ? `${Math.round(entry.offense_pct * 100)}%` : null;
        const pts = entry.points ?? 0;
        const statBits = [
          entry.offense_snaps != null && snapPct
            ? `${entry.offense_snaps} snaps (${snapPct})`
            : null,
          entry.targets > 0 ? `${entry.receptions}/${entry.targets} rec` : null,
          entry.carries > 0 ? `${entry.carries} rush` : null,
          entry.attempts > 0 ? `${entry.attempts} pass att` : null,
        ].filter(Boolean);

        return (
          <div
            key={`${entry.season}-${entry.week}`}
            className={`px-1 py-2.5 ${entry.included ? "" : "opacity-70"}`}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <p className="text-sm font-medium text-white">
                  {entry.season} W{entry.week}
                  <span className="font-normal text-bb-muted">
                    {" "}
                    vs {entry.opponent ?? "—"}
                  </span>
                </p>
                {statBits.length > 0 ? (
                  <p className="mt-0.5 text-[11px] text-bb-muted">{statBits.join(" · ")}</p>
                ) : null}
              </div>
              <div className="shrink-0 text-right">
                <p className={`text-lg font-bold tabular-nums ${ptsClass(pts, entry.included)}`}>
                  {formatPpg(entry.points)}
                </p>
                <span
                  className={`mt-0.5 inline-block rounded-full px-1.5 py-0.5 text-[10px] ${
                    entry.included
                      ? "bg-emerald-400/10 text-emerald-300"
                      : "bg-bb-border/50 text-bb-muted"
                  }`}
                >
                  {entry.included ? "Included" : "Outlier"}
                </span>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
