"use client";

import Link from "next/link";
import { useState } from "react";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { AdvisorShell } from "./AdvisorShell";
import type { AdvisorPageContext } from "./AdvisorContext";
import { LeagueSwitcher } from "./LeagueSwitcher";
import { MobileNav } from "./MobileNav";
import { PlayerSearch } from "./PlayerSearch";
import { SidebarNav } from "./SidebarNav";
import { SyncButton } from "./SyncButton";
import { SyncStatusBar } from "./SyncStatusBar";

type AppShellProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
  advisorContext?: AdvisorPageContext;
  children: React.ReactNode;
};

export function AppShell({
  leagues,
  activeLeagueId,
  advisorContext,
  children,
}: AppShellProps) {
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mobileSearchOpen, setMobileSearchOpen] = useState(false);
  const resolvedLeagueId =
    activeLeagueId ?? leagues[0]?.league_id;
  const myRosterId =
    leagues.find((l) => l.league_id === resolvedLeagueId)?.my_roster_id ?? undefined;

  return (
    <div className="flex min-h-full w-full max-w-[100vw] overflow-x-hidden">
      <SidebarNav leagues={leagues} activeLeagueId={resolvedLeagueId} />
      <MobileNav
        leagues={leagues}
        activeLeagueId={resolvedLeagueId}
        open={mobileNavOpen}
        onOpenChange={setMobileNavOpen}
      />

      <div className="flex min-h-full min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 border-b border-bb-border/40 bg-[#0a0e14]/95 backdrop-blur-md">
          {/* Mobile: hamburger always visible, league scroll, settings */}
          <div className="flex items-center gap-2 px-2 py-2 lg:hidden">
            <button
              type="button"
              aria-label="Open menu"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-bb-border/60 bg-black/30 text-base text-white transition hover:border-bb-gold/40"
              onClick={() => setMobileNavOpen(true)}
            >
              ☰
            </button>
            <div className="min-w-0 flex-1">
              <LeagueSwitcher leagues={leagues} activeLeagueId={resolvedLeagueId} />
            </div>
            <button
              type="button"
              aria-label="Search players"
              aria-expanded={mobileSearchOpen}
              className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border text-sm transition ${
                mobileSearchOpen
                  ? "border-bb-gold/50 bg-bb-gold/10 text-bb-gold"
                  : "border-bb-border/60 text-bb-muted hover:border-bb-gold/40 hover:text-white"
              }`}
              onClick={() => setMobileSearchOpen((open) => !open)}
            >
              ⌕
            </button>
            <Link
              href="/settings"
              className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-bb-border/60 text-sm text-bb-muted transition hover:border-bb-gold/40 hover:text-white"
              title="Settings"
            >
              ⚙
            </Link>
          </div>

          {mobileSearchOpen ? (
            <div className="border-t border-bb-border/30 px-2 py-2 lg:hidden">
              <PlayerSearch
                className="max-w-none"
                dropdownPlacement="overlay"
                onNavigate={() => setMobileSearchOpen(false)}
              />
            </div>
          ) : null}

          <div className="flex items-center justify-between gap-2 border-t border-bb-border/30 px-3 py-1.5 lg:hidden">
            <SyncStatusBar compact />
            <SyncButton compact />
          </div>

          {/* Desktop header */}
          <div className="hidden min-w-0 items-center justify-between gap-3 px-6 py-2 lg:flex">
            <div className="min-w-0 flex-1">
              <LeagueSwitcher leagues={leagues} activeLeagueId={resolvedLeagueId} />
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <PlayerSearch />
              <div className="flex items-center gap-2 rounded-lg border border-bb-border/50 bg-black/20 px-2 py-1.5">
                <SyncStatusBar />
                <SyncButton />
              </div>
              <Link
                href="/settings"
                className="rounded-lg border border-bb-border/60 px-2.5 py-1.5 text-sm text-bb-muted transition hover:border-bb-gold/40 hover:text-white"
                title="Settings"
              >
                ⚙
              </Link>
            </div>
          </div>
        </header>

        <main className="flex min-w-0 flex-1 flex-col pb-20 lg:pb-0">{children}</main>
      </div>

      <AdvisorShell
        leagueId={resolvedLeagueId}
        myRosterId={myRosterId ?? undefined}
        pageContext={advisorContext}
      />
    </div>
  );
}
