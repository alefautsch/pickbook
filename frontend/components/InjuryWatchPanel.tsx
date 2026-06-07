import Link from "next/link";
import type { InjuryWatchItem } from "@/lib/api";

type InjuryWatchPanelProps = {
  injuries: InjuryWatchItem[];
  leagueId: string;
  compact?: boolean;
};

export function InjuryWatchPanel({ injuries, leagueId, compact }: InjuryWatchPanelProps) {
  if (injuries.length === 0) {
    return (
      <section className={compact ? "" : "bb-card p-5"}>
        <h2 className="text-sm font-medium uppercase tracking-wider text-bb-muted">
          Injury Watch
        </h2>
        <p className="mt-2 text-sm text-bb-muted">No flagged injuries on roster.</p>
      </section>
    );
  }

  return (
    <section className={compact ? "" : "bb-card p-5"}>
      <h2 className="text-sm font-medium uppercase tracking-wider text-bb-muted">
        Injury Watch
      </h2>
      <ul className="mt-3 space-y-2">
        {injuries.map((item) => (
          <li
            key={item.player_id}
            className="flex items-start justify-between gap-2 rounded-lg bg-red-950/20 px-3 py-2"
          >
            <div>
              <Link
                href={`/players/${item.player_id}?league_id=${leagueId}`}
                className="text-sm font-medium text-white hover:text-bb-gold"
              >
                {item.player_name}
              </Link>
              <p className="text-xs text-bb-muted">
                {item.position}
                {item.injury_body_part ? ` · ${item.injury_body_part}` : ""}
              </p>
            </div>
            <span className="shrink-0 rounded bg-red-900/40 px-2 py-0.5 text-xs uppercase text-red-200">
              {item.injury_status}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
