import Link from "next/link";
import type { LineupSlot } from "@/lib/api";
import { formatPpg } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionPill, PositionTag } from "./PositionPill";
import { RookieBadge } from "./RookieBadge";

type OptimalStartersSidebarProps = {
  starters: LineupSlot[];
  leagueId: string;
  embedded?: boolean;
  showTitleOnDesktop?: boolean;
};

function panelTitleClass(embedded?: boolean, showTitleOnDesktop?: boolean): string {
  if (embedded) return "hidden";
  if (showTitleOnDesktop) return "hidden lg:block";
  return "";
}

export function OptimalStartersSidebar({
  starters,
  leagueId,
  embedded = false,
  showTitleOnDesktop = false,
}: OptimalStartersSidebarProps) {
  const withPlayers = starters.filter((s) => s.player);
  const totalProj = withPlayers.reduce(
    (sum, s) => sum + (s.player?.projected_ppg ?? 0),
    0,
  );

  return (
    <section className="bb-panel p-4">
      <h2 className={`bb-panel-title ${panelTitleClass(embedded, showTitleOnDesktop)}`}>
        My Optimal Starters
      </h2>
      <ul className="mt-4 space-y-3">
        {withPlayers.map((slot) => {
          const player = slot.player!;
          return (
            <li key={`${slot.slot}-${player.player_id}`} className="flex items-center gap-3">
              <PositionPill slot={slot.slot} className="shrink-0" />
              <PlayerHeadshot
                src={player.headshot_url}
                alt={player.player_name ?? "Player"}
                position={player.position}
                className="h-9 w-9"
                sizes="36px"
              />
              <div className="min-w-0 flex-1">
                <Link
                  href={`/players/${player.player_id}?league_id=${leagueId}`}
                  className="flex items-center gap-1.5 truncate text-sm font-medium text-white hover:text-bb-gold"
                >
                  <span className="truncate">{player.player_name}</span>
                  {player.dynasty_rookie ? <RookieBadge /> : null}
                </Link>
                <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                  {player.position ? <PositionTag position={player.position} /> : null}
                  <span className="text-xs text-bb-muted">
                    {[player.nfl_team, `Proj ${formatPpg(player.projected_ppg)}`]
                      .filter(Boolean)
                      .join(" · ")}
                  </span>
                </div>
              </div>
              <OvrBadge ovr={player.ovr} expected={player.hppg_expected} size="sm" />
            </li>
          );
        })}
      </ul>
      <p className="mt-4 border-t border-bb-border/50 pt-3 text-sm">
        <span className="text-bb-muted">Total projected PPG </span>
        <span className="font-semibold text-white">{formatPpg(totalProj)}</span>
      </p>
    </section>
  );
}
