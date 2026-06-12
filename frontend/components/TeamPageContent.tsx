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
    <div className="min-w-0 rounded-lg bg-white/4 px-2 py-2 ring-1 ring-inset ring-white/[0.07]">
      <dt className="truncate text-[9px] uppercase tracking-wide text-bb-muted">
        {label}
      </dt>
      <dd className={`mt-0.5 truncate text-xl font-bold tabular-nums leading-none ${toneClass}`}>
        {value}
      </dd>
      {sub ? (
        <p className={`mt-0.5 truncate text-[10px] ${rankSubClass(sub)}`}>{sub}</p>
      ) : null}
    </div>
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
    <div className="flex flex-1 flex-col bg-[#0d1117]/40 px-4 py-5">
      <section className="mb-5 grid gap-4 lg:grid-cols-[minmax(300px,1fr)_280px_220px]">
        <div className="bb-panel p-4">
          <div className="flex items-start gap-4">
            <div className="shrink-0">
              <OvrGauge ovr={displayOvr} size="md" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h1 className="text-xl font-semibold leading-tight text-white sm:text-2xl">
                  {team.team_name ?? "Team"}
                </h1>
                <ContenderTag tier={team.contender_tier} />
              </div>
              <p className="mt-0.5 text-sm text-bb-muted">
                {team.owner ?? "Unknown owner"}
                {team.is_me ? " · (me)" : ""}
                {team.dynasty_rank
                  ? ` · ${ordinal(team.dynasty_rank)} of ${leagueRosterCount}`
                  : ""}
              </p>
              <p className="text-xs uppercase tracking-wider text-bb-muted">
                {team.league_name}
              </p>
              <div className="mt-2 flex items-center gap-1.5">
                <span className="text-[10px] uppercase tracking-wider text-bb-muted">
                  Ratings
                </span>
                <div className="flex items-center gap-0.5 rounded-lg bg-white/4 p-0.5 ring-1 ring-inset ring-white/[0.07]">
                  <button
                    type="button"
                    onClick={() => setRatingMode("dynasty")}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition ${
                      ratingMode === "dynasty"
                        ? "bg-bb-gold/20 text-bb-gold"
                        : "text-bb-muted hover:text-white"
                    }`}
                  >
                    Dynasty
                  </button>
                  <button
                    type="button"
                    onClick={() => setRatingMode("win_now")}
                    className={`rounded px-2.5 py-1 text-xs font-medium transition ${
                      ratingMode === "win_now"
                        ? "bg-bb-gold/20 text-bb-gold"
                        : "text-bb-muted hover:text-white"
                    }`}
                  >
                    Win-Now
                  </button>
                </div>
              </div>
              <dl className="mt-3 grid grid-cols-3 gap-2 sm:grid-cols-5">
                <Metric
                  label="Start OVR"
                  value={displayStarterOvr ?? "—"}
                  sub="avg"
                />
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
                <Metric
                  label="Pick Value"
                  value={formatTv(team.draft_pick_value)}
                />
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
        </div>

        <section className="bb-panel p-4">
          <h2 className="bb-panel-title">Team OVR Breakdown</h2>
          <div className="mt-2">
            <ComponentDonut
              components={team.component_breakdown}
              ovr={team.avg_dynasty_rating}
              compact
            />
          </div>
        </section>

        <section className="bb-panel p-4">
          <h2 className="bb-panel-title">Team Traits</h2>
          {team.traits.length > 0 ? (
            <ul className="mt-3 space-y-1.5">
              {team.traits.map((trait) => (
                <li
                  key={trait.label}
                  className="flex items-center justify-between gap-3 text-sm"
                >
                  <span className="text-bb-muted">{trait.label}</span>
                  <span className="text-right font-medium text-white">
                    {trait.value}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="mt-3 text-sm text-bb-muted">No traits yet.</p>
          )}
        </section>
      </section>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0">
          <TeamTabs team={team} ratingMode={ratingMode} />
        </div>

        <aside className="space-y-4">
          {team.trade_candidates.length > 0 ? (
            <section className="bb-panel p-4">
              <h2 className="bb-panel-title">Trade Chips</h2>
              <p className="mt-1 text-xs text-bb-muted">
                Most movable pieces on this roster
              </p>
              <div className="mt-3">
                <TradeCandidatesPanel
                  candidates={team.trade_candidates}
                  leagueId={leagueId}
                />
              </div>
            </section>
          ) : null}

          <section className="bb-panel p-4">
            <h2 className="bb-panel-title">Depth Chart</h2>
            <div className="mt-3">
              <DepthChartPanel
                depthChart={team.depth_chart}
                leagueId={leagueId}
                compact
              />
            </div>
          </section>

          {positionStrength ? (
            <PositionStrengthBars
              data={positionStrength}
              myRosterId={rosterId}
            />
          ) : null}

          <AgeProfileSidebar profiles={ageProfiles} rosterId={rosterId} />

          <div className="bb-panel p-4">
            <h2 className="bb-panel-title">Draft Picks</h2>
            <div className="mt-3">
              <DraftPicksPanel picks={team.draft_picks} compact />
            </div>
          </div>

          <div className="bb-panel p-4">
            <InjuryWatchPanel
              injuries={team.injuries}
              leagueId={leagueId}
              compact
            />
          </div>
        </aside>
      </div>
    </div>
  );
}
