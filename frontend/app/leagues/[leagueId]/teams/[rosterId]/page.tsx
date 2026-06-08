import { notFound } from "next/navigation";
import type { ReactNode } from "react";
import { AppShell } from "@/components/AppShell";
import { AgeProfileSidebar } from "@/components/AgeProfileSidebar";
import { ComponentDonut } from "@/components/DonutChart";
import { InjuryWatchPanel } from "@/components/InjuryWatchPanel";
import { PositionStrengthBars } from "@/components/PositionStrengthBars";
import { TeamTabs } from "@/components/TeamTabs";
import { getLeagueAnalysis, getLeagues, getTeam } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { ContenderTag } from "@/components/ContenderTag";
import { DepthChartPanel } from "@/components/DepthChartPanel";
import { OvrGauge } from "@/components/OvrGauge";

type PageProps = {
  params: Promise<{ leagueId: string; rosterId: string }>;
};

function Metric({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "bad"
        ? "text-red-300"
        : "text-white";

  return (
    <div className="min-w-0 rounded-md bg-black/15 px-2 py-1.5">
      <dt className="truncate text-[9px] uppercase tracking-wider text-bb-muted">
        {label}
      </dt>
      <dd className={`mt-0.5 truncate text-base font-semibold tabular-nums ${toneClass}`}>
        {value}
      </dd>
      {sub ? <p className="truncate text-[9px] text-bb-muted">{sub}</p> : null}
    </div>
  );
}

export default async function TeamPage({ params }: PageProps) {
  const { leagueId, rosterId } = await params;

  let leagues = [];
  let team;
  let analysis: Awaited<ReturnType<typeof getLeagueAnalysis>> | null = null;

  try {
    [leagues, team, analysis] = await Promise.all([
      getLeagues(),
      getTeam(leagueId, rosterId),
      getLeagueAnalysis(leagueId).catch(() => null),
    ]);
  } catch {
    notFound();
  }

  const leagueTile = leagues.find((l) => l.league_id === leagueId);
  const ovrDelta =
    team.is_me && leagueTile ? leagueTile.my_roster_ovr_delta : null;
  const leagueRosterCount =
    leagues.find((l) => l.league_id === leagueId)?.total_rosters ?? "—";
  const positionStrength = analysis?.position_strength ?? null;
  const ageProfiles = analysis?.age_profiles ?? [];
  const ovrTone =
    ovrDelta == null
      ? "default"
      : ovrDelta > 0
        ? "good"
        : ovrDelta < 0
          ? "bad"
          : "default";

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col bg-[#0d1117]/40 px-4 py-5">
        <section className="mb-5 grid gap-4 lg:grid-cols-[minmax(300px,1fr)_280px_220px]">
          <div className="bb-panel p-4">
            <div className="flex flex-col gap-3 2xl:flex-row 2xl:items-center">
              <div className="flex items-start gap-4">
                <div className="shrink-0 rounded-2xl border border-bb-gold/25 bg-bb-gold/5 p-2 shadow-[0_0_24px_rgba(212,160,23,0.08)]">
                  <OvrGauge ovr={team.avg_dynasty_rating} size="md" />
                </div>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-3">
                    <h1 className="text-xl font-semibold leading-tight text-white sm:text-2xl">
                      {team.team_name ?? "Team"}
                    </h1>
                    <ContenderTag tier={team.contender_tier} />
                  </div>
                  <p className="mt-1 text-sm text-bb-muted">
                    {team.owner ?? "Unknown owner"}
                    {team.is_me ? " · (me)" : ""}
                  </p>
                  <p className="mt-1 text-xs uppercase tracking-wider text-bb-muted">
                    {team.league_name}
                  </p>
                </div>
              </div>

              <dl className="grid min-w-0 flex-1 grid-cols-5 gap-2">
                <Metric
                  label="Rank"
                  value={ordinal(team.dynasty_rank)}
                  sub={team.dynasty_rank ? `of ${leagueRosterCount}` : undefined}
                />
                <Metric
                  label="Start OVR"
                  value={team.starter_avg_dynasty_rating ?? "—"}
                  sub="avg"
                />
                <Metric
                  label="Start PPG"
                  value={formatPpg(team.starter_total_ppg)}
                  sub={team.starter_ppg_rank ? ordinal(team.starter_ppg_rank) : undefined}
                />
                <Metric
                  label="Trade Value"
                  value={formatTv(team.total_trade_value)}
                  sub={team.tv_rank ? ordinal(team.tv_rank) : undefined}
                />
                <Metric
                  label="OVR Trend"
                  value={
                    ovrDelta != null && ovrDelta !== 0
                      ? `${ovrDelta > 0 ? "+" : ""}${ovrDelta}`
                      : "—"
                  }
                  tone={ovrTone}
                />
              </dl>
            </div>
          </div>

          <section className="bb-panel p-4">
            <h2 className="bb-panel-title">Team OVR Breakdown</h2>
            <div className="mt-2">
              <ComponentDonut
                components={team.component_breakdown}
                ovr={team.avg_dynasty_rating}
                compact
              />
            </div>
          </section>

          <section className="bb-panel p-4">
            <h2 className="bb-panel-title">Team Traits</h2>
            {team.traits.length > 0 ? (
              <ul className="mt-3 space-y-1.5">
                {team.traits.map((trait) => (
                  <li
                    key={trait.label}
                    className="flex items-center justify-between gap-3 text-sm"
                  >
                    <span className="text-bb-muted">{trait.label}</span>
                    <span className="text-right font-medium text-white">
                      {trait.value}
                    </span>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-bb-muted">No traits yet.</p>
            )}
          </section>
        </section>

        <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
          <div className="min-w-0">
            <TeamTabs team={team} />
          </div>

          <aside className="space-y-4">
            <section className="bb-panel p-4">
              <h2 className="bb-panel-title">Depth Chart</h2>
              <div className="mt-3">
                <DepthChartPanel
                  depthChart={team.depth_chart}
                  leagueId={leagueId}
                  compact
                />
              </div>
            </section>

            {positionStrength ? (
              <PositionStrengthBars
                data={positionStrength}
                myRosterId={rosterId}
              />
            ) : null}

            <AgeProfileSidebar profiles={ageProfiles} rosterId={rosterId} />

            <div className="bb-panel p-4">
              <InjuryWatchPanel
                injuries={team.injuries}
                leagueId={leagueId}
                compact
              />
            </div>
          </aside>
        </div>
      </div>
    </AppShell>
  );
}
