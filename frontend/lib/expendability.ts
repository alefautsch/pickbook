export type ExpendabilityTier = "high" | "medium" | "low" | "core";

export function expendabilityTier(
  score: number | null | undefined,
): ExpendabilityTier | null {
  if (score == null) return null;
  if (score >= 60) return "high";
  if (score >= 30) return "medium";
  if (score >= 15) return "low";
  return "core";
}

const tierLabels: Record<ExpendabilityTier, string> = {
  high: "Move",
  medium: "Trade",
  low: "Depth",
  core: "Core",
};

const tierTitles: Record<ExpendabilityTier, string> = {
  high: "High expendability — strong sell candidate",
  medium: "Tradeable depth on this roster",
  low: "Replaceable but not a priority move",
  core: "Core piece — low trade appeal on this roster",
};

const tierStyles: Record<ExpendabilityTier, string> = {
  high: "bg-bb-gold/20 text-bb-gold border-bb-gold/45",
  medium: "bg-amber-500/15 text-amber-300 border-amber-500/35",
  low: "bg-sky-500/10 text-sky-300/90 border-sky-500/25",
  core: "bg-white/5 text-bb-muted border-bb-border/60",
};

export function expendabilityLabel(score: number | null | undefined): string | null {
  const tier = expendabilityTier(score);
  if (!tier) return null;
  return tierLabels[tier];
}

export function expendabilityTitle(score: number | null | undefined): string {
  const tier = expendabilityTier(score);
  if (!tier) return "Expendability score unavailable";
  const base = tierTitles[tier];
  if (score == null) return base;
  return `${base} (${Math.round(score)})`;
}

export function expendabilityStyle(score: number | null | undefined): string {
  const tier = expendabilityTier(score);
  if (!tier) return "bg-bb-surface text-bb-muted border-bb-border";
  return tierStyles[tier];
}
