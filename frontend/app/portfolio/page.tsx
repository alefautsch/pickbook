import Link from "next/link";
import { AppShell } from "@/components/AppShell";
import { OvrBadge } from "@/components/OvrBadge";
import { PortfolioHoldingsMobile } from "@/components/PortfolioHoldingsMobile";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { PositionTag } from "@/components/PositionPill";
import { getLeagues, getPortfolio } from "@/lib/api";

const FLAG_LABELS: Record<string, string> = {
  conviction: "Conviction",
  risk: "Risk",
  concentrated: "Concentrated",
};

const FLAG_STYLES: Record<string, string> = {
  conviction: "bg-emerald-500/15 text-emerald-300",
  risk: "bg-red-500/15 text-red-300",
  concentrated: "bg-amber-500/15 text-amber-300",
};

export default async function PortfolioPage() {
  const [leagues, portfolio] = await Promise.all([getLeagues(), getPortfolio()]);
  const multiLeague = portfolio.holdings.filter((h) => h.league_count >= 2);

  return (
    <AppShell
      leagues={leagues}
      advisorContext={{ pageType: "portfolio", summary: "Cross-league portfolio" }}
    >
      <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-10 md:px-10">
        <header className="mb-6 md:mb-8">
          <h1 className="text-2xl font-semibold text-white md:text-3xl">Portfolio</h1>
          <p className="mt-2 text-sm text-bb-muted">
            {portfolio.unique_players} players across {portfolio.total_leagues}{" "}
            leagues · {portfolio.multi_league_count} multi-league holdings
          </p>
        </header>

        <section className="mb-8 md:mb-10">
          <h2 className="mb-3 text-sm uppercase tracking-wider text-bb-muted">
            Exposure by position
          </h2>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-2 sm:gap-3 lg:grid-cols-4">
            {portfolio.by_position.map((row) => (
              <div key={row.position} className="bb-card p-3 sm:p-4">
                <p className="text-xl font-semibold text-white sm:text-2xl">
                  {row.holding_count}
                </p>
                <p className="text-sm text-bb-muted">
                  {row.position} · {row.unique_players} unique
                </p>
              </div>
            ))}
          </div>
        </section>

        {multiLeague.length > 0 ? (
          <section className="mb-10">
            <h2 className="mb-4 text-lg font-medium text-white">
              Multi-league exposure
            </h2>
            <div className="grid gap-3 md:grid-cols-2">
              {multiLeague.map((player) => (
                <article key={player.player_id} className="bb-card p-4">
                  <div className="flex items-start gap-3">
                    <PlayerHeadshot
                      src={player.headshot_url}
                      alt={player.player_name ?? "Player"}
                      position={player.position}
                      className="h-14 w-14"
                      sizes="56px"
                    />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <Link
                          href={`/players/${player.player_id}?league_id=${player.leagues[0]?.league_id}`}
                          className="font-semibold text-white hover:text-bb-gold"
                        >
                          {player.player_name}
                        </Link>
                        {player.position ? <PositionTag position={player.position} /> : null}
                        <span className="text-xs text-bb-muted">
                          {player.league_count}/{portfolio.total_leagues} leagues
                        </span>
                        {player.exposure_flag ? (
                          <span
                            className={`rounded px-2 py-0.5 text-xs font-medium ${
                              FLAG_STYLES[player.exposure_flag] ??
                              "bg-bb-border/50 text-bb-muted"
                            }`}
                          >
                            {FLAG_LABELS[player.exposure_flag] ??
                              player.exposure_flag}
                          </span>
                        ) : null}
                      </div>
                      <ul className="mt-2 space-y-1">
                        {player.leagues.map((league) => (
                          <li
                            key={league.league_id}
                            className="flex items-center justify-between text-sm"
                          >
                            <span className="text-bb-muted">
                              {league.league_name}
                            </span>
                            <OvrBadge ovr={league.ovr} size="sm" />
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          </section>
        ) : null}

        <section>
          <h2 className="mb-3 text-base font-medium text-white md:mb-4 md:text-lg">
            All holdings
          </h2>
          <div className="bb-card overflow-hidden">
            <PortfolioHoldingsMobile holdings={portfolio.holdings} />
            <table className="hidden w-full text-sm md:table">
              <thead>
                <tr className="border-b border-bb-border/80 text-left text-xs uppercase tracking-wider text-bb-muted">
                  <th className="px-4 py-3">Player</th>
                  <th className="px-4 py-3">Leagues</th>
                  <th className="px-4 py-3">OVRs</th>
                </tr>
              </thead>
              <tbody>
                {portfolio.holdings.map((player) => (
                  <tr
                    key={player.player_id}
                    className="border-b border-bb-border/40"
                  >
                    <td className="px-4 py-3">
                      <Link
                        href={`/players/${player.player_id}?league_id=${player.leagues[0]?.league_id}`}
                        className="flex items-center gap-3"
                      >
                        <PlayerHeadshot
                          src={player.headshot_url}
                          alt={player.player_name ?? "Player"}
                          position={player.position}
                          className="h-10 w-10"
                          sizes="40px"
                        />
                        <div>
                          <p className="font-medium text-white">{player.player_name}</p>
                          <div className="mt-0.5">
                            {player.position ? <PositionTag position={player.position} /> : null}
                          </div>
                        </div>
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-bb-muted">
                      {player.league_count}
                      {player.exposure_flag ? (
                        <span className="ml-2 text-xs text-bb-gold">
                          {FLAG_LABELS[player.exposure_flag]}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        {player.leagues.map((league) => (
                          <span
                            key={league.league_id}
                            className="inline-flex items-center gap-1 rounded bg-black/20 px-2 py-0.5 text-xs"
                            title={league.league_name}
                          >
                            <span className="max-w-[5rem] truncate text-bb-muted">
                              {league.league_name.split(" ")[0]}
                            </span>
                            <OvrBadge ovr={league.ovr} size="sm" />
                          </span>
                        ))}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </AppShell>
  );
}
