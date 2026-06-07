import { AppShell } from "@/components/AppShell";
import { LeagueTile } from "@/components/LeagueTile";
import { getLeagues, type LeagueTile as LeagueTileData } from "@/lib/api";

export default async function Home() {
  let leagues: LeagueTileData[] = [];
  let error: string | null = null;

  try {
    leagues = await getLeagues();
  } catch (err) {
    error = err instanceof Error ? err.message : "Failed to load leagues";
  }

  return (
    <AppShell leagues={leagues}>
      <div className="flex flex-1 flex-col px-6 py-10 sm:px-10">
        <header className="mb-10">
          <h1 className="text-4xl font-semibold tracking-tight text-white">
            Front Office Hub
          </h1>
          <p className="mt-3 max-w-2xl text-bb-muted">
            Research your dynasty rosters across three leagues — grades are
            league-context OVRs from the latest sync.
          </p>
        </header>

        {error ? (
          <p className="text-red-300">{error}</p>
        ) : (
          <main className="grid gap-6 md:grid-cols-2 xl:grid-cols-3">
            {leagues.map((league) => (
              <LeagueTile key={league.league_id} league={league} />
            ))}
          </main>
        )}

        <section className="bb-card mt-10 p-5">
          <h2 className="text-sm uppercase tracking-wider text-bb-muted">
            Portfolio
          </h2>
          <p className="mt-2 text-sm text-bb-muted">
            Cross-league holdings and exposure — coming in Phase 3.
          </p>
        </section>
      </div>
    </AppShell>
  );
}
