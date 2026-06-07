import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AgeOutlookTimeline } from "@/components/AgeOutlookTimeline";
import { ComponentDonut } from "@/components/DonutChart";
import { DurabilityGauge } from "@/components/DurabilityGauge";
import { LensPanel } from "@/components/LensPanel";
import { OvrGauge } from "@/components/OvrGauge";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { StatisticalProfile } from "@/components/StatisticalProfile";
import { OvrTrendSparkline } from "@/components/OvrTrendSparkline";
import Link from "next/link";
import { getLeagues, getPlayer, getPlayerHistory, getPlayerHoldings } from "@/lib/api";
import { OvrBadge } from "@/components/OvrBadge";
import {
  formatActvGames,
  formatDecimal,
  formatExp,
  formatHeight,
  formatPpg,
  formatTv,
  formatWorpPpg,
  ordinal,
} from "@/lib/format";
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
  const statStrip = [
    { label: "HPPG", value: formatPpg(player.hppg) },
    { label: "W/g", value: formatWorpPpg(player.worp_ppg) },
    {
      label: "ACTV",
      value: formatActvGames(
        player.healthy_games,
        player.total_games,
        player.availability,
      ),
    },
    { label: "WORP", value: formatDecimal(player.season_worp, 2) },
    { label: "TV", value: formatTv(player.trade_value) },
    { label: "FLEX", value: player.lenses.flex_rating ?? "—" },
    { label: "PORP", value: player.porp != null ? Math.round(player.porp) : "—" },
    { label: "Proj PPG", value: formatPpg(player.projected_ppg) },
  ];

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-6 py-8 sm:px-10">
        <section className="bb-card mb-6 overflow-hidden p-6">
          <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
            <PlayerHeadshot
              src={player.headshot_url}
              alt={player.player_name ?? "Player"}
              position={player.position}
              className="h-32 w-32 shrink-0"
              sizes="128px"
            />
            <div className="min-w-0 flex-1">
              <p className="text-sm text-bb-gold">{player.league_name}</p>
              <h1 className="mt-1 text-3xl font-semibold text-white">
                {player.player_name}
              </h1>
              <p className="mt-1 text-sm text-bb-muted">
                {player.nfl_team} · {player.position}
              </p>
              <dl className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-sm">
                <div>
                  <dt className="inline text-bb-muted">Age </dt>
                  <dd className="inline text-white">{player.age ?? "—"}</dd>
                </div>
                <div>
                  <dt className="inline text-bb-muted">Ht </dt>
                  <dd className="inline text-white">{formatHeight(player.bio.height)}</dd>
                </div>
                <div>
                  <dt className="inline text-bb-muted">Wt </dt>
                  <dd className="inline text-white">
                    {player.bio.weight ? `${player.bio.weight} lbs` : "—"}
                  </dd>
                </div>
                <div>
                  <dt className="inline text-bb-muted">Exp </dt>
                  <dd className="inline text-white">
                    {formatExp(player.bio.years_exp, player.dynasty_rookie)}
                  </dd>
                </div>
                <div>
                  <dt className="inline text-bb-muted">College </dt>
                  <dd className="inline text-white">{player.bio.college ?? "—"}</dd>
                </div>
              </dl>
            </div>
            <div className="flex flex-wrap items-center gap-6">
              <OvrGauge
                ovr={player.ovr}
                expected={player.hppg_expected}
                size="hero"
              />
              <div className="text-sm">
                {player.ranks.position_rank ? (
                  <p className="font-medium text-white">
                    {ordinal(player.ranks.position_rank)} {player.position} rank
                  </p>
                ) : null}
                {player.ranks.overall_rank ? (
                  <p className="mt-1 font-medium text-bb-gold">
                    {ordinal(player.ranks.overall_rank)} overall
                  </p>
                ) : null}
                <p className="mt-2 text-bb-muted">{tierLabels[tier]}</p>
              </div>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3 border-t border-bb-border/50 pt-4 sm:grid-cols-4 lg:grid-cols-8">
            {statStrip.map((stat) => (
              <div key={stat.label}>
                <p className="text-xs uppercase tracking-wide text-bb-muted">
                  {stat.label}
                </p>
                <p className="mt-0.5 font-medium text-white">{stat.value}</p>
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-8 lg:grid-cols-[1.2fr_1fr]">
          <LensPanel player={player} />

          <section className="bb-card p-5">
            <h2 className="text-lg font-medium text-white">Dynasty breakdown</h2>
            <p className="mt-1 text-sm text-bb-muted">Weighted component inputs</p>
            <div className="mt-4">
              <ComponentDonut components={player.components} ovr={player.ovr} />
            </div>
          </section>

          <StatisticalProfile player={player} />

          <section className="bb-card p-5">
            <h2 className="text-lg font-medium text-white">Durability</h2>
            <div className="mt-4 flex justify-center">
              <DurabilityGauge
                availability={player.availability}
                healthyGames={player.healthy_games}
                totalGames={player.total_games}
              />
            </div>
          </section>

          <AgeOutlookTimeline player={player} />

          {player.bio.college || player.bio.height ? (
            <section className="bb-card p-5">
              <h2 className="text-lg font-medium text-white">Bio</h2>
              <p className="mt-3 text-sm leading-relaxed text-bb-muted">
                {player.player_name} plays {player.position} for{" "}
                {player.nfl_team ?? "—"}
                {player.bio.college ? ` · ${player.bio.college}` : ""}.{" "}
                {player.outlook.archetype
                  ? `Archetype: ${player.outlook.archetype.replace(/_/g, " ")}.`
                  : ""}
              </p>
            </section>
          ) : null}

          {holdings && holdings.leagues.length > 0 ? (
            <section className="bb-card p-5 lg:col-span-2">
              <h2 className="text-lg font-medium text-white">Owned in leagues</h2>
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
            <h2 className="text-lg font-medium text-white">Grade trend</h2>
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
