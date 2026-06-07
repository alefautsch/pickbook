import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";

type LeagueSwitcherProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
};

export function LeagueSwitcher({ leagues, activeLeagueId }: LeagueSwitcherProps) {
  return (
    <nav className="flex flex-wrap gap-1">
      {leagues.map((league) => {
        const active = activeLeagueId === league.league_id;
        const meta = `${league.total_rosters}-Team ${league.superflex ? "SF" : "1QB"} · ${league.season}`;
        return (
          <Link
            key={league.league_id}
            href={`/leagues/${league.league_id}`}
            className={`rounded-t-lg border px-4 py-2 transition ${
              active
                ? "border-bb-gold/50 border-b-transparent bg-[#121820] text-bb-gold"
                : "border-transparent text-bb-muted hover:bg-white/5 hover:text-white"
            }`}
          >
            <span className="block text-sm font-medium uppercase tracking-wide">
              {league.name}
            </span>
            <span className="block text-[10px] text-bb-muted">{meta}</span>
          </Link>
        );
      })}
    </nav>
  );
}
