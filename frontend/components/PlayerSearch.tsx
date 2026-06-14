"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useRef, useState } from "react";
import { searchPlayers, type PlayerSearchHit } from "@/lib/api";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PlayerName } from "./PlayerName";
import { PositionTag } from "./PositionPill";

type PlayerSearchProps = {
  dropdownPlacement?: "down" | "up" | "overlay";
  className?: string;
  onNavigate?: () => void;
};

export function PlayerSearch({
  dropdownPlacement = "down",
  className,
  onNavigate,
}: PlayerSearchProps) {
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<PlayerSearchHit[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const inputId = useId();

  const runSearch = useCallback(async (value: string) => {
    const trimmed = value.trim();
    if (trimmed.length < 2) {
      setHits([]);
      return;
    }
    setLoading(true);
    try {
      const result = await searchPlayers(trimmed);
      setHits(result.hits);
    } catch {
      setHits([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void runSearch(query);
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query, runSearch]);

  useEffect(() => {
    function onClickOutside(event: MouseEvent) {
      if (
        containerRef.current &&
        !containerRef.current.contains(event.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClickOutside);
    return () => document.removeEventListener("mousedown", onClickOutside);
  }, []);

  const dropdownClass =
    dropdownPlacement === "overlay"
      ? "fixed left-3 right-3 top-[calc(env(safe-area-inset-top)+5.75rem)] z-[60] max-h-[min(20rem,calc(100dvh-7rem))]"
      : dropdownPlacement === "up"
        ? "absolute bottom-full z-50 mb-2 max-h-64"
        : "absolute top-full z-50 mt-2 max-h-80";

  return (
    <div ref={containerRef} className={`relative w-full max-w-xs ${className ?? ""}`}>
      <label className="sr-only" htmlFor={inputId}>
        Search players
      </label>
      <input
        id={inputId}
        type="search"
        placeholder="Search players…"
        value={query}
        onChange={(event) => {
          setQuery(event.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        className="w-full rounded-lg border border-bb-border bg-black/30 px-3 py-2 text-sm text-white placeholder:text-bb-muted focus:border-bb-gold/60 focus:outline-none"
      />

      {open && query.trim().length >= 2 ? (
        <div
          className={`${dropdownClass} w-full overflow-y-auto rounded-lg border border-bb-border bg-bb-surface shadow-xl`}
        >
          {loading ? (
            <p className="px-3 py-2 text-sm text-bb-muted">Searching…</p>
          ) : hits.length === 0 ? (
            <p className="px-3 py-2 text-sm text-bb-muted">No matches</p>
          ) : (
            <ul>
              {hits.map((hit) => {
                const top = hit.leagues[0];
                return (
                  <li key={hit.player_id}>
                    <Link
                      href={`/players/${hit.player_id}?league_id=${top?.league_id ?? ""}`}
                      className="flex items-center gap-3 px-3 py-2 transition hover:bg-white/5"
                      onClick={() => {
                        setOpen(false);
                        setQuery("");
                        onNavigate?.();
                      }}
                    >
                      <PlayerHeadshot
                        src={hit.headshot_url}
                        alt={hit.player_name ?? "Player"}
                        position={hit.position}
                        className="h-10 w-10"
                        sizes="40px"
                      />
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-1.5">
                          <PlayerName as="p">{hit.player_name}</PlayerName>
                          {hit.position ? <PositionTag position={hit.position} /> : null}
                        </div>
                        <p className="truncate text-xs text-bb-muted">
                          {[
                            hit.nfl_team,
                            hit.leagues.map((l) => l.league_name).join(" · "),
                          ]
                            .filter(Boolean)
                            .join(" · ")}
                        </p>
                      </div>
                      {top?.ovr != null ? (
                        <OvrBadge ovr={top.ovr} size="sm" />
                      ) : null}
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ) : null}
    </div>
  );
}
