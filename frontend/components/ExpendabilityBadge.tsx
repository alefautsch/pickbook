import {
  expendabilityLabel,
  expendabilityStyle,
  expendabilityTitle,
} from "@/lib/expendability";

type ExpendabilityBadgeProps = {
  score: number | null | undefined;
  size?: "sm" | "md";
  showScore?: boolean;
};

export function ExpendabilityBadge({
  score,
  size = "sm",
  showScore = false,
}: ExpendabilityBadgeProps) {
  const label = expendabilityLabel(score);
  if (label == null) return null;

  const sizeClass = size === "md" ? "px-2.5 py-1 text-xs" : "px-1.5 py-0.5 text-[10px]";

  return (
    <span
      className={`inline-flex shrink-0 items-center gap-1 rounded-full border font-semibold uppercase tracking-wide ${expendabilityStyle(score)} ${sizeClass}`}
      title={expendabilityTitle(score)}
    >
      {label}
      {showScore && score != null ? (
        <span className="font-normal tabular-nums opacity-80">{Math.round(score)}</span>
      ) : null}
    </span>
  );
}
