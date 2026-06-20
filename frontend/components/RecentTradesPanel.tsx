"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { postAnalyzeTrades, type RecentTrade, type TradeActivitySide } from "@/lib/api";

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

function TradeCard({ trade }: { trade: RecentTrade }) {
  const [sideA, sideB] = trade.sides;
  const analysis = trade.analysis;
  const pendingAnalysis = analysis == null;

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
        {analysis?.overall_grade ? (
          <span
            className={`rounded px-2 py-0.5 text-xs font-semibold uppercase tracking-wide ${gradeBadgeClass(analysis.overall_grade)}`}
          >
            {analysis.overall_grade}
          </span>
        ) : pendingAnalysis ? (
          <span className="rounded bg-bb-border/30 px-2 py-0.5 text-xs text-bb-muted">
            Not analyzed
          </span>
        ) : null}
      </div>

      {sideA && sideB ? (
        <div className="mb-4 grid gap-3 sm:grid-cols-2">
          {[sideA, sideB].map((side) => (
            <div key={side.roster_id} className="rounded bg-white/3 p-3">
              <p className="mb-2 text-xs font-medium uppercase tracking-wider text-bb-muted">
                {side.team_name}
              </p>
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
            </div>
          ))}
        </div>
      ) : null}

      {analysis?.summary ? (
        <p className="mb-3 text-sm text-bb-muted">{analysis.summary}</p>
      ) : null}

      {analysis && !analysis.skipped && analysis.side_a && analysis.side_b ? (
        <div className="grid gap-3 border-t border-bb-border/30 pt-3 sm:grid-cols-2">
          {[analysis.side_a, analysis.side_b].map((side) => (
            <div key={side.roster_id} className="text-sm">
              <p className="mb-1 font-medium text-white">{side.team_name}</p>
              {side.accept_likelihood ? (
                <p className={`text-xs font-medium uppercase ${likelihoodColor(side.accept_likelihood)}`}>
                  Would accept: {side.accept_likelihood}
                  {side.fairness_label ? ` · ${side.fairness_label}` : ""}
                </p>
              ) : null}
              {side.reasoning ? (
                <p className="mt-1 text-xs leading-relaxed text-bb-muted">{side.reasoning}</p>
              ) : null}
            </div>
          ))}
        </div>
      ) : analysis?.skipped ? (
        <p className="text-xs text-bb-muted">
          {analysis.error ?? "AI analysis unavailable for this trade."}
        </p>
      ) : null}
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

  async function handleAnalyze() {
    setAnalyzing(true);
    setError(null);
    try {
      await postAnalyzeTrades(leagueId);
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
            onClick={handleAnalyze}
            disabled={analyzing}
            className="rounded-md border border-bb-gold/40 bg-bb-gold/10 px-3 py-1.5 text-xs font-medium text-bb-gold transition hover:bg-bb-gold/20 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {analyzing
              ? "Analyzing…"
              : `Analyze ${unanalyzedCount} trade${unanalyzedCount === 1 ? "" : "s"}`}
          </button>
        ) : null}
      </div>
      {error ? <p className="text-xs text-red-400">{error}</p> : null}
      {trades.map((trade) => (
        <TradeCard key={trade.transaction_id} trade={trade} />
      ))}
    </div>
  );
}
