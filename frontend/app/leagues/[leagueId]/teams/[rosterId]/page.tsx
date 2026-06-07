import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TeamLineup } from "@/components/TeamLineup";
import { getLeagues, getTeam } from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "@/components/OvrBadge";

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

  return (
    <AppShell leagues={leagues} activeLeagueId={leagueId}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-8 flex flex-wrap items-start gap-4">
          <OvrBadge ovr={team.avg_dynasty_rating} size="hero" />
          <div>
            <h1 className="text-3xl font-semibold text-white">
              {team.team_name ?? "Team"}
            </h1>
            <p className="mt-1 text-sm text-bb-muted">
              {team.league_name}
              {team.owner ? ` · ${team.owner}` : ""}
              {team.is_me ? " · (me)" : ""}
            </p>
            <dl className="mt-3 flex flex-wrap gap-4 text-sm">
              <div>
                <dt className="text-bb-muted">Dynasty rank</dt>
                <dd className="font-medium text-white">#{team.dynasty_rank ?? "—"}</dd>
              </div>
              <div>
                <dt className="text-bb-muted">Starter Σ PPG</dt>
                <dd className="font-medium text-white">
                  {formatPpg(team.starter_total_ppg)}
                </dd>
              </div>
              <div>
                <dt className="text-bb-muted">TV</dt>
                <dd className="font-medium text-white">
                  {formatTv(team.total_trade_value)}
                </dd>
              </div>
            </dl>
          </div>
        </header>

        <TeamLineup team={team} />
      </div>
    </AppShell>
  );
}
