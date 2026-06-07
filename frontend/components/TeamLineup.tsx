import type { TeamDetail } from "@/lib/api";
import { PlayerCard } from "./PlayerCard";
import { StarterLineupPanel } from "./StarterLineupPanel";

type TeamLineupProps = {
  team: TeamDetail;
  lineupOnly?: boolean;
};

export function TeamLineup({ team, lineupOnly = false }: TeamLineupProps) {
  return (
    <div className="space-y-8">
      {!lineupOnly ? (
        <StarterLineupPanel starters={team.starters} leagueId={team.league_id} />
      ) : null}

      {team.bench.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm uppercase tracking-wider text-bb-muted">Bench</h2>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {team.bench.map((player) => (
              <PlayerCard key={player.player_id} player={player} />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
