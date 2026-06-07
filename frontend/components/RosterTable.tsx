import Link from "next/link";
import type { PlayerCard } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import {
  formatActvGames,
  formatDecimal,
  formatPpg,
  formatTv,
  formatWorpPpg,
} from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionPill } from "./PositionPill";

type RosterTableProps = {
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

function StatRow({
  player,
  slot,
  full,
  statsOnly,
}: {
  player: PlayerCard;
  slot: string;
  full: boolean;
  statsOnly: boolean;
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
        <td className="px-3 py-2.5 text-white">{player.age ?? "—"}</td>
      ) : null}
      <td className="px-3 py-2.5">
        <OvrBadge ovr={player.ovr} expected={player.hppg_expected} size="sm" />
      </td>
      <td className="px-3 py-2.5 text-white">
        {formatPpg(player.hppg)}
        {player.hppg_expected ? (
          <span className="ml-0.5 text-bb-gold">e</span>
        ) : null}
      </td>
      {!statsOnly ? (
        <td className="px-3 py-2.5">
          <span className="font-medium text-white">
            {formatPpg(player.projected_ppg)}
          </span>
          {player.projection_source ? (
            <p className="text-xs text-bb-muted">
              {projectionSourceLabel(player.projection_source)}
            </p>
          ) : null}
        </td>
      ) : null}
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

export function RosterTable({
  players,
  bench,
  slotLabels,
  full = false,
  statsOnly = false,
}: RosterTableProps) {
  const benchPlayers = bench ?? [];
  const flatPlayers = players ?? [];

  if (bench != null) {
    if (benchPlayers.length === 0) {
      return (
        <div className="bb-card px-4 py-8 text-center text-sm text-bb-muted">
          No bench players
        </div>
      );
    }
  } else if (flatPlayers.length === 0) {
    return null;
  }

  const colSpan = full ? (statsOnly ? 11 : 12) : statsOnly ? 6 : 7;

  return (
    <div className="bb-card overflow-x-auto">
      <table className="w-full min-w-[960px] text-left text-sm">
        <thead>
          <tr className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
            <th className="w-14 px-3 py-3 text-center font-medium">Pos</th>
            <th className="px-3 py-3 font-medium">Player</th>
            {full ? <th className="px-3 py-3 font-medium">Age</th> : null}
            <th className="px-3 py-3 font-medium">OVR</th>
            <th className="px-3 py-3 font-medium">HPPG</th>
            {!statsOnly ? (
              <th className="px-3 py-3 font-medium">Proj PPG</th>
            ) : null}
            <th className="px-3 py-3 font-medium">W/g</th>
            {full ? <th className="px-3 py-3 font-medium">ACTV</th> : null}
            <th className="px-3 py-3 font-medium">TV</th>
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
          {bench != null ? (
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
                  statsOnly={statsOnly}
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
                statsOnly={statsOnly}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
