"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import type { TeamDetail } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { AgeProfileSidebar } from "@/components/AgeProfileSidebar";
import { ComponentDonut } from "@/components/DonutChart";
import { ContenderTag } from "@/components/ContenderTag";
import { DepthChartPanel } from "@/components/DepthChartPanel";
import { DraftPicksPanel } from "@/components/DraftPicksPanel";
import { InjuryWatchPanel } from "@/components/InjuryWatchPanel";
import { TradeCandidatesPanel } from "@/components/TradeCandidatesPanel";
import { OvrGauge } from "@/components/OvrGauge";
import { PositionStrengthBars } from "@/components/PositionStrengthBars";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { TeamTabs } from "@/components/TeamTabs";
import type { AgeProfile, PositionStrengthMap } from "@/lib/api";

export type RatingMode = "dynasty" | "win_now";

type TeamPageContentProps = {
  team: TeamDetail;
  ovrDelta: number | null;
  leagueRosterCount: number | string;
  leagueId: string;
  rosterId: string;
  positionStrength: PositionStrengthMap | null;
  ageProfiles: AgeProfile[];
};

function rankSubClass(sub: ReactNode): string {
  if (typeof sub !== "string") return "text-bb-muted";
  const m = sub.match(/^(\d+)(st|nd|rd|th)$/);
  if (!m) return "text-bb-muted";
  const n = parseInt(m[1]);
  if (n <= 2) return "text-emerald-400 font-semibold";
  if (n <= 4) return "text-bb-gold";
  return "text-bb-muted";
}

function Metric({
  label,
  value,
  sub,
  tone = "default",
}: {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad";
}) {
  const toneClass =
    tone === "good"
      ? "text-emerald-400"
      : tone === "bad"
        ? "text-red-400"
        : "text-white";

  return (
    <div className="min-w-0 rounded-lg bg-white/4 px-2 py-1.5 ring-1 ring-inset ring-white/[0.07] md:px-2 md:py-2">
      <dt className="truncate text-[9px] uppercase tracking-wide text-bb-muted">
        {label}
      </dt>
      <dd className={`mt-0.5 truncate text-lg font-bold tabular-nums leading-none md:text-xl ${toneClass}`}>
        {value}
      </dd>
      {sub ? (
        <p className={`mt-0.5 truncate text-[10px] ${rankSubClass(sub)}`}>{sub}</p>
      ) : null}
    </div>
  );
}

function RatingToggle({
  ratingMode,
  onChange,
}: {
  ratingMode: RatingMode;
  onChange: (mode: RatingMode) => void;
}) {
  return (
    <div className="flex items-center gap-0.5 rounded-lg bg-white/4 p-0.5 ring-1 ring-inset ring-white/[0.07]">
      <button
        type="button"
        onClick={() => onChange("dynasty")}
        className={`rounded px-2 py-1 text-[11px] font-medium transition md:px-2.5 md:text-xs ${
          ratingMode === "dynasty"
            ? "bg-bb-gold/20 text-bb-gold"
            : "text-bb-muted hover:text-white"
        }`}
      >
        Dynasty
      </button>
      <button
        type="button"
        onClick={() => onChange("win_now")}
        className={`rounded px-2 py-1 text-[11px] font-medium transition md:px-2.5 md:text-xs ${
          ratingMode === "win_now"
            ? "bg-bb-gold/20 text-bb-gold"
            : "text-bb-muted hover:text-white"
        }`}
      >
        Win-Now
      </button>
    </div>
  );
}

function TeamBreakdownPanel({ team }: { team: TeamDetail }) {
  return (
    <section className="bb-panel p-3 md:p-4">
      <h2 className="bb-panel-title">Team OVR Breakdown</h2>
      <div className="mt-2">
        <ComponentDonut
          components={team.component_breakdown}
          ovr={team.avg_dynasty_rating}
          compact
        />
      </div>
    </section>
  );
}

function TeamTraitsPanel({ team }: { team: TeamDetail }) {
  return (
    <section className="bb-panel p-3 md:p-4">
      <h2 className="bb-panel-title">Team Traits</h2>
      {team.traits.length > 0 ? (
        <ul className="mt-2 space-y-1.5 md:mt-3">
          {team.traits.map((trait) => (
            <li
              key={trait.label}
              className="flex items-center justify-between gap-3 text-sm"
            >
              <span className="text-bb-muted">{trait.label}</span>
              <span className="text-right font-medium text-white">{trait.value}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-sm text-bb-muted md:mt-3">No traits yet.</p>
      )}
    </section>
  );
}

function TeamSidebarPanels({
  team,
  leagueId,
  rosterId,
  positionStrength,
  ageProfiles,
}: {
  team: TeamDetail;
  leagueId: string;
  rosterId: string;
  positionStrength: PositionStrengthMap | null;
  ageProfiles: AgeProfile[];
}) {
  return (
    <>
      {team.trade_candidates.length > 0 ? (
        <CollapsibleSection
          title="Trade Chips"
          subtitle="Most movable pieces on this roster"
          defaultOpen
        >
          <TradeCandidatesPanel candidates={team.trade_candidates} leagueId={leagueId} />
        </CollapsibleSection>
      ) : null}

      <CollapsibleSection title="Depth Chart">
        <DepthChartPanel depthChart={team.depth_chart} leagueId={leagueId} compact />
      </CollapsibleSection>

      {positionStrength ? (
        <PositionStrengthBars data={positionStrength} myRosterId={rosterId} />
      ) : null}

      <AgeProfileSidebar profiles={ageProfiles} rosterId={rosterId} />

      <CollapsibleSection title="Draft Picks">
        <DraftPicksPanel picks={team.draft_picks} compact />
      </CollapsibleSection>

      <CollapsibleSection title="Injury Watch">
        <InjuryWatchPanel injuries={team.injuries} leagueId={leagueId} compact />
      </CollapsibleSection>
    </>
  );
}

export function TeamPageContent({
  team,
  ovrDelta,
  leagueRosterCount,
  leagueId,
  rosterId,
  positionStrength,
  ageProfiles,
}: TeamPageContentProps) {
  const [ratingMode, setRatingMode] = useState<RatingMode>("dynasty");

  const displayOvr =
    ratingMode === "win_now" ? team.avg_win_now_rating : team.avg_dynasty_rating;
  const displayStarterOvr =
    ratingMode === "win_now"
      ? team.starter_avg_win_now_rating
      : team.starter_avg_dynasty_rating;

  const ovrTone =
    ovrDelta == null
      ? "default"
      : ovrDelta > 0
        ? "good"
        : ovrDelta < 0
          ? "bad"
          : "default";

  return (
    <div className="flex flex-1 flex-col bg-[#0d1117]/40 px-3 py-3 md:px-4 md:py-5">
      {/* Compact hero — team identity only */}
      <section className="bb-panel mb-3 p-3 md:mb-5 md:p-4">
        <div className="flex items-start gap-3">
          <div className="shrink-0 scale-90 md:scale-100">
            <OvrGauge ovr={displayOvr} size="md" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-lg font-semibold leading-tight text-white md:text-2xl">
                {team.team_name ?? "Team"}
              </h1>
              <ContenderTag tier={team.contender_tier} />
            </div>
            <p className="mt-0.5 text-xs text-bb-muted md:text-sm">
              {team.owner ?? "Unknown owner"}
              {team.is_me ? " · (me)" : ""}
              {team.dynasty_rank
                ? ` · ${ordinal(team.dynasty_rank)} of ${leagueRosterCount}`
                : ""}
            </p>
            <div className="mt-2 flex items-center justify-between gap-2">
              <RatingToggle ratingMode={ratingMode} onChange={setRatingMode} />
            </div>
            <dl className="mt-2 grid grid-cols-2 gap-1.5 sm:grid-cols-3 md:mt-3 md:gap-2">
              <Metric label="Start OVR" value={displayStarterOvr ?? "—"} sub="avg" />
              <Metric
                label="Start PPG"
                value={formatPpg(team.starter_total_ppg)}
                sub={team.starter_ppg_rank ? ordinal(team.starter_ppg_rank) : undefined}
              />
              <Metric
                label="Trade Value"
                value={formatTv(team.total_trade_value)}
                sub={team.tv_rank ? ordinal(team.tv_rank) : undefined}
              />
              <Metric label="Pick Value" value={formatTv(team.draft_pick_value)} />
              <Metric
                label="Trend"
                value={
                  ovrDelta != null && ovrDelta !== 0
                    ? `${ovrDelta > 0 ? "+" : ""}${ovrDelta}`
                    : "—"
                }
                tone={ovrTone}
              />
            </dl>
          </div>
        </div>
      </section>

      {/* Roster front and center */}
      <div className="flex flex-col gap-4 lg:grid lg:grid-cols-[minmax(0,1fr)_300px] lg:gap-5">
        <div className="min-w-0 space-y-4">
          <TeamTabs team={team} ratingMode={ratingMode} />

          <div className="grid gap-3 lg:grid-cols-2 lg:gap-4">
            <TeamBreakdownPanel team={team} />
            <TeamTraitsPanel team={team} />
          </div>
        </div>

        <aside className="space-y-3 md:space-y-4">
          <TeamSidebarPanels
            team={team}
            leagueId={leagueId}
            rosterId={rosterId}
            positionStrength={positionStrength}
            ageProfiles={ageProfiles}
          />
        </aside>
      </div>
    </div>
  );
}
