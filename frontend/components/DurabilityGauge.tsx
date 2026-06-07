import { formatActvGames } from "@/lib/format";

type DurabilityGaugeProps = {
  availability: number | null | undefined;
  healthyGames?: number | null;
  totalGames?: number | null;
};

export function DurabilityGauge({
  availability,
  healthyGames,
  totalGames,
}: DurabilityGaugeProps) {
  const pct = availability != null ? Math.round(availability * 100) : null;
  const size = 120;
  const stroke = 10;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const fraction = pct != null ? pct / 100 : 0;
  const dash = circumference * fraction;
  const color =
    pct == null ? "#64748b" : pct >= 90 ? "#22c55e" : pct >= 70 ? "#eab308" : "#ef4444";

  return (
    <div className="flex flex-col items-center">
      <div className="relative" style={{ width: size, height: size / 2 + stroke }}>
        <svg width={size} height={size / 2 + stroke} className="overflow-visible">
          <path
            d={`M ${stroke / 2} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - stroke / 2} ${size / 2}`}
            fill="none"
            stroke="color-mix(in srgb, var(--bb-border) 80%, transparent)"
            strokeWidth={stroke}
            strokeLinecap="round"
          />
          <path
            d={`M ${stroke / 2} ${size / 2} A ${radius} ${radius} 0 0 1 ${size - stroke / 2} ${size / 2}`}
            fill="none"
            stroke={color}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
          />
        </svg>
        <div className="absolute inset-x-0 bottom-0 text-center">
          <p className="text-2xl font-bold text-white">{pct != null ? `${pct}%` : "—"}</p>
          <p className="text-xs text-bb-muted">Availability</p>
        </div>
      </div>
      <p className="mt-2 text-sm text-bb-muted">
        {formatActvGames(healthyGames, totalGames, availability)}
      </p>
    </div>
  );
}
