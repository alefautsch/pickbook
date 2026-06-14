export type NavKey =
  | "overview"
  | "league"
  | "my-team"
  | "trade"
  | "rankings"
  | "players"
  | "portfolio"
  | "rookie-draft"
  | "settings";

export type NavItem = { key: NavKey; label: string; href: string };

export function resolveActiveNav(
  pathname: string,
  hash: string,
  leagueId?: string,
  myRosterId?: string | null,
): NavKey | null {
  if (pathname.startsWith("/settings")) return "settings";
  if (pathname.startsWith("/portfolio")) return "portfolio";
  if (pathname.startsWith("/players")) return "players";

  if (leagueId) {
    const leagueBase = `/leagues/${leagueId}`;
    if (pathname.startsWith(`${leagueBase}/rookie-draft`)) {
      return "rookie-draft";
    }
    if (pathname.startsWith(`${leagueBase}/trade`)) {
      return "trade";
    }
    const leagueAnalysis = `${leagueBase}/league`;

    if (myRosterId && pathname.startsWith(`${leagueBase}/teams/${myRosterId}`)) {
      return "my-team";
    }
    if (pathname === leagueAnalysis || pathname.startsWith(`${leagueAnalysis}/`)) {
      return "league";
    }
    if (pathname === leagueBase && hash === "#rankings") {
      return "rankings";
    }
    if (pathname === leagueBase) {
      return "overview";
    }
  }

  if (pathname === "/") return "overview";
  return null;
}

export function buildNavItems(
  leagueId?: string,
  myRosterId?: string | null,
): NavItem[] {
  const leagueBase = leagueId ? `/leagues/${leagueId}` : "/";
  const myTeamHref =
    leagueId && myRosterId
      ? `/leagues/${leagueId}/teams/${myRosterId}`
      : leagueBase;

  return [
    { key: "overview", label: "Overview", href: leagueBase },
    { key: "league", label: "League", href: `${leagueBase}/league` },
    { key: "my-team", label: "My Team", href: myTeamHref },
    { key: "trade", label: "Trade Calc", href: `${leagueBase}/trade` },
    { key: "rankings", label: "Rankings", href: `${leagueBase}#rankings` },
    {
      key: "players",
      label: "Players",
      href: leagueId ? `/players?league_id=${leagueId}` : "/players",
    },
    { key: "portfolio", label: "Portfolio", href: "/portfolio" },
    { key: "rookie-draft", label: "Rookie Draft", href: `${leagueBase}/rookie-draft` },
    { key: "settings", label: "Settings", href: "/settings" },
  ];
}
