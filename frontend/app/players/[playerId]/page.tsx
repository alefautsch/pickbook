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
import {
  getLeagues,
  getPlayer,
  getPlayerGameLog,
  getPlayerHistory,
  getPlayerHoldings,
} from "@/lib/api";
import { OvrBadge } from "@/components/OvrBadge";
import { ExpendabilityBadge } from "@/components/ExpendabilityBadge";
import { GameLogMobile } from "@/components/GameLogMobile";
import { projectionSourceLabel } from "@/lib/archetype";
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
import { positionColor } from "@/lib/positions";

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
  let gameLog = null;

  try {
    [leagues, player, history, holdings, gameLog] = await Promise.all([
      getLeagues(),
      getPlayer(playerId, leagueId),
      getPlayerHistory(playerId, leagueId).catch(() => null),
      getPlayerHoldings(playerId).catch(() => null),
      getPlayerGameLog(playerId, leagueId).catch(() => null),
    ]);
  } catch {
    notFound();
  }

  const tier = ovrTier(player.ovr);
  const statStrip: {
    label: string;
    value: string | number;
    sub?: string;
    title?: string;
    featured?: boolean;
  }[] = [
    {
      label: "Proj PPG",
      value: formatPpg(player.projected_ppg),
      sub: `HPPG ${formatPpg(player.hppg)}`,
      title: projectionSourceLabel(player.projection_source),
      featured: true,
    },
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
  ];

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{
        pageType: "player",
        playerId,
        playerName: player.player_name ?? undefined,
        summary: `${player.player_name ?? "Player"} · OVR ${player.ovr ?? "—"}`,
      }}
    >
      <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-8 md:px-10">
        <section className="bb-card mb-4 overflow-hidden p-4 sm:mb-6 sm:p-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
            <PlayerHeadshot
              src={player.headshot_url}
              alt={player.player_name ?? "Player"}
              position={player.position}
              className="h-20 w-20 shrink-0 sm:h-32 sm:w-32 lg:h-40 lg:w-40"
              sizes="160px"
            />

            <div className="min-w-0 flex-1 lg:hidden">
              <p className="text-[10px] uppercase tracking-wider text-bb-muted">
                {player.league_name}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-1.5">
                <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
                  {player.player_name}
                </h1>
                <span
                  className="shrink-0 rounded-md px-1.5 py-0.5 text-[10px] font-bold uppercase"
                  style={{
                    backgroundColor: `${positionColor(player.position)}22`,
                    color: positionColor(player.position),
                  }}
                >
                  {player.position}
                </span>
              </div>
              <p className="mt-0.5 text-xs text-bb-muted sm:text-sm">{player.nfl_team}</p>
              {player.trade_tag ? (
                <div className="mt-1.5">
                  <ExpendabilityBadge
                    tag={player.trade_tag}
                    lineupDelta={player.lineup_delta_ppg}
                    size="md"
                  />
                </div>
              ) : null}
              <div className="mt-2">
                <OvrGauge
                  ovr={player.ovr}
                  expected={player.hppg_expected}
                  size="md"
                />
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2">
                {[
                  { label: "Age", value: player.age ?? "—" },
                  { label: "Height", value: formatHeight(player.bio.height) },
                  { label: "Weight", value: player.bio.weight ? `${player.bio.weight}` : "—" },
                ].map(({ label, value }) => (
                  <div key={label} className="rounded-md bg-white/4 px-2 py-1.5">
                    <dd className="text-sm font-semibold text-white">{value}</dd>
                    <dt className="text-[8px] uppercase tracking-wider text-bb-muted">{label}</dt>
                  </div>
                ))}
              </dl>
            </div>

            {/* Name / bio block — desktop */}
            <div className="hidden min-w-0 flex-1 lg:block">
              <p className="text-xs uppercase tracking-wider text-bb-muted">
                {player.league_name}
              </p>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                <h1 className="text-4xl font-bold tracking-tight text-white">
                  {player.player_name}
                </h1>
                <span
                  className="shrink-0 rounded-md px-2 py-0.5 text-xs font-bold uppercase"
                  style={{
                    backgroundColor: `${positionColor(player.position)}22`,
                    color: positionColor(player.position),
                  }}
                >
                  {player.position}
                </span>
                {player.trade_tag ? (
                  <ExpendabilityBadge
                    tag={player.trade_tag}
                    lineupDelta={player.lineup_delta_ppg}
                    size="md"
                  />
                ) : null}
              </div>
              <p className="mt-1 text-sm font-medium text-bb-muted">
                {player.nfl_team}
              </p>

              {/* Physical stats — stacked blocks */}
              <dl className="mt-4 flex flex-wrap gap-4">
                {[
                  { label: "Age", value: player.age ?? "—" },
                  { label: "Height", value: formatHeight(player.bio.height) },
                  {
                    label: "Weight",
                    value: player.bio.weight ? `${player.bio.weight}` : "—",
                  },
                  {
                    label: "Exp",
                    value: formatExp(player.bio.years_exp, player.dynasty_rookie),
                  },
                  { label: "College", value: player.bio.college ?? "—" },
                ].map(({ label, value }) => (
                  <div key={label}>
                    <dd className="text-base font-semibold text-white">{value}</dd>
                    <dt className="text-[9px] uppercase tracking-widest text-bb-muted">
                      {label}
                    </dt>
                  </div>
                ))}
              </dl>
            </div>

            {/* OVR gauge + rank boxes — desktop */}
            <div className="hidden shrink-0 flex-col items-center gap-3 lg:flex">
              <OvrGauge
                ovr={player.ovr}
                expected={player.hppg_expected}
                size="hero"
              />
              <div className="flex gap-2">
                {player.ranks.position_rank ? (
                  <div className="rounded-lg bg-white/4 px-4 py-2.5 text-center ring-1 ring-inset ring-white/[0.07]">
                    <p className="text-xl font-bold tabular-nums text-white">
                      {ordinal(player.ranks.position_rank)}
                    </p>
                    <p className="mt-0.5 text-[9px] uppercase tracking-wider text-bb-muted">
                      {player.position} rank
                    </p>
                  </div>
                ) : null}
                {player.ranks.overall_rank ? (
                  <div className="rounded-lg bg-white/4 px-4 py-2.5 text-center ring-1 ring-inset ring-white/[0.07]">
                    <p className="text-xl font-bold tabular-nums text-bb-gold">
                      {ordinal(player.ranks.overall_rank)}
                    </p>
                    <p className="mt-0.5 text-[9px] uppercase tracking-wider text-bb-muted">
                      overall
                    </p>
                  </div>
                ) : null}
              </div>
              <span className="rounded-full bg-bb-gold/10 px-3 py-0.5 text-[10px] font-bold uppercase tracking-widest text-bb-gold">
                {tierLabels[tier]}
              </span>
            </div>
          </div>

          {/* Stat strip */}
          <div className="mt-6 grid grid-cols-3 gap-2 border-t border-bb-border/50 pt-4 sm:grid-cols-4 lg:grid-cols-7">
            {statStrip.map((stat) => (
              <div
                key={stat.label}
                title={stat.title}
                className="rounded-lg bg-white/4 px-2.5 py-2 ring-1 ring-inset ring-white/[0.07]"
              >
                <p className="truncate text-[9px] uppercase tracking-wider text-bb-muted">
                  {stat.label}
                </p>
                <p
                  className={`mt-0.5 font-bold tabular-nums text-white ${
                    stat.featured ? "text-xl" : "text-base"
                  }`}
                >
                  {stat.value}
                </p>
                {stat.sub ? (
                  <p className="mt-0.5 text-[10px] text-bb-muted">{stat.sub}</p>
                ) : null}
              </div>
            ))}
          </div>
        </section>

        <div className="grid gap-4 md:gap-8 lg:grid-cols-[1.2fr_1fr]">
          {/* Row 1: Stats percentiles | Dynasty breakdown */}
          <StatisticalProfile player={player} />

          <section className="bb-card p-5">
            <h2 className="text-lg font-medium text-white">Dynasty breakdown</h2>
            <p className="mt-1 text-sm text-bb-muted">Weighted component inputs</p>
            <div className="mt-4">
              <ComponentDonut components={player.components} ovr={player.ovr} />
            </div>
          </section>

          {/* Row 2: Age outlook | Durability */}
          <AgeOutlookTimeline player={player} />

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

          {/* Row 3: Lenses | Owned in leagues */}
          <LensPanel player={player} />

          {holdings && holdings.leagues.length > 0 ? (
            <section className="bb-card p-5">
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

          {/* Row 4: Grade trend */}
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

          {/* Game log — full width, last */}
          <section className="bb-card overflow-hidden p-4 md:p-5 lg:col-span-2">
            <div className="flex flex-wrap items-end justify-between gap-3">
              <div>
                <h2 className="text-lg font-medium text-white">Game log</h2>
                <p className="mt-1 text-sm text-bb-muted">
                  Half-PPR rows from nflverse. Low snap-share injury outliers are excluded.
                </p>
              </div>
              {gameLog ? (
                <p className="text-xs uppercase tracking-wide text-bb-muted">
                  {gameLog.entries.filter((entry) => entry.included).length} included ·{" "}
                  {gameLog.entries.length} total
                </p>
              ) : null}
            </div>
            <div className="mt-4">
              {gameLog && gameLog.entries.length > 0 ? (
                <>
                  <GameLogMobile entries={gameLog.entries} />
                  <div className="hidden overflow-x-auto md:block">
                <table className="min-w-full text-left text-sm">
                  <thead className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
                    <tr>
                      <th className="py-2 pr-4 font-medium">Week</th>
                      <th className="px-3 py-2 font-medium">Opp</th>
                      <th className="px-3 py-2 text-right font-medium">Pts</th>
                      <th className="px-3 py-2 text-right font-medium">Snaps</th>
                      <th className="px-3 py-2 text-right font-medium">Rec/Tgt</th>
                      <th className="px-3 py-2 text-right font-medium">Rec Yds</th>
                      <th className="px-3 py-2 text-right font-medium">Rush</th>
                      <th className="px-3 py-2 text-right font-medium">Pass</th>
                      <th className="py-2 pl-3 font-medium">Model</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-bb-border/40">
                    {gameLog.entries.map((entry) => {
                      const snapPct =
                        entry.offense_pct != null
                          ? `${Math.round(entry.offense_pct * 100)}%`
                          : "—";
                      const rush =
                        entry.carries > 0
                          ? `${entry.carries}/${entry.rushing_yards}`
                          : "—";
                      const pass =
                        entry.attempts > 0
                          ? `${entry.passing_yards}/${entry.passing_tds}/${entry.interceptions}`
                          : "—";
                      const modelLabel = entry.included ? "Included" : "Snap outlier";
                      const pts = entry.points ?? 0;
                      const ptsClass = !entry.included
                        ? ""
                        : pts >= 20
                          ? "text-emerald-400"
                          : pts >= 15
                            ? "text-emerald-300/80"
                            : pts >= 8
                              ? "text-white"
                              : "text-amber-400/80";
                      return (
                        <tr
                          key={`${entry.season}-${entry.week}`}
                          className={entry.included ? "text-white" : "text-bb-muted"}
                        >
                          <td className="whitespace-nowrap py-2 pr-4">
                            {entry.season} W{entry.week}
                          </td>
                          <td className="px-3 py-2">{entry.opponent ?? "—"}</td>
                          <td className={`px-3 py-2 text-right tabular-nums font-bold text-base ${ptsClass}`}>
                            {formatPpg(entry.points)}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {entry.offense_snaps ?? "—"} / {snapPct}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {entry.receptions}/{entry.targets}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">
                            {entry.receiving_yards}
                            {entry.receiving_tds ? ` (${entry.receiving_tds})` : ""}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums">{rush}</td>
                          <td className="px-3 py-2 text-right tabular-nums">{pass}</td>
                          <td className="py-2 pl-3">
                            <span
                              className={`rounded-full px-2 py-0.5 text-xs ${
                                entry.included
                                  ? "bg-emerald-400/10 text-emerald-300"
                                  : "bg-bb-border/50 text-bb-muted"
                              }`}
                            >
                              {modelLabel}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                  </div>
                </>
              ) : (
                <p className="text-sm text-bb-muted">No nflverse game log found.</p>
              )}
            </div>
          </section>
        </div>
      </div>
    </AppShell>
  );
}
