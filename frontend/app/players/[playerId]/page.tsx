import { notFound } from "next/navigation";
import { AppShell } from "@/components/AppShell";
import { PlayerHero } from "@/components/PlayerHero";
import { PlayerPageSections } from "@/components/PlayerPageSections";
import {
  getLeagues,
  getPlayer,
  getPlayerGameLog,
  getPlayerHistory,
  getPlayerHoldings,
} from "@/lib/api";

type PageProps = {
  params: Promise<{ playerId: string }>;
  searchParams: Promise<{ league_id?: string }>;
};

export default async function PlayerPage({ params, searchParams }: PageProps) {
  const { playerId } = await params;
  const { league_id: leagueId } = await searchParams;

  if (!leagueId) {
    notFound();
  }

  let leagues = [];
  let player;
  let history = null;
  let holdings = null;
  let gameLog = null;

  try {
    [leagues, player, history, holdings, gameLog] = await Promise.all([
      getLeagues(),
      getPlayer(playerId, leagueId),
      getPlayerHistory(playerId, leagueId).catch(() => null),
      getPlayerHoldings(playerId).catch(() => null),
      getPlayerGameLog(playerId, leagueId).catch(() => null),
    ]);
  } catch {
    notFound();
  }

  return (
    <AppShell
      leagues={leagues}
      activeLeagueId={leagueId}
      advisorContext={{
        pageType: "player",
        playerId,
        playerName: player.player_name ?? undefined,
        summary: `${player.player_name ?? "Player"} · OVR ${player.ovr ?? "—"}`,
      }}
    >
      <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-8 md:px-10">
        <PlayerHero player={player} />
        <PlayerPageSections
          player={player}
          playerId={playerId}
          leagueId={leagueId}
          history={history}
          holdings={holdings}
          gameLog={gameLog}
        />
      </div>
    </AppShell>
  );
}
