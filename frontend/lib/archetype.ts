const LABELS: Record<string, string> = {
  alpha_wr: "Alpha WR",
  slot_volume: "Slot volume",
  depth_wr: "Depth WR",
  workhorse_rb: "Workhorse RB",
  committee_rb: "Committee RB",
  pass_catching_rb: "Pass-catching RB",
  depth_rb: "Depth RB",
  alpha_te: "Alpha TE",
  blocking_te: "Blocking TE",
  elite_qb: "Elite QB",
  starter_qb: "Starter QB",
  developmental_qb: "Developmental QB",
  developmental: "Developmental",
  undervalued_producer: "Undervalued producer",
};

export function archetypeLabel(key: string | null | undefined): string {
  if (!key) return "—";
  return LABELS[key] ?? key.replace(/_/g, " ");
}

export function projectionSourceLabel(
  source: string | null | undefined
): string {
  if (!source) return "";
  if (source === "nflverse_blend") return "nflverse + Sleeper";
  if (source === "sleeper") return "Sleeper";
  if (source === "custom") return "volume model";
  return source;
}
