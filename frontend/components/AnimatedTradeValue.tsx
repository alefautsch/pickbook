"use client";

import { useEffect, useRef, useState } from "react";
import { formatTv } from "@/lib/format";

const DIGITS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9"];
const TICK_MS = 420;

type AnimatedTradeValueProps = {
  value: number;
  className?: string;
};

function OdometerDigit({ digit }: { digit: string }) {
  if (!/\d/.test(digit)) {
    return <span className="inline-block">{digit}</span>;
  }

  const index = Number(digit);
  return (
    <span className="relative inline-block h-[1em] w-[0.62em] overflow-hidden align-bottom">
      <span
        className="flex flex-col transition-transform duration-500 ease-[cubic-bezier(0.22,1,0.36,1)] will-change-transform"
        style={{ transform: `translateY(-${index * 10}%)` }}
      >
        {DIGITS.map((d) => (
          <span key={d} className="block h-[1em] leading-none tabular-nums">
            {d}
          </span>
        ))}
      </span>
    </span>
  );
}

export function AnimatedTradeValue({ value, className = "" }: AnimatedTradeValueProps) {
  const displayRef = useRef(value);
  const [displayValue, setDisplayValue] = useState(value);
  const [direction, setDirection] = useState<"up" | "down" | null>(null);
  const rafRef = useRef<number | null>(null);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const from = displayRef.current;
    const to = value;
    if (from === to) return;

    setDirection(to > from ? "up" : "down");
    const start = performance.now();

    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / TICK_MS);
      const eased = 1 - (1 - t) ** 3;
      const next = Math.round(from + (to - from) * eased);
      displayRef.current = next;
      setDisplayValue(next);

      if (t < 1) {
        rafRef.current = requestAnimationFrame(tick);
      } else {
        displayRef.current = to;
        setDisplayValue(to);
        if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
        timeoutRef.current = window.setTimeout(() => setDirection(null), 550);
      }
    };

    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      if (timeoutRef.current) window.clearTimeout(timeoutRef.current);
    };
  }, [value]);

  const formatted = formatTv(displayValue);
  const directionClass =
    direction === "up"
      ? "text-emerald-300 drop-shadow-[0_0_10px_rgba(52,211,153,0.45)]"
      : direction === "down"
        ? "text-rose-300 drop-shadow-[0_0_10px_rgba(251,113,133,0.45)]"
        : "";

  return (
    <span
      className={`inline-flex items-baseline transition-colors duration-300 ${directionClass} ${className}`}
      aria-live="polite"
      aria-atomic="true"
    >
      {formatted.split("").map((char, idx) => (
        <OdometerDigit key={idx} digit={char} />
      ))}
    </span>
  );
}
