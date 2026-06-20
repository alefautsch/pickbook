"use client";

import Link from "next/link";
import type {
  AgeProfile,
  LeagueAnalysis,
  LeagueDetail,
  PositionStrengthMap,
  RecentTradesResponse,
} from "@/lib/api";
import { AgeProfilePanel } from "@/components/AgeProfilePanel";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { PositionHeatmap } from "@/components/PositionHeatmap";
import { RecentTradesPanel } from "@/components/RecentTradesPanel";
import { TradeSurplusPanel } from "@/components/TradeSurplusPanel";
import { OvrBadge } from "@/components/OvrBadge";

type LeagueAnalysisSectionsProps = {
  leagueId: string;
  league: LeagueDetail;
  analysis: LeagueAnalysis;
  recentTrades: RecentTradesResponse;
};

export function LeagueAnalysisSections({
  leagueId,
  league,
  analysis,
  recentTrades,
}: LeagueAnalysisSectionsProps) {
  return (
    <div className="flex flex-col gap-4 md:gap-5">
      <CollapsibleSection title="Recent Trades" defaultOpen subtitle="League trade activity">
        <RecentTradesPanel
          leagueId={leagueId}
          trades={recentTrades.trades}
          totalStored={recentTrades.total_stored}
          unanalyzedCount={recentTrades.unanalyzed_count}
        />
      </CollapsibleSection>

      <CollapsibleSection title="All Teams" defaultOpen>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {league.teams.map((team) => (
            <Link
              key={team.roster_id}
              href={`/leagues/${leagueId}/teams/${team.roster_id}`}
              className="block"
            >
              <article
                className={`flex items-center gap-3 rounded-lg border border-bb-border/40 bg-black/20 p-3 transition hover:border-bb-gold/30 ${
                  team.is_me ? "border-bb-gold/40" : ""
                }`}
              >
                <OvrBadge ovr={team.avg_dynasty_rating} size="sm" />
                <div className="min-w-0">
                  <p className="truncate font-medium text-white">{team.team_name}</p>
                  <p className="text-xs text-bb-muted">Rank #{team.dynasty_rank ?? "—"}</p>
                </div>
              </article>
            </Link>
          ))}
        </div>
      </CollapsibleSection>

      <div className="grid gap-4 md:gap-5 lg:grid-cols-2">
        <CollapsibleSection title="Age & Window">
          <AgeProfilePanel profiles={analysis.age_profiles} />
        </CollapsibleSection>
        <CollapsibleSection title="Trade Surplus">
          <TradeSurplusPanel tradeSurplus={analysis.trade_surplus} leagueId={leagueId} />
        </CollapsibleSection>
      </div>

      {analysis.position_strength ? (
        <CollapsibleSection title="Position Strength Heatmap">
          <PositionHeatmap data={analysis.position_strength} leagueId={leagueId} />
        </CollapsibleSection>
      ) : null}
    </div>
  );
}
