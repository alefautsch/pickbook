import { notFound } from "next/navigation";
import { ApiUnavailable } from "@/components/ApiUnavailable";
import { AppShell } from "@/components/AppShell";
import { HashScroll } from "@/components/HashScroll";
import { LeagueOverviewAside } from "@/components/LeagueOverviewAside";
import { PortfolioOverviewRow } from "@/components/PortfolioOverviewRow";
import { RankingsTable } from "@/components/RankingsTable";
import { SummaryCards } from "@/components/SummaryCards";
import {
  getLeague,
  getLeagueAnalysis,
  getLeagueRankings,
  getLeagues,
  getPortfolio,
  getTeam,
} from "@/lib/api";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function LeagueOverviewPage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  let league;
  let rankings;
  let analysis;
  let portfolio;
  let myTeam = null;

  try {
    [leagues, league, rankings, analysis, portfolio] = await Promise.all([
      getLeagues(),
      getLeague(leagueId),
      getLeagueRankings(leagueId),
      getLeagueAnalysis(leagueId),
      getPortfolio(),
    ]);

    const myRoster = league.teams.find((t) => t.is_me);
    if (myRoster) {
      myTeam = await getTeam(leagueId, myRoster.roster_id);
    }
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    if (message.includes("fetch failed") || message.includes("ECONNREFUSED") || message.includes("500")) {
      return <ApiUnavailable />;
    }
    notFound();
  }

  const leagueTile = leagues.find((l) => l.league_id === leagueId);
  const myContender =
    analysis.contender_index?.teams.find((t) => t.is_me) ?? null;

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{
        pageType: "league",
        rosterId: leagueTile?.my_roster_id ?? undefined,
        summary: league.name,
      }}
    >
      <HashScroll />
      <div className="flex flex-1 flex-col bg-[#0d1117]/40 px-3 py-4 sm:px-8 sm:py-6">
        {leagueTile ? <SummaryCards league={leagueTile} /> : null}

        <div className="flex flex-col gap-6 xl:grid xl:grid-cols-[minmax(0,1fr)_300px] xl:gap-6">
          <div className="order-1 min-w-0 space-y-6 xl:order-1">
            <div id="rankings" className="scroll-mt-24 sm:scroll-mt-28">
              <RankingsTable
                leagueId={leagueId}
                byDynasty={rankings.by_dynasty}
                byStarterPpg={rankings.by_starter_ppg}
                byTv={rankings.by_tv}
                byWinNow={rankings.by_win_now}
              />
            </div>

            {portfolio ? (
              <PortfolioOverviewRow portfolio={portfolio} leagueId={leagueId} />
            ) : null}
          </div>

          <LeagueOverviewAside
            myTeam={myTeam}
            leagueId={leagueId}
            myRosterId={leagueTile?.my_roster_id}
            positionStrength={analysis.position_strength}
            ageProfiles={analysis.age_profiles}
            myContender={myContender}
          />
        </div>
      </div>
    </AppShell>
  );
}
