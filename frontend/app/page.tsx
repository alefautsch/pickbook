import { AppShell } from "@/components/AppShell";
import { LeagueTile } from "@/components/LeagueTile";
import Link from "next/link";
import { getLeagues, getPortfolio, type LeagueTile as LeagueTileData } from "@/lib/api";
import { OvrBadge } from "@/components/OvrBadge";

export default async function Home() {
  let leagues: LeagueTileData[] = [];
  let portfolio = null;
  let error: string | null = null;

  try {
    [leagues, portfolio] = await Promise.all([getLeagues(), getPortfolio()]);
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load leagues";
  }

  const multiLeague =
    portfolio?.holdings.filter((h) => h.league_count >= 2).slice(0, 6) ?? [];

  return (
    <AppShell leagues={leagues}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-10">
          <h1 className="text-4xl font-semibold tracking-tight text-white">
            Front Office Hub
          </h1>
          <p className="mt-3 max-w-2xl text-bb-muted">
            Research your dynasty rosters across three leagues — grades are
            league-context OVRs from the latest sync.
          </p>
        </header>

        {error ? (
          <p className="text-red-300">{error}</p>
        ) : (
          <main className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {leagues.map((league) => (
              <LeagueTile key={league.league_id} league={league} />
            ))}
          </main>
        )}

        {portfolio ? (
          <section className="bb-card mt-10 p-5">
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-sm uppercase tracking-wider text-bb-muted">
                  Portfolio
                </h2>
                <p className="mt-1 text-sm text-white">
                  {portfolio.unique_players} players ·{" "}
                  {portfolio.multi_league_count} multi-league
                </p>
              </div>
              <Link
                href="/portfolio"
                className="text-sm text-bb-gold hover:underline"
              >
                View all →
              </Link>
            </div>
            {multiLeague.length > 0 ? (
              <ul className="mt-4 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
                {multiLeague.map((player) => (
                  <li
                    key={player.player_id}
                    className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2"
                  >
                    <Link
                      href={`/players/${player.player_id}?league_id=${player.leagues[0]?.league_id}`}
                      className="truncate text-sm text-white hover:text-bb-gold"
                    >
                      {player.player_name}
                      <span className="ml-2 text-xs text-bb-muted">
                        {player.league_count}/{portfolio.total_leagues}
                      </span>
                    </Link>
                    <OvrBadge ovr={player.leagues[0]?.ovr ?? null} size="sm" />
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-bb-muted">
                No multi-league overlap yet.
              </p>
            )}
          </section>
        ) : null}
      </div>
    </AppShell>
  );
}
