import { redirect } from "next/navigation";
import { getLeagues } from "@/lib/api";

const DEFAULT_LEAGUE_ID = "1314731206859853824";

export default async function Home() {
  let leagues = [];
  try {
    leagues = await getLeagues();
  } catch {
    redirect(`/leagues/${DEFAULT_LEAGUE_ID}`);
  }

  const preferred =
    leagues.find((l) => l.league_id === DEFAULT_LEAGUE_ID) ?? leagues[0];

  if (preferred) {
    redirect(`/leagues/${preferred.league_id}`);
  }

  return null;
}
