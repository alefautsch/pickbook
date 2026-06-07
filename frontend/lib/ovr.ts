export type OvrTier = "elite" | "blue-chip" | "solid" | "depth" | "replacement";

export function ovrTier(ovr: number | null | undefined): OvrTier {
  const n = ovr ?? 0;
  if (n >= 90) return "elite";
  if (n >= 80) return "blue-chip";
  if (n >= 70) return "solid";
  if (n >= 60) return "depth";
  return "replacement";
}

export const tierColors: Record<OvrTier, string> = {
  elite: "#d4a017",
  "blue-chip": "#3b82f6",
  solid: "#22c55e",
  depth: "#64748b",
  replacement: "#475569",
};

export const tierLabels: Record<OvrTier, string> = {
  elite: "Elite",
  "blue-chip": "Blue-chip",
  solid: "Solid",
  depth: "Depth",
  replacement: "Replacement",
};

export type Position = "QB" | "RB" | "WR" | "TE" | string;

export { positionColor, positionColors, slotColor, formatSlotLabel } from "./positions";

export function sleeperHeadshot(playerId: string): string {
  return `https://sleepercdn.com/content/nfl/players/thumb/${playerId}.jpg`;
}
