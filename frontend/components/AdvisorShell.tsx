"use client";

import { useState } from "react";
import { AdvisorProvider, type AdvisorPageContext } from "./AdvisorContext";
import { AdvisorWidget } from "./AdvisorWidget";

type AdvisorShellProps = {
  leagueId?: string;
  myRosterId?: string;
  pageContext?: AdvisorPageContext;
};

export function AdvisorShell({
  leagueId,
  myRosterId,
  pageContext,
}: AdvisorShellProps) {
  const [open, setOpen] = useState(false);

  if (!leagueId) return null;

  return (
    <AdvisorProvider
      key={leagueId}
      leagueId={leagueId}
      myRosterId={myRosterId ?? undefined}
      pageContext={pageContext}
    >
      <AdvisorWidget open={open} onOpenChange={setOpen} />
    </AdvisorProvider>
  );
}
