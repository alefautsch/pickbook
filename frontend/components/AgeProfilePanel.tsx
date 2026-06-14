import type { AgeProfile } from "@/lib/api";
import { formatDecimal } from "@/lib/format";
import { PositionTag } from "./PositionPill";

type AgeProfilePanelProps = {
  profiles: AgeProfile[];
};

const windowLabels: Record<string, string> = {
  rising: "Rising window",
  peak: "Peak window",
  closing: "Closing window",
};

const windowStyles: Record<string, string> = {
  rising: "text-emerald-300",
  peak: "text-sky-300",
  closing: "text-amber-300",
};

export function AgeProfilePanel({ profiles }: AgeProfilePanelProps) {
  const mine = profiles.find((p) => p.is_me);
  if (!mine) {
    return (
      <p className="text-sm text-bb-muted">
        No age profile for your team — mark a roster as yours in seed data.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline gap-3">
        <div>
          <p className="text-xs uppercase tracking-wider text-bb-muted">Starter avg age</p>
          <p className="text-2xl font-semibold text-white">
            {formatDecimal(mine.starter_avg_age, 1)}
          </p>
        </div>
        <div>
          <p className="text-xs uppercase tracking-wider text-bb-muted">vs league</p>
          <p
            className={`text-lg font-medium ${
              (mine.age_delta ?? 0) < 0
                ? "text-emerald-300"
                : (mine.age_delta ?? 0) > 0
                  ? "text-amber-300"
                  : "text-white"
            }`}
          >
            {mine.age_delta != null
              ? `${mine.age_delta > 0 ? "+" : ""}${formatDecimal(mine.age_delta, 1)} yrs`
              : "—"}
          </p>
        </div>
        {mine.window ? (
          <div>
            <p className="text-xs uppercase tracking-wider text-bb-muted">Window</p>
            <p className={`text-lg font-medium ${windowStyles[mine.window] ?? "text-white"}`}>
              {windowLabels[mine.window] ?? mine.window}
            </p>
          </div>
        ) : null}
      </div>

      <div>
        <p className="mb-2 text-xs uppercase tracking-wider text-bb-muted">
          Optimal starters
        </p>
        <ul className="space-y-1">
          {mine.starter_ages.map((s) => (
            <li
              key={`${s.player_id}-${s.slot}`}
              className="rounded bg-black/20 px-3 py-1.5 text-sm"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate font-medium text-white">{s.name}</span>
                <span className="shrink-0 text-bb-muted">
                  {s.age != null ? `${s.age} yrs` : "—"}
                  {s.ovr != null ? (
                    <span className="ml-2 text-bb-gold">OVR {s.ovr}</span>
                  ) : null}
                </span>
              </div>
              <p className="mt-0.5 flex flex-wrap items-center gap-1.5">
                {s.pos ? <PositionTag position={s.pos} /> : null}
                <span className="text-xs text-bb-muted">{s.slot}</span>
              </p>
            </li>
          ))}
        </ul>
      </div>

      {mine.league_avg_starter_age != null ? (
        <p className="text-xs text-bb-muted">
          League avg starter age: {formatDecimal(mine.league_avg_starter_age, 1)} · Bench depth avg:{" "}
          {formatDecimal(mine.bench_avg_age, 1)}
        </p>
      ) : null}
    </div>
  );
}
