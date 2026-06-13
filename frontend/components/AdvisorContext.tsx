"use client";

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

export type AdvisorPageContext = {
  pageType: string;
  path?: string;
  rosterId?: string;
  playerId?: string;
  playerName?: string;
  summary?: string;
};

type AdvisorContextValue = {
  leagueId: string | undefined;
  myRosterId: string | undefined;
  /** Trade-tool proposer (suggest_trades / validate_trade). Defaults to my team. */
  tradePerspectiveRosterId: string | undefined;
  setTradePerspectiveRosterId: (rosterId: string | undefined) => void;
  /** Sent as focused_roster_id — drives trade surplus + packages. */
  focusedRosterId: string | undefined;
  pageContext: AdvisorPageContext;
  setPageContext: (ctx: AdvisorPageContext) => void;
};

const AdvisorContext = createContext<AdvisorContextValue | null>(null);

const perspectiveStorageKey = (leagueId: string) =>
  `bb-advisor-trade-perspective:${leagueId}`;

type AdvisorProviderProps = {
  leagueId?: string;
  myRosterId?: string;
  pageContext?: AdvisorPageContext;
  children: ReactNode;
};

export function AdvisorProvider({
  leagueId,
  myRosterId,
  pageContext: initialPageContext,
  children,
}: AdvisorProviderProps) {
  const [pageContext, setPageContext] = useState<AdvisorPageContext>(
    initialPageContext ?? { pageType: "unknown" },
  );
  const [tradePerspectiveRosterId, setTradePerspectiveRosterId] = useState<
    string | undefined
  >(undefined);

  useEffect(() => {
    if (!leagueId || typeof window === "undefined") {
      setTradePerspectiveRosterId(undefined);
      return;
    }
    const stored = window.localStorage.getItem(perspectiveStorageKey(leagueId));
    if (stored) {
      setTradePerspectiveRosterId(stored);
      return;
    }
    setTradePerspectiveRosterId(myRosterId);
  }, [leagueId, myRosterId]);

  useEffect(() => {
    if (!leagueId || typeof window === "undefined") return;
    const id = tradePerspectiveRosterId ?? myRosterId;
    if (!id) return;
    window.localStorage.setItem(perspectiveStorageKey(leagueId), id);
  }, [leagueId, myRosterId, tradePerspectiveRosterId]);

  const focusedRosterId = tradePerspectiveRosterId ?? myRosterId;

  const value = useMemo(
    () => ({
      leagueId,
      myRosterId,
      tradePerspectiveRosterId,
      setTradePerspectiveRosterId,
      focusedRosterId,
      pageContext,
      setPageContext,
    }),
    [
      leagueId,
      myRosterId,
      tradePerspectiveRosterId,
      focusedRosterId,
      pageContext,
    ],
  );

  return (
    <AdvisorContext.Provider value={value}>{children}</AdvisorContext.Provider>
  );
}

export function useAdvisorContext() {
  const ctx = useContext(AdvisorContext);
  if (!ctx) {
    throw new Error("useAdvisorContext must be used within AdvisorProvider");
  }
  return ctx;
}

/** Sync page-level advisor context from a client child (optional pattern). */
export function AdvisorPageBinder({
  pageContext,
}: {
  pageContext: AdvisorPageContext;
  /** @deprecated Trade perspective is chosen in the advisor dropdown, not from navigation. */
  focusedRosterId?: string;
}) {
  const { setPageContext } = useAdvisorContext();

  useEffect(() => {
    setPageContext(pageContext);
  }, [pageContext, setPageContext]);

  return null;
}
