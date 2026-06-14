"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import type { TeamDetail } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { OvrGauge } from "@/components/OvrGauge";
import { ComponentDonut } from "@/components/DonutChart";
import { ContenderTag } from "@/components/ContenderTag";
import { DepthChartPanel } from "@/components/DepthChartPanel";
import { DraftPicksPanel } from "@/components/DraftPicksPanel";
import { InjuryWatchPanel } from "@/components/InjuryWatchPanel";
import { TradeCandidatesPanel } from "@/components/TradeCandidatesPanel";
import { PositionStrengthBars } from "@/components/PositionStrengthBars";
import { AgeProfileSidebar } from "@/components/AgeProfileSidebar";
import { CollapsibleSection } from "@/components/CollapsibleSection";
import { SleeperAvatarWatermark, TeamAvatar } from "@/components/SleeperAvatarWatermark";
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

type TeamStat = {
  label: string;
  value: ReactNode;
  sub?: ReactNode;
  tone?: "default" | "good" | "bad";
};

function StatStrip({ stats }: { stats: TeamStat[] }) {
  return (
    <>
      <dl className="scrollbar-none -mx-0.5 flex gap-2 overflow-x-auto px-0.5 pb-0.5 sm:hidden">
        {stats.map((stat) => (
          <StatCell key={stat.label} stat={stat} className="min-w-[5.25rem] shrink-0" />
        ))}
      </dl>
      <dl className="hidden gap-2 sm:grid sm:grid-cols-5 lg:hidden">
        {stats.map((stat) => (
          <StatCell key={stat.label} stat={stat} />
        ))}
      </dl>
      <dl className="hidden lg:grid lg:grid-cols-5 lg:divide-x lg:divide-white/8">
        {stats.map((stat) => (
          <StatCell
            key={stat.label}
            stat={stat}
            className="lg:rounded-none lg:bg-transparent lg:px-4 lg:py-0 lg:ring-0 lg:first:pl-0 lg:last:pr-0"
          />
        ))}
      </dl>
    </>
  );
}

function StatCell({
  stat,
  className = "",
}: {
  stat: TeamStat;
  className?: string;
}) {
  const toneClass =
    stat.tone === "good"
      ? "text-emerald-400"
      : stat.tone === "bad"
        ? "text-red-400"
        : "text-white";

  return (
    <div
      className={`min-w-0 rounded-lg bg-white/3 px-2.5 py-2 ring-1 ring-inset ring-white/6 ${className}`}
    >
      <dt className="truncate text-[9px] uppercase tracking-wider text-bb-muted">
        {stat.label}
      </dt>
      <dd
        className={`mt-0.5 truncate text-base font-bold tabular-nums leading-none ${toneClass}`}
      >
        {stat.value}
      </dd>
      {stat.sub ? (
        <p className={`mt-0.5 truncate text-[10px] ${rankSubClass(stat.sub)}`}>
          {stat.sub}
        </p>
      ) : null}
    </div>
  );
}

function HeroRankTile({
  label,
  value,
  accent = "default",
}: {
  label: string;
  value: ReactNode;
  accent?: "default" | "gold";
}) {
  const valueClass = accent === "gold" ? "text-bb-gold" : "text-white";

  return (
    <div className="flex h-[4.25rem] w-[4.25rem] shrink-0 flex-col items-center justify-center rounded-lg bg-white/4 px-1 text-center ring-1 ring-inset ring-white/[0.07] xl:h-[4.75rem] xl:w-[4.75rem]">
      <p className={`text-lg font-bold tabular-nums leading-none xl:text-xl ${valueClass}`}>
        {value}
      </p>
      <p className="mt-1 line-clamp-2 px-0.5 text-[8px] leading-tight uppercase tracking-wider text-bb-muted xl:text-[9px]">
        {label}
      </p>
    </div>
  );
}

function OvrGaugeTile({ ovr }: { ovr: number | null | undefined }) {
  return (
    <div className="flex shrink-0 items-center justify-center">
      <div className="xl:hidden">
        <OvrGauge ovr={ovr} size="sm" showTier />
      </div>
      <div className="hidden xl:block">
        <OvrGauge ovr={ovr} size="md" showTier />
      </div>
    </div>
  );
}

function TeamHero({
  team,
  displayOvr,
  displayStarterOvr,
  ovrDelta,
  ovrTone,
  leagueRosterCount,
  ratingMode,
  onRatingModeChange,
}: {
  team: TeamDetail;
  displayOvr: number | null | undefined;
  displayStarterOvr: number | null | undefined;
  ovrDelta: number | null;
  ovrTone: "default" | "good" | "bad";
  leagueRosterCount: number | string;
  ratingMode: RatingMode;
  onRatingModeChange: (mode: RatingMode) => void;
}) {
  const stats: TeamStat[] = [
    { label: "Start OVR", value: displayStarterOvr ?? "—", sub: "avg" },
    {
      label: "Start PPG",
      value: formatPpg(team.starter_total_ppg),
      sub: team.starter_ppg_rank ? ordinal(team.starter_ppg_rank) : undefined,
    },
    {
      label: "Trade Value",
      value: formatTv(team.total_trade_value),
      sub: team.tv_rank ? ordinal(team.tv_rank) : undefined,
    },
    { label: "Pick Value", value: formatTv(team.draft_pick_value) },
    {
      label: "Trend",
      value:
        ovrDelta != null && ovrDelta !== 0
          ? `${ovrDelta > 0 ? "+" : ""}${ovrDelta}`
          : "—",
      tone: ovrTone,
    },
  ];

  const metaLine = [
    team.owner ?? "Unknown owner",
    team.is_me ? "(me)" : null,
    team.dynasty_rank ? `${ordinal(team.dynasty_rank)} of ${leagueRosterCount}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <section className="bb-panel relative mb-3 overflow-hidden md:mb-5">
      {team.avatar_url ? (
        <>
          <SleeperAvatarWatermark
            avatarUrl={team.avatar_url}
            className="hidden opacity-[0.14] md:block md:right-2 md:top-1/2 md:h-52 md:w-52 md:-translate-y-1/2 lg:right-4 lg:h-64 lg:w-64 lg:opacity-[0.18] xl:h-72 xl:w-72 xl:opacity-[0.22]"
          />
          <div
            aria-hidden
            className="pointer-events-none absolute inset-0 hidden bg-[linear-gradient(105deg,#0d1117_0%,#0d1117_48%,rgba(13,17,23,0.72)_70%,rgba(13,17,23,0.15)_100%)] md:block"
          />
        </>
      ) : null}

      <div className="relative p-3 sm:p-4 lg:p-5">
        <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 sm:gap-4 md:items-center md:gap-4 lg:gap-5">
          <TeamAvatar
            avatarUrl={team.avatar_url}
            teamName={team.team_name}
            className="h-12 w-12 rounded-xl shadow-md ring-1 ring-white/15 sm:h-14 sm:w-14 lg:h-16 lg:w-16 lg:rounded-2xl"
          />

          <div className="min-w-0">
            <p className="truncate text-[10px] uppercase tracking-wider text-bb-muted sm:text-xs">
              {team.league_name}
            </p>
            <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-1">
              <h1 className="text-lg font-semibold leading-tight text-white sm:text-xl lg:text-2xl">
                {team.team_name ?? "Team"}
              </h1>
              <ContenderTag tier={team.contender_tier} size="md" />
            </div>
            <p className="mt-0.5 truncate text-xs text-bb-muted sm:text-sm">{metaLine}</p>
            <div className="mt-2 w-fit lg:mt-3">
              <RatingToggle ratingMode={ratingMode} onChange={onRatingModeChange} />
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2 self-start md:self-center">
            <div className="md:hidden">
              <OvrGauge ovr={displayOvr} size="sm" showTier />
            </div>
            <div className="hidden items-center gap-2 md:flex">
              {team.dynasty_rank ? (
                <HeroRankTile label="Dynasty" value={ordinal(team.dynasty_rank)} />
              ) : null}
              {team.tv_rank ? (
                <HeroRankTile
                  label="Trade Value"
                  value={ordinal(team.tv_rank)}
                  accent="gold"
                />
              ) : null}
              <OvrGaugeTile ovr={displayOvr} />
            </div>
          </div>
        </div>

        <div className="mt-3 border-t border-bb-border/40 pt-3 sm:mt-4 lg:mt-5 lg:pt-4">
          <StatStrip stats={stats} />
        </div>
      </div>
    </section>
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
    <div className="inline-flex w-fit items-center gap-0.5 rounded-lg bg-white/4 p-0.5 ring-1 ring-inset ring-white/[0.07]">
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
        <CollapsibleSection title="Position Strength" subtitle="Starter OVR rank in league">
          <PositionStrengthBars data={positionStrength} myRosterId={rosterId} embedded />
        </CollapsibleSection>
      ) : null}

      <CollapsibleSection title="Age Profile">
        <AgeProfileSidebar profiles={ageProfiles} rosterId={rosterId} embedded />
      </CollapsibleSection>

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
      <TeamHero
        team={team}
        displayOvr={displayOvr}
        displayStarterOvr={displayStarterOvr}
        ovrDelta={ovrDelta}
        ovrTone={ovrTone}
        leagueRosterCount={leagueRosterCount}
        ratingMode={ratingMode}
        onRatingModeChange={setRatingMode}
      />

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
