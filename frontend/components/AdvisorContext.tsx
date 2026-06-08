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
  focusedRosterId: string | undefined;
  pageContext: AdvisorPageContext;
  setPageContext: (ctx: AdvisorPageContext) => void;
  setFocusedRosterId: (rosterId: string | undefined) => void;
};

const AdvisorContext = createContext<AdvisorContextValue | null>(null);

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
  const [focusedRosterId, setFocusedRosterId] = useState<string | undefined>(
    initialPageContext?.rosterId ?? myRosterId,
  );

  const value = useMemo(
    () => ({
      leagueId,
      focusedRosterId: focusedRosterId ?? myRosterId,
      pageContext,
      setPageContext,
      setFocusedRosterId,
    }),
    [leagueId, focusedRosterId, myRosterId, pageContext],
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
  focusedRosterId,
}: {
  pageContext: AdvisorPageContext;
  focusedRosterId?: string;
}) {
  const { setPageContext, setFocusedRosterId } = useAdvisorContext();

  useEffect(() => {
    setPageContext(pageContext);
    if (focusedRosterId) setFocusedRosterId(focusedRosterId);
  }, [pageContext, focusedRosterId, setPageContext, setFocusedRosterId]);

  return null;
}
