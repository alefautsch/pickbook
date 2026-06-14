/** NFL team logo URLs (public CDN). */

const NFL_LOGO_BASE =
  "https://static.www.nfl.com/t_headshot_desktop/f_auto/league/api/clubs/logos";

export function nflTeamLogoUrl(team: string | null | undefined): string | null {
  const abbr = (team || "").trim().toUpperCase();
  if (!abbr || abbr.length < 2) return null;
  return `${NFL_LOGO_BASE}/${abbr}.png`;
}
