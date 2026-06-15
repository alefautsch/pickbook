import type { PlayerCard } from "@/lib/api";
import { formatTv } from "@/lib/format";
import { TradeValueBreakdown } from "@/components/TradeValueBreakdown";

type LensPanelProps = {
  player: PlayerCard;
};

export function LensPanel({ player }: LensPanelProps) {
  const lenses = [
    { label: "Dynasty OVR", value: player.ovr, highlight: true },
    { label: "Win-now", value: player.lenses.win_now_rating },
    { label: "Flex", value: player.lenses.flex_rating },
    { label: "TV (market)", value: player.trade_value, format: "tv" as const },
  ];

  return (
    <section className="bb-panel p-4 md:p-5">
      <h2 className="text-lg font-medium text-white">Lenses</h2>
      <p className="mt-1 text-sm text-bb-muted">
        Same player, different readings — OVR uses blended market TV in its composite
      </p>
      <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
        {lenses.map((lens) => (
          <div key={lens.label}>
            <dt className="text-xs uppercase tracking-wide text-bb-muted">
              {lens.label}
            </dt>
            <dd
              className={`mt-1 text-2xl font-semibold ${
                lens.highlight ? "text-bb-gold" : "text-white"
              }`}
            >
              {lens.format === "tv"
                ? formatTv(lens.value as number | null)
                : lens.value ?? "—"}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-4 border-t border-white/8 pt-4">
        <TradeValueBreakdown
          sources={player.trade_value_sources}
          blended={player.trade_value}
        />
      </div>
    </section>
  );
}
