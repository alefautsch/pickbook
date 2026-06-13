import Link from "next/link";
import type { PortfolioPlayer } from "@/lib/api";
import { OvrBadge } from "@/components/OvrBadge";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { PositionTag } from "@/components/PositionPill";

const FLAG_LABELS: Record<string, string> = {
  conviction: "Conviction",
  risk: "Risk",
  concentrated: "Concentrated",
};

type PortfolioHoldingsMobileProps = {
  holdings: PortfolioPlayer[];
};

export function PortfolioHoldingsMobile({ holdings }: PortfolioHoldingsMobileProps) {
  return (
    <div className="divide-y divide-bb-border/30 md:hidden">
      {holdings.map((player) => (
        <Link
          key={player.player_id}
          href={`/players/${player.player_id}?league_id=${player.leagues[0]?.league_id}`}
          className="flex items-center gap-3 px-3 py-3 transition hover:bg-white/3"
        >
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className="h-10 w-10 shrink-0"
            sizes="40px"
          />
          <div className="min-w-0 flex-1">
            <p className="truncate font-medium text-white">{player.player_name}</p>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
              {player.position ? <PositionTag position={player.position} /> : null}
              <span className="text-xs text-bb-muted">
                {player.league_count} league{player.league_count === 1 ? "" : "s"}
              </span>
              {player.exposure_flag ? (
                <span className="text-[10px] font-medium uppercase text-bb-gold">
                  {FLAG_LABELS[player.exposure_flag] ?? player.exposure_flag}
                </span>
              ) : null}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1">
              {player.leagues.map((league) => (
                <span
                  key={league.league_id}
                  className="inline-flex items-center gap-1 rounded bg-black/25 px-1.5 py-0.5"
                  title={league.league_name}
                >
                  <span className="max-w-[4.5rem] truncate text-[10px] text-bb-muted">
                    {league.league_name.split(" ")[0]}
                  </span>
                  <OvrBadge ovr={league.ovr} size="sm" />
                </span>
              ))}
            </div>
          </div>
        </Link>
      ))}
    </div>
  );
}
