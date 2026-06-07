"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getFreeAgents, type FreeAgentBoard as FreeAgentBoardData } from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";

type FreeAgentBoardProps = {
  leagueId: string;
  superflex: boolean;
  initialBoard: FreeAgentBoardData;
};

const BASE_POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"] as const;

export function FreeAgentBoard({
  leagueId,
  superflex,
  initialBoard,
}: FreeAgentBoardProps) {
  const positions = superflex
    ? ([...BASE_POSITIONS, "SUPER_FLEX"] as const)
    : BASE_POSITIONS;

  const [filter, setFilter] = useState<string>("ALL");
  const [board, setBoard] = useState(initialBoard);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (filter === "ALL") {
      setBoard(initialBoard);
      return;
    }

    let cancelled = false;
    setLoading(true);
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
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-medium text-white">Free Agents</h2>
          <p className="text-sm text-bb-muted">
            Top {board.fa_pool_size} unrostered by trade value ·{" "}
            {loading ? "…" : board.total_available} shown
          </p>
        </div>
        <div className="flex flex-wrap gap-1">
          {positions.map((pos) => (
            <button
              key={pos}
              type="button"
              onClick={() => setFilter(pos)}
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

      <div className="bb-card overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-bb-border/80 text-left text-xs uppercase tracking-wider text-bb-muted">
              <th className="px-4 py-3">Player</th>
              <th className="px-4 py-3">OVR</th>
              <th className="hidden px-4 py-3 sm:table-cell">HPPG</th>
              <th className="hidden px-4 py-3 md:table-cell">TV</th>
            </tr>
          </thead>
          <tbody>
            {board.players.length === 0 ? (
              <tr>
                <td colSpan={4} className="px-4 py-6 text-center text-bb-muted">
                  {loading ? "Loading…" : "No free agents in this filter."}
                </td>
              </tr>
            ) : (
              board.players.map((player) => (
                <tr
                  key={player.player_id}
                  className="border-b border-bb-border/40 transition hover:bg-white/[0.03]"
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
                        <p className="font-medium text-white">
                          {player.player_name}
                        </p>
                        <p className="text-xs text-bb-muted">
                          {player.position}
                          {player.nfl_team ? ` · ${player.nfl_team}` : ""}
                          {player.age != null ? ` · ${player.age}y` : ""}
                        </p>
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
                  <td className="hidden px-4 py-3 text-white sm:table-cell">
                    {formatPpg(player.hppg)}
                    {player.hppg_expected ? (
                      <span className="ml-0.5 text-bb-gold">e</span>
                    ) : null}
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
