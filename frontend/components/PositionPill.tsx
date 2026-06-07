import { formatSlotLabel, slotColor } from "@/lib/positions";

type PositionPillProps = {
  slot: string;
  className?: string;
  /** Stretch to fill a table cell (parent must be `relative`). */
  fill?: boolean;
};

export function PositionPill({ slot, className = "", fill = false }: PositionPillProps) {
  const label = formatSlotLabel(slot);
  const color = slotColor(slot);
  const labelClass =
    "text-center text-[10px] font-bold uppercase tracking-wide text-white";

  if (fill) {
    return (
      <span
        className={`absolute inset-0 flex items-center justify-center ${labelClass} ${className}`}
        style={{ backgroundColor: color }}
      >
        {label}
      </span>
    );
  }

  return (
    <span
      className={`inline-flex h-[1.375rem] w-11 shrink-0 items-center justify-center rounded ${labelClass} ${className}`}
      style={{ backgroundColor: color }}
    >
      {label}
    </span>
  );
}
