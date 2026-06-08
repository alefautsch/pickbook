"use client";

import { useState } from "react";
import type { TeamDetail } from "@/lib/api";
import { DepthChartPanel } from "./DepthChartPanel";
import { RosterTable } from "./RosterTable";

type TeamTabsProps = {
  team: TeamDetail;
};

type TabKey = "roster" | "depth" | "stats";

const tabs: { key: TabKey; label: string }[] = [
  { key: "roster", label: "Roster" },
  { key: "depth", label: "Depth" },
  { key: "stats", label: "Stats" },
];

export function TeamTabs({ team }: TeamTabsProps) {
  const [tab, setTab] = useState<TabKey>("roster");

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center gap-2 border-b border-bb-border/50 pb-3">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-3 py-1.5 text-sm transition ${
              tab === t.key
                ? "bg-bb-gold/20 text-bb-gold"
                : "text-bb-muted hover:bg-white/5 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "roster" ? (
        <RosterTable starters={team.starters} bench={team.bench} full />
      ) : null}
      {tab === "depth" ? (
        <DepthChartPanel depthChart={team.depth_chart} leagueId={team.league_id} />
      ) : null}
      {tab === "stats" ? (
        <RosterTable
          starters={team.starters}
          bench={team.bench}
          full
          statsOnly
        />
      ) : null}
    </div>
  );
}
