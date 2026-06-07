import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PlayerCard } from "@/components/PlayerCard";
import { OvrTrendSparkline } from "@/components/OvrTrendSparkline";
import Link from "next/link";
import { getLeagues, getPlayer, getPlayerHistory, getPlayerHoldings } from "@/lib/api";
import { OvrBadge } from "@/components/OvrBadge";
import { tierLabels, ovrTier } from "@/lib/ovr";

type PageProps = {
  params: Promise<{ playerId: string }>;
  searchParams: Promise<{ league_id?: string }>;
};

export default async function PlayerPage({ params, searchParams }: PageProps) {
  const { playerId } = await params;
  const { league_id: leagueId } = await searchParams;

  if (!leagueId) {
    notFound();
  }

  let leagues = [];
  let player;
  let history = null;
  let holdings = null;

  try {
    [leagues, player, history, holdings] = await Promise.all([
      getLeagues(),
      getPlayer(playerId, leagueId),
      getPlayerHistory(playerId, leagueId).catch(() => null),
      getPlayerHoldings(playerId).catch(() => null),
    ]);
  } catch {
    notFound();
  }

  const tier = ovrTier(player.ovr);
  const components = [
    { label: "Trade value", value: player.components.tv },
    { label: "WORP", value: player.components.worp },
    { label: "Per-game", value: player.components.per_game },
    { label: "Upside", value: player.components.upside },
    { label: "Age", value: player.components.age },
    { label: "Trajectory", value: player.components.trajectory },
  ];

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-6">
          <p className="text-sm text-bb-gold">{player.league_name}</p>
          <h1 className="mt-1 text-3xl font-semibold text-white">
            {player.player_name}
          </h1>
          <p className="mt-1 text-sm text-bb-muted">
            {tierLabels[tier]} · OVR {player.ovr}
          </p>
        </header>

        <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
          <PlayerCard player={player} size="hero" showLeague link={false} />

          <section className="bb-card p-5">
            <h2 className="text-lg font-medium text-white">Component Breakdown</h2>
            <p className="mt-1 text-sm text-bb-muted">
              Normalized 0–1 inputs to dynasty score
            </p>
            <ul className="mt-4 space-y-3">
              {components.map((c) => (
                <li key={c.label}>
                  <div className="mb-1 flex justify-between text-sm">
                    <span className="text-bb-muted">{c.label}</span>
                    <span className="font-medium text-white">
                      {c.value != null ? c.value.toFixed(3) : "—"}
                    </span>
                  </div>
                  <div className="h-2 overflow-hidden rounded-full bg-bb-border/50">
                    <div
                      className="h-full rounded-full bg-bb-gold"
                      style={{ width: `${(c.value ?? 0) * 100}%` }}
                    />
                  </div>
                </li>
              ))}
            </ul>

            {(player.lenses.flex_rating != null ||
              player.lenses.win_now_rating != null) && (
              <dl className="mt-6 grid grid-cols-2 gap-3 text-sm">
                {player.lenses.flex_rating != null ? (
                  <div>
                    <dt className="text-bb-muted">Flex rating</dt>
                    <dd className="font-medium text-white">
                      {player.lenses.flex_rating}
                    </dd>
                  </div>
                ) : null}
                {player.lenses.win_now_rating != null ? (
                  <div>
                    <dt className="text-bb-muted">Win-now</dt>
                    <dd className="font-medium text-white">
                      {player.lenses.win_now_rating}
                    </dd>
                  </div>
                ) : null}
              </dl>
            )}
          </section>

          {holdings && holdings.leagues.length > 0 ? (
            <section className="bb-card p-5 lg:col-span-2">
              <h2 className="text-lg font-medium text-white">Owned in leagues</h2>
              <p className="mt-1 text-sm text-bb-muted">
                Cross-league OVRs for your rosters
              </p>
              <ul className="mt-4 space-y-2">
                {holdings.leagues.map((league) => (
                  <li
                    key={league.league_id}
                    className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2"
                  >
                    <Link
                      href={`/players/${playerId}?league_id=${league.league_id}`}
                      className={`text-sm ${
                        league.league_id === leagueId
                          ? "font-medium text-bb-gold"
                          : "text-white hover:text-bb-gold"
                      }`}
                    >
                      {league.league_name}
                    </Link>
                    <OvrBadge ovr={league.ovr} size="sm" />
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          <section className="bb-card p-5 lg:col-span-2">
            <h2 className="text-lg font-medium text-white">Grade Trend</h2>
            <p className="mt-1 text-sm text-bb-muted">
              OVR and HPPG across syncs in {player.league_name}
            </p>
            <div className="mt-4">
              {history && history.points.length > 0 ? (
                <OvrTrendSparkline points={history.points} />
              ) : (
                <p className="text-sm text-bb-muted">
                  No history yet — sync twice to see trends.
                </p>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
