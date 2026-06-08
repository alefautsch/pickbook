import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { RookieDraftPanel } from "@/components/RookieDraftPanel";
import { getLeagues, getRookieDraft } from "@/lib/api";

type PageProps = {
  params: Promise<{ leagueId: string }>;
};

export default async function RookieDraftPage({ params }: PageProps) {
  const { leagueId } = await params;

  let leagues = [];
  let draft = null;

  try {
    leagues = await getLeagues();
    draft = await getRookieDraft(leagueId);
  } catch {
    notFound();
  }

  if (!draft) {
    notFound();
  }

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{ pageType: "rookie-draft", summary: "Rookie draft prep" }}
    >
      <RookieDraftPanel leagueId={leagueId} initial={draft} />
    </AppShell>
  );
}
