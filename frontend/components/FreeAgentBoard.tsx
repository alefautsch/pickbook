"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getFreeAgents, type FreeAgentBoard as FreeAgentBoardData } from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { RookieBadge } from "./RookieBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionTag } from "./PositionPill";

type FreeAgentBoardProps = {
  leagueId: string;
  superflex: boolean;
  initialBoard: FreeAgentBoardData;
  embedded?: boolean;
};

const BASE_POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"] as const;

export function FreeAgentBoard({
  leagueId,
  superflex,
  initialBoard,
  embedded = false,
}: FreeAgentBoardProps) {
  const positions = superflex
    ? ([...BASE_POSITIONS, "SUPER_FLEX"] as const)
    : BASE_POSITIONS;

  const [filter, setFilter] = useState<string>("ALL");
  const [board, setBoard] = useState(initialBoard);
  const [loading, setLoading] = useState(false);
  const activeBoard = filter === "ALL" ? initialBoard : board;
  const handleFilter = (pos: string) => {
    setFilter(pos);
    setLoading(pos !== "ALL");
  };

  useEffect(() => {
    if (filter === "ALL") {
      return;
    }

    let cancelled = false;
    void getFreeAgents(leagueId, filter)
      .then((data) => {
        if (!cancelled) setBoard(data);
      })
      .catch(() => {
        if (!cancelled) setBoard({ ...initialBoard, players: [], total_available: 0 });
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [filter, leagueId, initialBoard]);

  return (
    <section>
      {!embedded ? (
        <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-lg font-medium text-white">Free Agents</h2>
            <p className="text-sm text-bb-muted">
              Top {activeBoard.fa_pool_size} unrostered by trade value ·{" "}
              {loading ? "…" : activeBoard.total_available} shown
            </p>
          </div>
          <div className="flex flex-wrap gap-1">
            {positions.map((pos) => (
              <button
                key={pos}
                type="button"
                onClick={() => handleFilter(pos)}
                className={`rounded-full px-3 py-1 text-xs font-medium transition ${
                  filter === pos
                    ? "bg-bb-gold/20 text-bb-gold"
                    : "bg-bb-border/40 text-bb-muted hover:text-white"
                }`}
              >
                {pos === "ALL" ? "All" : pos.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <p className="text-xs text-bb-muted">
            Top {activeBoard.fa_pool_size} unrostered ·{" "}
            {loading ? "…" : activeBoard.total_available} shown
          </p>
          <div className="flex flex-wrap gap-1">
            {positions.map((pos) => (
              <button
                key={pos}
                type="button"
                onClick={() => handleFilter(pos)}
                className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition ${
                  filter === pos
                    ? "bg-bb-gold/20 text-bb-gold"
                    : "bg-bb-border/40 text-bb-muted hover:text-white"
                }`}
              >
                {pos === "ALL" ? "All" : pos.replace("_", " ")}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="bb-card overflow-hidden">
        <div className="divide-y divide-bb-border/30 md:hidden">
          {activeBoard.players.length === 0 ? (
            <p className="px-4 py-6 text-center text-sm text-bb-muted">
              {loading ? "Loading…" : "No free agents in this filter."}
            </p>
          ) : (
            activeBoard.players.map((player) => (
              <Link
                key={player.player_id}
                href={`/players/${player.player_id}?league_id=${leagueId}`}
                className="flex items-center gap-2 px-3 py-2.5 transition hover:bg-white/3"
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
                    <p className="truncate text-sm font-medium text-white">
                      {player.player_name}
                    </p>
                    {player.dynasty_rookie ? <RookieBadge /> : null}
                  </div>
                  <div className="mt-0.5 flex flex-wrap items-center gap-1">
                    {player.position ? <PositionTag position={player.position} /> : null}
                    <span className="text-[11px] text-bb-muted">
                      {[player.nfl_team, player.age != null ? String(player.age) : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2 pr-1">
                  <div className="text-center">
                    <p className="text-[9px] uppercase tracking-wide text-bb-muted">OVR</p>
                    <div className="mt-0.5 flex justify-center">
                      <OvrBadge
                        ovr={player.ovr}
                        expected={player.hppg_expected}
                        size="sm"
                      />
                    </div>
                  </div>
                  <div className="w-10 text-center">
                    <p className="text-[9px] uppercase tracking-wide text-bb-muted">PPG</p>
                    <p className="mt-0.5 text-sm font-semibold tabular-nums text-white">
                      {formatPpg(player.projected_ppg)}
                    </p>
                  </div>
                </div>
              </Link>
            ))
          )}
        </div>

        <table className="hidden w-full text-sm md:table">
          <thead>
            <tr className="border-b border-bb-border/80 text-left text-xs uppercase tracking-wider text-bb-muted">
              <th className="px-4 py-3">Player</th>
              <th className="px-4 py-3">OVR</th>
              <th className="hidden px-4 py-3 sm:table-cell">Proj PPG</th>
              <th className="hidden px-4 py-3 md:table-cell">TV</th>
            </tr>
          </thead>
          <tbody>
            {activeBoard.players.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-bb-muted">
                  {loading ? "Loading…" : "No free agents in this filter."}
                </td>
              </tr>
            ) : (
              activeBoard.players.map((player) => (
                <tr
                  key={player.player_id}
                  className="border-b border-bb-border/40 transition hover:bg-white/3"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/players/${player.player_id}?league_id=${leagueId}`}
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
                        <div className="flex items-center gap-1.5">
                          <p className="font-medium text-white">{player.player_name}</p>
                          {player.dynasty_rookie ? <RookieBadge /> : null}
                        </div>
                        <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                          {player.position ? <PositionTag position={player.position} /> : null}
                          <span className="text-xs text-bb-muted">
                            {[player.nfl_team, player.age != null ? `${player.age}y` : null]
                              .filter(Boolean)
                              .join(" · ")}
                          </span>
                        </div>
                      </div>
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <OvrBadge
                      ovr={player.ovr}
                      expected={player.hppg_expected}
                      size="sm"
                    />
                  </td>
                  <td
                    className="hidden px-4 py-3 text-white sm:table-cell"
                    title={`HPPG ${formatPpg(player.hppg)}`}
                  >
                    <span className="font-semibold tabular-nums">
                      {formatPpg(player.projected_ppg)}
                    </span>
                    <p className="text-xs text-bb-muted">
                      HPPG {formatPpg(player.hppg)}
                      {player.hppg_expected ? (
                        <span className="ml-0.5 text-bb-gold">e</span>
                      ) : null}
                    </p>
                  </td>
                  <td className="hidden px-4 py-3 text-white md:table-cell">
                    {formatTv(player.trade_value)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
