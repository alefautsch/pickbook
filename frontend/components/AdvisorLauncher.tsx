"use client";

import { useState } from "react";
import { AdvisorPanel } from "./AdvisorPanel";

type AdvisorLauncherProps = {
  leagueId?: string;
};

export function AdvisorLauncher({ leagueId }: AdvisorLauncherProps) {
  const [open, setOpen] = useState(false);

  if (!leagueId) return null;

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="rounded-lg border border-bb-gold/30 bg-bb-gold/10 px-2.5 py-1.5 text-sm font-medium text-bb-gold transition hover:bg-bb-gold/20"
        title="Open dynasty advisor"
      >
        Advisor
      </button>
      <AdvisorPanel
        leagueId={leagueId}
        open={open}
        onClose={() => setOpen(false)}
      />
    </>
  );
}
