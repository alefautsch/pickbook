export type TradeTag = "core" | "trade";

export function tradeTagLabel(tag: TradeTag | null | undefined): string | null {
  if (tag === "core") return "Core";
  if (tag === "trade") return "Trade";
  return null;
}

export function tradeTagTitle(
  tag: TradeTag | null | undefined,
  lineupDelta?: number | null,
): string {
  if (tag === "core") {
    const delta =
      lineupDelta != null ? ` · +${lineupDelta.toFixed(1)} PPG vs next backup` : "";
    return `Core piece — high marginal lineup value${delta}`;
  }
  if (tag === "trade") {
    const delta =
      lineupDelta != null ? ` · +${lineupDelta.toFixed(1)} PPG vs backup` : "";
    return `Trade chip — movable depth or pick currency${delta}`;
  }
  return "No trade tag — neutral roster piece";
}

export function tradeTagStyle(tag: TradeTag | null | undefined): string {
  if (tag === "core") return "bg-white/5 text-bb-muted border-bb-border/60";
  if (tag === "trade") return "bg-amber-500/15 text-amber-300 border-amber-500/35";
  return "bg-bb-surface text-bb-muted border-bb-border";
}
