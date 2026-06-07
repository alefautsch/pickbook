import type { PlayerCard } from "@/lib/api";

type StatisticalProfileProps = {
  player: PlayerCard;
};

const METRICS = [
  { key: "hppg_pct" as const, label: "HPPG", field: "hppg" as const },
  { key: "worp_ppg_pct" as const, label: "W/g", field: "worp_ppg" as const },
  { key: "tv_pct" as const, label: "TV", field: "trade_value" as const },
];

export function StatisticalProfile({ player }: StatisticalProfileProps) {
  const pct = player.outlook?.percentiles ?? {
    hppg_pct: null,
    worp_ppg_pct: null,
    tv_pct: null,
  };
  const hasAny = METRICS.some((m) => pct[m.key] != null);
  if (!hasAny) return null;

  return (
    <section className="bb-card p-5">
      <h2 className="text-lg font-medium text-white">Statistical profile</h2>
      <p className="mt-1 text-sm text-bb-muted">
        Percentile vs {player.position} pool in {player.league_name}
      </p>
      <ul className="mt-4 space-y-4">
        {METRICS.map((metric) => {
          const percentile = pct[metric.key];
          const raw = player[metric.field];
          return (
            <li key={metric.key}>
              <div className="mb-1 flex justify-between text-sm">
                <span className="text-bb-muted">{metric.label}</span>
                <span className="font-medium text-white">
                  {percentile != null ? `${percentile.toFixed(0)}th` : "—"}
                  {raw != null ? (
                    <span className="ml-2 text-bb-muted">
                      ({typeof raw === "number" && raw >= 100 ? Math.round(raw) : Number(raw).toFixed(metric.field === "worp_ppg" ? 3 : 1)})
                    </span>
                  ) : null}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-bb-border/50">
                <div
                  className="h-full rounded-full bg-emerald-500/80"
                  style={{ width: `${percentile ?? 0}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
