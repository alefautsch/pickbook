import Link from "next/link";
import type { LineupSlot, PlayerCard } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import {
  formatActvGames,
  formatDecimal,
  formatPpg,
  formatTv,
  formatWorpPpg,
} from "@/lib/format";
import { formatSlotLabel } from "@/lib/positions";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionPill } from "./PositionPill";

type RosterTableProps = {
  starters?: LineupSlot[];
  players?: PlayerCard[];
  bench?: PlayerCard[];
  slotLabels?: Record<string, string>;
  full?: boolean;
  statsOnly?: boolean;
};

function PlayerCell({ player }: { player: PlayerCard }) {
  return (
    <div className="flex items-center gap-2.5">
      <PlayerHeadshot
        src={player.headshot_url}
        alt={player.player_name ?? "Player"}
        position={player.position}
        className="h-8 w-8 shrink-0 rounded-full"
        sizes="32px"
      />
      <div className="min-w-0">
        <Link
          href={`/players/${player.player_id}?league_id=${player.league_id}`}
          className="block truncate font-medium text-white hover:text-bb-gold"
        >
          {player.player_name}
        </Link>
        <p className="truncate text-xs text-bb-muted">
          {player.position ?? "—"}
          {player.nfl_team ? ` · ${player.nfl_team}` : ""}
        </p>
      </div>
    </div>
  );
}

function ProjectionCell({ player }: { player: PlayerCard }) {
  const title = [
    player.projection_source ? projectionSourceLabel(player.projection_source) : null,
    player.hppg != null ? `HPPG ${formatPpg(player.hppg)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <td className="px-3 py-2.5" title={title}>
      <span className="text-lg font-semibold tabular-nums text-white">
        {formatPpg(player.projected_ppg)}
      </span>
      <p className="text-xs text-bb-muted">
        HPPG {formatPpg(player.hppg)}
        {player.hppg_expected ? <span className="ml-0.5 text-bb-gold">e</span> : null}
      </p>
    </td>
  );
}

function StatRow({
  player,
  slot,
  full,
}: {
  player: PlayerCard;
  slot: string;
  full: boolean;
}) {
  return (
    <tr className="border-b border-bb-border/30 hover:bg-white/5">
      <td className="relative w-14 p-0 align-middle">
        <PositionPill slot={slot} fill />
      </td>
      <td className="px-3 py-2.5">
        <PlayerCell player={player} />
      </td>
      {full ? (
        <>
          <td className="px-3 py-2.5 text-white">{player.nfl_team ?? "—"}</td>
          <td className="px-3 py-2.5 text-white">{player.age ?? "—"}</td>
        </>
      ) : null}
      <td className="px-3 py-2.5">
        <OvrBadge ovr={player.ovr} expected={player.hppg_expected} size="sm" />
      </td>
      <ProjectionCell player={player} />
      <td className="px-3 py-2.5 text-white">
        {formatWorpPpg(player.worp_ppg)}
      </td>
      {full ? (
        <td className="px-3 py-2.5 text-white">
          {formatActvGames(
            player.healthy_games,
            player.total_games,
            player.availability,
          )}
        </td>
      ) : null}
      <td className="px-3 py-2.5 text-white">{formatTv(player.trade_value)}</td>
      {full ? (
        <>
          <td className="px-3 py-2.5 text-white">
            {formatDecimal(player.season_worp, 2)}
          </td>
          <td className="px-3 py-2.5 text-white">
            {player.lenses.flex_rating ?? "—"}
          </td>
          <td className="px-3 py-2.5 text-white">
            {player.porp != null ? Math.round(player.porp) : "—"}
          </td>
        </>
      ) : null}
    </tr>
  );
}

function EmptyStatRow({
  slot,
  full,
}: {
  slot: string;
  full: boolean;
}) {
  return (
    <tr className="border-b border-bb-border/30">
      <td className="relative w-14 p-0 align-middle">
        <PositionPill slot={slot} fill />
      </td>
      <td className="px-3 py-2.5 text-bb-muted">
        Empty {formatSlotLabel(slot)} slot
      </td>
      {full ? (
        <>
          <td className="px-3 py-2.5 text-bb-muted">—</td>
          <td className="px-3 py-2.5 text-bb-muted">—</td>
        </>
      ) : null}
      <td className="px-3 py-2.5 text-bb-muted">—</td>
      <td className="px-3 py-2.5 text-bb-muted">—</td>
      <td className="px-3 py-2.5 text-bb-muted">—</td>
      {full ? <td className="px-3 py-2.5 text-bb-muted">—</td> : null}
      <td className="px-3 py-2.5 text-bb-muted">—</td>
      {full ? (
        <>
          <td className="px-3 py-2.5 text-bb-muted">—</td>
          <td className="px-3 py-2.5 text-bb-muted">—</td>
          <td className="px-3 py-2.5 text-bb-muted">—</td>
        </>
      ) : null}
    </tr>
  );
}

export function RosterTable({
  starters,
  players,
  bench,
  slotLabels,
  full = false,
}: RosterTableProps) {
  const starterSlots = starters ?? [];
  const benchPlayers = bench ?? [];
  const flatPlayers = players ?? [];
  const hasStarterSection = starters != null;

  if (bench != null && !hasStarterSection) {
    if (benchPlayers.length === 0) {
      return (
        <div className="bb-card px-4 py-8 text-center text-sm text-bb-muted">
          No bench players
        </div>
      );
    }
  } else if (!hasStarterSection && flatPlayers.length === 0) {
    return null;
  }

  const colSpan = full ? 12 : 6;

  return (
    <div className="bb-card overflow-x-auto">
      <table className="w-full min-w-[1040px] text-left text-sm">
        <thead>
          <tr className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
            <th className="w-14 px-3 py-3 text-center font-medium">Pos</th>
            <th className="px-3 py-3 font-medium">Player</th>
            {full ? (
              <>
                <th className="px-3 py-3 font-medium">Team</th>
                <th className="px-3 py-3 font-medium">Age</th>
              </>
            ) : null}
            <th className="px-3 py-3 font-medium">OVR</th>
            <th className="px-3 py-3 font-medium">Proj PPG</th>
            <th className="px-3 py-3 font-medium">W/G</th>
            {full ? <th className="px-3 py-3 font-medium">ACTV</th> : null}
            <th className="px-3 py-3 font-medium">Trade Value</th>
            {full ? (
              <>
                <th className="px-3 py-3 font-medium">WORP</th>
                <th className="px-3 py-3 font-medium">FLEX</th>
                <th className="px-3 py-3 font-medium">PORP</th>
              </>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {hasStarterSection ? (
            <>
              <tr className="bg-white/2">
                <td
                  colSpan={colSpan}
                  className="px-3 py-2 text-xs font-bold uppercase tracking-widest text-bb-muted"
                >
                  Roster
                </td>
              </tr>
              {starterSlots.map((slot, index) =>
                slot.player ? (
                  <StatRow
                    key={`starter-${slot.slot}-${slot.player.player_id}-${index}`}
                    player={slot.player}
                    slot={slot.slot}
                    full={full}
                  />
                ) : (
                  <EmptyStatRow
                    key={`starter-empty-${slot.slot}-${index}`}
                    slot={slot.slot}
                    full={full}
                  />
                ),
              )}
              {benchPlayers.length > 0 ? (
                <>
                  <tr className="bg-white/2">
                    <td
                      colSpan={colSpan}
                      className="px-3 py-2 text-xs font-bold uppercase tracking-widest text-bb-muted"
                    >
                      Bench
                    </td>
                  </tr>
                  {benchPlayers.map((player) => (
                    <StatRow
                      key={`bench-${player.player_id}`}
                      player={player}
                      slot="BN"
                      full={full}
                    />
                  ))}
                </>
              ) : null}
            </>
          ) : bench != null ? (
            <>
              <tr className="bg-white/2">
                <td
                  colSpan={colSpan}
                  className="px-3 py-2 text-xs font-bold uppercase tracking-widest text-bb-muted"
                >
                  Bench
                </td>
              </tr>
              {benchPlayers.map((player) => (
                <StatRow
                  key={`bench-${player.player_id}`}
                  player={player}
                  slot="BN"
                  full={full}
                />
              ))}
            </>
          ) : (
            flatPlayers.map((player) => (
              <StatRow
                key={`${player.player_id}-${slotLabels?.[player.player_id] ?? "row"}`}
                player={player}
                slot={slotLabels?.[player.player_id] ?? player.position ?? "BN"}
                full={full}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
