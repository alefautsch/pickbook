"use client";

import { useEffect, useId, useRef, useState } from "react";

export type DarkSelectOption = {
  value: string;
  label: string;
  hint?: string;
};

type DarkSelectProps = {
  value: string;
  onChange: (value: string) => void;
  options: DarkSelectOption[];
  placeholder?: string;
  className?: string;
  accent?: "gold" | "sky" | "default";
  disabled?: boolean;
};

const accentRing: Record<NonNullable<DarkSelectProps["accent"]>, string> = {
  gold: "focus-within:border-bb-gold/50 focus-within:ring-bb-gold/20",
  sky: "focus-within:border-sky-500/50 focus-within:ring-sky-500/20",
  default: "focus-within:border-bb-gold/40 focus-within:ring-bb-gold/15",
};

const accentSelected: Record<NonNullable<DarkSelectProps["accent"]>, string> = {
  gold: "bg-bb-gold/10 text-bb-gold",
  sky: "bg-sky-500/10 text-sky-300",
  default: "bg-white/8 text-white",
};

export function DarkSelect({
  value,
  onChange,
  options,
  placeholder = "Select…",
  className = "",
  accent = "default",
  disabled = false,
}: DarkSelectProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();
  const selected = options.find((opt) => opt.value === value);

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((prev) => !prev)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border border-bb-border/60 bg-[#121820] px-3 py-2 text-left text-sm text-white shadow-inner shadow-black/20 transition focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${accentRing[accent]}`}
      >
        <span className="min-w-0 truncate">
          {selected ? (
            <>
              <span className="font-medium">{selected.label}</span>
              {selected.hint ? (
                <span className="ml-1.5 text-xs text-bb-muted">{selected.hint}</span>
              ) : null}
            </>
          ) : (
            <span className="text-bb-muted">{placeholder}</span>
          )}
        </span>
        <span
          className={`shrink-0 text-[10px] text-bb-muted transition ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          ▾
        </span>
      </button>

      {open ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-bb-border/70 bg-[#0f1419] py-1 shadow-2xl ring-1 ring-black/40"
        >
          {options.map((option) => {
            const isSelected = option.value === value;
            return (
              <li key={option.value} role="option" aria-selected={isSelected}>
                <button
                  type="button"
                  className={`flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm transition hover:bg-white/6 ${
                    isSelected ? accentSelected[accent] : "text-white/90"
                  }`}
                  onClick={() => {
                    onChange(option.value);
                    setOpen(false);
                  }}
                >
                  <span className="min-w-0 truncate font-medium">{option.label}</span>
                  {option.hint ? (
                    <span className="shrink-0 text-xs text-bb-muted">{option.hint}</span>
                  ) : null}
                </button>
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
}

type DarkMenuProps = {
  label: string;
  options: DarkSelectOption[];
  onSelect: (value: string) => void;
  className?: string;
  accent?: "gold" | "sky" | "default";
  disabled?: boolean;
};

export function DarkMenu({
  label,
  options,
  onSelect,
  className = "",
  accent = "default",
  disabled = false,
}: DarkMenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    function onPointerDown(event: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    }
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  if (options.length === 0) return null;

  return (
    <div ref={rootRef} className={`relative ${className}`}>
      <button
        type="button"
        disabled={disabled}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        onClick={() => setOpen((prev) => !prev)}
        className={`flex w-full items-center justify-between gap-2 rounded-lg border border-dashed border-bb-border/50 bg-black/20 px-3 py-2 text-left text-sm text-bb-muted transition hover:border-bb-border/80 hover:bg-black/30 hover:text-white focus:outline-none focus-visible:ring-2 disabled:cursor-not-allowed disabled:opacity-50 ${accentRing[accent]}`}
      >
        <span className="truncate">{label}</span>
        <span
          className={`shrink-0 text-[10px] transition ${open ? "rotate-180" : ""}`}
          aria-hidden
        >
          ▾
        </span>
      </button>

      {open ? (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-56 w-full overflow-auto rounded-lg border border-bb-border/70 bg-[#0f1419] py-1 shadow-2xl ring-1 ring-black/40"
        >
          {options.map((option) => (
            <li key={option.value} role="option">
              <button
                type="button"
                className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left text-sm text-white/90 transition hover:bg-white/6"
                onClick={() => {
                  onSelect(option.value);
                  setOpen(false);
                }}
              >
                <span className="min-w-0 truncate">{option.label}</span>
                {option.hint ? (
                  <span className="shrink-0 text-xs tabular-nums text-bb-muted">
                    {option.hint}
                  </span>
                ) : null}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
