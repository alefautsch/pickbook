import type { ContenderTeam } from "@/lib/api";

type ContenderBreakdownProps = {
  team: ContenderTeam | null;
  embedded?: boolean;
  showTitleOnDesktop?: boolean;
};

function panelTitleClass(embedded?: boolean, showTitleOnDesktop?: boolean): string {
  if (embedded) return "hidden";
  if (showTitleOnDesktop) return "hidden lg:block";
  return "";
}

export function ContenderBreakdown({
  team,
  embedded = false,
  showTitleOnDesktop = false,
}: ContenderBreakdownProps) {
  if (!team) {
    return (
      <section className="bb-panel p-4">
        <h2 className={`bb-panel-title ${panelTitleClass(embedded, showTitleOnDesktop)}`}>
          Contender Breakdown
        </h2>
        <p className="mt-3 text-sm text-bb-muted">No contender data for your team yet.</p>
      </section>
    );
  }

  const bars = [
    { label: "Starter OVR", value: team.inputs.starter_ovr_norm },
    { label: "Starter Σ PPG", value: team.inputs.starter_ppg_norm },
    { label: "Age-weighted depth", value: team.inputs.age_depth_norm },
  ];

  return (
    <section className="bb-panel p-4">
      <h2 className={`bb-panel-title ${panelTitleClass(embedded, showTitleOnDesktop)}`}>
        Contender Breakdown
      </h2>
      <p className="mt-1 text-xs text-bb-muted">
        {team.tier} · composite {team.composite_score.toFixed(0)}
      </p>
      <ul className="mt-4 space-y-3">
        {bars.map((bar) => (
          <li key={bar.label}>
            <div className="mb-1 flex justify-between text-xs">
              <span className="text-bb-muted">{bar.label}</span>
              <span className="text-white">{bar.value != null ? Math.round(bar.value) : "—"}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-bb-border/50">
              <div
                className="h-full rounded-full bg-bb-gold"
                style={{ width: `${bar.value ?? 0}%` }}
              />
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}
