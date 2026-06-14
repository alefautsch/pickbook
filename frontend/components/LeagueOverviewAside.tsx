"use client";

import type { AgeProfile, ContenderTeam, PositionStrengthMap, TeamDetail } from "@/lib/api";
import { AgeProfileSidebar } from "@/components/AgeProfileSidebar";
import { ContenderBreakdown } from "@/components/ContenderBreakdown";
import { MobilePanelCollapse } from "@/components/MobilePanelCollapse";
import { OptimalStartersSidebar } from "@/components/OptimalStartersSidebar";
import { PositionStrengthBars } from "@/components/PositionStrengthBars";

type LeagueOverviewAsideProps = {
  myTeam: TeamDetail | null;
  leagueId: string;
  myRosterId?: string | null;
  positionStrength: PositionStrengthMap | null;
  ageProfiles: AgeProfile[];
  myContender: ContenderTeam | null;
};

export function LeagueOverviewAside({
  myTeam,
  leagueId,
  myRosterId,
  positionStrength,
  ageProfiles,
  myContender,
}: LeagueOverviewAsideProps) {
  return (
    <aside className="order-2 space-y-3 xl:order-2">
      {myTeam ? (
        <MobilePanelCollapse title="My Optimal Starters" defaultOpen>
          <OptimalStartersSidebar
            starters={myTeam.starters}
            leagueId={leagueId}
            showTitleOnDesktop
          />
        </MobilePanelCollapse>
      ) : null}
      {positionStrength ? (
        <MobilePanelCollapse title="Position Strength">
          <PositionStrengthBars data={positionStrength} myRosterId={myRosterId} showTitleOnDesktop />
        </MobilePanelCollapse>
      ) : null}
      <MobilePanelCollapse title="Age Profile">
        <AgeProfileSidebar profiles={ageProfiles} showTitleOnDesktop />
      </MobilePanelCollapse>
      <MobilePanelCollapse title="Contender Breakdown" defaultOpen>
        <ContenderBreakdown team={myContender} showTitleOnDesktop />
      </MobilePanelCollapse>
    </aside>
  );
}
