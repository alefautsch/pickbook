import Link from "next/link";
import type { PortfolioSummary } from "@/lib/api";
import { OvrBadge } from "./OvrBadge";

type PortfolioOverviewRowProps = {
  portfolio: PortfolioSummary;
  leagueId: string;
};

export function PortfolioOverviewRow({ portfolio, leagueId }: PortfolioOverviewRowProps) {
  const multiLeague = portfolio.holdings.filter((h) => h.league_count >= 2).slice(0, 4);
  const topExposure = portfolio.holdings[0];

  return (
    <div className="flex flex-col gap-4 lg:grid lg:grid-cols-3 lg:gap-4">
      <section className="bb-panel p-4">
        <h2 className="bb-panel-title">Portfolio Overview</h2>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-bb-muted">Leagues</dt>
            <dd className="text-xl font-semibold text-white">{portfolio.total_leagues}</dd>
          </div>
          <div>
            <dt className="text-bb-muted">Unique players</dt>
            <dd className="text-xl font-semibold text-white">{portfolio.unique_players}</dd>
          </div>
          <div>
            <dt className="text-bb-muted">Multi-league</dt>
            <dd className="text-xl font-semibold text-white">{portfolio.multi_league_count}</dd>
          </div>
          <div>
            <dt className="text-bb-muted">Top exposure</dt>
            <dd className="truncate text-sm font-medium text-bb-gold">
              {topExposure?.player_name ?? "—"}
            </dd>
          </div>
        </dl>
      </section>

      <section className="bb-panel p-4">
        <div className="flex items-center justify-between">
          <h2 className="bb-panel-title">Multi-League Holdings</h2>
          <Link href="/portfolio" className="text-xs text-bb-gold hover:underline">
            View all
          </Link>
        </div>
        <ul className="mt-3 space-y-2">
          {multiLeague.length > 0 ? (
            multiLeague.map((player) => (
              <li
                key={player.player_id}
                className="flex items-center justify-between gap-2 rounded-lg bg-black/20 px-2 py-1.5"
              >
                <Link
                  href={`/players/${player.player_id}?league_id=${leagueId}`}
                  className="min-w-0 truncate text-sm text-white hover:text-bb-gold"
                >
                  {player.player_name}
                </Link>
                <div className="flex shrink-0 items-center gap-1">
                  {player.leagues.slice(0, 3).map((lg) => (
                    <OvrBadge key={lg.league_id} ovr={lg.ovr} size="sm" />
                  ))}
                </div>
              </li>
            ))
          ) : (
            <li className="text-sm text-bb-muted">No overlap yet.</li>
          )}
        </ul>
      </section>

      <section className="bb-panel p-4">
        <h2 className="bb-panel-title">Exposure by Position</h2>
        <ul className="mt-4 space-y-2">
          {portfolio.by_position.slice(0, 6).map((row) => (
            <li key={row.position}>
              <div className="mb-1 flex justify-between text-xs">
                <span className="font-semibold uppercase text-bb-muted">
                  {row.position}
                </span>
                <span className="text-white">{row.unique_players} players</span>
              </div>
              <div className="h-1.5 overflow-hidden rounded-full bg-black/40">
                <div
                  className="h-full rounded-full bg-bb-gold/70"
                  style={{
                    width: `${Math.min(100, (row.unique_players / Math.max(portfolio.unique_players, 1)) * 100 * 2.5)}%`,
                  }}
                />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
