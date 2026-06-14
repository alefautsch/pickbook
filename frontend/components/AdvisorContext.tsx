"use client";

import {
  createContext,
  useCallback,
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

function readStoredPerspective(
  leagueId: string | undefined,
  myRosterId: string | undefined,
): string | undefined {
  if (!leagueId || typeof window === "undefined") {
    return myRosterId;
  }
  return (
    window.localStorage.getItem(perspectiveStorageKey(leagueId)) ?? myRosterId
  );
}

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
  const [tradePerspectiveRosterId, setTradePerspectiveRosterIdState] = useState<
    string | undefined
  >(() => readStoredPerspective(leagueId, myRosterId));

  const setTradePerspectiveRosterId = useCallback(
    (rosterId: string | undefined) => {
      setTradePerspectiveRosterIdState(rosterId);
      if (leagueId && typeof window !== "undefined" && rosterId) {
        window.localStorage.setItem(perspectiveStorageKey(leagueId), rosterId);
      }
    },
    [leagueId],
  );

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
      setTradePerspectiveRosterId,
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
