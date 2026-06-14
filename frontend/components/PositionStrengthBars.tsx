import type { PositionStrengthMap } from "@/lib/api";
import { ordinal } from "@/lib/format";
import { slotColor } from "@/lib/positions";

function ovrClass(ovr: number | null): string {
  if (ovr == null) return "text-bb-muted";
  if (ovr >= 90) return "text-emerald-400";
  if (ovr >= 85) return "text-emerald-300/80";
  if (ovr >= 80) return "text-white";
  return "text-amber-300/80";
}

function rankClass(rank: number | null, numTeams: number): string {
  if (rank == null) return "text-bb-muted";
  if (rank <= 2) return "text-emerald-400 font-semibold";
  if (rank <= Math.ceil(numTeams / 2)) return "text-bb-gold/90";
  if (rank <= numTeams - 2) return "text-bb-muted";
  return "text-red-400/80";
}

type PositionStrengthBarsProps = {
  data: PositionStrengthMap;
  myRosterId?: string | null;
  embedded?: boolean;
  showTitleOnDesktop?: boolean;
};

function panelTitleClass(embedded?: boolean, showTitleOnDesktop?: boolean): string {
  if (embedded) return "hidden";
  if (showTitleOnDesktop) return "hidden lg:block";
  return "";
}

function rankInLeague(values: (number | null)[], mine: number | null): number | null {
  if (mine == null) return null;
  const ranked = values
    .filter((v): v is number => v != null)
    .sort((a, b) => b - a);
  const idx = ranked.indexOf(mine);
  return idx >= 0 ? idx + 1 : null;
}

export function PositionStrengthBars({
  data,
  myRosterId,
  embedded = false,
  showTitleOnDesktop = false,
}: PositionStrengthBarsProps) {
  const myTeam = data.teams.find((t) => t.is_me || t.roster_id === myRosterId);
  if (!myTeam || !data.positions.length) {
    return <p className="text-sm text-bb-muted">No position data yet.</p>;
  }

  const numTeams = data.teams.filter((t) => t.by_position).length || data.teams.length;

  return (
    <section className="bb-panel">
      <h2 className={`bb-panel-title px-4 pt-4 ${panelTitleClass(embedded, showTitleOnDesktop)}`}>
        Position Strength
      </h2>
      <p className={`px-4 pb-2 text-xs text-bb-muted ${embedded ? "lg:px-4" : ""}`}>
        Starter OVR rank in league
      </p>
      <ul className="space-y-3 px-4 pb-4">
        {data.positions.map((pos) => {
          const ovr = myTeam.by_position[pos] ?? null;
          const allOvrs = data.teams.map((t) => t.by_position[pos] ?? null);
          const rank = rankInLeague(allOvrs, ovr);
          // Rank-based width: rank 1 = 100%, rank N = ~(1/N)*100%
          const width =
            rank != null && numTeams > 1
              ? Math.round(((numTeams - rank) / (numTeams - 1)) * 100)
              : ovr != null
                ? 50
                : 0;
          const color = slotColor(pos);

          return (
            <li key={pos}>
              <div className="mb-1 flex items-center justify-between text-xs">
                <span className="font-semibold uppercase" style={{ color }}>
                  {pos}
                </span>
                <span className="flex items-baseline gap-1">
                  <span className={`font-bold tabular-nums ${ovrClass(ovr)}`}>
                    {ovr ?? "—"}
                  </span>
                  {rank ? (
                    <span className={`text-[10px] ${rankClass(rank, numTeams)}`}>
                      {ordinal(rank)}
                    </span>
                  ) : null}
                </span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-black/40">
                <div
                  className="h-full rounded-full transition-all duration-300"
                  style={{
                    width: `${width}%`,
                    backgroundColor: color,
                    opacity: 0.85,
                  }}
                />
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
