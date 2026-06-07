import { formatSlotLabel, slotColor } from "@/lib/positions";

type PositionPillProps = {
  slot: string;
  className?: string;
};

export function PositionPill({ slot, className = "" }: PositionPillProps) {
  const label = formatSlotLabel(slot);
  const color = slotColor(slot);

  return (
    <span
      className={`inline-flex min-h-[1.375rem] min-w-[2rem] items-center justify-center rounded px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white ${className}`}
      style={{ backgroundColor: color }}
    >
      {label}
    </span>
  );
}
