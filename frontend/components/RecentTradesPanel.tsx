"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { postAnalyzeTrade, postAnalyzeTrades, type RecentTrade, type TradeActivityAnalysis, type TradeActivitySide, type TradeSideValidation } from "@/lib/api";

type RecentTradesPanelProps = {
  leagueId: string;
  trades: RecentTrade[];
  totalStored: number;
  unanalyzedCount: number;
};

function formatTradeDate(createdMs: number): string {
  return new Date(createdMs).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function likelihoodColor(likelihood: string | null | undefined): string {
  switch (likelihood) {
    case "high":
      return "text-emerald-400";
    case "low":
      return "text-red-400";
    default:
      return "text-amber-400";
  }
}

function gradeBadgeClass(grade: string | null | undefined): string {
  if (!grade) return "bg-bb-border/40 text-bb-muted";
  const g = grade.toUpperCase();
  if (g.startsWith("A")) return "bg-emerald-500/20 text-emerald-300";
  if (g.startsWith("B")) return "bg-sky-500/20 text-sky-300";
  if (g.startsWith("C")) return "bg-amber-500/20 text-amber-300";
  return "bg-red-500/20 text-red-300";
}

function validationForRoster(
  analysis: TradeActivityAnalysis,
  rosterId: string,
): TradeSideValidation | null {
  if (analysis.side_a?.roster_id === rosterId) return analysis.side_a;
  if (analysis.side_b?.roster_id === rosterId) return analysis.side_b;
  return null;
}

function fairnessLabel(
  validation: TradeSideValidation,
  teamName: string,
  otherTeamName: string,
): string {
  if (validation.fairness_label) return validation.fairness_label;
  if (!validation.fairness_view || validation.fairness_view === "fair") return "Fair";
  if (validation.fairness_view === "favors_them") return `Favors ${teamName}`;
  return `Favors ${otherTeamName}`;
}

function AssetList({ side, direction }: { side: TradeActivitySide; direction: "gives" | "receives" }) {
  const assets = side[direction];
  const players = assets.players ?? [];
  const picks = assets.picks ?? [];
  if (players.length === 0 && picks.length === 0) {
    return <span className="text-bb-muted">—</span>;
  }
  return (
    <ul className="space-y-1 text-sm">
      {players.map((p) => (
        <li key={p.player_id} className="text-white">
          {p.name}
          {p.position ? (
            <span className="ml-1 text-bb-muted">
              {p.position}
              {p.tv != null ? ` · ${Math.round(p.tv).toLocaleString()} TV` : ""}
            </span>
          ) : null}
        </li>
      ))}
      {picks.map((pick) => (
        <li key={`${pick.season}-${pick.round}-${pick.original_roster_id}`} className="text-white">
          {pick.label ?? `${pick.season} R${pick.round}`}
          {pick.tv != null ? (
            <span className="ml-1 text-bb-muted">· {Math.round(pick.tv).toLocaleString()} TV</span>
          ) : null}
        </li>
      ))}
    </ul>
  );
}

function TradeCard({ leagueId, trade }: { leagueId: string; trade: RecentTrade }) {
  const router = useRouter();
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sideA, sideB] = trade.sides;
  const analysis = trade.analysis;
  const pendingAnalysis = analysis == null;
  const teamGrades =
    analysis && !analysis.skipped
      ? trade.sides
          .map((side) => {
            const validation = validationForRoster(analysis, side.roster_id);
            return validation?.grade
              ? { name: side.team_name ?? "Team", grade: validation.grade }
              : null;
          })
          .filter((row): row is { name: string; grade: string } => row != null)
      : [];

  async function handleAnalyze(reanalyze = false) {
    setAnalyzing(true);
    setError(null);
    try {
      await postAnalyzeTrade(leagueId, trade.transaction_id, { reanalyze });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  return (
    <article className="rounded-lg border border-bb-border/40 bg-black/20 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium text-white">
            {sideA?.team_name ?? "Team A"}
            <span className="mx-2 text-bb-muted">↔</span>
            {sideB?.team_name ?? "Team B"}
          </p>
          <p className="text-xs text-bb-muted">
            {formatTradeDate(trade.created_ms)}
            {trade.leg != null ? ` · Week ${trade.leg}` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {analysis && !analysis.skipped ? (
            <>
              {analysis.overall_grade ? (
                <span
                  className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${gradeBadgeClass(analysis.overall_grade)}`}
                  title="Overall trade grade"
                >
                  Overall {analysis.overall_grade}
                </span>
              ) : null}
              {analysis.tv_fairness_grade ? (
                <span className="rounded bg-white/5 px-2 py-0.5 text-xs text-bb-muted">
                  TV {analysis.tv_fairness_grade}
                </span>
              ) : null}
            </>
          ) : pendingAnalysis ? (
            <span className="rounded bg-bb-border/30 px-2 py-0.5 text-xs text-bb-muted">
              Not analyzed
            </span>
          ) : null}
          <button
            type="button"
            onClick={() => handleAnalyze(!pendingAnalysis)}
            disabled={analyzing}
            className="rounded border border-bb-border/60 bg-white/5 px-2 py-0.5 text-xs text-bb-muted transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing
              ? "Analyzing…"
              : pendingAnalysis
                ? "Analyze"
                : "Reanalyze"}
          </button>
        </div>
      </div>

      {teamGrades.length > 0 ? (
        <div className="mb-3 flex flex-wrap gap-2">
          {teamGrades.map((row) => (
            <span
              key={row.name}
              className={`rounded px-2 py-0.5 text-xs font-semibold ${gradeBadgeClass(row.grade)}`}
            >
              {row.name} {row.grade}
            </span>
          ))}
        </div>
      ) : null}

      {sideA && sideB ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {trade.sides.map((side) => {
            const otherSide = trade.sides.find((s) => s.roster_id !== side.roster_id);
            const validation =
              analysis && !analysis.skipped
                ? validationForRoster(analysis, side.roster_id)
                : null;
            return (
              <div key={side.roster_id} className="rounded bg-white/3 p-3">
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs font-medium uppercase tracking-wider text-bb-muted">
                    {side.team_name}
                  </p>
                  {validation?.grade ? (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-bold ${gradeBadgeClass(validation.grade)}`}
                    >
                      {validation.grade}
                    </span>
                  ) : null}
                </div>
                <div className="grid gap-2 text-xs sm:grid-cols-2">
                  <div>
                    <p className="mb-1 text-red-400/80">Gives</p>
                    <AssetList side={side} direction="gives" />
                  </div>
                  <div>
                    <p className="mb-1 text-emerald-400/80">Gets</p>
                    <AssetList side={side} direction="receives" />
                  </div>
                </div>
                {validation && !validation.skipped ? (
                  <div className="mt-3 border-t border-bb-border/20 pt-3 text-xs">
                    {validation.accept_likelihood ? (
                      <p className={`font-medium uppercase ${likelihoodColor(validation.accept_likelihood)}`}>
                        Would accept: {validation.accept_likelihood}
                      </p>
                    ) : null}
                    <p className="mt-1 text-bb-muted">
                      {fairnessLabel(
                        validation,
                        side.team_name ?? "Team",
                        otherSide?.team_name ?? "Other team",
                      )}
                      {validation.would_improve_roster ? " · Improves roster" : ""}
                    </p>
                    {validation.reasoning ? (
                      <p className="mt-2 leading-relaxed text-bb-muted">{validation.reasoning}</p>
                    ) : null}
                  </div>
                ) : null}
              </div>
            );
          })}
        </div>
      ) : null}

      {analysis?.summary ? (
        <p className="mb-3 text-sm text-bb-muted">{analysis.summary}</p>
      ) : null}

      {analysis?.skipped ? (
        <p className="text-xs text-bb-muted">
          {analysis.error ?? "AI analysis unavailable for this trade."}
        </p>
      ) : null}
      {error ? <p className="mb-3 text-xs text-red-400">{error}</p> : null}
    </article>
  );
}

export function RecentTradesPanel({
  leagueId,
  trades,
  totalStored,
  unanalyzedCount,
}: RecentTradesPanelProps) {
  const router = useRouter();
  const [analyzing, setAnalyzing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAnalyze(reanalyze = false) {
    setAnalyzing(true);
    setError(null);
    try {
      await postAnalyzeTrades(leagueId, { reanalyze });
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Analysis failed");
    } finally {
      setAnalyzing(false);
    }
  }

  if (trades.length === 0) {
    return (
      <p className="text-sm text-bb-muted">
        No trades synced yet. Run a league sync to pull recent trades.
      </p>
    );
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-xs text-bb-muted">
          Showing {trades.length} of {totalStored} stored trade{totalStored === 1 ? "" : "s"}
          {unanalyzedCount > 0
            ? ` · ${unanalyzedCount} awaiting analysis`
            : ""}
        </p>
        {unanalyzedCount > 0 ? (
          <button
            type="button"
            onClick={() => handleAnalyze(false)}
            disabled={analyzing}
            className="rounded-md border border-bb-gold/40 bg-bb-gold/10 px-3 py-1.5 text-xs font-medium text-bb-gold transition hover:bg-bb-gold/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing
              ? "Analyzing…"
              : `Analyze ${unanalyzedCount} trade${unanalyzedCount === 1 ? "" : "s"}`}
          </button>
        ) : (
          <button
            type="button"
            onClick={() => handleAnalyze(true)}
            disabled={analyzing}
            className="rounded-md border border-bb-border/60 bg-white/5 px-3 py-1.5 text-xs font-medium text-bb-muted transition hover:bg-white/10 hover:text-white disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing ? "Reanalyzing…" : "Reanalyze trades"}
          </button>
        )}
      </div>
      {error ? <p className="text-xs text-red-400">{error}</p> : null}
      {trades.map((trade) => (
        <TradeCard key={trade.transaction_id} leagueId={leagueId} trade={trade} />
      ))}
    </div>
  );
}
