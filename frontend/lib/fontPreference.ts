import {
  DEFAULT_FONT_ID,
  FONT_STORAGE_KEY,
  type FontId,
  isFontId,
} from "@/lib/fonts";

export function readFontPreference(): FontId {
  if (typeof window === "undefined") return DEFAULT_FONT_ID;
  try {
    const stored = window.localStorage.getItem(FONT_STORAGE_KEY);
    return isFontId(stored) ? stored : DEFAULT_FONT_ID;
  } catch {
    return DEFAULT_FONT_ID;
  }
}

export function writeFontPreference(id: FontId): void {
  window.localStorage.setItem(FONT_STORAGE_KEY, id);
  applyFontPreference(id);
}

export function applyFontPreference(id: FontId): void {
  document.documentElement.dataset.font = id;
}
