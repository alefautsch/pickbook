import { ovrTier, tierColors, tierLabels } from "@/lib/ovr";

type OvrGaugeProps = {
  ovr: number | null | undefined;
  expected?: boolean;
  size?: "hero" | "md" | "sm";
  showTier?: boolean;
};

const sizes = {
  hero: { outer: 140, stroke: 10, font: "text-3xl", label: "text-xs" },
  md: { outer: 96, stroke: 8, font: "text-xl", label: "text-[10px]" },
  sm: { outer: 72, stroke: 6, font: "text-lg", label: "text-[8px]" },
};

export function OvrGauge({
  ovr,
  expected = false,
  size = "hero",
  showTier = true,
}: OvrGaugeProps) {
  const value = ovr ?? 0;
  const tier = ovrTier(ovr);
  const color = tierColors[tier];
  const dim = sizes[size];
  const radius = (dim.outer - dim.stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = Math.max(0, Math.min(100, value)) / 100;
  const dash = circumference * pct;

  return (
    <div className="relative inline-flex flex-col items-center">
      <svg width={dim.outer} height={dim.outer} className="-rotate-90">
        <circle
          cx={dim.outer / 2}
          cy={dim.outer / 2}
          r={radius}
          fill="none"
          stroke="color-mix(in srgb, var(--bb-border) 80%, transparent)"
          strokeWidth={dim.stroke}
        />
        <circle
          cx={dim.outer / 2}
          cy={dim.outer / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={dim.stroke}
          strokeLinecap="round"
          strokeDasharray={`${dash} ${circumference - dash}`}
          style={{ filter: `drop-shadow(0 0 8px color-mix(in srgb, ${color} 50%, transparent))` }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`font-bold text-white ${dim.font}`}>{value || "—"}</span>
        {expected ? (
          <span className="text-[10px] font-semibold text-bb-gold">e</span>
        ) : showTier ? (
          <span className={`uppercase tracking-wider text-bb-muted ${dim.label}`}>
            {tierLabels[tier]}
          </span>
        ) : null}
      </div>
    </div>
  );
}
