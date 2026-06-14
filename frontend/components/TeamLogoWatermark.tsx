import { nflTeamLogoUrl } from "@/lib/teamLogos";

type TeamLogoWatermarkProps = {
  team: string | null | undefined;
  className?: string;
};

export function TeamLogoWatermark({ team, className = "" }: TeamLogoWatermarkProps) {
  const src = nflTeamLogoUrl(team);
  if (!src) return null;

  return (
    <img
      src={src}
      alt=""
      aria-hidden
      className={`pointer-events-none absolute -right-4 top-1/2 h-40 w-40 -translate-y-1/2 object-contain opacity-[0.07] sm:h-52 sm:w-52 sm:opacity-[0.09] ${className}`}
    />
  );
}
