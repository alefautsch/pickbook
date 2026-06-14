import Link from "next/link";
import type { LineupSlot, PlayerCard } from "@/lib/api";
import type { RatingMode } from "./TeamPageContent";
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
import { RookieBadge } from "./RookieBadge";
import { ExpendabilityBadge } from "./ExpendabilityBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PositionPill, PositionTag } from "./PositionPill";
import { RosterMobileList } from "./RosterMobileList";

type RosterTableProps = {
  starters?: LineupSlot[];
  players?: PlayerCard[];
  bench?: PlayerCard[];
  slotLabels?: Record<string, string>;
  full?: boolean;
  ratingMode?: RatingMode;
};

function PlayerCell({ player }: { player: PlayerCard }) {
  const metaParts = [player.nfl_team, player.age != null ? String(player.age) : null].filter(
    Boolean,
  );

  return (
    <div className="flex items-center gap-2 md:gap-2.5">
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
          className="flex items-center gap-1.5 truncate font-medium text-white hover:text-bb-gold"
        >
          <span className="truncate">{player.player_name}</span>
          {player.dynasty_rookie ? <RookieBadge /> : null}
        </Link>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 md:hidden">
          {player.position ? <PositionTag position={player.position} /> : null}
          {metaParts.length > 0 ? (
            <span className="text-xs text-bb-muted">{metaParts.join(" · ")}</span>
          ) : null}
          <ExpendabilityBadge
            tag={player.trade_tag}
            lineupDelta={player.lineup_delta_ppg}
          />
        </div>
        <div className="mt-0.5 hidden flex-wrap items-center gap-1.5 md:flex">
          <p className="truncate text-xs text-bb-muted">
            {player.position ?? "—"}
            {player.nfl_team ? ` · ${player.nfl_team}` : ""}
          </p>
          <ExpendabilityBadge
            tag={player.trade_tag}
            lineupDelta={player.lineup_delta_ppg}
          />
        </div>
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
    <td className="px-2 py-2 md:px-3 md:py-2.5" title={title}>
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
  ratingMode = "dynasty",
}: {
  player: PlayerCard;
  slot: string;
  full: boolean;
  ratingMode?: RatingMode;
}) {
  const displayOvr =
    ratingMode === "win_now" ? (player.lenses.win_now_rating ?? player.ovr) : player.ovr;
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
          <td className="hidden px-3 py-2.5 text-white md:table-cell">
            {player.nfl_team ?? "—"}
          </td>
          <td className="hidden px-3 py-2.5 text-white md:table-cell">
            {player.age ?? "—"}
          </td>
        </>
      ) : null}
      <td className="px-2 py-2 md:px-3 md:py-2.5">
        <OvrBadge ovr={displayOvr} expected={player.hppg_expected} size="sm" />
      </td>
      <ProjectionCell player={player} />
      <td className="px-2 py-2 text-white md:px-3 md:py-2.5">
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
      <td className="px-2 py-2 text-white md:px-3 md:py-2.5">
        {formatTv(player.trade_value)}
      </td>
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
          <td className="hidden px-3 py-2.5 text-bb-muted md:table-cell">—</td>
          <td className="hidden px-3 py-2.5 text-bb-muted md:table-cell">—</td>
        </>
      ) : null}
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
  ratingMode = "dynasty",
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
    <div className="bb-card overflow-hidden md:overflow-x-auto">
      <RosterMobileList
        starters={starters}
        players={players}
        bench={bench}
        slotLabels={slotLabels}
        full={full}
        ratingMode={ratingMode}
      />
      <table className="hidden w-full min-w-[1040px] text-left text-sm md:table">
        <thead>
          <tr className="border-b border-bb-border/60 text-xs uppercase tracking-wide text-bb-muted">
            <th className="w-11 px-2 py-2.5 text-center font-medium md:w-14 md:px-3 md:py-3">
              Pos
            </th>
            <th className="px-2 py-2.5 font-medium md:px-3 md:py-3">Player</th>
            {full ? (
              <>
                <th className="hidden px-3 py-3 font-medium md:table-cell">Team</th>
                <th className="hidden px-3 py-3 font-medium md:table-cell">Age</th>
              </>
            ) : null}
            <th className="px-2 py-2.5 font-medium md:px-3 md:py-3">OVR</th>
            <th className="px-2 py-2.5 font-medium md:px-3 md:py-3">Proj PPG</th>
            <th className="px-2 py-2.5 font-medium md:px-3 md:py-3">W/G</th>
            {full ? <th className="px-3 py-3 font-medium">ACTV</th> : null}
            <th className="px-2 py-2.5 font-medium md:px-3 md:py-3">Trade Value</th>
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
                    ratingMode={ratingMode}
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
                      ratingMode={ratingMode}
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
                  ratingMode={ratingMode}
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
                ratingMode={ratingMode}
              />
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}
