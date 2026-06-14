/** NFL team logo URLs (public CDN). */

const NFL_LOGO_BASE =
  "https://static.www.nfl.com/t_headshot_desktop/f_auto/league/api/clubs/logos";

const SLEEPER_AVATAR_BASE = "https://sleepercdn.com/avatars";

export function nflTeamLogoUrl(team: string | null | undefined): string | null {
  const abbr = (team || "").trim().toUpperCase();
  if (!abbr || abbr.length < 2) return null;
  return `${NFL_LOGO_BASE}/${abbr}.png`;
}

export function sleeperAvatarThumbUrl(
  avatarUrl: string | null | undefined,
): string | null {
  if (!avatarUrl) return null;
  return avatarUrl.replace("/avatars/", "/avatars/thumbs/");
}
