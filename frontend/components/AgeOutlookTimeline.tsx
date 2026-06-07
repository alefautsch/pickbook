import type { PlayerCard } from "@/lib/api";
import { archetypeLabel } from "@/lib/archetype";

type AgeOutlookTimelineProps = {
  player: PlayerCard;
};

export function AgeOutlookTimeline({ player }: AgeOutlookTimelineProps) {
  const outlook = player.outlook ?? {
    archetype: null,
    peak_window: { years_to_peak: null, peak_window_end: null },
    opportunity_score: null,
    percentiles: { hppg_pct: null, worp_ppg_pct: null, tv_pct: null },
  };
  const { peak_window: peak, archetype, opportunity_score } = outlook;
  const age = player.age;
  const peakEnd = peak.peak_window_end;
  const yearsToPeak = peak.years_to_peak;

  if (age == null && !archetype && opportunity_score == null) {
    return null;
  }

  const windowStart = peakEnd != null ? Math.max(18, peakEnd - 6) : 20;
  const windowEnd = peakEnd != null ? peakEnd + 4 : 34;
  const span = windowEnd - windowStart;
  const markerPct =
    age != null && span > 0
      ? Math.min(100, Math.max(0, ((age - windowStart) / span) * 100))
      : 50;
  const peakStartPct =
    peakEnd != null && span > 0
      ? Math.min(100, Math.max(0, ((peakEnd - 3 - windowStart) / span) * 100))
      : 40;
  const peakEndPct =
    peakEnd != null && span > 0
      ? Math.min(100, Math.max(0, ((peakEnd - windowStart) / span) * 100))
      : 70;

  return (
    <section className="bb-card p-5">
      <h2 className="text-lg font-medium text-white">Age &amp; outlook</h2>
      <p className="mt-1 text-sm text-bb-muted">
        Archetype and peak window given current opportunity
      </p>

      <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-bb-muted">Age</dt>
          <dd className="font-medium text-white">{age ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-bb-muted">Archetype</dt>
          <dd className="font-medium text-white">{archetypeLabel(archetype)}</dd>
        </div>
        <div>
          <dt className="text-bb-muted">Years to peak</dt>
          <dd className="font-medium text-white">
            {yearsToPeak != null
              ? yearsToPeak > 0
                ? yearsToPeak
                : yearsToPeak === 0
                  ? "At peak"
                  : `${Math.abs(yearsToPeak)} past`
              : "—"}
          </dd>
        </div>
        <div>
          <dt className="text-bb-muted">Opportunity</dt>
          <dd className="font-medium text-white">
            {opportunity_score != null ? opportunity_score.toFixed(0) : "—"}
          </dd>
        </div>
      </dl>

      {age != null && peakEnd != null ? (
        <div className="mt-6">
          <div className="relative h-3 overflow-hidden rounded-full bg-bb-border/50">
            <div
              className="absolute inset-y-0 rounded-full bg-bb-gold/30"
              style={{
                left: `${peakStartPct}%`,
                width: `${Math.max(peakEndPct - peakStartPct, 4)}%`,
              }}
            />
            <div
              className="absolute top-1/2 h-4 w-4 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-bb-gold bg-white"
              style={{ left: `${markerPct}%` }}
              title={`Age ${age}`}
            />
          </div>
          <div className="mt-1 flex justify-between text-xs text-bb-muted">
            <span>{windowStart}</span>
            <span>Peak ~{peakEnd - 3}–{peakEnd}</span>
            <span>{windowEnd}</span>
          </div>
        </div>
      ) : null}
    </section>
  );
}
