/** Shared font catalog — ids must match `data-font` on `<html>`. */

export const FONT_CATALOG = [
  {
    id: "jakarta",
    label: "Plus Jakarta Sans",
    hint: "Warm, modern",
    cssVar: "--font-jakarta",
  },
  {
    id: "geist",
    label: "Geist Sans",
    hint: "Clean, neutral — default",
    cssVar: "--font-geist-sans",
  },
  {
    id: "plex",
    label: "IBM Plex Sans",
    hint: "Technical, editorial",
    cssVar: "--font-plex-sans",
  },
  {
    id: "dm",
    label: "DM Sans",
    hint: "Subtle geometric",
    cssVar: "--font-dm-sans",
  },
  {
    id: "sora",
    label: "Sora",
    hint: "Soft, slightly futuristic",
    cssVar: "--font-sora",
  },
  {
    id: "figtree",
    label: "Figtree",
    hint: "Friendly, approachable",
    cssVar: "--font-figtree",
  },
] as const;

export type FontId = (typeof FONT_CATALOG)[number]["id"];

export const DEFAULT_FONT_ID: FontId = "geist";

export const FONT_STORAGE_KEY = "bb-font-preference";

export const FONT_IDS: FontId[] = FONT_CATALOG.map((font) => font.id);

export function isFontId(value: string | null | undefined): value is FontId {
  return FONT_IDS.includes(value as FontId);
}

export function fontById(id: FontId) {
  return FONT_CATALOG.find((font) => font.id === id)!;
}

export function fontFamilyStyle(id: FontId): string {
  const cssVar = fontById(id).cssVar;
  return `var(${cssVar}), system-ui, sans-serif`;
}
