import Link from "next/link";
import type { PositionStrengthMap } from "@/lib/api";
import { ovrTier, tierColors } from "@/lib/ovr";

type PositionHeatmapProps = {
  data: PositionStrengthMap;
  leagueId: string;
};

function ovrCellStyle(ovr: number): React.CSSProperties {
  const color = tierColors[ovrTier(ovr)];
  return {
    backgroundColor: `color-mix(in srgb, ${color} 30%, transparent)`,
    color: "white",
  };
}

export function PositionHeatmap({ data, leagueId }: PositionHeatmapProps) {
  const { positions, teams } = data;
  if (!positions.length || !teams.length) {
    return <p className="text-sm text-bb-muted">No position data yet — sync the league.</p>;
  }

  return (
    <>
      <div className="space-y-2 md:hidden">
        {teams.map((team) => (
          <article
            key={team.roster_id}
            className={`rounded-lg border border-bb-border/40 bg-black/20 p-3 ${
              team.is_me ? "border-bb-gold/40 bg-bb-gold/5" : ""
            }`}
          >
            <Link
              href={`/leagues/${leagueId}/teams/${team.roster_id}`}
              className={`block truncate text-sm font-medium hover:text-bb-gold ${
                team.is_me ? "text-bb-gold" : "text-white"
              }`}
            >
              {team.team_name ?? "Team"}
            </Link>
            <div className="mt-2 grid grid-cols-3 gap-1.5 sm:grid-cols-4">
              {positions.map((pos) => {
                const ovr = team.by_position[pos] ?? null;
                return (
                  <div
                    key={pos}
                    className="rounded-md bg-black/25 px-2 py-1.5 text-center"
                  >
                    <p className="text-[9px] font-semibold uppercase tracking-wide text-bb-muted">
                      {pos}
                    </p>
                    <span
                      className={`mt-0.5 inline-block min-w-[2rem] rounded px-1 py-0.5 text-xs font-semibold ${
                        ovr == null ? "bg-black/30 text-bb-muted" : ""
                      }`}
                      style={ovr != null ? ovrCellStyle(ovr) : undefined}
                    >
                      {ovr ?? "—"}
                    </span>
                  </div>
                );
              })}
            </div>
          </article>
        ))}
      </div>

      <div className="hidden overflow-x-auto md:block">
        <table className="w-full min-w-[32rem] border-collapse text-sm">
        <thead>
          <tr>
            <th className="sticky left-0 z-10 bg-bb-surface/95 px-3 py-2 text-left text-xs font-medium uppercase tracking-wider text-bb-muted">
              Team
            </th>
            {positions.map((pos) => (
              <th
                key={pos}
                className="px-2 py-2 text-center text-xs font-medium uppercase tracking-wider text-bb-muted"
              >
                {pos}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {teams.map((team) => (
            <tr
              key={team.roster_id}
              className={team.is_me ? "bg-bb-gold/5" : undefined}
            >
              <td className="sticky left-0 z-10 bg-bb-surface/95 border-t border-bb-border px-3 py-2">
                <Link
                  href={`/leagues/${leagueId}/teams/${team.roster_id}`}
                  className={`truncate font-medium hover:text-bb-gold ${
                    team.is_me ? "text-bb-gold" : "text-white"
                  }`}
                >
                  {team.team_name ?? "Team"}
                </Link>
              </td>
              {positions.map((pos) => {
                const ovr = team.by_position[pos] ?? null;
                return (
                  <td key={pos} className="border-t border-bb-border px-1 py-1 text-center">
                    <span
                      className={`inline-block min-w-[2.25rem] rounded px-1.5 py-0.5 text-xs font-semibold ${
                        ovr == null ? "bg-black/30 text-bb-muted" : ""
                      }`}
                      style={ovr != null ? ovrCellStyle(ovr) : undefined}
                      title={ovr != null ? `Avg starter OVR ${ovr}` : "No starter"}
                    >
                      {ovr ?? "—"}
                    </span>
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
