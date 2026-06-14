import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";

type LeagueSwitcherProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
  leagueHref?: (leagueId: string) => string;
};

export function LeagueSwitcher({
  leagues,
  activeLeagueId,
  leagueHref = (leagueId) => `/leagues/${leagueId}`,
}: LeagueSwitcherProps) {
  return (
    <nav className="flex min-w-0 gap-2 overflow-x-auto pb-0.5 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
      {leagues.map((league) => {
        const active = activeLeagueId === league.league_id;
        const meta = `${league.total_rosters}-Team ${league.superflex ? "SF" : "1QB"} · ${league.season}`;
        return (
          <Link
            key={league.league_id}
            href={leagueHref(league.league_id)}
            prefetch={false}
            className={`w-36 shrink-0 rounded-lg border px-2.5 py-1.5 transition sm:w-44 sm:px-3 sm:py-2 ${
              active
                ? "border-bb-gold/50 bg-[#121820] text-bb-gold"
                : "border-transparent text-bb-muted hover:bg-white/5 hover:text-white"
            }`}
          >
            <span className="block truncate text-[11px] font-semibold uppercase tracking-wide sm:text-xs">
              {league.name}
            </span>
            <span className="block text-[9px] text-bb-muted sm:text-[10px]">{meta}</span>
          </Link>
        );
      })}
    </nav>
  );
}
