"use client";

import { useState } from "react";
import type { TeamDetail } from "@/lib/api";
import type { RatingMode } from "./TeamPageContent";
import { DepthChartPanel } from "./DepthChartPanel";
import { RosterTable } from "./RosterTable";

type TeamTabsProps = {
  team: TeamDetail;
  ratingMode?: RatingMode;
};

type TabKey = "roster" | "depth";

const tabs: { key: TabKey; label: string }[] = [
  { key: "roster", label: "Roster" },
  { key: "depth", label: "Depth" },
];

export function TeamTabs({ team, ratingMode = "dynasty" }: TeamTabsProps) {
  const [tab, setTab] = useState<TabKey>("roster");

  return (
    <div>
      <div className="mb-3 grid grid-cols-2 gap-1 rounded-xl bg-black/25 p-1 ring-1 ring-inset ring-white/[0.06] md:mb-4 md:flex md:w-fit md:gap-2 md:rounded-none md:bg-transparent md:p-0 md:ring-0">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            className={`rounded-lg px-2 py-2 text-xs font-medium transition md:px-3 md:py-1.5 md:text-sm ${
              tab === t.key
                ? "bg-bb-gold/20 text-bb-gold shadow-sm"
                : "text-bb-muted hover:bg-white/5 hover:text-white"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "roster" ? (
        <RosterTable starters={team.starters} bench={team.bench} full ratingMode={ratingMode} />
      ) : null}
      {tab === "depth" ? (
        <DepthChartPanel depthChart={team.depth_chart} leagueId={team.league_id} />
      ) : null}
    </div>
  );
}
