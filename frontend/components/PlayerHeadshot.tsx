"use client";

import Image from "next/image";
import { useState } from "react";
import { positionColor } from "@/lib/ovr";

type PlayerHeadshotProps = {
  src: string;
  alt: string;
  position: string | null;
  className?: string;
  sizes?: string;
};

export function PlayerHeadshot({
  src,
  alt,
  position,
  className = "h-16 w-16",
  sizes = "64px",
}: PlayerHeadshotProps) {
  const [failed, setFailed] = useState(false);
  const color = positionColor(position);

  if (failed) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-bb-border font-bold ${className}`}
        style={{ background: `color-mix(in srgb, ${color} 25%, #1e293b)`, color }}
      >
        {position ?? "?"}
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden rounded-lg border border-bb-border bg-bb-surface ${className}`}>
      <Image
        src={src}
        alt={alt}
        fill
        className="object-cover"
        sizes={sizes}
        onError={() => setFailed(true)}
      />
    </div>
  );
}
