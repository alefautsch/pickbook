import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { LeagueSwitcher } from "./LeagueSwitcher";
import { PlayerSearch } from "./PlayerSearch";
import { SidebarNav } from "./SidebarNav";
import { AdvisorLauncher } from "./AdvisorLauncher";
import { SyncButton } from "./SyncButton";
import { SyncStatusBar } from "./SyncStatusBar";

type AppShellProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
  children: React.ReactNode;
};

export function AppShell({ leagues, activeLeagueId, children }: AppShellProps) {
  const resolvedLeagueId =
    activeLeagueId ?? leagues[0]?.league_id;

  return (
    <div className="flex min-h-full">
      <SidebarNav leagues={leagues} activeLeagueId={resolvedLeagueId} />

      <div className="flex min-h-full min-w-0 flex-1 flex-col">
        <header className="border-b border-bb-border/40 bg-[#0a0e14]/80 px-5 py-2 sm:px-8">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <LeagueSwitcher leagues={leagues} activeLeagueId={resolvedLeagueId} />
            <div className="flex flex-wrap items-center gap-3 lg:justify-end">
              <PlayerSearch />
              <AdvisorLauncher leagueId={resolvedLeagueId} />
              <div className="flex items-center gap-2 rounded-lg border border-bb-border/50 bg-black/20 px-3 py-1.5">
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
    </div>
  );
}
