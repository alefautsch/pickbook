"use client";

import { useEffect } from "react";
import { applyFontPreference, readFontPreference } from "@/lib/fontPreference";

/** Re-apply stored font on client navigations (inline script handles first paint). */
export function FontBootstrap() {
  useEffect(() => {
    applyFontPreference(readFontPreference());
  }, []);

  return null;
}
