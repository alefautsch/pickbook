import { ovrTier, tierColors } from "@/lib/ovr";

type OvrBadgeSize = "hero" | "md" | "sm";

const sizeClasses: Record<OvrBadgeSize, string> = {
  hero: "h-16 w-16 text-2xl",
  md: "h-11 w-11 text-lg",
  sm: "h-8 w-8 text-sm",
};

type OvrBadgeProps = {
  ovr: number | null | undefined;
  expected?: boolean;
  size?: OvrBadgeSize;
  className?: string;
};

export function OvrBadge({
  ovr,
  expected = false,
  size = "md",
  className = "",
}: OvrBadgeProps) {
  const value = ovr ?? 0;
  const tier = ovrTier(ovr);
  const color = tierColors[tier];

  return (
    <div
      className={`relative flex shrink-0 items-center justify-center rounded-full font-bold text-white shadow-lg ${sizeClasses[size]} ${className}`}
      style={{
        background: `linear-gradient(145deg, ${color} 0%, color-mix(in srgb, ${color} 70%, #000) 100%)`,
        boxShadow: `0 4px 14px color-mix(in srgb, ${color} 45%, transparent)`,
      }}
      title={tier}
    >
      <span className="leading-none tracking-tight">{value || "—"}</span>
      {expected ? (
        <span className="absolute -right-0.5 -top-0.5 rounded bg-black/70 px-1 text-[9px] font-semibold text-bb-gold">
          e
        </span>
      ) : null}
    </div>
  );
}
