import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { TradeCalculator } from "@/components/TradeCalculator";
import { getLeagues } from "@/lib/api";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function TradeCalculatorPage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  try {
    leagues = await getLeagues();
  } catch {
    notFound();
  }

  const league = leagues.find((l) => l.league_id === leagueId);
  if (!league) notFound();

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{
        pageType: "trade",
        summary: "Trade Calculator",
      }}
    >
      <TradeCalculator
        leagueId={leagueId}
        defaultSideA={league.my_roster_id ?? undefined}
      />
    </AppShell>
  );
}
