"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  evaluateTrade,
  getLeague,
  getLeaguePlayers,
  getTeam,
  validateTrade,
  type DraftPickAsset,
  type LeagueDetail,
  type LeaguePlayerRow,
  type TradeEvaluateRequest,
  type TradeEvaluation,
  type TradePickRef,
  type TradeValidationResult,
} from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { matchesPositionFilter } from "@/lib/positions";
import { AnimatedTradeValue } from "@/components/AnimatedTradeValue";
import { DarkMenu, DarkSelect } from "@/components/DarkSelect";
import { OvrBadge } from "@/components/OvrBadge";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { PlayerName } from "@/components/PlayerName";
import { PositionPill, PositionTag } from "@/components/PositionPill";

const ROSTER_POSITIONS = ["ALL", "QB", "RB", "WR", "TE", "FLEX"] as const;

type TradeCalculatorProps = {
  leagueId: string;
  defaultSideA?: string;
  defaultSideB?: string;
};

type SideAssets = {
  players: string[];
  picks: TradePickRef[];
};

function pickKey(pick: TradePickRef): string {
  return `${pick.season}-${pick.round}-${pick.original_roster_id}`;
}

function gradeColor(grade: string | null | undefined): string {
  if (!grade) return "text-bb-muted";
  if (grade.startsWith("A")) return "text-emerald-400";
  if (grade.startsWith("B")) return "text-bb-gold";
  if (grade.startsWith("C")) return "text-amber-400";
  if (grade === "D" || grade === "F") return "text-rose-400";
  return "text-bb-muted";
}

function fairnessLabel(
  evaluation: TradeEvaluation,
  sideAName: string,
  sideBName: string,
  sideARosterId: string,
  sideBRosterId: string,
): string {
  if (evaluation.fairness === "fair") return "Fair trade";
  if (evaluation.favors_roster_id === sideARosterId) return `Favors ${sideAName}`;
  if (evaluation.favors_roster_id === sideBRosterId) return `Favors ${sideBName}`;
  if (evaluation.fairness === "favors_counterparty") return `Favors ${sideBName}`;
  if (evaluation.fairness === "favors_you") return `Favors ${sideAName}`;
  return "Fair trade";
}

function buildRequest(
  sideARosterId: string,
  sideBRosterId: string,
  sideA: SideAssets,
  sideB: SideAssets,
): TradeEvaluateRequest {
  return {
    side_a_roster_id: sideARosterId,
    side_b_roster_id: sideBRosterId,
    side_a_gives: { players: sideA.players, picks: sideA.picks },
    side_b_gives: { players: sideB.players, picks: sideB.picks },
  };
}

function sumRawTv(
  assets: SideAssets,
  playerById: Map<string, LeaguePlayerRow>,
  pickPool: DraftPickAsset[],
): number {
  let total = 0;
  for (const id of assets.players) {
    total += playerById.get(id)?.trade_value ?? 0;
  }
  for (const pick of assets.picks) {
    const row = pickPool.find(
      (p) =>
        p.season === pick.season &&
        p.round === pick.round &&
        p.original_roster_id === pick.original_roster_id,
    );
    total += row?.trade_value ?? 0;
  }
  return total;
}

export function TradeCalculator({
  leagueId,
  defaultSideA,
  defaultSideB,
}: TradeCalculatorProps) {
  const [league, setLeague] = useState<LeagueDetail | null>(null);
  const [players, setPlayers] = useState<LeaguePlayerRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [sideARosterId, setSideARosterId] = useState(defaultSideA ?? "");
  const [sideBRosterId, setSideBRosterId] = useState(defaultSideB ?? "");
  const [sideA, setSideA] = useState<SideAssets>({ players: [], picks: [] });
  const [sideB, setSideB] = useState<SideAssets>({ players: [], picks: [] });
  const [sideAPicks, setSideAPicks] = useState<DraftPickAsset[]>([]);
  const [sideBPicks, setSideBPicks] = useState<DraftPickAsset[]>([]);
  const [evaluation, setEvaluation] = useState<TradeEvaluation | null>(null);
  const [validation, setValidation] = useState<TradeValidationResult | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [validateLoading, setValidateLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    void Promise.all([getLeague(leagueId), getLeaguePlayers(leagueId)])
      .then(([leagueDetail, directory]) => {
        setLeague(leagueDetail);
        setPlayers(directory.players);

        const teams = leagueDetail.teams;
        const sorted = [...teams].sort((a, b) =>
          (a.team_name ?? a.roster_id).localeCompare(b.team_name ?? b.roster_id),
        );

        if (defaultSideA) {
          setSideARosterId(defaultSideA);
        } else if (sorted[0]) {
          setSideARosterId(sorted[0].roster_id);
        }

        if (defaultSideB) {
          setSideBRosterId(defaultSideB);
        } else {
          const aId = defaultSideA ?? sorted[0]?.roster_id;
          const other = sorted.find((t) => t.roster_id !== aId) ?? sorted[1];
          if (other) setSideBRosterId(other.roster_id);
        }
      })
      .catch(() => setError("Could not load league data"))
      .finally(() => setLoading(false));
  }, [leagueId, defaultSideA, defaultSideB]);

  useEffect(() => {
    if (!sideARosterId) return;
    void getTeam(leagueId, sideARosterId)
      .then((team) => setSideAPicks(team.draft_picks))
      .catch(() => setSideAPicks([]));
  }, [leagueId, sideARosterId]);

  useEffect(() => {
    if (!sideBRosterId) return;
    void getTeam(leagueId, sideBRosterId)
      .then((team) => setSideBPicks(team.draft_picks))
      .catch(() => setSideBPicks([]));
  }, [leagueId, sideBRosterId]);

  const playerById = useMemo(() => {
    const map = new Map<string, LeaguePlayerRow>();
    for (const row of players) map.set(row.player_id, row);
    return map;
  }, [players]);

  const sideAName =
    league?.teams.find((t) => t.roster_id === sideARosterId)?.team_name ?? "Side A";
  const sideBName =
    league?.teams.find((t) => t.roster_id === sideBRosterId)?.team_name ?? "Side B";
  const sameTeam = Boolean(
    sideARosterId && sideBRosterId && sideARosterId === sideBRosterId,
  );
  const hasAssets =
    sideA.players.length + sideA.picks.length + sideB.players.length + sideB.picks.length > 0;

  const runEvaluate = useCallback(async () => {
    if (!sideARosterId || !sideBRosterId || sameTeam) return;
    if (!hasAssets) {
      setEvaluation(null);
      setValidation(null);
      return;
    }
    setEvalLoading(true);
    setError(null);
    try {
      const result = await evaluateTrade(
        leagueId,
        buildRequest(sideARosterId, sideBRosterId, sideA, sideB),
      );
      setEvaluation(result.evaluation);
      setValidation(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Evaluation failed");
    } finally {
      setEvalLoading(false);
    }
  }, [leagueId, sideA, sideB, sideARosterId, sideBRosterId, sameTeam, hasAssets]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void runEvaluate();
    }, 300);
    return () => window.clearTimeout(timer);
  }, [runEvaluate]);

  async function handleValidate() {
    if (!sideARosterId || !sideBRosterId || sameTeam) return;
    setValidateLoading(true);
    setError(null);
    try {
      const result = await validateTrade(
        leagueId,
        buildRequest(sideARosterId, sideBRosterId, sideA, sideB),
      );
      setEvaluation(result.evaluation);
      setValidation(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : "AI validation failed");
    } finally {
      setValidateLoading(false);
    }
  }

  function handleRosterChange(side: "a" | "b", rosterId: string) {
    if (side === "a") {
      setSideARosterId(rosterId);
      setSideA({ players: [], picks: [] });
    } else {
      setSideBRosterId(rosterId);
      setSideB({ players: [], picks: [] });
    }
    setValidation(null);
  }

  function swapSides() {
    setSideARosterId(sideBRosterId);
    setSideBRosterId(sideARosterId);
    setSideA(sideB);
    setSideB(sideA);
    setValidation(null);
  }

  function addPlayer(side: "a" | "b", playerId: string) {
    const setter = side === "a" ? setSideA : setSideB;
    setter((prev) => {
      if (prev.players.includes(playerId)) return prev;
      return { ...prev, players: [...prev.players, playerId] };
    });
  }

  function removePlayer(side: "a" | "b", playerId: string) {
    const setter = side === "a" ? setSideA : setSideB;
    setter((prev) => ({
      ...prev,
      players: prev.players.filter((id) => id !== playerId),
    }));
    setValidation(null);
  }

  function addPick(side: "a" | "b", pick: DraftPickAsset) {
    const ref: TradePickRef = {
      season: pick.season,
      round: pick.round,
      original_roster_id: pick.original_roster_id,
    };
    const setter = side === "a" ? setSideA : setSideB;
    setter((prev) => {
      if (prev.picks.some((p) => pickKey(p) === pickKey(ref))) return prev;
      return { ...prev, picks: [...prev.picks, ref] };
    });
    setValidation(null);
  }

  function removePick(side: "a" | "b", key: string) {
    const setter = side === "a" ? setSideA : setSideB;
    setter((prev) => ({
      ...prev,
      picks: prev.picks.filter((p) => pickKey(p) !== key),
    }));
    setValidation(null);
  }

  const adjustedA = evaluation?.give_adjusted_tv ?? sumRawTv(sideA, playerById, sideAPicks);
  const adjustedB =
    evaluation?.receive_adjusted_tv ?? sumRawTv(sideB, playerById, sideBPicks);
  const totalAdjusted = adjustedA + adjustedB;
  const barA = totalAdjusted > 0 ? (adjustedA / totalAdjusted) * 100 : 50;
  const barB = totalAdjusted > 0 ? (adjustedB / totalAdjusted) * 100 : 50;

  if (loading) {
    return (
      <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-3 py-6 sm:px-6">
        <div className="h-8 w-48 animate-pulse rounded-lg bg-white/5" />
        <div className="h-4 w-72 animate-pulse rounded bg-white/5" />
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="bb-card h-80 animate-pulse bg-white/3" />
          <div className="bb-card h-80 animate-pulse bg-white/3" />
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex w-full max-w-6xl flex-col gap-4 px-3 py-4 sm:px-6 sm:py-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white sm:text-2xl">Trade Calculator</h1>
          <p className="mt-1 text-sm text-bb-muted">
            KTC-blended values · stud adjustments · consolidation tax · depth discount
          </p>
          <p className="mt-1 max-w-xl text-xs text-bb-muted">
            Pick any two teams — yours does not need to be in the deal. Left column is what
            that team gives; AI grades whether each manager would accept.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void handleValidate()}
          disabled={validateLoading || !evaluation || !hasAssets || sameTeam}
          className="rounded-lg bg-bb-gold px-4 py-2.5 text-sm font-semibold text-black transition hover:bg-bb-gold/90 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {validateLoading ? "Evaluating…" : "AI Grade Both Sides"}
        </button>
      </div>

      {sameTeam ? (
        <p className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-200">
          Select two different teams to build a trade.
        </p>
      ) : null}

      {error ? (
        <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-300">
          {error}
        </p>
      ) : null}

      <div className="grid gap-3 lg:grid-cols-[1fr_auto_1fr] lg:items-start">
        <TradeSideColumn
          accent="gold"
          teamName={sideAName}
          rosterId={sideARosterId}
          teams={league?.teams ?? []}
          superflex={league?.superflex ?? false}
          rosterPlayers={players}
          onRosterChange={(id) => handleRosterChange("a", id)}
          playerIds={sideA.players}
          picks={sideA.picks}
          availablePicks={sideAPicks}
          playerById={playerById}
          sideTotal={evaluation?.give_adjusted_tv ?? sumRawTv(sideA, playerById, sideAPicks)}
          onAddPlayer={(id) => addPlayer("a", id)}
          onRemovePlayer={(id) => removePlayer("a", id)}
          onAddPick={(pick) => addPick("a", pick)}
          onRemovePick={(key) => removePick("a", key)}
        />

        <div className="hidden flex-col items-center justify-center gap-2 lg:flex lg:pt-16">
          <button
            type="button"
            onClick={swapSides}
            title="Swap sides"
            className="flex h-10 w-10 items-center justify-center rounded-full border border-bb-border/60 bg-black/30 text-lg text-bb-muted transition hover:border-bb-gold/50 hover:text-bb-gold"
          >
            ⇄
          </button>
          {evaluation && !sameTeam ? (
            <div className="text-center">
              <p
                className={`text-2xl font-bold tabular-nums ${gradeColor(evaluation.tv_fairness_grade)}`}
              >
                {evaluation.tv_fairness_grade}
              </p>
              <p className="text-[10px] uppercase tracking-wider text-bb-muted">TV grade</p>
            </div>
          ) : null}
        </div>

        <TradeSideColumn
          accent="sky"
          teamName={sideBName}
          rosterId={sideBRosterId}
          teams={league?.teams ?? []}
          superflex={league?.superflex ?? false}
          rosterPlayers={players}
          onRosterChange={(id) => handleRosterChange("b", id)}
          playerIds={sideB.players}
          picks={sideB.picks}
          availablePicks={sideBPicks}
          playerById={playerById}
          sideTotal={evaluation?.receive_adjusted_tv ?? sumRawTv(sideB, playerById, sideBPicks)}
          onAddPlayer={(id) => addPlayer("b", id)}
          onRemovePlayer={(id) => removePlayer("b", id)}
          onAddPick={(pick) => addPick("b", pick)}
          onRemovePick={(key) => removePick("b", key)}
        />
      </div>

      <button
        type="button"
        onClick={swapSides}
        className="rounded-lg border border-bb-border/60 py-2 text-sm text-bb-muted transition hover:border-bb-gold/40 hover:text-white lg:hidden"
      >
        ⇄ Swap sides
      </button>

      <section className="bb-card p-4 sm:p-5">
        <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-sm font-semibold uppercase tracking-wide text-bb-muted">
            Value Comparison
          </h2>
          <div className="flex items-center gap-3">
            {evalLoading ? (
              <span className="text-xs text-bb-muted">Calculating…</span>
            ) : evaluation ? (
              <span
                className={`text-sm font-semibold lg:hidden ${gradeColor(evaluation.tv_fairness_grade)}`}
              >
                TV Grade {evaluation.tv_fairness_grade}
              </span>
            ) : null}
            {evaluation?.within_band ? (
              <span className="rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-xs font-medium text-emerald-400">
                Within band
              </span>
            ) : null}
          </div>
        </div>

        {evaluation && !sameTeam ? (
          <>
            <div className="mb-4 grid gap-3 sm:grid-cols-2">
              <ValueBlock
                teamName={sideAName}
                raw={evaluation.give_total_tv}
                adjustment={evaluation.give_value_adjustment}
                adjusted={evaluation.give_adjusted_tv}
                effective={evaluation.give_effective_tv}
                consolidating={evaluation.give_consolidating}
              />
              <ValueBlock
                teamName={sideBName}
                raw={evaluation.receive_total_tv}
                adjustment={evaluation.receive_value_adjustment}
                adjusted={evaluation.receive_adjusted_tv}
                effective={evaluation.receive_effective_tv}
                consolidating={evaluation.receive_consolidating}
              />
            </div>

            <div className="mb-4">
              <div className="mb-1.5 flex justify-between text-xs font-medium text-bb-muted">
                <span>
                  {sideAName}{" "}
                  <span className="text-bb-gold">{formatTv(adjustedA)}</span>
                </span>
                <span>
                  <span className="text-sky-400">{formatTv(adjustedB)}</span> {sideBName}
                </span>
              </div>
              <div className="flex h-2.5 overflow-hidden rounded-full bg-black/40">
                <div
                  className="bg-bb-gold/85 transition-all duration-300"
                  style={{ width: `${barA}%` }}
                />
                <div
                  className="bg-sky-500/80 transition-all duration-300"
                  style={{ width: `${barB}%` }}
                />
              </div>
            </div>

            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
              <Metric
                label="Adjusted delta"
                value={`${evaluation.net_delta_adjusted_pct >= 0 ? "+" : ""}${evaluation.net_delta_adjusted_pct.toFixed(1)}%`}
                highlight={
                  evaluation.within_band
                    ? "good"
                    : Math.abs(evaluation.net_delta_adjusted_pct) > 15
                      ? "bad"
                      : undefined
                }
              />
              <Metric label="After tax" value={formatTv(evaluation.net_delta_adjusted_total_tv)} />
              <Metric
                label="Consolidation tax"
                value={
                  evaluation.consolidation_tax_tv === 0
                    ? "None"
                    : `${evaluation.consolidation_tax_tv > 0 ? "+" : ""}${formatTv(evaluation.consolidation_tax_tv)}`
                }
              />
              <Metric
                label="Verdict"
                value={fairnessLabel(
                  evaluation,
                  sideAName,
                  sideBName,
                  sideARosterId,
                  sideBRosterId,
                )}
              />
            </div>

            {evaluation.lineup ? (
              <div className="mt-4 border-t border-white/6 pt-4">
                <h3 className="mb-3 text-xs font-semibold uppercase tracking-wide text-bb-muted">
                  Ideal Lineup After Trade
                </h3>
                <div className="grid gap-3 sm:grid-cols-2">
                  <LineupBlock
                    teamName={sideAName}
                    accent="gold"
                    side={evaluation.lineup.side_a}
                  />
                  <LineupBlock
                    teamName={sideBName}
                    accent="sky"
                    side={evaluation.lineup.side_b}
                  />
                </div>
              </div>
            ) : null}

            {evaluation.positional_notes.length > 0 ? (
              <ul className="mt-4 space-y-1 border-t border-white/6 pt-3 text-xs text-bb-muted">
                {evaluation.positional_notes.map((note) => (
                  <li key={note}>• {note}</li>
                ))}
              </ul>
            ) : null}

            {evaluation.missing_assets.length > 0 ? (
              <p className="mt-2 text-xs text-rose-400">
                Missing assets: {evaluation.missing_assets.join(", ")}
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-sm text-bb-muted">
            Add players or picks to evaluate a trade package.
          </p>
        )}
      </section>

      {validation ? (
        <section className="bb-card p-4 sm:p-5">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-bb-muted">
              AI Evaluation
            </h2>
            <span className={`text-xl font-bold ${gradeColor(validation.overall_grade)}`}>
              Overall {validation.overall_grade}
            </span>
          </div>
          {validation.summary ? (
            <p className="mb-4 rounded-lg bg-black/20 px-3 py-2.5 text-sm leading-relaxed text-white/90">
              {validation.summary}
            </p>
          ) : null}
          <div className="grid gap-4 md:grid-cols-2">
            <ValidationCard
              label={sideAName}
              otherTeamName={sideBName}
              validation={validation.side_a}
            />
            <ValidationCard
              label={sideBName}
              otherTeamName={sideAName}
              validation={validation.side_b}
            />
          </div>
        </section>
      ) : null}
    </div>
  );
}

type TradeSideColumnProps = {
  accent: "gold" | "sky";
  teamName: string;
  rosterId: string;
  teams: { roster_id: string; team_name: string | null; is_me: boolean }[];
  superflex: boolean;
  rosterPlayers: LeaguePlayerRow[];
  onRosterChange: (id: string) => void;
  playerIds: string[];
  picks: TradePickRef[];
  availablePicks: DraftPickAsset[];
  playerById: Map<string, LeaguePlayerRow>;
  sideTotal: number;
  onAddPlayer: (id: string) => void;
  onRemovePlayer: (id: string) => void;
  onAddPick: (pick: DraftPickAsset) => void;
  onRemovePick: (key: string) => void;
};

function TradeSideColumn({
  accent,
  teamName,
  rosterId,
  teams,
  superflex,
  rosterPlayers,
  onRosterChange,
  playerIds,
  picks,
  availablePicks,
  playerById,
  sideTotal,
  onAddPlayer,
  onRemovePlayer,
  onAddPick,
  onRemovePick,
}: TradeSideColumnProps) {
  const [search, setSearch] = useState("");
  const [positionFilter, setPositionFilter] = useState<string>("ALL");

  const positions = superflex
    ? ([...ROSTER_POSITIONS, "SUPER_FLEX"] as const)
    : ROSTER_POSITIONS;

  useEffect(() => {
    setSearch("");
    setPositionFilter("ALL");
  }, [rosterId]);

  const accentBorder = accent === "gold" ? "border-bb-gold/30" : "border-sky-500/30";
  const accentText = accent === "gold" ? "text-bb-gold" : "text-sky-400";
  const accentTotal =
    accent === "gold"
      ? "bg-bb-gold/10 ring-bb-gold/30"
      : "bg-sky-500/10 ring-sky-500/30";
  const accentPillActive =
    accent === "gold"
      ? "bg-bb-gold/20 text-bb-gold"
      : "bg-sky-500/20 text-sky-300";
  const selectedIds = new Set(playerIds);
  const selectedPickKeys = new Set(picks.map(pickKey));
  const unusedPicks = availablePicks.filter(
    (p) =>
      !selectedPickKeys.has(
        pickKey({
          season: p.season,
          round: p.round,
          original_roster_id: p.original_roster_id,
        }),
      ),
  );

  const browsePlayers = useMemo(() => {
    const q = search.trim().toLowerCase();
    return rosterPlayers
      .filter((p) => p.roster_id === rosterId)
      .filter((p) => !selectedIds.has(p.player_id))
      .filter((p) => matchesPositionFilter(p.position, positionFilter, superflex))
      .filter((p) => {
        if (!q) return true;
        const haystack = [p.player_name, p.position, p.nfl_team]
          .filter(Boolean)
          .join(" ")
          .toLowerCase();
        return haystack.includes(q);
      })
      .sort((a, b) => (b.trade_value ?? 0) - (a.trade_value ?? 0));
  }, [rosterPlayers, rosterId, selectedIds, positionFilter, superflex, search]);

  const positionLabel =
    positionFilter === "ALL"
      ? "players"
      : positionFilter === "SUPER_FLEX"
        ? "SF QBs"
        : `${positionFilter}s`;

  return (
    <section className={`bb-card flex flex-col border-t-2 p-4 ${accentBorder}`}>
      <div className="mb-3 space-y-3">
        <DarkSelect
          className="w-full"
          value={rosterId}
          onChange={onRosterChange}
          accent={accent}
          options={teams.map((team) => ({
            value: team.roster_id,
            label: team.team_name ?? team.roster_id,
          }))}
        />
        <div className={`rounded-xl px-3 py-2.5 ring-1 ring-inset ${accentTotal}`}>
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-bb-muted">
            Total Trade Value
          </p>
          <AnimatedTradeValue
            value={sideTotal}
            className={`mt-0.5 text-2xl font-black sm:text-3xl ${accentText}`}
          />
        </div>
      </div>
      <p className="mb-3 text-xs font-medium uppercase tracking-wide text-bb-muted">
        {teamName} gives
      </p>

      <ul className="mb-3 min-h-12 space-y-2">
        {playerIds.map((id) => {
          const player = playerById.get(id);
          return (
            <li
              key={id}
              className="flex items-center justify-between gap-2 rounded-lg bg-white/4 px-3 py-2 ring-1 ring-inset ring-white/[0.07]"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-1.5">
                  <PlayerName className="text-sm">{player?.player_name ?? id}</PlayerName>
                  {player?.position ? <PositionTag position={player.position} /> : null}
                </div>
                <p className="text-xs tabular-nums text-bb-muted">
                  {formatTv(player?.trade_value)} TV
                </p>
              </div>
              <button
                type="button"
                onClick={() => onRemovePlayer(id)}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-bb-muted transition hover:bg-white/10 hover:text-rose-400"
                aria-label="Remove player"
              >
                ×
              </button>
            </li>
          );
        })}
        {picks.map((pick) => {
          const avail = availablePicks.find(
            (p) =>
              p.season === pick.season &&
              p.round === pick.round &&
              p.original_roster_id === pick.original_roster_id,
          );
          return (
            <li
              key={pickKey(pick)}
              className="flex items-center justify-between gap-2 rounded-lg bg-white/4 px-3 py-2 ring-1 ring-inset ring-white/[0.07]"
            >
              <div className="min-w-0">
                <p className="text-sm font-medium text-white">
                  {avail?.label ?? `${pick.season} Rd ${pick.round}`}
                </p>
                <p className="text-xs tabular-nums text-bb-muted">
                  {formatTv(avail?.trade_value)} TV
                </p>
              </div>
              <button
                type="button"
                onClick={() => onRemovePick(pickKey(pick))}
                className="flex h-6 w-6 shrink-0 items-center justify-center rounded text-bb-muted transition hover:bg-white/10 hover:text-rose-400"
                aria-label="Remove pick"
              >
                ×
              </button>
            </li>
          );
        })}
        {playerIds.length === 0 && picks.length === 0 ? (
          <li className="rounded-lg border border-dashed border-bb-border/40 px-3 py-4 text-center text-xs text-bb-muted">
            Click players below to add
          </li>
        ) : null}
      </ul>

      <div className="mb-2">
        <input
          type="search"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Filter roster…"
          className="w-full rounded-lg border border-bb-border/60 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-bb-muted focus:border-bb-gold/40 focus:outline-none"
        />
      </div>

      <div className="mb-2 flex flex-wrap gap-1">
        {positions.map((pos) => (
          <button
            key={pos}
            type="button"
            onClick={() => setPositionFilter(pos)}
            className={`rounded-full px-2.5 py-0.5 text-[11px] font-medium transition ${
              positionFilter === pos
                ? accentPillActive
                : "bg-bb-border/40 text-bb-muted hover:text-white"
            }`}
          >
            {pos === "ALL" ? "All" : pos.replace("_", " ")}
          </button>
        ))}
      </div>

      <p className="mb-1.5 text-[10px] uppercase tracking-wider text-bb-muted">
        {browsePlayers.length} {positionLabel}
      </p>

      <div className="-mx-1 mb-3 max-h-64 overflow-y-auto rounded-lg border border-bb-border/40 bg-black/20">
        {browsePlayers.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-bb-muted">
            {search.trim()
              ? "No matches — try another filter"
              : `No ${positionLabel} available`}
          </p>
        ) : (
          <ul className="divide-y divide-white/5">
            {browsePlayers.map((player) => (
              <li key={player.player_id}>
                <button
                  type="button"
                  onClick={() => onAddPlayer(player.player_id)}
                  className="flex w-full items-center gap-2 px-2 py-2 text-left transition hover:bg-white/5"
                >
                  <PlayerHeadshot
                    src={player.headshot_url}
                    alt={player.player_name ?? "Player"}
                    position={player.position}
                    className="h-8 w-8 shrink-0 rounded-full"
                    sizes="32px"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <PlayerName className="truncate text-sm">{player.player_name}</PlayerName>
                      {player.position ? <PositionTag position={player.position} /> : null}
                    </div>
                    <p className="truncate text-[11px] text-bb-muted">
                      {[player.nfl_team, player.age != null ? `Age ${player.age}` : null]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-0.5">
                    <span className={`text-xs font-semibold tabular-nums ${accentText}`}>
                      {formatTv(player.trade_value)}
                    </span>
                    {player.ovr != null ? (
                      <span className="text-[10px] tabular-nums text-bb-muted">
                        OVR {player.ovr}
                      </span>
                    ) : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>

      {unusedPicks.length > 0 ? (
        <DarkMenu
          label="+ Add draft pick"
          accent={accent}
          options={unusedPicks.map((pick, idx) => ({
            value: String(idx),
            label: pick.label ?? `${pick.season} Rd ${pick.round}`,
            hint: formatTv(pick.trade_value),
          }))}
          onSelect={(idx) => {
            const pick = unusedPicks[Number(idx)];
            if (pick) onAddPick(pick);
          }}
        />
      ) : null}
    </section>
  );
}

function LineupBlock({
  teamName,
  accent,
  side,
}: {
  teamName: string;
  accent: "gold" | "sky";
  side: {
    before?: number | null;
    after?: number | null;
    delta?: number | null;
    starters?: {
      slot: string;
      player_id?: string | null;
      name?: string | null;
      position?: string | null;
      ppg?: number | null;
      ovr?: number | null;
      is_incoming?: boolean;
      is_changed?: boolean;
    }[];
    incoming_picks?: {
      label?: string | null;
      season: string;
      round: number;
      trade_value?: number | null;
    }[];
  };
}) {
  const accentText = accent === "gold" ? "text-bb-gold" : "text-sky-400";
  const accentBg = accent === "gold" ? "bg-bb-gold/10" : "bg-sky-500/10";
  const accentRing = accent === "gold" ? "ring-bb-gold/30" : "ring-sky-500/30";
  const delta = side.delta;
  const deltaClass =
    delta == null
      ? "text-bb-muted"
      : delta > 0
        ? "text-emerald-400"
        : delta < 0
          ? "text-rose-400"
          : "text-bb-muted";
  const starters = side.starters ?? [];
  const incomingPicks = side.incoming_picks ?? [];

  return (
    <div className="rounded-lg bg-black/20 px-3 py-3 ring-1 ring-inset ring-white/6">
      <div className="mb-3 flex items-end justify-between gap-2">
        <p className="text-xs font-medium text-bb-muted">{teamName}</p>
        <div className="text-right">
          <p className="text-[10px] uppercase tracking-wider text-bb-muted">
            Lineup PPG{" "}
            <span className={`font-semibold ${deltaClass}`}>
              {delta == null ? "" : `${delta >= 0 ? "+" : ""}${delta.toFixed(1)}`}
            </span>
          </p>
          <p className="text-sm tabular-nums text-white">
            {formatPpg(side.before)} →{" "}
            <span className={accentText}>{formatPpg(side.after)}</span>
          </p>
        </div>
      </div>

      <ul className="space-y-1.5">
        {starters.map((slot) => {
          return (
            <li
              key={`${slot.slot}-${slot.player_id}`}
              className={`flex items-center gap-2 rounded-lg px-2 py-1.5 ${
                slot.is_incoming
                  ? `${accentBg} ring-1 ring-inset ${accentRing}`
                  : slot.is_changed
                    ? "bg-white/5 ring-1 ring-inset ring-white/10"
                    : ""
              }`}
            >
              <PositionPill slot={slot.slot} className="shrink-0" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-1.5">
                  <PlayerName className="truncate text-sm">
                    {slot.name ?? "Empty"}
                  </PlayerName>
                  {slot.position ? <PositionTag position={slot.position} /> : null}
                  {slot.is_incoming ? (
                    <span
                      className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-bold uppercase tracking-wide ${accentText} ${accentBg}`}
                    >
                      New
                    </span>
                  ) : slot.is_changed ? (
                    <span className="shrink-0 rounded bg-white/10 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-bb-muted">
                      Changed
                    </span>
                  ) : null}
                </div>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                {slot.ovr != null ? <OvrBadge ovr={slot.ovr} size="sm" /> : null}
                <span className="text-xs font-medium tabular-nums text-bb-muted">
                  {formatPpg(slot.ppg)}
                </span>
              </div>
            </li>
          );
        })}
        {starters.length === 0 ? (
          <li className="py-2 text-center text-xs text-bb-muted">No starter data</li>
        ) : null}
      </ul>

      {incomingPicks.length > 0 ? (
        <div className="mt-3 border-t border-white/6 pt-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-bb-muted">
            Incoming picks
          </p>
          <ul className="space-y-1">
            {incomingPicks.map((pick) => (
              <li
                key={`${pick.season}-${pick.round}-${pick.label}`}
                className={`flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 ${accentBg} ring-1 ring-inset ${accentRing}`}
              >
                <span className="text-sm font-medium text-white">
                  {pick.label ?? `${pick.season} Rd ${pick.round}`}
                </span>
                <span className={`text-xs font-semibold tabular-nums ${accentText}`}>
                  {formatTv(pick.trade_value)}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}

function ValueBlock({
  teamName,
  raw,
  adjustment,
  adjusted,
  effective,
  consolidating,
}: {
  teamName: string;
  raw: number;
  adjustment: number;
  adjusted: number;
  effective: number;
  consolidating: boolean;
}) {
  return (
    <div className="rounded-xl bg-black/25 px-4 py-3 ring-1 ring-inset ring-white/8">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-medium text-bb-muted">{teamName}</p>
          <p className="mt-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-bb-muted">
            Total Adjusted TV
          </p>
        </div>
        <AnimatedTradeValue
          value={adjusted}
          className="text-2xl font-black text-white sm:text-3xl"
        />
      </div>
      <dl className="mt-2 space-y-1 text-xs text-bb-muted">
        <div className="flex justify-between gap-2">
          <dt>Raw TV</dt>
          <dd className="tabular-nums text-white/80">{formatTv(raw)}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Stud adj.</dt>
          <dd
            className={`tabular-nums ${adjustment >= 0 ? "text-emerald-400" : "text-rose-400"}`}
          >
            {adjustment >= 0 ? "+" : ""}
            {formatTv(adjustment)}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt>Effective</dt>
          <dd className="tabular-nums text-white/80">{formatTv(effective)}</dd>
        </div>
        {consolidating ? (
          <div className="pt-0.5 text-bb-gold">Consolidating side (+tax)</div>
        ) : null}
      </dl>
    </div>
  );
}

function Metric({
  label,
  value,
  highlight,
}: {
  label: string;
  value: string;
  highlight?: "good" | "bad";
}) {
  const valueClass =
    highlight === "good"
      ? "text-emerald-400"
      : highlight === "bad"
        ? "text-rose-400"
        : "text-white";
  return (
    <div className="rounded-lg bg-black/20 px-3 py-2 ring-1 ring-inset ring-white/5">
      <p className="text-xs text-bb-muted">{label}</p>
      <p className={`text-sm font-medium ${valueClass}`}>{value}</p>
    </div>
  );
}

function validationFairnessLabel(
  validation: TradeValidationResult["side_a"],
  teamName: string,
  otherTeamName: string,
): string {
  if (validation.fairness_label) return validation.fairness_label;
  const view = validation.fairness_view;
  if (!view || view === "fair") return "Fair";
  // favors_them = favors the team being graded (card title); favors_you = the other side
  if (view === "favors_them") return `Favors ${teamName}`;
  return `Favors ${otherTeamName}`;
}

function ValidationCard({
  label,
  otherTeamName,
  validation,
}: {
  label: string;
  otherTeamName: string;
  validation: TradeValidationResult["side_a"];
}) {
  if (validation.skipped) {
    return (
      <div className="rounded-lg border border-bb-border/40 bg-black/20 p-4">
        <p className="font-medium text-white">{label}</p>
        <p className="mt-1.5 text-sm text-bb-muted">
          {validation.error ?? "AI validation unavailable — add Anthropic API key in settings."}
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-bb-border/40 bg-black/20 p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="font-medium text-white">{label}</p>
        <span className={`text-xl font-bold ${gradeColor(validation.grade)}`}>
          {validation.grade ?? "—"}
        </span>
      </div>
      <p className="text-[11px] text-bb-muted">Would {label} accept this offer?</p>
      <p className="mt-1 text-[11px] uppercase tracking-wide text-bb-muted">
        Accept: {validation.accept_likelihood ?? "—"} · Fairness:{" "}
        {validationFairnessLabel(validation, label, otherTeamName)}
        {validation.would_improve_roster ? " · Improves roster" : ""}
      </p>
      {validation.reasoning ? (
        <p className="mt-2.5 text-sm leading-relaxed text-white/85">{validation.reasoning}</p>
      ) : null}
      {validation.blockers.length > 0 ? (
        <ul className="mt-2.5 space-y-1 text-xs text-rose-300">
          {validation.blockers.map((b) => (
            <li key={b}>• {b}</li>
          ))}
        </ul>
      ) : null}
      {validation.suggested_tweak ? (
        <p className="mt-2.5 text-xs text-bb-gold">Tweak: {validation.suggested_tweak}</p>
      ) : null}
    </div>
  );
}
