import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { ComponentDonut } from "@/components/DonutChart";
import { InjuryWatchPanel } from "@/components/InjuryWatchPanel";
import { TeamTabs } from "@/components/TeamTabs";
import { getLeagues, getTeam } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { ContenderTag } from "@/components/ContenderTag";
import { DepthChartPanel } from "@/components/DepthChartPanel";
import { OvrGauge } from "@/components/OvrGauge";

type PageProps = {
  params: Promise<{ leagueId: string; rosterId: string }>;
};

export default async function TeamPage({ params }: PageProps) {
  const { leagueId, rosterId } = await params;

  let leagues = [];
  let team;

  try {
    [leagues, team] = await Promise.all([
      getLeagues(),
      getTeam(leagueId, rosterId),
    ]);
  } catch {
    notFound();
  }

  const leagueTile = leagues.find((l) => l.league_id === leagueId);
  const ovrDelta =
    team.is_me && leagueTile ? leagueTile.my_roster_ovr_delta : null;
  const leagueRosterCount =
    leagues.find((l) => l.league_id === leagueId)?.total_rosters ?? "—";

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-6 py-6 sm:px-10">
        <header className="mb-6">
          <div className="flex flex-wrap items-start gap-5">
            <OvrGauge ovr={team.avg_dynasty_rating} size="md" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-3">
                <h1 className="text-2xl font-semibold text-white sm:text-3xl">
                  {team.team_name ?? "Team"}
                </h1>
                <ContenderTag tier={team.contender_tier} />
              </div>
              <p className="mt-1 text-sm text-bb-muted">
                {team.league_name}
                {team.owner ? ` · ${team.owner}` : ""}
                {team.is_me ? " · (me)" : ""}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                <div>
                  <dt className="text-bb-muted">Dynasty rank</dt>
                  <dd className="font-medium text-white">
                    {ordinal(team.dynasty_rank)}
                    {team.dynasty_rank ? ` of ${leagueRosterCount}` : ""}
                  </dd>
                </div>
                <div>
                  <dt className="text-bb-muted">Starter Σ PPG</dt>
                  <dd className="font-medium text-white">
                    {formatPpg(team.starter_total_ppg)}
                    {team.starter_ppg_rank ? (
                      <span className="ml-1 text-xs text-bb-muted">
                        ({ordinal(team.starter_ppg_rank)})
                      </span>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt className="text-bb-muted">Trade value</dt>
                  <dd className="font-medium text-white">
                    {formatTv(team.total_trade_value)}
                    {team.tv_rank ? (
                      <span className="ml-1 text-xs text-bb-muted">
                        ({ordinal(team.tv_rank)})
                      </span>
                    ) : null}
                  </dd>
                </div>
                <div>
                  <dt className="text-bb-muted">OVR trend</dt>
                  <dd
                    className={`font-medium ${
                      ovrDelta == null
                        ? "text-white"
                        : ovrDelta > 0
                          ? "text-emerald-400"
                          : ovrDelta < 0
                            ? "text-red-300"
                            : "text-white"
                    }`}
                  >
                    {ovrDelta != null && ovrDelta !== 0
                      ? `${ovrDelta > 0 ? "+" : ""}${ovrDelta}`
                      : "—"}
                  </dd>
                </div>
              </dl>
            </div>
          </div>
        </header>

        <div className="grid gap-6 xl:grid-cols-[1fr_280px]">
          <TeamTabs team={team} />

          <aside className="space-y-4">
            <section className="bb-card p-4">
              <h2 className="text-xs font-medium uppercase tracking-wider text-bb-muted">
                Team OVR breakdown
              </h2>
              <div className="mt-3">
                <ComponentDonut
                  components={team.component_breakdown}
                  ovr={team.avg_dynasty_rating}
                />
              </div>
            </section>

            {team.traits.length > 0 ? (
              <section className="bb-card p-4">
                <h2 className="text-xs font-medium uppercase tracking-wider text-bb-muted">
                  Team traits
                </h2>
                <ul className="mt-3 space-y-2">
                  {team.traits.map((trait) => (
                    <li
                      key={trait.label}
                      className="flex items-center justify-between text-sm"
                    >
                      <span className="text-bb-muted">{trait.label}</span>
                      <span className="font-medium text-white">{trait.value}</span>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            <section className="bb-card p-4">
              <h2 className="text-xs font-medium uppercase tracking-wider text-bb-muted">
                Depth chart
              </h2>
              <div className="mt-3">
                <DepthChartPanel
                  depthChart={team.depth_chart}
                  leagueId={leagueId}
                />
              </div>
            </section>

            <div className="bb-card p-4">
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
