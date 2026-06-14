import type { ElementType, ReactNode } from "react";

const sizeClasses = {
  sm: "text-sm",
  base: "text-base",
  lg: "text-lg",
  hero: "text-xl font-bold sm:text-2xl lg:text-4xl",
} as const;

type PlayerNameSize = keyof typeof sizeClasses;

type PlayerNameProps = {
  children: ReactNode;
  as?: ElementType;
  size?: PlayerNameSize;
  className?: string;
  title?: string;
};

/** Consistent player name typography across lists, tables, and hero cards. */
export function PlayerName({
  children,
  as: Component = "span",
  size = "sm",
  className = "",
  title,
}: PlayerNameProps) {
  const classes = ["player-name", "truncate", sizeClasses[size], className]
    .filter(Boolean)
    .join(" ");

  return (
    <Component title={title} className={classes}>
      {children}
    </Component>
  );
}
