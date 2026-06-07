import Link from "next/link";
import type { DepthChartGroup } from "@/lib/api";
import { OvrBadge } from "./OvrBadge";

type DepthChartPanelProps = {
  depthChart: DepthChartGroup[];
  leagueId: string;
};

export function DepthChartPanel({ depthChart, leagueId }: DepthChartPanelProps) {
  if (depthChart.length === 0) {
    return <p className="text-sm text-bb-muted">No depth chart data.</p>;
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {depthChart.map((group) => (
        <section key={group.position} className="bb-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-bb-gold">
            {group.position}
          </h3>
          <ul className="mt-3 space-y-2">
            {group.players.map((player) => (
              <li key={player.player_id} className="flex items-center gap-2">
                <span className="w-4 text-xs text-bb-muted">{player.depth_rank}</span>
                <Link
                  href={`/players/${player.player_id}?league_id=${leagueId}`}
                  className="min-w-0 flex-1 truncate text-sm text-white hover:text-bb-gold"
                >
                  {player.player_name}
                </Link>
                <OvrBadge ovr={player.ovr} size="sm" />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
