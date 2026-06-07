import Link from "next/link";
import type { PlayerCard } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import { formatDecimal, formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";

type RosterTableProps = {
  players: PlayerCard[];
  slotLabels?: Record<string, string>;
};

export function RosterTable({ players, slotLabels }: RosterTableProps) {
  if (players.length === 0) return null;

  return (
    <div className="bb-card overflow-x-auto">
      <table className="w-full min-w-[640px] text-left text-sm">
        <thead>
          <tr className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
            {slotLabels ? <th className="px-4 py-3 font-medium">Slot</th> : null}
            <th className="px-4 py-3 font-medium">Player</th>
            <th className="px-4 py-3 font-medium">OVR</th>
            <th className="px-4 py-3 font-medium">HPPG</th>
            <th className="px-4 py-3 font-medium">Proj PPG</th>
            <th className="px-4 py-3 font-medium">W/g</th>
            <th className="px-4 py-3 font-medium">TV</th>
          </tr>
        </thead>
        <tbody>
          {players.map((player) => (
            <tr
              key={`${player.player_id}-${slotLabels?.[player.player_id] ?? "row"}`}
              className="border-b border-bb-border/30 hover:bg-white/5"
            >
              {slotLabels ? (
                <td className="px-4 py-3 text-xs font-semibold uppercase text-bb-gold">
                  {slotLabels[player.player_id] ?? "—"}
                </td>
              ) : null}
              <td className="px-4 py-3">
                <Link
                  href={`/players/${player.player_id}?league_id=${player.league_id}`}
                  className="font-medium text-white hover:text-bb-gold"
                >
                  {player.player_name}
                </Link>
                <span className="ml-2 text-xs text-bb-muted">
                  {player.position}
                  {player.nfl_team ? ` · ${player.nfl_team}` : ""}
                </span>
              </td>
              <td className="px-4 py-3">
                <OvrBadge
                  ovr={player.ovr}
                  expected={player.hppg_expected}
                  size="sm"
                />
              </td>
              <td className="px-4 py-3 text-white">
                {formatPpg(player.hppg)}
                {player.hppg_expected ? (
                  <span className="ml-0.5 text-bb-gold">e</span>
                ) : null}
              </td>
              <td className="px-4 py-3">
                <span className="font-medium text-white">
                  {formatPpg(player.projected_ppg)}
                </span>
                {player.projection_source ? (
                  <p className="text-xs text-bb-muted">
                    {projectionSourceLabel(player.projection_source)}
                  </p>
                ) : null}
              </td>
              <td className="px-4 py-3 text-white">
                {formatDecimal(player.worp_ppg, 3)}
              </td>
              <td className="px-4 py-3 text-white">{formatTv(player.trade_value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
