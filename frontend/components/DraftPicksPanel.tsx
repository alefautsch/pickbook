import type { DraftPickAsset } from "@/lib/api";
import { formatTv } from "@/lib/format";
import { TradeTagBadge } from "@/components/ExpendabilityBadge";

type DraftPicksPanelProps = {
  picks?: DraftPickAsset[];
  compact?: boolean;
};

export function DraftPicksPanel({ picks, compact = false }: DraftPicksPanelProps) {
  const safePicks = picks ?? [];
  if (safePicks.length === 0) {
    return (
      <p className="text-sm text-bb-muted">
        No future picks synced — run a league sync.
      </p>
    );
  }

  const sorted = [...safePicks].sort(
    (a, b) =>
      a.season.localeCompare(b.season) ||
      a.round - b.round ||
      (b.trade_value ?? 0) - (a.trade_value ?? 0),
  );
  const total = safePicks.reduce((sum, pick) => sum + (pick.trade_value ?? 0), 0);

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-3 text-sm">
        <span className="text-bb-muted">Total pick value</span>
        <span className="font-medium tabular-nums text-bb-gold">
          {formatTv(total)}
        </span>
      </div>
      <ul className={compact ? "space-y-1" : "space-y-1.5"}>
        {sorted.map((pick) => (
          <li
            key={`${pick.season}-${pick.round}-${pick.original_roster_id}`}
            className="flex items-center justify-between gap-3 text-sm"
          >
            <span className="min-w-0 truncate text-white">
              {pick.label ?? `${pick.season} R${pick.round}`}
              {!pick.is_own_slot ? (
                <span className="ml-1 text-[10px] text-bb-muted">via trade</span>
              ) : null}
            </span>
            <div className="flex shrink-0 items-center gap-2">
              <TradeTagBadge tag={pick.trade_tag} />
              <span className="tabular-nums text-bb-gold">
                {formatTv(pick.trade_value)}
              </span>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
