import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";

type LeagueSwitcherProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
};

export function LeagueSwitcher({ leagues, activeLeagueId }: LeagueSwitcherProps) {
  return (
    <nav className="flex flex-wrap gap-2">
      <Link
        href="/"
        className={`rounded-full px-3 py-1.5 text-sm transition ${
          !activeLeagueId
            ? "bg-bb-gold/20 text-bb-gold"
            : "text-bb-muted hover:bg-bb-surface hover:text-white"
        }`}
      >
        Hub
      </Link>
      {leagues.map((league) => (
        <Link
          key={league.league_id}
          href={`/leagues/${league.league_id}`}
          className={`rounded-full px-3 py-1.5 text-sm transition ${
            activeLeagueId === league.league_id
              ? "bg-bb-gold/20 text-bb-gold"
              : "text-bb-muted hover:bg-bb-surface hover:text-white"
          }`}
        >
          {league.name}
        </Link>
      ))}
    </nav>
  );
}
