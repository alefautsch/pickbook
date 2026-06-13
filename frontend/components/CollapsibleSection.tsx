"use client";

import { useState, type ReactNode } from "react";

type CollapsibleSectionProps = {
  title: string;
  subtitle?: string;
  defaultOpen?: boolean;
  children: ReactNode;
  className?: string;
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

export function CollapsibleSection({
  title,
  subtitle,
  defaultOpen = false,
  children,
  className = "bb-panel",
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <section className={className}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between gap-2 p-3 text-left lg:hidden"
        aria-expanded={open}
      >
        <div className="min-w-0">
          <h2 className="bb-panel-title">{title}</h2>
          {subtitle ? <p className="mt-0.5 text-xs text-bb-muted">{subtitle}</p> : null}
        </div>
        <ChevronIcon expanded={open} />
      </button>

      <div className="hidden p-3 md:p-4 lg:block">
        <h2 className="bb-panel-title">{title}</h2>
        {subtitle ? <p className="mt-1 text-xs text-bb-muted">{subtitle}</p> : null}
        <div className="mt-3">{children}</div>
      </div>

      {open ? <div className="px-3 pb-3 lg:hidden">{children}</div> : null}
    </section>
  );
}
