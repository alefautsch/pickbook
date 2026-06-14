type FaTagProps = {
  className?: string;
};

export function FaTag({ className = "" }: FaTagProps) {
  return (
    <span
      className={`inline-flex shrink-0 items-center rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-bb-gold bg-bb-gold/15 ${className}`}
    >
      FA
    </span>
  );
}
