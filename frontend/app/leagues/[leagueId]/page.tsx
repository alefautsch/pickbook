import Link from "next/link";
import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { RankingsTable } from "@/components/RankingsTable";
import { getLeague, getLeagueRankings, getLeagues } from "@/lib/api";
import { timeAgo } from "@/lib/format";
import { OvrBadge } from "@/components/OvrBadge";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function LeaguePage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  let league;
  let rankings;

  try {
    [leagues, league, rankings] = await Promise.all([
      getLeagues(),
      getLeague(leagueId),
      getLeagueRankings(leagueId),
    ]);
  } catch {
    notFound();
  }

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-8">
          <h1 className="text-3xl font-semibold text-white">{league.name}</h1>
          <p className="mt-2 text-sm text-bb-muted">
            {league.total_rosters} teams ·{" "}
            {league.superflex ? "Superflex" : "1QB"} · Synced{" "}
            {timeAgo(league.last_synced)}
          </p>
        </header>

        <section className="mb-10">
          <h2 className="mb-4 text-lg font-medium text-white">Power Rankings</h2>
          <RankingsTable
            leagueId={leagueId}
            byDynasty={rankings.by_dynasty}
            byStarterPpg={rankings.by_starter_ppg}
            byTv={rankings.by_tv}
            byWinNow={rankings.by_win_now}
          />
        </section>

        <section>
          <h2 className="mb-4 text-lg font-medium text-white">Teams</h2>
          <div className="grid gap-2 sm:grid-cols-2">
            {league.teams.map((team) => (
              <Link
                key={team.roster_id}
                href={`/leagues/${leagueId}/teams/${team.roster_id}`}
                className="block"
              >
                <article
                  className={`bb-card flex items-center gap-3 p-4 transition hover:-translate-y-0.5 ${
                    team.is_me ? "border-bb-gold/40" : ""
                  }`}
                >
                  <OvrBadge ovr={team.avg_dynasty_rating} size="sm" />
                  <div className="min-w-0 flex-1">
                    <p className="truncate font-medium text-white">
                      {team.team_name}
                      {team.is_me ? (
                        <span className="ml-2 text-xs text-bb-gold">(me)</span>
                      ) : null}
                    </p>
                    <p className="text-xs text-bb-muted">
                      Dynasty rank #{team.dynasty_rank ?? "—"}
                    </p>
                  </div>
                </article>
              </Link>
            ))}
          </div>
        </section>
      </div>
    </AppShell>
  );
}
