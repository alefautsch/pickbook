import Link from "next/link";
import type { LeagueTile as LeagueTileData } from "@/lib/api";
import { formatPpg, timeAgo } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";

type LeagueTileProps = {
  league: LeagueTileData;
};

export function LeagueTile({ league }: LeagueTileProps) {
  return (
    <Link href={`/leagues/${league.league_id}`} className="block">
      <article className="bb-card p-5 transition hover:-translate-y-0.5 hover:shadow-xl">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-white">{league.name}</h2>
            <p className="mt-1 text-sm text-bb-muted">
              {league.my_team_name ?? "My team"} · Rank #{league.my_dynasty_rank ?? "—"}
            </p>
          </div>
          <div className="flex flex-col items-end gap-1">
            <OvrBadge ovr={league.my_roster_ovr} size="md" />
            {league.my_roster_ovr_delta != null && league.my_roster_ovr_delta !== 0 ? (
              <span
                className={`text-xs font-medium ${
                  league.my_roster_ovr_delta > 0
                    ? "text-emerald-400"
                    : "text-red-300"
                }`}
              >
                {league.my_roster_ovr_delta > 0 ? "+" : ""}
                {league.my_roster_ovr_delta} OVR
              </span>
            ) : null}
          </div>
        </div>

        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div>
            <dt className="text-bb-muted">Starter Σ PPG</dt>
            <dd className="font-medium text-white">
              {formatPpg(league.my_starter_ppg)}
            </dd>
          </div>
          <div>
            <dt className="text-bb-muted">Synced</dt>
            <dd className="font-medium text-white">
              {timeAgo(league.last_synced)}
            </dd>
          </div>
        </dl>

        <p className="mt-3 text-xs text-bb-muted">
          {league.total_rosters} teams · {league.superflex ? "Superflex" : "1QB"} · {league.season}
        </p>
      </article>
    </Link>
  );
}
