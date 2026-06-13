"use client";

import { useState, type ReactNode } from "react";

type MobilePanelCollapseProps = {
  title: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      viewBox="0 0 20 20"
      fill="currentColor"
      className={`h-4 w-4 shrink-0 text-bb-muted transition-transform ${expanded ? "rotate-180" : ""}`}
      aria-hidden
    >
      <path
        fillRule="evenodd"
        d="M5.23 7.21a.75.75 0 011.06.02L10 11.168l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export function MobilePanelCollapse({
  title,
  defaultOpen = false,
  children,
}: MobilePanelCollapseProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="mb-2 flex w-full items-center justify-between rounded-lg border border-bb-border/40 bg-black/20 px-3 py-2.5 text-left lg:hidden"
        aria-expanded={open}
      >
        <span className="text-sm font-medium text-white">{title}</span>
        <ChevronIcon expanded={open} />
      </button>
      <div className={open ? "block" : "hidden lg:block"}>{children}</div>
    </div>
  );
}
