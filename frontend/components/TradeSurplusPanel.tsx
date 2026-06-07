import Link from "next/link";
import type { TradeSurplus } from "@/lib/api";

type TradeSurplusPanelProps = {
  tradeSurplus: TradeSurplus | null;
  leagueId: string;
};

export function TradeSurplusPanel({ tradeSurplus, leagueId }: TradeSurplusPanelProps) {
  if (!tradeSurplus) {
    return (
      <p className="text-sm text-bb-muted">
        No trade surplus data — sync the league and ensure a roster is marked as yours.
      </p>
    );
  }

  return (
    <div className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-emerald-400">
            Surplus (top 3)
          </h3>
          {tradeSurplus.surplus.length === 0 ? (
            <p className="text-sm text-bb-muted">No positional surplus.</p>
          ) : (
            <ul className="space-y-1">
              {tradeSurplus.surplus.map((item) => (
                <li
                  key={item.position}
                  className="flex items-center justify-between rounded bg-emerald-500/10 px-3 py-2 text-sm"
                >
                  <span className="font-medium text-white">{item.position}</span>
                  <span className="text-bb-muted">
                    #{item.league_rank} · OVR {item.avg_ovr ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-amber-400">
            Needs (bottom 3)
          </h3>
          {tradeSurplus.needs.length === 0 ? (
            <p className="text-sm text-bb-muted">No positional needs.</p>
          ) : (
            <ul className="space-y-1">
              {tradeSurplus.needs.map((item) => (
                <li
                  key={item.position}
                  className="flex items-center justify-between rounded bg-amber-500/10 px-3 py-2 text-sm"
                >
                  <span className="font-medium text-white">{item.position}</span>
                  <span className="text-bb-muted">
                    #{item.league_rank}/{item.league_size} · OVR {item.avg_ovr ?? "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {tradeSurplus.counterparties.length > 0 ? (
        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wider text-bb-muted">
            Suggested counterparties
          </h3>
          <ul className="space-y-1">
            {tradeSurplus.counterparties.map((cp) => (
              <li key={`${cp.position}-${cp.direction}-${cp.roster_id}`}>
                <Link
                  href={`/leagues/${leagueId}/teams/${cp.roster_id}`}
                  className="flex items-center justify-between rounded bg-black/20 px-3 py-2 text-sm transition hover:bg-black/30"
                >
                  <span className="text-white">
                    {cp.team_name ?? "Team"}
                    <span className="ml-2 text-xs text-bb-muted">
                      {cp.direction === "sell" ? "buy" : "sell"} {cp.position}
                    </span>
                  </span>
                  <span className="text-bb-muted">
                    you #{cp.my_rank} · them #{cp.their_rank}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  );
}
