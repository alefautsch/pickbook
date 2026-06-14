import { sleeperAvatarThumbUrl } from "@/lib/teamLogos";

type SleeperAvatarWatermarkProps = {
  avatarUrl: string | null | undefined;
  className?: string;
};

export function SleeperAvatarWatermark({
  avatarUrl,
  className = "",
}: SleeperAvatarWatermarkProps) {
  const src = sleeperAvatarThumbUrl(avatarUrl);
  if (!src) return null;

  return (
    <img
      src={src}
      alt=""
      aria-hidden
      className={`pointer-events-none absolute -right-6 top-1/2 h-44 w-44 -translate-y-1/2 object-contain opacity-[0.14] blur-[0.5px] sm:-right-4 sm:h-56 sm:w-56 sm:opacity-[0.18] md:h-64 md:w-64 ${className}`}
    />
  );
}

type TeamAvatarProps = {
  avatarUrl: string | null | undefined;
  teamName: string | null | undefined;
  className?: string;
};

export function TeamAvatar({ avatarUrl, teamName, className = "" }: TeamAvatarProps) {
  if (!avatarUrl) return null;

  return (
    <img
      src={avatarUrl}
      alt=""
      aria-hidden
      className={`shrink-0 rounded-xl object-cover ring-1 ring-white/10 ${className}`}
      title={teamName ?? undefined}
    />
  );
}
