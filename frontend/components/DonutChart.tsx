type DonutSegment = {
  label: string;
  value: number;
  color: string;
};

type DonutChartProps = {
  segments: DonutSegment[];
  centerLabel?: string;
  centerValue?: string | number;
  size?: number;
};

export function DonutChart({
  segments,
  centerLabel,
  centerValue,
  size = 160,
}: DonutChartProps) {
  const total = segments.reduce((sum, s) => sum + s.value, 0) || 1;
  const stroke = 18;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const renderedSegments = segments.map((segment, index) => {
    const fraction = segment.value / total;
    const dash = circumference * fraction;
    const offset = segments
      .slice(0, index)
      .reduce((sum, s) => sum + circumference * (s.value / total), 0);

    return { ...segment, dash, offset };
  });

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="color-mix(in srgb, var(--bb-border) 60%, transparent)"
          strokeWidth={stroke}
        />
        {renderedSegments.map((segment) => (
          <circle
            key={segment.label}
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={segment.color}
            strokeWidth={stroke}
            strokeDasharray={`${segment.dash} ${circumference - segment.dash}`}
            strokeDashoffset={-segment.offset}
          />
        ))}
      </svg>
      {(centerLabel || centerValue != null) && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          {centerValue != null ? (
            <span className="text-2xl font-bold text-white">{centerValue}</span>
          ) : null}
          {centerLabel ? (
            <span className="text-[10px] uppercase tracking-wider text-bb-muted">
              {centerLabel}
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}

export function ComponentDonut({
  components,
  ovr,
  compact = false,
}: {
  components: { tv?: number | null; worp?: number | null; per_game?: number | null; upside?: number | null; age?: number | null; trajectory?: number | null };
  ovr?: number | null;
  compact?: boolean;
}) {
  const segments: DonutSegment[] = [
    { label: "Trade value", value: components.tv ?? 0, color: "#3b82f6" },
    { label: "WORP", value: components.worp ?? 0, color: "#22c55e" },
    { label: "Per-game", value: components.per_game ?? 0, color: "#a855f7" },
    { label: "Upside", value: components.upside ?? 0, color: "#f97316" },
    { label: "Age", value: components.age ?? 0, color: "#eab308" },
    { label: "Trajectory", value: components.trajectory ?? 0, color: "#06b6d4" },
  ].filter((s) => s.value > 0);

  return (
    <div className={`flex flex-col items-center ${compact ? "gap-3 sm:flex-row sm:items-start" : "gap-4 sm:flex-row sm:items-start"}`}>
      <DonutChart
        segments={segments}
        centerValue={ovr ?? "—"}
        centerLabel="OVR"
        size={compact ? 112 : 160}
      />
      <ul className={`flex-1 space-y-2 ${compact ? "text-xs" : "text-sm"}`}>
        {segments.map((s) => (
          <li key={s.label} className="flex items-center gap-2">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: s.color }}
            />
            <span className="flex-1 text-bb-muted">{s.label}</span>
            <span className="font-medium text-white">{s.value.toFixed(2)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
