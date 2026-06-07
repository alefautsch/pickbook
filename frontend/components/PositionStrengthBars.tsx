import type { PositionStrengthMap } from "@/lib/api";
import { ordinal } from "@/lib/format";

type PositionStrengthBarsProps = {
  data: PositionStrengthMap;
  myRosterId?: string | null;
};

function rankInLeague(values: (number | null)[], mine: number | null): number | null {
  if (mine == null) return null;
  const ranked = values
    .filter((v): v is number => v != null)
    .sort((a, b) => b - a);
  const idx = ranked.indexOf(mine);
  return idx >= 0 ? idx + 1 : null;
}

export function PositionStrengthBars({ data, myRosterId }: PositionStrengthBarsProps) {
  const myTeam = data.teams.find((t) => t.is_me || t.roster_id === myRosterId);
  if (!myTeam || !data.positions.length) {
    return <p className="text-sm text-bb-muted">No position data yet.</p>;
  }

  return (
    <section className="bb-panel">
      <h2 className="bb-panel-title px-4 pt-4">Position Strength</h2>
      <p className="px-4 pb-2 text-xs text-bb-muted">Starter OVR rank in league</p>
      <ul className="space-y-3 px-4 pb-4">
        {data.positions.map((pos) => {
          const ovr = myTeam.by_position[pos] ?? null;
          const allOvrs = data.teams.map((t) => t.by_position[pos] ?? null);
          const rank = rankInLeague(allOvrs, ovr);
          const maxOvr = Math.max(...allOvrs.filter((v): v is number => v != null), 1);
          const width = ovr != null ? Math.round((ovr / maxOvr) * 100) : 0;

          return (
            <li key={pos}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-semibold uppercase text-bb-muted">{pos}</span>
                <span className="text-white">
                  {ovr ?? "—"}
                  {rank ? (
                    <span className="ml-1 text-bb-muted">({ordinal(rank)})</span>
                  ) : null}
                </span>
              </div>
              <div className="h-2 overflow-hidden rounded-full bg-black/40">
                <div
                  className="h-full rounded-full bg-gradient-to-r from-emerald-600 to-emerald-400"
                  style={{ width: `${width}%` }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
