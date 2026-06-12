import {
  tradeTagLabel,
  tradeTagStyle,
  tradeTagTitle,
  type TradeTag,
} from "@/lib/tradeTag";

type TradeTagBadgeProps = {
  tag: TradeTag | null | undefined;
  lineupDelta?: number | null;
  size?: "sm" | "md";
};

export function TradeTagBadge({
  tag,
  lineupDelta,
  size = "sm",
}: TradeTagBadgeProps) {
  const label = tradeTagLabel(tag);
  if (!label) return null;

  const sizeClass = size === "md" ? "px-2.5 py-0.5 text-[11px]" : "px-2 py-0.5 text-[10px]";

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border font-semibold uppercase tracking-wide ${tradeTagStyle(tag)} ${sizeClass}`}
      title={tradeTagTitle(tag, lineupDelta)}
    >
      {label}
    </span>
  );
}

/** @deprecated Use TradeTagBadge — kept for gradual migration */
export function ExpendabilityBadge({
  score,
  tag,
  lineupDelta,
  showScore,
  size = "sm",
}: {
  score?: number | null;
  tag?: TradeTag | null;
  lineupDelta?: number | null;
  showScore?: boolean;
  size?: "sm" | "md";
}) {
  if (tag) {
    return <TradeTagBadge tag={tag} lineupDelta={lineupDelta} size={size} />;
  }
  return null;
}
