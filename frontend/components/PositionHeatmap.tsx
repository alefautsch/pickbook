import Link from "next/link";
import type { PositionStrengthMap } from "@/lib/api";

type PositionHeatmapProps = {
  data: PositionStrengthMap;
  leagueId: string;
};

function ovrColor(ovr: number | null | undefined): string {
  if (ovr == null) return "bg-black/30 text-bb-muted";
  if (ovr >= 90) return "bg-emerald-600/50 text-emerald-100";
  if (ovr >= 85) return "bg-emerald-500/30 text-emerald-200";
  if (ovr >= 80) return "bg-sky-500/30 text-sky-200";
  if (ovr >= 75) return "bg-amber-500/25 text-amber-200";
  return "bg-red-500/20 text-red-200";
}

export function PositionHeatmap({ data, leagueId }: PositionHeatmapProps) {
  const { positions, teams } = data;
  if (!positions.length || !teams.length) {
    return <p className="text-sm text-bb-muted">No position data yet — sync the league.</p>;
  }

  return (
    <div className="overflow-x-auto">
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
                      className={`inline-block min-w-[2.25rem] rounded px-1.5 py-0.5 text-xs font-semibold ${ovrColor(ovr)}`}
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
  );
}
