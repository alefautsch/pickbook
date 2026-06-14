"use client";

import { useEffect, useState } from "react";
import { FONT_CATALOG, type FontId, fontFamilyStyle } from "@/lib/fonts";
import { readFontPreference, writeFontPreference } from "@/lib/fontPreference";

export function FontPicker() {
  const [active, setActive] = useState<FontId | null>(null);

  useEffect(() => {
    setActive(readFontPreference());
  }, []);

  if (active == null) {
    return <p className="text-sm text-bb-muted">Loading fonts…</p>;
  }

  return (
    <div className="mt-4 grid gap-2 sm:grid-cols-2">
      {FONT_CATALOG.map((font) => {
        const selected = active === font.id;
        return (
          <button
            key={font.id}
            type="button"
            onClick={() => {
              writeFontPreference(font.id);
              setActive(font.id);
            }}
            className={`rounded-lg px-3 py-3 text-left ring-1 ring-inset transition ${
              selected
                ? "bg-bb-gold/10 ring-bb-gold/50"
                : "bg-white/3 ring-white/8 hover:bg-white/5 hover:ring-white/12"
            }`}
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-semibold text-white">{font.label}</p>
              {selected ? (
                <span className="shrink-0 text-[10px] font-semibold uppercase tracking-wide text-bb-gold">
                  Active
                </span>
              ) : null}
            </div>
            <p className="mt-0.5 text-xs text-bb-muted">{font.hint}</p>
            <p
              className="mt-2 text-base font-semibold text-white"
              style={{ fontFamily: fontFamilyStyle(font.id) }}
            >
              The Process · 88 OVR
            </p>
            <p
              className="mt-0.5 text-xs text-bb-muted"
              style={{ fontFamily: fontFamilyStyle(font.id) }}
            >
              Bo Nix · 130.8 PPG · 74.3k TV
            </p>
          </button>
        );
      })}
    </div>
  );
}
