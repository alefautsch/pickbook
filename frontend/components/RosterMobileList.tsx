"use client";

import Link from "next/link";
import { useState } from "react";
import type { LineupSlot, PlayerCard } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import {
  formatActvGames,
  formatDecimal,
  formatPpg,
  formatTv,
  formatWorpPpg,
} from "@/lib/format";
import { formatSlotLabel, slotColor } from "@/lib/positions";
import type { RatingMode } from "./TeamPageContent";
import { ExpendabilityBadge } from "./ExpendabilityBadge";
import { OvrBadge } from "./OvrBadge";
import { RookieBadge } from "./RookieBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PlayerName } from "./PlayerName";
import { PositionTag } from "./PositionPill";

type RosterMobileListProps = {
  starters?: LineupSlot[];
  players?: PlayerCard[];
  bench?: PlayerCard[];
  slotLabels?: Record<string, string>;
  full?: boolean;
  ratingMode?: RatingMode;
};

function displayOvr(player: PlayerCard, ratingMode: RatingMode) {
  return ratingMode === "win_now"
    ? (player.lenses.win_now_rating ?? player.ovr)
    : player.ovr;
}

function MobileSectionHeader({ label }: { label: string }) {
  return (
    <div className="bg-white/3 px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest text-bb-muted">
      {label}
    </div>
  );
}

function MobileStat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md bg-black/20 px-2 py-1.5">
      <p className="text-[9px] uppercase tracking-wide text-bb-muted">{label}</p>
      <p className="mt-0.5 text-sm font-semibold tabular-nums text-white">{value}</p>
    </div>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-4 w-4 transition-transform ${expanded ? "rotate-180" : ""}`}
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
        clipRule="evenodd"
      />
    </svg>
  );
}

function MobilePlayerRow({
  player,
  slot,
  full,
  ratingMode,
  expanded,
  onToggle,
}: {
  player: PlayerCard;
  slot: string;
  full: boolean;
  ratingMode: RatingMode;
  expanded: boolean;
  onToggle: () => void;
}) {
  const ovr = displayOvr(player, ratingMode);
  const metaParts = [player.nfl_team, player.age != null ? String(player.age) : null].filter(
    Boolean,
  );
  const accent = slotColor(slot);

  return (
    <div className="border-b border-bb-border/25">
      <div className="flex w-full items-center gap-1 px-1 py-1">
        <Link
          href={`/players/${player.player_id}?league_id=${player.league_id}`}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-lg px-1 py-1.5 transition hover:bg-white/4 active:bg-white/6"
        >
          <div
            className="w-1 shrink-0 self-stretch rounded-full"
            style={{ backgroundColor: accent }}
            title={formatSlotLabel(slot)}
          />
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className="h-9 w-9 shrink-0 rounded-full"
            sizes="36px"
          />
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5">
              <PlayerName as="p">{player.player_name}</PlayerName>
              {player.dynasty_rookie ? <RookieBadge /> : null}
            </div>
            <div className="mt-0.5 flex flex-wrap items-center gap-1">
              {player.position ? <PositionTag position={player.position} /> : null}
              {metaParts.length > 0 ? (
                <span className="text-[11px] text-bb-muted">{metaParts.join(" · ")}</span>
              ) : null}
              <ExpendabilityBadge
                tag={player.trade_tag}
                lineupDelta={player.lineup_delta_ppg}
              />
            </div>
          </div>
          <div className="flex shrink-0 items-center gap-2 pr-1">
            <div className="text-center">
              <p className="text-[9px] uppercase tracking-wide text-bb-muted">OVR</p>
              <div className="mt-0.5 flex justify-center">
                <OvrBadge ovr={ovr} expected={player.hppg_expected} size="sm" />
              </div>
            </div>
            <div className="w-11 text-center">
              <p className="text-[9px] uppercase tracking-wide text-bb-muted">PPG</p>
              <p className="mt-0.5 text-sm font-semibold tabular-nums text-white">
                {formatPpg(player.projected_ppg)}
              </p>
            </div>
          </div>
        </Link>
        {full ? (
          <button
            type="button"
            onClick={onToggle}
            className="shrink-0 rounded-lg p-2 text-bb-muted transition hover:bg-white/5 hover:text-white"
            aria-expanded={expanded}
            aria-label={expanded ? "Hide extra stats" : "Show extra stats"}
          >
            <ChevronIcon expanded={expanded} />
          </button>
        ) : null}
      </div>

      {expanded ? (
        <div className="space-y-2 border-t border-bb-border/20 bg-black/15 px-3 py-2.5">
          <div className="grid grid-cols-3 gap-1.5">
            <MobileStat label="W/G" value={formatWorpPpg(player.worp_ppg)} />
            <MobileStat label="Trade Value" value={formatTv(player.trade_value)} />
            {full ? (
              <MobileStat
                label="ACTV"
                value={formatActvGames(
                  player.healthy_games,
                  player.total_games,
                  player.availability,
                )}
              />
            ) : (
              <MobileStat label="HPPG" value={formatPpg(player.hppg)} />
            )}
          </div>
          {full ? (
            <div className="grid grid-cols-3 gap-1.5">
              <MobileStat label="HPPG" value={formatPpg(player.hppg)} />
              <MobileStat label="WORP" value={formatDecimal(player.season_worp, 2)} />
              <MobileStat
                label="FLEX"
                value={player.lenses.flex_rating != null ? String(player.lenses.flex_rating) : "—"}
              />
            </div>
          ) : null}
          {full ? (
            <div className="grid grid-cols-3 gap-1.5">
              <MobileStat
                label="PORP"
                value={player.porp != null ? String(Math.round(player.porp)) : "—"}
              />
              <MobileStat label="Slot" value={formatSlotLabel(slot)} />
              <MobileStat
                label="Proj"
                value={
                  player.projection_source
                    ? projectionSourceLabel(player.projection_source)
                    : "—"
                }
              />
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

function MobileEmptyRow({ slot }: { slot: string }) {
  return (
    <div
      className="flex items-center gap-2 border-b border-bb-border/25 px-2 py-2.5 text-sm text-bb-muted"
      style={{ borderLeftWidth: 4, borderLeftColor: slotColor(slot) }}
    >
      Empty {formatSlotLabel(slot)} slot
    </div>
  );
}

export function RosterMobileList({
  starters,
  players,
  bench,
  slotLabels,
  full = false,
  ratingMode = "dynasty",
}: RosterMobileListProps) {
  const [expandedKey, setExpandedKey] = useState<string | null>(null);
  const starterSlots = starters ?? [];
  const benchPlayers = bench ?? [];
  const flatPlayers = players ?? [];
  const hasStarterSection = starters != null;

  function toggle(key: string) {
    setExpandedKey((current) => (current === key ? null : key));
  }

  return (
    <div className="md:hidden">
      <div className="grid grid-cols-[1fr_3.5rem_2.75rem] gap-2 border-b border-bb-border/50 px-2 py-1.5 text-[10px] font-medium uppercase tracking-wide text-bb-muted">
        <span className="pl-12">Player</span>
        <span className="text-center">OVR</span>
        <span className="text-center">PPG</span>
      </div>

      {hasStarterSection ? (
        <>
          <MobileSectionHeader label="Starters" />
          {starterSlots.map((slot, index) => {
            const key = `starter-${slot.slot}-${slot.player?.player_id ?? "empty"}-${index}`;
            if (!slot.player) {
              return <MobileEmptyRow key={key} slot={slot.slot} />;
            }
            return (
              <MobilePlayerRow
                key={key}
                player={slot.player}
                slot={slot.slot}
                full={full}
                ratingMode={ratingMode}
                expanded={expandedKey === key}
                onToggle={() => toggle(key)}
              />
            );
          })}
          {benchPlayers.length > 0 ? (
            <>
              <MobileSectionHeader label="Bench" />
              {benchPlayers.map((player) => {
                const key = `bench-${player.player_id}`;
                return (
                  <MobilePlayerRow
                    key={key}
                    player={player}
                    slot="BN"
                    full={full}
                    ratingMode={ratingMode}
                    expanded={expandedKey === key}
                    onToggle={() => toggle(key)}
                  />
                );
              })}
            </>
          ) : null}
        </>
      ) : bench != null ? (
        <>
          <MobileSectionHeader label="Bench" />
          {benchPlayers.map((player) => {
            const key = `bench-${player.player_id}`;
            return (
              <MobilePlayerRow
                key={key}
                player={player}
                slot="BN"
                full={full}
                ratingMode={ratingMode}
                expanded={expandedKey === key}
                onToggle={() => toggle(key)}
              />
            );
          })}
        </>
      ) : (
        flatPlayers.map((player) => {
          const key = `${player.player_id}-${slotLabels?.[player.player_id] ?? "row"}`;
          return (
            <MobilePlayerRow
              key={key}
              player={player}
              slot={slotLabels?.[player.player_id] ?? player.position ?? "BN"}
              full={full}
              ratingMode={ratingMode}
              expanded={expandedKey === key}
              onToggle={() => toggle(key)}
            />
          );
        })
      )}
    </div>
  );
}
