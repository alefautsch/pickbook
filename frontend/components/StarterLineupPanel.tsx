import Link from "next/link";
import type { LineupSlot } from "@/lib/api";
import { formatPpg, formatWorpPpg } from "@/lib/format";
import { formatSlotLabel } from "@/lib/positions";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionPill } from "./PositionPill";

type StarterLineupPanelProps = {
  starters: LineupSlot[];
  leagueId: string;
};

function playerMeta(player: NonNullable<LineupSlot["player"]>): string {
  const parts = [player.position, player.nfl_team].filter(Boolean);
  return parts.join(" · ");
}

export function StarterLineupPanel({ starters, leagueId }: StarterLineupPanelProps) {
  const filled = starters.filter((s) => s.player);
  const totalProj = filled.reduce(
    (sum, s) => sum + (s.player?.projected_ppg ?? 0),
    0,
  );

  return (
    <section className="bb-card overflow-hidden">
      <div className="flex items-center justify-between border-b border-bb-border/50 px-4 py-3">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-white">
            Starters
          </h2>
          <p className="mt-0.5 text-xs text-bb-muted">
            Optimal lineup by projected PPG
          </p>
        </div>
        <p className="text-xs text-bb-muted">
          Proj Σ{" "}
          <span className="font-semibold tabular-nums text-white">
            {formatPpg(totalProj)}
          </span>
        </p>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b border-bb-border/30 text-[10px] uppercase tracking-wide text-bb-muted">
              <th className="w-14 px-3 py-2 text-center font-medium" />
              <th className="px-3 py-2 text-left font-medium">Player</th>
              <th className="hidden w-16 px-3 py-2 text-center font-medium sm:table-cell">
                OVR
              </th>
              <th className="hidden w-28 px-3 py-2 text-center font-medium sm:table-cell">
                Proj PPG
              </th>
              <th className="hidden w-16 px-3 py-2 text-center font-medium sm:table-cell">
                W/g
              </th>
            </tr>
          </thead>
          <tbody>
            {starters.map((slot, index) => {
              const player = slot.player;

              return (
                <tr
                  key={`${slot.slot}-${index}`}
                  className="border-b border-bb-border/20 last:border-0"
                >
                  <td className="relative w-14 p-0 align-middle">
                    <PositionPill slot={slot.slot} fill />
                  </td>
                  <td className="px-3 py-2.5 align-middle">
                    {player ? (
                      <Link
                        href={`/players/${player.player_id}?league_id=${leagueId}`}
                        className="flex items-center gap-3 hover:opacity-90"
                      >
                        <PlayerHeadshot
                          src={player.headshot_url}
                          alt={player.player_name ?? "Player"}
                          position={player.position}
                          className="h-10 w-10 shrink-0 rounded-full"
                          sizes="40px"
                        />
                        <div className="min-w-0">
                          <p className="truncate font-medium text-white">
                            {player.player_name}
                          </p>
                          <p className="text-xs text-bb-muted">{playerMeta(player)}</p>
                        </div>
                      </Link>
                    ) : (
                      <span className="text-sm text-bb-muted">
                        Empty {formatSlotLabel(slot.slot)} slot
                      </span>
                    )}
                  </td>
                  {player ? (
                    <>
                      <td className="hidden px-3 py-2.5 align-middle sm:table-cell">
                        <div className="flex justify-center">
                          <OvrBadge
                            ovr={player.ovr}
                            expected={player.hppg_expected}
                            size="sm"
                          />
                        </div>
                      </td>
                      <td
                        className="hidden px-3 py-2.5 text-center align-middle sm:table-cell"
                        title={`HPPG ${formatPpg(player.hppg)}`}
                      >
                        <span className="text-xl font-semibold tabular-nums text-white">
                          {formatPpg(player.projected_ppg)}
                        </span>
                        <p className="text-[10px] text-bb-muted">
                          HPPG {formatPpg(player.hppg)}
                          {player.hppg_expected ? (
                            <span className="ml-0.5 text-bb-gold">e</span>
                          ) : null}
                        </p>
                      </td>
                      <td className="hidden px-3 py-2.5 text-center align-middle sm:table-cell">
                        <span className="tabular-nums text-white/80">
                          {formatWorpPpg(player.worp_ppg)}
                        </span>
                      </td>
                    </>
                  ) : (
                    <td
                      colSpan={3}
                      className="hidden px-3 py-2.5 sm:table-cell"
                    />
                  )}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
