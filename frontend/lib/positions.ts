/** Sleeper-inspired roster position colors. */
export const positionColors: Record<string, string> = {
  QB: "#ff3366",
  RB: "#00ceb8",
  WR: "#3399ff",
  TE: "#ffab40",
  K: "#ef4444",
  DEF: "#374151",
};

export const slotColors: Record<string, string> = {
  QB: "#ff3366",
  RB: "#00ceb8",
  WR: "#3399ff",
  TE: "#ffab40",
  FLEX: "#9333ea",
  SUPER_FLEX: "#991b1b",
  SF: "#991b1b",
  BN: "#64748b",
};

export function positionColor(pos: string | null | undefined): string {
  return positionColors[(pos ?? "").toUpperCase()] ?? "#64748b";
}

export function slotColor(slot: string | null | undefined): string {
  const key = (slot ?? "").toUpperCase();
  return slotColors[key] ?? positionColors[key] ?? "#64748b";
}

/** Display label for roster slots. */
export function formatSlotLabel(slot: string | null | undefined): string {
  const key = (slot ?? "").toUpperCase();
  if (key === "SUPER_FLEX") return "SF";
  return key || "BN";
}
