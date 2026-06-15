import type { TradeValueSources } from "@/lib/api";
import { formatTv } from "@/lib/format";

type TradeValueBreakdownProps = {
  sources: TradeValueSources | null | undefined;
  blended?: number | null;
  compact?: boolean;
};

function weightPct(weight: number | null | undefined): string | null {
  if (weight == null || weight <= 0) return null;
  return `${Math.round(weight * 100)}%`;
}

export function TradeValueBreakdown({
  sources,
  blended,
  compact = false,
}: TradeValueBreakdownProps) {
  const displayTv = blended ?? sources?.blended ?? null;
  if (displayTv == null && !sources) return null;

  const rows = [
    {
      label: "Dynasty Dealer",
      value: sources?.dynasty_dealer,
      weight: weightPct(sources?.dealer_weight),
      highlight: true,
    },
    {
      label: "KeepTradeCut",
      value: sources?.ktc,
      weight: weightPct(sources?.ktc_weight),
    },
    {
      label: "Dynasty Daddy",
      value: sources?.dynasty_daddy,
      weight: weightPct(sources?.dd_weight),
    },
  ].filter((row) => row.value != null && row.value > 0);

  if (compact) {
    return (
      <div className="text-[10px] text-bb-muted">
        <p className="font-medium text-white/80">{formatTv(displayTv)} blended TV</p>
        {rows.length > 0 ? (
          <p className="mt-0.5">
            {rows.map((row) => `${row.label} ${formatTv(row.value)}`).join(" · ")}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex items-baseline justify-between gap-2">
        <p className="text-xs uppercase tracking-wide text-bb-muted">Blended trade value</p>
        <p className="text-lg font-semibold tabular-nums text-white">{formatTv(displayTv)}</p>
      </div>
      {rows.length > 0 ? (
        <ul className="space-y-1.5">
          {rows.map((row) => (
            <li
              key={row.label}
              className="flex items-center justify-between gap-2 text-xs"
            >
              <span className={row.highlight ? "text-sky-300" : "text-bb-muted"}>
                {row.label}
                {row.weight ? (
                  <span className="ml-1 text-[10px] text-bb-muted">({row.weight})</span>
                ) : null}
              </span>
              <span className="font-medium tabular-nums text-white">{formatTv(row.value)}</span>
            </li>
          ))}
        </ul>
      ) : null}
      <p className="text-[10px] leading-relaxed text-bb-muted">
        Blended TV is ~45% of dynasty OVR. Includes{" "}
        <a
          href="https://www.dynastydealer.com"
          target="_blank"
          rel="noopener noreferrer"
          className="underline decoration-white/20 underline-offset-2 hover:text-white"
        >
          Dynasty Dealer
        </a>{" "}
        trade-derived values when available.
      </p>
    </div>
  );
}
