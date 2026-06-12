import Link from "next/link";
import type { TradeCandidate } from "@/lib/api";
import { formatTv } from "@/lib/format";
import { ExpendabilityBadge } from "./ExpendabilityBadge";

type TradeCandidatesPanelProps = {
  candidates: TradeCandidate[];
  leagueId: string;
};

export function TradeCandidatesPanel({
  candidates,
  leagueId,
}: TradeCandidatesPanelProps) {
  if (candidates.length === 0) {
    return (
      <p className="text-sm text-bb-muted">
        No clear trade chips — core pieces and low-surplus depth only.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {candidates.map((player) => (
        <li
          key={player.player_id}
          className="flex items-center justify-between gap-3 rounded-lg bg-white/4 px-3 py-2 ring-1 ring-inset ring-white/[0.07]"
        >
          <div className="min-w-0">
            <Link
              href={`/players/${player.player_id}?league_id=${leagueId}`}
              className="block truncate text-sm font-medium text-white hover:text-bb-gold"
            >
              {player.player_name ?? "Unknown"}
            </Link>
            <p className="text-xs text-bb-muted">
              {player.position ?? "—"}
              {player.depth_rank != null ? ` · ${player.position}${player.depth_rank}` : ""}
              {player.trade_value != null ? ` · ${formatTv(player.trade_value)}` : ""}
            </p>
          </div>
          <ExpendabilityBadge score={player.expendability_score} showScore />
        </li>
      ))}
    </ul>
  );
}
