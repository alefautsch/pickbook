"use client";

import { useEffect } from "react";

function scrollToHashTarget(id: string) {
  const el = document.getElementById(id);
  if (!el) return;

  const header = document.querySelector("header");
  const offset = (header?.getBoundingClientRect().height ?? 88) + 8;
  const top = el.getBoundingClientRect().top + window.scrollY - offset;
  window.scrollTo({ top: Math.max(0, top), behavior: "smooth" });
}

export function HashScroll() {
  useEffect(() => {
    const id = window.location.hash.slice(1);
    if (!id) return;

    // Wait for layout so sticky header height is accurate.
    const timer = window.setTimeout(() => scrollToHashTarget(id), 50);
    return () => window.clearTimeout(timer);
  }, []);

  return null;
}
