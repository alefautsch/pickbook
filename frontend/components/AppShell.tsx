import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { AdvisorShell } from "./AdvisorShell";
import type { AdvisorPageContext } from "./AdvisorContext";
import { LeagueSwitcher } from "./LeagueSwitcher";
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
  const resolvedLeagueId =
    activeLeagueId ?? leagues[0]?.league_id;
  const myRosterId =
    leagues.find((l) => l.league_id === resolvedLeagueId)?.my_roster_id ?? undefined;

  return (
    <div className="flex min-h-full">
      <SidebarNav leagues={leagues} activeLeagueId={resolvedLeagueId} />

      <div className="flex min-h-full min-w-0 flex-1 flex-col">
        <header className="border-b border-bb-border/40 bg-[#0a0e14]/80 px-4 py-2 sm:px-6">
          <div className="flex min-w-0 items-center justify-between gap-3">
            <LeagueSwitcher leagues={leagues} activeLeagueId={resolvedLeagueId} />
            <div className="flex shrink-0 items-center gap-2">
              <div className="hidden sm:block">
                <PlayerSearch />
              </div>
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
        <main className="flex flex-1 flex-col">{children}</main>
      </div>

      <AdvisorShell
        leagueId={resolvedLeagueId}
        myRosterId={myRosterId ?? undefined}
        pageContext={advisorContext}
      />
    </div>
  );
}
