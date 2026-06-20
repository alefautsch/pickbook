import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { LeagueAnalysisSections } from "@/components/LeagueAnalysisSections";
import { getLeague, getLeagueAnalysis, getLeagues, getRecentTrades } from "@/lib/api";
import { timeAgo } from "@/lib/format";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function LeagueAnalysisPage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  let league;
  let analysis;
  let recentTrades;

  try {
    [leagues, league, analysis, recentTrades] = await Promise.all([
      getLeagues(),
      getLeague(leagueId),
      getLeagueAnalysis(leagueId),
      getRecentTrades(leagueId),
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

        <LeagueAnalysisSections
          leagueId={leagueId}
          league={league}
          analysis={analysis}
          recentTrades={recentTrades}
        />
      </div>
    </AppShell>
  );
}
