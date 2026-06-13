"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { buildNavItems, resolveActiveNav } from "@/lib/nav";
import { PlayerSearch } from "./PlayerSearch";
import { SyncButton } from "./SyncButton";
import { SyncStatusBar } from "./SyncStatusBar";

const PICKBOOK_URL =
  process.env.NEXT_PUBLIC_PICKBOOK_URL ??
  (process.env.NODE_ENV === "development" ? "http://localhost:8501" : "");

type MobileNavProps = {
  leagues: LeagueTileData[];
  activeLeagueId?: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
};

export function MobileNav({
  leagues,
  activeLeagueId,
  open,
  onOpenChange,
}: MobileNavProps) {
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

  useEffect(() => {
    onOpenChange(false);
  }, [pathname, onOpenChange]);

  useEffect(() => {
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [open]);

  const active = resolveActiveNav(pathname, hash, leagueId, myRosterId);
  const items = buildNavItems(leagueId, myRosterId);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 lg:hidden">
      <button
        type="button"
        aria-label="Close menu"
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={() => onOpenChange(false)}
      />
      <aside className="absolute inset-y-0 left-0 flex w-[min(18rem,85vw)] flex-col border-r border-bb-border/60 bg-[#0a0e14] shadow-2xl">
        <div className="border-b border-bb-border/40 px-4 py-4">
          <Link href={leagueBase} className="block" onClick={() => onOpenChange(false)}>
            <div className="flex items-center gap-2">
              <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-bb-gold/15 text-sm font-bold text-bb-gold">
                B
              </span>
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-normal text-bb-gold">
                  Blackbook
                </p>
                <p className="text-[10px] uppercase tracking-wider text-bb-muted">
                  Command Center
                </p>
              </div>
            </div>
          </Link>
        </div>

        <nav className="flex flex-1 flex-col gap-0.5 overflow-y-auto px-3 py-4">
          {items.map((item) => {
            const isActive = active === item.key;
            return (
              <Link
                key={item.key}
                href={item.href}
                className={`relative rounded-lg px-3 py-3 text-sm transition ${
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

        <div className="border-t border-bb-border/40 px-4 py-3">
          <p className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-bb-muted">
            Search
          </p>
          <PlayerSearch dropdownPlacement="up" onNavigate={() => onOpenChange(false)} />
        </div>

        <div className="border-t border-bb-border/40 px-4 py-3">
          <SyncStatusBar compact />
          <div className="mt-2">
            <SyncButton />
          </div>
        </div>

        {activeLeague?.my_team_name ? (
          <div className="border-t border-bb-border/40 px-4 py-3">
            <p className="truncate text-sm font-medium text-white">
              {activeLeague.my_team_name}
            </p>
            <p className="truncate text-xs text-bb-muted">{activeLeague.name}</p>
          </div>
        ) : null}

        {PICKBOOK_URL ? (
          <div className="border-t border-bb-border/40 px-4 py-4">
            <a
              href={PICKBOOK_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between rounded-lg border border-bb-gold/30 bg-bb-gold/5 px-3 py-2.5 text-sm font-medium text-bb-gold transition hover:bg-bb-gold/10"
            >
              <span>View Pickbook</span>
              <span>↗</span>
            </a>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
