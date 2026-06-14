type RookieBadgeProps = {
  className?: string;
};

export function RookieBadge({ className = "" }: RookieBadgeProps) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded px-1 py-0.5 text-[9px] font-semibold uppercase tracking-wide text-bb-gold bg-bb-gold/15 ${className}`}
      title="Dynasty rookie"
    >
      Rk
    </span>
  );
}
