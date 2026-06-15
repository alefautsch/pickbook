import { notFound } from "next/navigation";
import { ApiUnavailable } from "@/components/ApiUnavailable";
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
  } catch (err) {
    const message = err instanceof Error ? err.message : "";
    if (message.includes("fetch failed") || message.includes("ECONNREFUSED") || message.includes("500")) {
      return <ApiUnavailable />;
    }
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
      <TradeCalculator leagueId={leagueId} />
    </AppShell>
  );
}
