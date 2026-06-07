type ContenderTier = "contender" | "competitive" | "rebuild" | string | null | undefined;

const tierStyles: Record<string, string> = {
  contender: "bg-emerald-500/20 text-emerald-300 border-emerald-500/40",
  competitive: "bg-sky-500/20 text-sky-300 border-sky-500/40",
  rebuild: "bg-amber-500/20 text-amber-300 border-amber-500/40",
};

const tierLabels: Record<string, string> = {
  contender: "Contender",
  competitive: "Competitive",
  rebuild: "Rebuild",
};

type ContenderTagProps = {
  tier: ContenderTier;
  size?: "sm" | "md";
};

export function ContenderTag({ tier, size = "sm" }: ContenderTagProps) {
  if (!tier) return null;
  const style = tierStyles[tier] ?? "bg-bb-surface text-bb-muted border-bb-border";
  const label = tierLabels[tier] ?? tier;
  const sizeClass = size === "md" ? "px-2.5 py-1 text-xs" : "px-2 py-0.5 text-[10px]";

  return (
    <span
      className={`inline-flex shrink-0 items-center rounded-full border font-medium uppercase tracking-wide ${style} ${sizeClass}`}
    >
      {label}
    </span>
  );
}
