"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import {
  getRookieDraft,
  type RookieBoardRow,
  type RookieDraftTimelineRow,
  type RookieDraftView,
  type StarterNeeds,
} from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { RookieBadge } from "./RookieBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PlayerName } from "./PlayerName";
import { PositionPill, PositionTag } from "./PositionPill";

type RookieDraftPanelProps = {
  leagueId: string;
  initial: RookieDraftView;
};

const NEED_LABELS: (keyof StarterNeeds)[] = ["QB", "RB", "WR", "TE", "FLEX"];

function targetsKey(leagueId: string, draftId: string) {
  return `bb-rookie-targets:${leagueId}:${draftId}`;
}

function loadTargets(leagueId: string, draftId: string): Set<string> {
  if (typeof window === "undefined") return new Set();
  try {
    const raw = localStorage.getItem(targetsKey(leagueId, draftId));
    if (!raw) return new Set();
    return new Set(JSON.parse(raw) as string[]);
  } catch {
    return new Set();
  }
}

function saveTargets(leagueId: string, draftId: string, ids: Set<string>) {
  localStorage.setItem(targetsKey(leagueId, draftId), JSON.stringify([...ids]));
}

function ScrollPanel({
  title,
  subtitle,
  headerRight,
  maxHeightClass = "max-h-[min(50dvh,28rem)]",
  children,
}: {
  title: string;
  subtitle?: string;
  headerRight?: ReactNode;
  maxHeightClass?: string;
  children: ReactNode;
}) {
  return (
    <section className="bb-panel min-w-0 overflow-hidden">
      <div className="bb-panel-header">
        <div className="min-w-0 flex-1">
          <h2 className="bb-panel-title">{title}</h2>
          {subtitle ? (
            <p className="mt-0.5 line-clamp-2 text-xs text-bb-muted">{subtitle}</p>
          ) : null}
        </div>
        {headerRight ? <div className="shrink-0">{headerRight}</div> : null}
      </div>
      <div className={`overflow-y-auto overscroll-contain ${maxHeightClass}`}>
        {children}
      </div>
    </section>
  );
}

function BoardSortToggle({
  boardSort,
  onChange,
}: {
  boardSort: "bpa" | "ovr";
  onChange: (sort: "bpa" | "ovr") => void;
}) {
  return (
    <div className="flex rounded-lg border border-bb-border/50 p-0.5 text-xs">
      <button
        type="button"
        onClick={() => onChange("bpa")}
        className={`rounded-md px-2.5 py-1 ${
          boardSort === "bpa"
            ? "bg-white/10 text-white"
            : "text-bb-muted hover:text-white"
        }`}
      >
        BPA
      </button>
      <button
        type="button"
        onClick={() => onChange("ovr")}
        className={`rounded-md px-2.5 py-1 ${
          boardSort === "ovr"
            ? "bg-white/10 text-white"
            : "text-bb-muted hover:text-white"
        }`}
      >
        OVR
      </button>
    </div>
  );
}

function SidebarPanels({
  draft,
  targetRows,
}: {
  draft: RookieDraftView;
  targetRows: RookieBoardRow[];
}) {
  return (
    <>
      <section className="rounded-xl border border-bb-border/50 bg-black/20 p-4">
        <h3 className="text-sm font-medium text-white">Positional needs</h3>
        <p className="mb-3 text-xs text-bb-muted">
          {draft.drafting_team_name ?? "My team"} · open starter slots
        </p>
        <NeedsStrip needs={draft.starter_needs} />
      </section>

      {targetRows.length > 0 ? (
        <section className="rounded-xl border border-bb-gold/30 bg-bb-gold/5 p-4">
          <h3 className="text-sm font-medium text-bb-gold">My targets</h3>
          <ul className="mt-2 space-y-2">
            {targetRows.map((row) => (
              <li
                key={row.player_id}
                className="flex items-center justify-between gap-2 text-sm"
              >
                <span className="min-w-0 truncate text-white">
                  <PlayerName>{row.player_name}</PlayerName>{" "}
                  <span className="text-bb-muted">({row.position})</span>
                </span>
                <OvrBadge ovr={row.ovr} size="sm" expected={row.hppg_expected} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {draft.bpa_top.length > 0 ? (
        <section className="rounded-xl border border-bb-border/50 bg-black/20 p-4">
          <h3 className="text-sm font-medium text-white">BPA top 5</h3>
          <ol className="mt-2 space-y-1.5 text-sm">
            {draft.bpa_top.slice(0, 5).map((row) => (
              <li key={row.player_id} className="flex justify-between gap-2">
                <span className="truncate">
                  {row.bpa_rank}. <PlayerName as="span">{row.player_name}</PlayerName>
                </span>
                <OvrBadge ovr={row.ovr} size="sm" expected={row.hppg_expected} />
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      {draft.strategy_notes.length > 0 ? (
        <section className="rounded-xl border border-bb-border/50 bg-black/20 p-4">
          <h3 className="text-sm font-medium text-white">Notes</h3>
          <ul className="mt-2 list-disc space-y-1 pl-4 text-xs text-bb-muted">
            {draft.strategy_notes.map((note) => (
              <li key={note}>{note}</li>
            ))}
          </ul>
        </section>
      ) : null}
    </>
  );
}

function NeedsStrip({ needs }: { needs: StarterNeeds }) {
  return (
    <div className="flex flex-wrap gap-2">
      {NEED_LABELS.map((pos) => {
        const n = needs[pos];
        const hot = n > 0;
        return (
          <span
            key={pos}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              hot
                ? "bg-amber-500/15 text-amber-300 ring-1 ring-amber-500/30"
                : "bg-white/5 text-bb-muted"
            }`}
          >
            {pos} {hot ? `+${n}` : "✓"}
          </span>
        );
      })}
    </div>
  );
}

function TimelineRow({ row }: { row: RookieDraftTimelineRow }) {
  const isProjected = row.status === "projected";
  const statusClass =
    row.status === "on_clock"
      ? "bg-bb-gold/15 ring-1 ring-bb-gold/40"
      : isProjected
        ? "opacity-80 italic"
        : row.is_me
          ? "bg-blue-500/10"
          : row.status === "done"
            ? ""
            : "opacity-70";

  return (
    <tr className={`border-b border-bb-border/30 ${statusClass}`}>
      <td className="whitespace-nowrap px-2 py-2 text-xs text-bb-muted">
        #{row.pick_no}
        {row.status === "on_clock" ? (
          <span className="ml-1 text-bb-gold">●</span>
        ) : null}
      </td>
      <td className="px-2 py-2 text-xs text-bb-muted">{row.round ?? "—"}</td>
      <td className="max-w-32 truncate px-2 py-2 text-xs text-white">
        {row.team_name ?? "—"}
      </td>
      <td className="px-2 py-2 text-sm text-white">
        {row.player_name ? (
          <span className="inline-flex items-center gap-1">
            <PlayerName>{row.player_name}</PlayerName>
            {row.dynasty_rookie ? <RookieBadge /> : null}
            {isProjected ? (
              <span className="text-[10px] not-italic text-bb-muted">proj</span>
            ) : null}
          </span>
        ) : row.status === "on_clock" ? (
          <span className="text-bb-gold">On the clock</span>
        ) : (
          <span className="text-bb-muted">—</span>
        )}
      </td>
      <td className="px-2 py-2 text-xs">
        {row.position ? <PositionTag position={row.position} /> : null}
      </td>
      <td className="px-2 py-2 text-right">
        {row.ovr != null ? <OvrBadge ovr={row.ovr} size="sm" /> : "—"}
      </td>
    </tr>
  );
}

function boardDisplayRank(row: RookieBoardRow, sort: "bpa" | "ovr"): number {
  return sort === "ovr" ? (row.ovr_rank ?? row.bpa_rank) : row.bpa_rank;
}

function BoardRowMobile({
  leagueId,
  row,
  rank,
  isTarget,
  onToggleTarget,
}: {
  leagueId: string;
  row: RookieBoardRow;
  rank: number;
  isTarget: boolean;
  onToggleTarget: (playerId: string) => void;
}) {
  return (
    <div
      className={`grid grid-cols-[auto_auto_minmax(0,1fr)_auto] items-center gap-x-2 px-3 py-2.5 ${
        isTarget ? "bg-bb-gold/10" : ""
      }`}
    >
      <button
        type="button"
        onClick={() => onToggleTarget(row.player_id)}
        className={`shrink-0 text-base leading-none ${isTarget ? "text-bb-gold" : "text-bb-muted"}`}
        title={isTarget ? "Remove target" : "Add target"}
      >
        {isTarget ? "★" : "☆"}
      </button>
      <span className="w-5 text-center text-xs tabular-nums text-bb-muted">{rank}</span>
      <div className="flex min-w-0 items-center gap-2">
        <PlayerHeadshot
          src={row.headshot_url}
          alt={row.player_name ?? "Player"}
          position={row.position}
          className="h-8 w-8 shrink-0"
          sizes="32px"
        />
        <div className="min-w-0">
          <Link
            href={`/players/${row.player_id}?league_id=${encodeURIComponent(leagueId)}`}
            className="block truncate text-sm hover:text-bb-gold"
          >
            <PlayerName>{row.player_name}</PlayerName>
          </Link>
          <div className="mt-0.5 flex items-center gap-1.5">
            {row.position ? <PositionTag position={row.position} /> : null}
            {row.dynasty_rookie ? <RookieBadge /> : null}
            <span className="truncate text-[10px] text-bb-muted">
              {[row.nfl_team, row.age != null ? String(row.age) : null]
                .filter(Boolean)
                .join(" · ")}
            </span>
          </div>
        </div>
      </div>
      <div className="flex flex-col items-end gap-0.5">
        <OvrBadge ovr={row.ovr} size="sm" expected={row.hppg_expected} />
        <span className="text-[10px] tabular-nums text-bb-muted">
          {formatPpg(row.projected_ppg ?? row.hppg)}
        </span>
      </div>
    </div>
  );
}

function TimelineRowMobile({ row }: { row: RookieDraftTimelineRow }) {
  const isProjected = row.status === "projected";
  const statusClass =
    row.status === "on_clock"
      ? "border-bb-gold/40 bg-bb-gold/10"
      : isProjected
        ? "border-bb-border/30 border-dashed bg-black/10 opacity-80"
        : row.is_me
          ? "border-blue-500/30 bg-blue-500/10"
          : "border-bb-border/30 bg-black/15";

  return (
    <div className={`rounded-lg border px-2.5 py-2 ${statusClass}`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-[11px] text-bb-muted">
          #{row.pick_no}
          {row.round != null ? ` · R${row.round}` : ""}
          {row.status === "on_clock" ? (
            <span className="ml-1 text-bb-gold">● clock</span>
          ) : isProjected ? (
            <span className="ml-1 not-italic text-bb-muted">proj</span>
          ) : null}
        </p>
        {row.ovr != null ? <OvrBadge ovr={row.ovr} size="sm" /> : null}
      </div>
      <p className="mt-0.5 truncate text-xs font-medium text-white">
        {row.team_name ?? "—"}
      </p>
      <p className="mt-0.5 truncate text-sm text-white">
        {row.player_name ? (
          <span className="inline-flex items-center gap-1.5">
            <PlayerName>{row.player_name}</PlayerName>
            {row.position ? <PositionTag position={row.position} /> : null}
          </span>
        ) : row.status === "on_clock" ? (
          <span className="text-bb-gold">On the clock</span>
        ) : (
          <span className="text-bb-muted">—</span>
        )}
      </p>
    </div>
  );
}

function BoardRow({
  leagueId,
  row,
  rank,
  isTarget,
  onToggleTarget,
}: {
  leagueId: string;
  row: RookieBoardRow;
  rank: number;
  isTarget: boolean;
  onToggleTarget: (playerId: string) => void;
}) {
  return (
    <tr
      className={`border-b border-bb-border/30 transition hover:bg-white/3 ${
        isTarget ? "bg-bb-gold/10 ring-1 ring-inset ring-bb-gold/25" : ""
      }`}
    >
      <td className="px-2 py-2 text-xs text-bb-muted">{rank}</td>
      <td className="px-2 py-2">
        <button
          type="button"
          onClick={() => onToggleTarget(row.player_id)}
          className={`text-sm ${isTarget ? "text-bb-gold" : "text-bb-muted hover:text-bb-gold"}`}
          title={isTarget ? "Remove target" : "Add target"}
        >
          {isTarget ? "★" : "☆"}
        </button>
      </td>
      <td className="px-2 py-2">
        <div className="flex items-center gap-2">
          <PlayerHeadshot
            src={row.headshot_url}
            alt={row.player_name ?? "Player"}
            position={row.position}
            className="h-8 w-8"
            sizes="32px"
          />
          <div className="min-w-0">
            <Link
              href={`/players/${row.player_id}?league_id=${encodeURIComponent(leagueId)}`}
              className="flex items-center gap-1 truncate hover:text-bb-gold"
            >
              <PlayerName>{row.player_name}</PlayerName>
              {row.dynasty_rookie ? <RookieBadge /> : null}
            </Link>
            <div className="flex flex-wrap items-center gap-1.5">
              {row.position ? <PositionTag position={row.position} /> : null}
              <span className="text-[10px] text-bb-muted">
                {[row.nfl_team, row.age != null ? String(row.age) : null]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            </div>
          </div>
        </div>
      </td>
      <td className="px-2 py-2 text-right">
        <OvrBadge
          ovr={row.ovr}
          size="sm"
          expected={row.hppg_expected}
        />
      </td>
      <td className="px-2 py-2 text-right text-xs text-white">
        {formatPpg(row.projected_ppg ?? row.hppg)}
        {row.hppg_expected ? (
          <span className="text-bb-muted">e</span>
        ) : null}
      </td>
      <td className="px-2 py-2 text-right text-xs text-bb-muted">
        {formatTv(row.trade_value)}
      </td>
      <td className="px-2 py-2 text-right text-xs text-bb-muted">
        {row.adp_pick ?? "—"}
        {row.adp_delta != null && row.adp_delta !== 0 ? (
          <span
            className={
              row.adp_delta > 0 ? " text-emerald-400" : " text-red-400/80"
            }
          >
            {" "}
            ({row.adp_delta > 0 ? "+" : ""}
            {row.adp_delta})
          </span>
        ) : null}
      </td>
    </tr>
  );
}

export function RookieDraftPanel({ leagueId, initial }: RookieDraftPanelProps) {
  const [draft, setDraft] = useState(initial);
  const [boardSort, setBoardSort] = useState<"bpa" | "ovr">("ovr");
  const [targets, setTargets] = useState<Set<string>>(() =>
    loadTargets(leagueId, initial.draft_id),
  );
  const [polling, setPolling] = useState(true);
  const [lastError, setLastError] = useState<string | null>(null);
  const refreshInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshInFlight.current) return;
    refreshInFlight.current = true;
    try {
      const next = await getRookieDraft(leagueId, { draftId: draft.draft_id });
      setDraft(next);
      setLastError(null);
    } catch {
      setLastError("Failed to refresh draft state — is the API running? (just bb-api)");
    } finally {
      refreshInFlight.current = false;
    }
  }, [leagueId, draft.draft_id]);

  useEffect(() => {
    if (!polling) return;
    const ms = Math.max(10, draft.poll_seconds) * 1000;
    const id = window.setInterval(() => void refresh(), ms);
    return () => window.clearInterval(id);
  }, [polling, draft.poll_seconds, refresh]);

  const toggleTarget = (playerId: string) => {
    setTargets((prev) => {
      const next = new Set(prev);
      if (next.has(playerId)) next.delete(playerId);
      else next.add(playerId);
      saveTargets(leagueId, draft.draft_id, next);
      return next;
    });
  };

  const targetRows = useMemo(
    () => draft.board.filter((r) => targets.has(r.player_id)),
    [draft.board, targets],
  );

  const sortedBoard = useMemo(() => {
    if (boardSort === "ovr") return draft.board;
    return [...draft.board].sort((a, b) => a.bpa_rank - b.bpa_rank);
  }, [draft.board, boardSort]);

  const clockLabel = draft.is_my_pick
    ? "You're on the clock"
    : draft.on_clock.team_name
      ? `${draft.on_clock.team_name} on the clock`
      : "Waiting for next pick";

  return (
    <div className="flex flex-col gap-5 px-3 py-4 sm:gap-6 sm:p-8">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-white sm:text-2xl">Rookie Draft</h1>
          <p className="mt-1 text-xs text-bb-muted sm:text-sm">
            <span className="block truncate sm:inline">{draft.league_name}</span>
            <span className="hidden sm:inline"> · </span>
            <span className="block sm:inline">
              {draft.picks_made}/{draft.total_picks} picks · {draft.adp_source ?? "ADP"}
            </span>
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 self-end sm:self-auto">
          <button
            type="button"
            onClick={() => void refresh()}
            className="rounded-lg border border-bb-border/60 px-3 py-1.5 text-xs text-bb-muted hover:text-white"
          >
            Refresh
          </button>
          <label className="flex items-center gap-2 text-xs text-bb-muted">
            <input
              type="checkbox"
              checked={polling}
              onChange={(e) => setPolling(e.target.checked)}
              className="rounded"
            />
            Auto ({draft.poll_seconds}s)
          </label>
        </div>
      </div>

      {lastError ? (
        <p className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-sm text-red-300">
          {lastError}
        </p>
      ) : null}

      <div
        className={`rounded-xl border px-4 py-3 ${
          draft.is_my_pick
            ? "border-bb-gold/50 bg-bb-gold/10"
            : "border-bb-border/50 bg-black/20"
        }`}
      >
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-white">{clockLabel}</p>
            <p className="text-xs text-bb-muted">
              Pick #{draft.next_pick_no ?? "—"}
              {draft.next_pick_info.picks_until_mine != null &&
              !draft.is_my_pick
                ? ` · your pick in ${draft.next_pick_info.picks_until_mine}`
                : null}
              {draft.next_pick_info.back_to_back
                ? " · back-to-back picks"
                : null}
            </p>
          </div>
          <div className="text-right text-xs text-bb-muted">
            Updated {new Date(draft.fetched_at).toLocaleTimeString()}
          </div>
        </div>
      </div>

      <div className="flex flex-col gap-5 xl:grid xl:grid-cols-[1fr_320px] xl:gap-6">
        <div className="flex min-w-0 flex-col gap-5">
          <ScrollPanel
            title="Mock draft"
            subtitle="Real team order · unpicked slots show projected picks"
            maxHeightClass="max-h-[min(45dvh,26rem)] sm:max-h-[min(50dvh,28rem)]"
          >
            <div className="space-y-1.5 p-2 md:hidden">
              {draft.timeline.map((row) => (
                <TimelineRowMobile key={row.pick_no} row={row} />
              ))}
            </div>
            <div className="hidden md:block">
              <table className="w-full text-left">
                <thead className="sticky top-0 z-10 bg-[#121820]">
                  <tr className="border-b border-bb-border/50 text-[10px] uppercase tracking-wider text-bb-muted">
                    <th className="px-2 py-2">Pick</th>
                    <th className="px-2 py-2">Rd</th>
                    <th className="px-2 py-2">Team</th>
                    <th className="px-2 py-2">Player</th>
                    <th className="px-2 py-2">Pos</th>
                    <th className="px-2 py-2 text-right">OVR</th>
                  </tr>
                </thead>
                <tbody>
                  {draft.timeline.map((row) => (
                    <TimelineRow key={row.pick_no} row={row} />
                  ))}
                </tbody>
              </table>
            </div>
          </ScrollPanel>

          <ScrollPanel
            title="Available rookies"
            subtitle={`${draft.board.length} on board · ☆ = my target`}
            maxHeightClass="max-h-[min(55dvh,32rem)] sm:max-h-[min(60dvh,36rem)]"
            headerRight={
              <BoardSortToggle boardSort={boardSort} onChange={setBoardSort} />
            }
          >
            <div className="divide-y divide-bb-border/30 md:hidden">
              {sortedBoard.map((row) => (
                <BoardRowMobile
                  key={row.player_id}
                  leagueId={leagueId}
                  row={row}
                  rank={boardDisplayRank(row, boardSort)}
                  isTarget={targets.has(row.player_id)}
                  onToggleTarget={toggleTarget}
                />
              ))}
            </div>
            <div className="hidden overflow-x-auto md:block">
              <table className="w-full min-w-[640px] text-left">
                <thead className="sticky top-0 z-10 bg-[#121820]">
                  <tr className="border-b border-bb-border/50 text-[10px] uppercase tracking-wider text-bb-muted">
                    <th className="px-2 py-2">#</th>
                    <th className="px-2 py-2">☆</th>
                    <th className="px-2 py-2">Player</th>
                    <th className="px-2 py-2 text-right">OVR</th>
                    <th className="px-2 py-2 text-right">Proj</th>
                    <th className="px-2 py-2 text-right">TV</th>
                    <th className="px-2 py-2 text-right">ADP</th>
                  </tr>
                </thead>
                <tbody>
                  {sortedBoard.map((row) => (
                    <BoardRow
                      key={row.player_id}
                      leagueId={leagueId}
                      row={row}
                      rank={boardDisplayRank(row, boardSort)}
                      isTarget={targets.has(row.player_id)}
                      onToggleTarget={toggleTarget}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          </ScrollPanel>
        </div>

        <aside className="flex flex-col gap-4">
          <SidebarPanels draft={draft} targetRows={targetRows} />
        </aside>
      </div>
    </div>
  );
}
