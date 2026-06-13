"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";
import type {
  PlayerCard,
  PlayerGameLog,
  PlayerHistorySeries,
  PlayerHoldings,
} from "@/lib/api";
import { AgeOutlookTimeline } from "@/components/AgeOutlookTimeline";
import { ComponentDonut } from "@/components/DonutChart";
import { DurabilityGauge } from "@/components/DurabilityGauge";
import { GameLogMobile } from "@/components/GameLogMobile";
import { LensPanel } from "@/components/LensPanel";
import { OvrBadge } from "@/components/OvrBadge";
import { OvrTrendSparkline } from "@/components/OvrTrendSparkline";
import { StatisticalProfile } from "@/components/StatisticalProfile";
import { formatDecimal, formatPpg } from "@/lib/format";

type TabKey = "snapshot" | "outlook" | "games";

const tabs: { key: TabKey; label: string }[] = [
  { key: "snapshot", label: "Snapshot" },
  { key: "outlook", label: "Outlook" },
  { key: "games", label: "Games" },
];

type PlayerPageSectionsProps = {
  player: PlayerCard;
  playerId: string;
  leagueId: string;
  history: PlayerHistorySeries | null;
  holdings: PlayerHoldings | null;
  gameLog: PlayerGameLog | null;
};

function Card({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`bb-card p-4 md:p-5 ${className}`}>{children}</section>
  );
}

function SecondaryStats({ player }: { player: PlayerCard }) {
  const stats = [
    { label: "WORP", value: formatDecimal(player.season_worp, 2) },
    { label: "FLEX", value: player.lenses.flex_rating ?? "—" },
    { label: "PORP", value: player.porp != null ? Math.round(player.porp) : "—" },
    { label: "HPPG", value: formatPpg(player.hppg) },
  ];

  return (
    <Card>
      <h2 className="text-base font-medium text-white md:text-lg">More metrics</h2>
      <dl className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-4">
        {stats.map((stat) => (
          <div
            key={stat.label}
            className="rounded-lg bg-white/4 px-2.5 py-2 ring-1 ring-inset ring-white/[0.07]"
          >
            <dt className="text-[9px] uppercase tracking-wider text-bb-muted">{stat.label}</dt>
            <dd className="mt-0.5 text-base font-bold tabular-nums text-white">{stat.value}</dd>
          </div>
        ))}
      </dl>
    </Card>
  );
}

function GameLogSection({ gameLog }: { gameLog: PlayerGameLog | null }) {
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-medium text-white md:text-lg">Game log</h2>
          <p className="mt-1 text-xs text-bb-muted md:text-sm">
            Half-PPR from nflverse. Low snap-share outliers excluded.
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
                      entry.carries > 0 ? `${entry.carries}/${entry.rushing_yards}` : "—";
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
                        <td
                          className={`px-3 py-2 text-right tabular-nums text-base font-bold ${ptsClass}`}
                        >
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
    </Card>
  );
}

export function PlayerPageSections({
  player,
  playerId,
  leagueId,
  history,
  holdings,
  gameLog,
}: PlayerPageSectionsProps) {
  const [tab, setTab] = useState<TabKey>("snapshot");

  const snapshot = (
    <div className="space-y-4">
      <StatisticalProfile player={player} />
      <Card>
        <h2 className="text-base font-medium text-white md:text-lg">Dynasty breakdown</h2>
        <p className="mt-1 text-xs text-bb-muted md:text-sm">Weighted component inputs</p>
        <div className="mt-4">
          <ComponentDonut components={player.components} ovr={player.ovr} compact />
        </div>
      </Card>
      <LensPanel player={player} />
      <Card>
        <h2 className="text-base font-medium text-white md:text-lg">Durability</h2>
        <div className="mt-4 flex justify-center">
          <DurabilityGauge
            availability={player.availability}
            healthyGames={player.healthy_games}
            totalGames={player.total_games}
          />
        </div>
      </Card>
      <SecondaryStats player={player} />
      {holdings && holdings.leagues.length > 0 ? (
        <Card>
          <h2 className="text-base font-medium text-white md:text-lg">Owned in leagues</h2>
          <ul className="mt-3 space-y-2">
            {holdings.leagues.map((league) => (
              <li
                key={league.league_id}
                className="flex items-center justify-between rounded-lg bg-black/20 px-3 py-2"
              >
                <Link
                  href={`/players/${playerId}?league_id=${league.league_id}`}
                  className={`min-w-0 truncate text-sm ${
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
        </Card>
      ) : null}
    </div>
  );

  const outlook = (
    <div className="space-y-4">
      <AgeOutlookTimeline player={player} />
      <Card>
        <h2 className="text-base font-medium text-white md:text-lg">Grade trend</h2>
        <div className="mt-4">
          {history && history.points.length > 0 ? (
            <OvrTrendSparkline points={history.points} />
          ) : (
            <p className="text-sm text-bb-muted">No history yet — sync twice to see trends.</p>
          )}
        </div>
      </Card>
    </div>
  );

  const games = <GameLogSection gameLog={gameLog} />;

  return (
    <>
      <div className="mb-3 grid grid-cols-3 gap-1 rounded-xl bg-black/25 p-1 ring-1 ring-inset ring-white/[0.06] lg:hidden">
        {tabs.map((item) => (
          <button
            key={item.key}
            type="button"
            onClick={() => setTab(item.key)}
            className={`rounded-lg px-2 py-2 text-xs font-medium transition ${
              tab === item.key
                ? "bg-bb-gold/20 text-bb-gold shadow-sm"
                : "text-bb-muted hover:bg-white/5 hover:text-white"
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      <div className="lg:hidden">
        {tab === "snapshot" ? snapshot : null}
        {tab === "outlook" ? outlook : null}
        {tab === "games" ? games : null}
      </div>

      <div className="hidden gap-4 md:gap-8 lg:grid lg:grid-cols-[1.2fr_1fr]">
        <StatisticalProfile player={player} />
        <Card>
          <h2 className="text-lg font-medium text-white">Dynasty breakdown</h2>
          <p className="mt-1 text-sm text-bb-muted">Weighted component inputs</p>
          <div className="mt-4">
            <ComponentDonut components={player.components} ovr={player.ovr} compact />
          </div>
        </Card>
        <AgeOutlookTimeline player={player} />
        <Card>
          <h2 className="text-lg font-medium text-white">Durability</h2>
          <div className="mt-4 flex justify-center">
            <DurabilityGauge
              availability={player.availability}
              healthyGames={player.healthy_games}
              totalGames={player.total_games}
            />
          </div>
        </Card>
        <LensPanel player={player} />
        {holdings && holdings.leagues.length > 0 ? (
          <Card>
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
          </Card>
        ) : null}
        <Card className="lg:col-span-2">
          <h2 className="text-lg font-medium text-white">Grade trend</h2>
          <div className="mt-4">
            {history && history.points.length > 0 ? (
              <OvrTrendSparkline points={history.points} />
            ) : (
              <p className="text-sm text-bb-muted">No history yet — sync twice to see trends.</p>
            )}
          </div>
        </Card>
        <div className="lg:col-span-2">
          <GameLogSection gameLog={gameLog} />
        </div>
      </div>
    </>
  );
}
