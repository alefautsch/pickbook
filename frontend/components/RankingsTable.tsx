"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { RankingRow } from "@/lib/api";
import { formatPpg, formatTv } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";

type SortKey = "dynasty" | "ppg" | "tv" | "win";

type RankingsTableProps = {
  leagueId: string;
  byDynasty: RankingRow[];
  byStarterPpg: RankingRow[];
  byTv: RankingRow[];
  byWinNow: RankingRow[];
};

const sortOptions: { key: SortKey; label: string }[] = [
  { key: "dynasty", label: "Dynasty OVR" },
  { key: "ppg", label: "Starter Σ PPG" },
  { key: "tv", label: "Trade Value" },
  { key: "win", label: "Win-now" },
];

function rankField(key: SortKey): keyof RankingRow {
  switch (key) {
    case "ppg":
      return "starter_ppg_rank";
    case "tv":
      return "tv_rank";
    case "win":
      return "win_rank";
    default:
      return "dynasty_rank";
  }
}

function rowsForSort(
  key: SortKey,
  data: RankingsTableProps,
): RankingRow[] {
  switch (key) {
    case "ppg":
      return data.byStarterPpg;
    case "tv":
      return data.byTv;
    case "win":
      return data.byWinNow;
    default:
      return data.byDynasty;
  }
}

export function RankingsTable(props: RankingsTableProps) {
  const { leagueId } = props;
  const [sort, setSort] = useState<SortKey>("dynasty");

  const rows = useMemo(() => rowsForSort(sort, props), [sort, props]);
  const rankKey = rankField(sort);

  return (
    <section>
      <div className="mb-4 flex flex-wrap gap-2">
        {sortOptions.map((opt) => (
          <button
            key={opt.key}
            type="button"
            onClick={() => setSort(opt.key)}
            className={`rounded-full px-3 py-1.5 text-sm transition ${
              sort === opt.key
                ? "bg-bb-gold/20 text-bb-gold"
                : "text-bb-muted hover:bg-bb-surface hover:text-white"
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {rows.map((row) => (
          <Link
            key={row.roster_id}
            href={`/leagues/${leagueId}/teams/${row.roster_id}`}
            className="block"
          >
            <article
              className={`bb-card flex items-center gap-4 p-4 transition hover:-translate-y-0.5 ${
                row.is_me ? "border-bb-gold/40" : ""
              }`}
            >
              <span className="w-8 text-center text-lg font-bold text-bb-gold">
                #{row[rankKey] ?? "—"}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate font-medium text-white">
                  {row.team_name ?? "Team"}
                  {row.is_me ? (
                    <span className="ml-2 text-xs text-bb-gold">(me)</span>
                  ) : null}
                </p>
                {row.owner ? (
                  <p className="truncate text-xs text-bb-muted">{row.owner}</p>
                ) : null}
              </div>
              <OvrBadge ovr={row.avg_dynasty_rating} size="sm" />
              <div className="hidden text-right text-sm sm:block">
                <p className="text-bb-muted">Σ PPG</p>
                <p className="font-medium text-white">
                  {formatPpg(row.starter_total_ppg)}
                </p>
              </div>
              <div className="hidden text-right text-sm md:block">
                <p className="text-bb-muted">TV</p>
                <p className="font-medium text-white">
                  {formatTv(row.total_trade_value)}
                </p>
              </div>
            </article>
          </Link>
        ))}
      </div>
    </section>
  );
}
