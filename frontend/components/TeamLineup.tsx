import type { TeamDetail } from "@/lib/api";
import { PlayerCard } from "./PlayerCard";

type TeamLineupProps = {
  team: TeamDetail;
};

export function TeamLineup({ team }: TeamLineupProps) {
  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-3 text-sm uppercase tracking-wider text-bb-muted">
          Starters
        </h2>
        <div className="grid gap-3 lg:grid-cols-2">
          {team.starters.map((slot) => (
            <div key={`${slot.slot}-${slot.player?.player_id ?? "empty"}`}>
              <p className="mb-1 text-xs font-semibold uppercase text-bb-gold">
                {slot.slot}
              </p>
              {slot.player ? (
                <PlayerCard player={slot.player} />
              ) : (
                <div className="bb-card p-4 text-sm text-bb-muted">Empty slot</div>
              )}
            </div>
          ))}
        </div>
      </section>

      {team.bench.length > 0 ? (
        <section>
          <h2 className="mb-3 text-sm uppercase tracking-wider text-bb-muted">
            Bench
          </h2>
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
