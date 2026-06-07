import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { LeagueSwitcher } from "./LeagueSwitcher";
import { SyncButton } from "./SyncButton";
import { SyncStatusBar } from "./SyncStatusBar";

type AppShellProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
  children: React.ReactNode;
};

export function AppShell({ leagues, activeLeagueId, children }: AppShellProps) {
  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-bb-border/80 bg-black/20 px-6 py-4 sm:px-10">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.2em] text-bb-gold">
              Dynasty Blackbook
            </p>
            <LeagueSwitcher leagues={leagues} activeLeagueId={activeLeagueId} />
          </div>
          <div className="flex flex-col items-start gap-2 sm:items-end">
            <SyncStatusBar />
            <SyncButton />
          </div>
        </div>
      </header>
      <div className="flex flex-1 flex-col">{children}</div>
    </div>
  );
}
