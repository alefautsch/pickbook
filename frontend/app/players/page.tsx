import { AppShell } from "@/components/AppShell";
import { PlayerSearch } from "@/components/PlayerSearch";
import { getLeagues } from "@/lib/api";

export default async function PlayersPage() {
  const leagues = await getLeagues().catch(() => []);

  return (
    <AppShell leagues={leagues}>
      <div className="flex flex-1 flex-col px-3 py-4 sm:px-6 sm:py-10 md:px-10">
        <header className="mb-6 md:mb-8">
          <h1 className="text-2xl font-semibold text-white md:text-3xl">Players</h1>
          <p className="mt-2 text-sm text-bb-muted">
            Search across leagues — OVRs are league-context from latest sync.
          </p>
        </header>
        <div className="max-w-xl">
          <PlayerSearch />
        </div>
      </div>
    </AppShell>
  );
}
