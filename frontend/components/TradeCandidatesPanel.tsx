import Link from "next/link";
import type { TradeCandidate } from "@/lib/api";
import { formatTv } from "@/lib/format";
import { TradeTagBadge } from "@/components/ExpendabilityBadge";
import { PositionTag } from "./PositionPill";

type TradeCandidatesPanelProps = {
  candidates: TradeCandidate[];
  leagueId: string;
};

function candidateKey(candidate: TradeCandidate): string {
  if (candidate.asset_type === "pick") {
    return `pick-${candidate.season}-${candidate.round}-${candidate.original_roster_id}`;
  }
  return candidate.player_id ?? candidate.player_name ?? "unknown";
}

export function TradeCandidatesPanel({
  candidates,
  leagueId,
}: TradeCandidatesPanelProps) {
  if (candidates.length === 0) {
    return (
      <p className="text-sm text-bb-muted">
        No trade chips tagged — core pieces and neutral depth only.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {candidates.map((asset) => {
        const isPick = asset.asset_type === "pick";
        const name = asset.player_name ?? "Unknown";
        return (
          <li
            key={candidateKey(asset)}
            className="flex items-center justify-between gap-3 rounded-lg bg-white/4 px-3 py-2 ring-1 ring-inset ring-white/[0.07]"
          >
            <div className="min-w-0">
              {isPick ? (
                <p className="truncate text-sm font-medium text-white">{name}</p>
              ) : (
                <Link
                  href={`/players/${asset.player_id}?league_id=${leagueId}`}
                  className="block truncate text-sm font-medium text-white hover:text-bb-gold"
                >
                  {name}
                </Link>
              )}
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                {isPick ? (
                  <span className="text-xs text-bb-muted">
                    Pick{asset.is_own_slot ? " · own slot" : " · via trade"}
                  </span>
                ) : (
                  <>
                    {asset.position ? <PositionTag position={asset.position} /> : null}
                    <span className="text-xs text-bb-muted">
                      {[
                        asset.depth_rank != null ? `Depth ${asset.depth_rank}` : null,
                        asset.lineup_delta_ppg != null
                          ? `+${asset.lineup_delta_ppg.toFixed(1)} PPG cliff`
                          : null,
                        asset.trade_value != null ? formatTv(asset.trade_value) : null,
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    </span>
                  </>
                )}
              </div>
            </div>
            <TradeTagBadge
              tag={asset.trade_tag ?? "trade"}
              lineupDelta={asset.lineup_delta_ppg}
            />
          </li>
        );
      })}
    </ul>
  );
}
