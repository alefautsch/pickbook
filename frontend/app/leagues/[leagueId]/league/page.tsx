import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { AgeProfilePanel } from "@/components/AgeProfilePanel";
import { FreeAgentBoard } from "@/components/FreeAgentBoard";
import { PositionHeatmap } from "@/components/PositionHeatmap";
import { TradeSurplusPanel } from "@/components/TradeSurplusPanel";
import {
  getFreeAgents,
  getLeague,
  getLeagueAnalysis,
  getLeagues,
} from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { OvrBadge } from "@/components/OvrBadge";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function LeagueAnalysisPage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  let league;
  let freeAgents;
  let analysis;

  try {
    [leagues, league, freeAgents, analysis] = await Promise.all([
      getLeagues(),
      getLeague(leagueId),
      getFreeAgents(leagueId),
      getLeagueAnalysis(leagueId),
    ]);
  } catch {
    notFound();
  }

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col bg-[#0d1117]/40 px-3 py-4 sm:px-8 sm:py-6">
        <header className="mb-4 md:mb-6">
          <h1 className="text-xl font-semibold text-white md:text-2xl">{league.name}</h1>
          <p className="mt-1 text-xs text-bb-muted md:text-sm">
            League analysis · synced {timeAgo(league.last_synced)}
          </p>
        </header>

        <div className="flex flex-col gap-5 md:gap-6">
          <div className="order-1">
            <FreeAgentBoard
              leagueId={leagueId}
              superflex={league.superflex}
              initialBoard={freeAgents}
            />
          </div>

          <section className="bb-panel order-2 p-4 md:p-5">
            <h2 className="bb-panel-title">All Teams</h2>
            <div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3 md:mt-4">
              {league.teams.map((team) => (
                <Link
                  key={team.roster_id}
                  href={`/leagues/${leagueId}/teams/${team.roster_id}`}
                  className="block"
                >
                  <article
                    className={`flex items-center gap-3 rounded-lg border border-bb-border/40 bg-black/20 p-3 transition hover:border-bb-gold/30 ${
                      team.is_me ? "border-bb-gold/40" : ""
                    }`}
                  >
                    <OvrBadge ovr={team.avg_dynasty_rating} size="sm" />
                    <div className="min-w-0">
                      <p className="truncate font-medium text-white">
                        {team.team_name}
                      </p>
                      <p className="text-xs text-bb-muted">
                        Rank #{team.dynasty_rank ?? "—"}
                      </p>
                    </div>
                  </article>
                </Link>
              ))}
            </div>
          </section>

          <div className="order-3 grid gap-5 md:gap-6 lg:grid-cols-2">
            <section className="bb-panel p-4 md:p-5">
              <h2 className="bb-panel-title">Age & Window</h2>
              <div className="mt-3 md:mt-4">
                <AgeProfilePanel profiles={analysis.age_profiles} />
              </div>
            </section>
            <section className="bb-panel p-4 md:p-5">
              <h2 className="bb-panel-title">Trade Surplus</h2>
              <div className="mt-3 md:mt-4">
                <TradeSurplusPanel
                  tradeSurplus={analysis.trade_surplus}
                  leagueId={leagueId}
                />
              </div>
            </section>
          </div>

          {analysis.position_strength ? (
            <section className="bb-panel order-4 p-4 md:p-5">
              <h2 className="bb-panel-title">Position Strength Heatmap</h2>
              <div className="mt-3 md:mt-4">
                <PositionHeatmap data={analysis.position_strength} leagueId={leagueId} />
              </div>
            </section>
          ) : null}
        </div>
      </div>
    </AppShell>
  );
}
