"use client";

import Link from "next/link";
import type {
  AgeProfile,
  FreeAgentBoard as FreeAgentBoardData,
  LeagueAnalysis,
  LeagueDetail,
  PositionStrengthMap,
} from "@/lib/api";
import { AgeProfilePanel } from "@/components/AgeProfilePanel";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { FreeAgentBoard } from "@/components/FreeAgentBoard";
import { PositionHeatmap } from "@/components/PositionHeatmap";
import { TradeSurplusPanel } from "@/components/TradeSurplusPanel";
import { OvrBadge } from "@/components/OvrBadge";

type LeagueAnalysisSectionsProps = {
  leagueId: string;
  league: LeagueDetail;
  freeAgents: FreeAgentBoardData;
  analysis: LeagueAnalysis;
};

export function LeagueAnalysisSections({
  leagueId,
  league,
  freeAgents,
  analysis,
}: LeagueAnalysisSectionsProps) {
  return (
    <div className="flex flex-col gap-4 md:gap-5">
      <CollapsibleSection title="Free Agents" defaultOpen className="bb-panel p-0">
        <div className="px-3 pb-3 md:px-4 md:pb-4">
          <FreeAgentBoard
            leagueId={leagueId}
            superflex={league.superflex}
            initialBoard={freeAgents}
            embedded
          />
        </div>
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
