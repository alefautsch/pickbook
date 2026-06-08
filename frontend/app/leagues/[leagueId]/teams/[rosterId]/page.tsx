import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TeamPageContent } from "@/components/TeamPageContent";
import { getLeagueAnalysis, getLeagues, getTeam } from "@/lib/api";

type PageProps = {
  params: Promise<{ leagueId: string; rosterId: string }>;
};

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

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{
        pageType: "team",
        rosterId,
        summary: team.team_name ?? "Team",
      }}
    >
      <TeamPageContent
        team={team}
        ovrDelta={ovrDelta}
        leagueRosterCount={leagueRosterCount}
        leagueId={leagueId}
        rosterId={rosterId}
        positionStrength={positionStrength}
        ageProfiles={ageProfiles}
      />
    </AppShell>
  );
}
