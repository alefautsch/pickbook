import Link from "next/link";
import type { DepthChartGroup } from "@/lib/api";
import { OvrBadge } from "./OvrBadge";
import { PlayerName } from "./PlayerName";

function abbreviateName(full: string | null): string {
  if (!full) return "Unknown";
  const parts = full.trim().split(/\s+/);
  if (parts.length < 2) return full;
  const lastName = parts.slice(1).join(" ");
  // Last-name-only in compact mode; prepend initial if last name is short enough
  // e.g. "Henderson" stays as-is; "Lee" becomes "T. Lee" to disambiguate
  return lastName.length <= 5 ? `${parts[0][0]}. ${lastName}` : lastName;
}

type DepthChartPanelProps = {
  depthChart: DepthChartGroup[];
  leagueId: string;
  compact?: boolean;
};

export function DepthChartPanel({
  depthChart,
  leagueId,
  compact = false,
}: DepthChartPanelProps) {
  if (depthChart.length === 0) {
    return <p className="text-sm text-bb-muted">No depth chart data.</p>;
  }

  if (compact) {
    return (
      <div className="grid grid-cols-2 gap-x-4 gap-y-3">
        {depthChart.map((group) => (
          <div key={group.position}>
            <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-bb-gold">
              {group.position}
            </h3>
            <ul className="space-y-1.5">
              {group.players.map((player) => {
                const playerName = player.player_name ?? "Unknown";
                return (
                <li key={player.player_id} className="flex items-center gap-1.5">
                  <span className="w-3 shrink-0 text-xs text-bb-muted">{player.depth_rank}</span>
                  <Link
                    href={`/players/${player.player_id}?league_id=${leagueId}`}
                    className="min-w-0 flex-1 hover:text-bb-gold"
                    title={playerName}
                  >
                    <PlayerName className="text-xs">{abbreviateName(playerName)}</PlayerName>
                  </Link>
                  <OvrBadge ovr={player.ovr} size="sm" />
                </li>
              )})}
            </ul>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
      {depthChart.map((group) => (
        <section key={group.position} className="bb-card p-4">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-bb-gold">
            {group.position}
          </h3>
          <ul className="mt-3 space-y-2">
            {group.players.map((player) => {
              const playerName = player.player_name ?? "Unknown";
              return (
              <li key={player.player_id} className="flex items-center gap-2">
                <span className="w-4 text-xs text-bb-muted">{player.depth_rank}</span>
                <Link
                  href={`/players/${player.player_id}?league_id=${leagueId}`}
                  className="min-w-0 flex-1 hover:text-bb-gold"
                  title={playerName}
                >
                  <PlayerName>{playerName}</PlayerName>
                </Link>
                <OvrBadge ovr={player.ovr} size="sm" />
              </li>
            )})}
          </ul>
        </section>
      ))}
    </div>
  );
}
