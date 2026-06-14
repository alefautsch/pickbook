"use client";

import Link from "next/link";
import { Fragment, useMemo, useState } from "react";
import type { LeaguePlayerDirectory, LeaguePlayerRow, LeagueTile } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import {
  formatActvGames,
  formatDecimal,
  formatPpg,
  formatTv,
  formatWorpPpg,
} from "@/lib/format";
import { FaTag } from "./FaTag";
import { LeagueSwitcher } from "./LeagueSwitcher";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PlayerName } from "./PlayerName";
import { PositionTag } from "./PositionPill";
import { RookieBadge } from "./RookieBadge";
import { matchesPositionFilter } from "@/lib/positions";

const BASE_POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"] as const;
const ROOKIE_FILTERS = ["ALL", "ROOKIES", "VETERANS"] as const;
type RookieFilter = (typeof ROOKIE_FILTERS)[number];

type PlayersDirectoryProps = {
  leagues: LeagueTile[];
  leagueId: string;
  superflex: boolean;
  initial: LeaguePlayerDirectory;
};

function FilterToggle({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`rounded-full px-3 py-1 text-xs font-medium transition ${
        active
          ? "bg-bb-gold/20 text-bb-gold"
          : "bg-bb-border/40 text-bb-muted hover:text-white"
      }`}
    >
      {label}
    </button>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function ExpandedStats({ player }: { player: LeaguePlayerRow }) {
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-6">
      {[
        { label: "W/G", value: formatWorpPpg(player.worp_ppg) },
        { label: "HPPG", value: formatPpg(player.hppg) },
        {
          label: "ACTV",
          value: formatActvGames(
            player.healthy_games,
            player.total_games,
            player.availability,
          ),
        },
        { label: "WORP", value: formatDecimal(player.season_worp, 2) },
        {
          label: "FLEX",
          value: player.flex_rating != null ? String(player.flex_rating) : "—",
        },
        {
          label: "PORP",
          value: player.porp != null ? String(Math.round(player.porp)) : "—",
        },
      ].map((stat) => (
        <div key={stat.label} className="rounded-md bg-black/20 px-2 py-1.5">
          <p className="text-[9px] uppercase tracking-wide text-bb-muted">{stat.label}</p>
          <p className="mt-0.5 text-sm font-semibold tabular-nums text-white">{stat.value}</p>
        </div>
      ))}
      {player.projection_source ? (
        <div className="col-span-3 rounded-md bg-black/20 px-2 py-1.5 sm:col-span-6">
          <p className="text-[9px] uppercase tracking-wide text-bb-muted">Projection</p>
          <p className="mt-0.5 text-xs text-white">
            {projectionSourceLabel(player.projection_source)}
          </p>
        </div>
      ) : null}
    </div>
  );
}

function PlayerIdentity({
  player,
  leagueId,
}: {
  player: LeaguePlayerRow;
  leagueId: string;
}) {
  return (
    <Link
      href={`/players/${player.player_id}?league_id=${leagueId}`}
      className="flex min-w-0 items-center gap-2.5 hover:opacity-90"
      onClick={(event) => event.stopPropagation()}
    >
      <PlayerHeadshot
        src={player.headshot_url}
        alt={player.player_name ?? "Player"}
        position={player.position}
        className="h-9 w-9 shrink-0 rounded-full"
        sizes="36px"
      />
      <div className="min-w-0">
        <div className="flex items-center gap-1.5">
          <PlayerName as="span">{player.player_name}</PlayerName>
          {player.dynasty_rookie ? <RookieBadge /> : null}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-1">
          {player.position ? <PositionTag position={player.position} /> : null}
          {player.nfl_team ? (
            <span className="text-[11px] text-bb-muted">{player.nfl_team}</span>
          ) : null}
        </div>
      </div>
    </Link>
  );
}

function TeamStatus({ player }: { player: LeaguePlayerRow }) {
  if (player.is_free_agent) {
    return <FaTag />;
  }
  return (
    <span
      className="truncate text-sm font-bold text-white"
      title={player.roster_team_name ?? undefined}
    >
      {player.roster_team_name ?? "—"}
    </span>
  );
}

function DirectoryRowMobile({
  player,
  leagueId,
  expanded,
  onToggle,
}: {
  player: LeaguePlayerRow;
  leagueId: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div className="border-b border-bb-border/25">
      <div className="flex w-full items-center gap-1 px-1 py-1">
        <Link
          href={`/players/${player.player_id}?league_id=${leagueId}`}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1.5 transition hover:bg-white/4 active:bg-white/6"
        >
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className="h-9 w-9 shrink-0 rounded-full"
            sizes="36px"
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <PlayerName as="p">{player.player_name}</PlayerName>
              {player.dynasty_rookie ? <RookieBadge /> : null}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1">
              {player.position ? <PositionTag position={player.position} /> : null}
              {player.nfl_team ? (
                <span className="text-[11px] text-bb-muted">{player.nfl_team}</span>
              ) : null}
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 pr-1">
            <div className="hidden min-w-18 text-right sm:block">
              <TeamStatus player={player} />
            </div>
            <OvrBadge ovr={player.ovr} expected={player.hppg_expected} size="sm" />
            <span className="w-12 text-right text-sm font-bold tabular-nums text-white">
              {formatTv(player.trade_value)}
            </span>
          </div>
        </Link>
        <button
          type="button"
          onClick={onToggle}
          className="shrink-0 rounded-lg p-2 text-bb-muted transition hover:bg-white/5 hover:text-white"
          aria-expanded={expanded}
          aria-label={expanded ? "Hide extra stats" : "Show extra stats"}
        >
          <ChevronIcon expanded={expanded} />
        </button>
      </div>
      <div className="flex items-center justify-between px-3 pb-2 sm:hidden">
        <TeamStatus player={player} />
        <span className="text-xs font-bold tabular-nums text-white">
          Proj {formatPpg(player.projected_ppg)}
        </span>
      </div>
      {expanded ? (
        <div className="border-t border-bb-border/20 bg-black/15 px-3 py-2.5">
          <ExpandedStats player={player} />
        </div>
      ) : null}
    </div>
  );
}

export function PlayersDirectory({
  leagues,
  leagueId,
  superflex,
  initial,
}: PlayersDirectoryProps) {
  const positions = superflex
    ? ([...BASE_POSITIONS, "SUPER_FLEX"] as const)
    : BASE_POSITIONS;

  const [query, setQuery] = useState("");
  const [positionFilter, setPositionFilter] = useState<string>("ALL");
  const [freeAgentsOnly, setFreeAgentsOnly] = useState(false);
  const [rookieFilter, setRookieFilter] = useState<RookieFilter>("ALL");
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return initial.players.filter((player) => {
      if (!matchesPositionFilter(player.position, positionFilter, superflex)) return false;
      if (freeAgentsOnly && !player.is_free_agent) return false;
      if (rookieFilter === "ROOKIES" && !player.dynasty_rookie) return false;
      if (rookieFilter === "VETERANS" && player.dynasty_rookie) return false;
      if (!q) return true;
      const haystack = [
        player.player_name,
        player.position,
        player.nfl_team,
        player.roster_team_name,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(q);
    });
  }, [initial.players, query, positionFilter, superflex, freeAgentsOnly, rookieFilter]);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 max-w-md flex-1">
          <label htmlFor="players-search" className="sr-only">
            Search players
          </label>
          <input
            id="players-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name, team, position…"
            className="w-full rounded-lg border border-bb-border bg-black/30 px-3 py-2.5 text-sm text-white placeholder:text-bb-muted"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <FilterToggle
            label="Free Agents"
            active={freeAgentsOnly}
            onClick={() => setFreeAgentsOnly((value) => !value)}
          />
          <div className="flex flex-wrap gap-1">
            {ROOKIE_FILTERS.map((filter) => (
              <button
                key={filter}
                type="button"
                onClick={() => setRookieFilter(filter)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                  rookieFilter === filter
                    ? "bg-bb-gold/20 text-bb-gold"
                    : "bg-bb-border/40 text-bb-muted hover:text-white"
                }`}
              >
                {filter === "ALL" ? "All" : filter === "ROOKIES" ? "Rookies" : "Veterans"}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="flex flex-wrap gap-1">
        {positions.map((pos) => (
          <button
            key={pos}
            type="button"
            onClick={() => setPositionFilter(pos)}
            className={`rounded-full px-3 py-1 text-xs font-medium transition ${
              positionFilter === pos
                ? "bg-bb-gold/20 text-bb-gold"
                : "bg-bb-border/40 text-bb-muted hover:text-white"
            }`}
          >
            {pos === "ALL" ? "All" : pos.replace("_", " ")}
          </button>
        ))}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-bb-muted">
        <p>
          {filtered.length} of {initial.total_players} players · {initial.league_name}
        </p>
        <div className="min-w-48">
          <LeagueSwitcher
            leagues={leagues}
            activeLeagueId={leagueId}
            leagueHref={(id) => `/players?league_id=${id}`}
          />
        </div>
      </div>

      <div className="bb-card overflow-hidden">
        <div className="md:hidden">
          {filtered.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-bb-muted">No players match.</p>
          ) : (
            filtered.map((player) => (
              <DirectoryRowMobile
                key={player.player_id}
                player={player}
                leagueId={leagueId}
                expanded={expandedId === player.player_id}
                onToggle={() =>
                  setExpandedId((current) =>
                    current === player.player_id ? null : player.player_id,
                  )
                }
              />
            ))
          )}
        </div>

        <table className="hidden w-full min-w-[760px] text-sm md:table">
          <thead>
            <tr className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
              <th className="px-3 py-3 text-left font-medium">Player</th>
              <th className="px-3 py-3 text-left font-medium">Team</th>
              <th className="px-3 py-3 text-center font-medium">Age</th>
              <th className="px-3 py-3 text-center font-medium">OVR</th>
              <th className="px-3 py-3 text-center font-medium">Proj</th>
              <th className="px-3 py-3 text-right font-medium">TV</th>
              <th className="w-10 px-2 py-3" />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-4 py-8 text-center text-bb-muted">
                  No players match.
                </td>
              </tr>
            ) : (
              filtered.map((player) => {
                const expanded = expandedId === player.player_id;
                return (
                  <Fragment key={player.player_id}>
                    <tr
                      className="cursor-pointer border-b border-bb-border/30 transition hover:bg-white/5"
                      onClick={() =>
                        setExpandedId((current) =>
                          current === player.player_id ? null : player.player_id,
                        )
                      }
                    >
                      <td className="px-3 py-2.5">
                        <PlayerIdentity player={player} leagueId={leagueId} />
                      </td>
                      <td className="px-3 py-2.5">
                        <TeamStatus player={player} />
                      </td>
                      <td className="px-3 py-2.5 text-center font-bold tabular-nums text-white">
                        {player.age ?? "—"}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex justify-center">
                          <OvrBadge
                            ovr={player.ovr}
                            expected={player.hppg_expected}
                            size="sm"
                          />
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-center font-bold tabular-nums text-white">
                        {formatPpg(player.projected_ppg)}
                      </td>
                      <td className="px-3 py-2.5 text-right text-base font-bold tabular-nums text-white">
                        {formatTv(player.trade_value)}
                      </td>
                      <td className="px-2 py-2.5 text-bb-muted">
                        <ChevronIcon expanded={expanded} />
                      </td>
                    </tr>
                    {expanded ? (
                      <tr className="border-b border-bb-border/30 bg-black/15">
                        <td colSpan={7} className="px-3 py-3">
                          <ExpandedStats player={player} />
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
