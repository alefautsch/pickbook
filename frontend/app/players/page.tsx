import { notFound, redirect } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PlayersDirectory } from "@/components/PlayersDirectory";
import { getLeaguePlayers, getLeagues } from "@/lib/api";

const DEFAULT_LEAGUE_ID = "1314731206859853824";

type PageProps = {
  searchParams: Promise<{ league_id?: string }>;
};

export default async function PlayersPage({ searchParams }: PageProps) {
  const { league_id: leagueIdParam } = await searchParams;
  const leagues = await getLeagues().catch(() => []);

  if (leagues.length === 0) {
    return (
      <AppShell leagues={leagues}>
        <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-10 md:px-10">
          <h1 className="text-2xl font-semibold text-white md:text-3xl">Players</h1>
          <p className="mt-4 text-sm text-bb-muted">Sync a league to browse players.</p>
        </div>
      </AppShell>
    );
  }

  const leagueId =
    leagueIdParam ??
    leagues.find((league) => league.league_id === DEFAULT_LEAGUE_ID)?.league_id ??
    leagues[0].league_id;

  if (!leagueIdParam) {
    redirect(`/players?league_id=${leagueId}`);
  }

  let directory;
  try {
    directory = await getLeaguePlayers(leagueId);
  } catch {
    notFound();
  }

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-10 md:px-10">
        <header className="mb-6 md:mb-8">
          <h1 className="text-2xl font-semibold text-white md:text-3xl">Players</h1>
          <p className="mt-2 text-sm text-bb-muted">
            League player directory — search, filter, and expand rows for more stats.
          </p>
        </header>
        <PlayersDirectory leagues={leagues} leagueId={leagueId} initial={directory} />
      </div>
    </AppShell>
  );
}
