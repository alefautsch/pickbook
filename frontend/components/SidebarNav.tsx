"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { buildNavItems, resolveActiveNav } from "@/lib/nav";

type SidebarNavProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
};

export function SidebarNav({ leagues, activeLeagueId }: SidebarNavProps) {
  const pathname = usePathname();
  const activeLeague = leagues.find((l) => l.league_id === activeLeagueId) ?? leagues[0];
  const leagueId = activeLeague?.league_id;
  const myRosterId = activeLeague?.my_roster_id;
  const leagueBase = leagueId ? `/leagues/${leagueId}` : "/";

  const [hash, setHash] = useState("");
  useEffect(() => {
    const sync = () => setHash(window.location.hash);
    sync();
    window.addEventListener("hashchange", sync);
    return () => window.removeEventListener("hashchange", sync);
  }, [pathname]);

  const active = resolveActiveNav(pathname, hash, leagueId, myRosterId);
  const items = buildNavItems(leagueId, myRosterId);

  return (
    <aside className="hidden w-32 shrink-0 flex-col border-r border-bb-border/60 bg-[#0a0e14]/90 lg:flex">
      <div className="border-b border-bb-border/40 px-3 py-4">
        <Link href={leagueBase} className="block">
          <div className="flex items-center gap-1.5">
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-bb-gold/15 text-xs font-bold text-bb-gold">
              B
            </span>
            <div className="min-w-0">
              <p className="truncate text-[9px] font-semibold uppercase tracking-normal text-bb-gold">
                Blackbook
              </p>
              <p className="truncate text-[8px] uppercase tracking-wider text-bb-muted">
                Command Center
              </p>
            </div>
          </div>
        </Link>
      </div>

      <nav className="flex flex-1 flex-col gap-0.5 px-2 py-4">
        {items.map((item) => {
          const isActive = active === item.key;
          return (
            <Link
              key={item.key}
              href={item.href}
              className={`relative rounded-lg px-2 py-2.5 text-xs transition ${
                isActive
                  ? "bg-bb-gold/10 font-medium text-bb-gold"
                  : "text-bb-muted hover:bg-white/5 hover:text-white"
              }`}
            >
              {isActive ? (
                <span className="absolute bottom-2 left-0 top-2 w-0.5 rounded-full bg-bb-gold" />
              ) : null}
              <span className={isActive ? "pl-2" : ""}>{item.label}</span>
            </Link>
          );
        })}
      </nav>

      {activeLeague?.my_team_name ? (
        <div className="border-t border-bb-border/40 px-3 py-3">
          <p className="truncate text-sm font-medium text-white">
            {activeLeague.my_team_name}
          </p>
          <p className="truncate text-xs text-bb-muted">{activeLeague.name}</p>
        </div>
      ) : null}
    </aside>
  );
}
