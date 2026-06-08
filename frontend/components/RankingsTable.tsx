"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import type { RankingRow } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { ContenderTag } from "./ContenderTag";
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
  { key: "dynasty", label: "By OVR" },
  { key: "ppg", label: "By Starter PPG" },
  { key: "tv", label: "By Player Value" },
  { key: "win", label: "By Win-Now" },
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

function rowsForSort(key: SortKey, data: RankingsTableProps): RankingRow[] {
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
    <section className="bb-panel">
      <div className="bb-panel-header">
        <h2 className="bb-panel-title">League Power Rankings</h2>
        <div className="flex flex-wrap gap-1">
          {sortOptions.map((opt) => (
            <button
              key={opt.key}
              type="button"
              onClick={() => setSort(opt.key)}
              className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                sort === opt.key
                  ? "bg-bb-gold/20 text-bb-gold"
                  : "text-bb-muted hover:bg-white/5 hover:text-white"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[820px] text-left text-sm">
          <thead>
            <tr className="border-b border-bb-border/50 text-xs uppercase tracking-wide text-bb-muted">
              <th className="px-4 py-3 font-medium">Rank</th>
              <th className="px-4 py-3 font-medium">Team</th>
              <th className="px-4 py-3 font-medium text-center">Team OVR</th>
              <th className="px-4 py-3 font-medium text-right">Starter Σ PPG</th>
              <th className="px-4 py-3 font-medium text-right">Player Value</th>
              <th className="px-4 py-3 font-medium text-right">Pick Value</th>
              <th className="px-4 py-3 font-medium text-center">Contender</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.roster_id}
                className={`border-b border-bb-border/30 transition hover:bg-white/3 ${
                  row.is_me ? "bg-bb-gold/6" : ""
                }`}
              >
                <td className="px-4 py-3">
                  <span className="text-lg font-bold text-bb-gold">
                    {row[rankKey] ?? "—"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <Link
                    href={`/leagues/${leagueId}/teams/${row.roster_id}`}
                    className="group block min-w-0"
                  >
                    <p className="truncate font-medium text-white group-hover:text-bb-gold">
                      {row.team_name ?? "Team"}
                      {row.is_me ? (
                        <span className="ml-2 text-xs text-bb-gold">(me)</span>
                      ) : null}
                    </p>
                    {row.owner ? (
                      <p className="truncate text-xs text-bb-muted">{row.owner}</p>
                    ) : null}
                  </Link>
                </td>
                <td className="px-4 py-3 text-center">
                  <div className="inline-flex justify-center">
                    <OvrBadge ovr={row.avg_dynasty_rating} size="sm" />
                  </div>
                </td>
                <td className="px-4 py-3 text-right">
                  <p className="font-medium text-white">
                    {formatPpg(row.starter_total_ppg)}
                  </p>
                  {row.starter_ppg_rank ? (
                    <p className="text-xs text-bb-muted">
                      {ordinal(row.starter_ppg_rank)}
                    </p>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-right">
                  <p className="font-medium text-white">
                    {formatTv(row.total_trade_value)}
                  </p>
                  {row.tv_rank ? (
                    <p className="text-xs text-bb-muted">{ordinal(row.tv_rank)}</p>
                  ) : null}
                </td>
                <td className="px-4 py-3 text-right">
                  <p className="font-medium text-white">
                    {formatTv(row.draft_pick_value)}
                  </p>
                </td>
                <td className="px-4 py-3 text-center">
                  <div className="flex flex-col items-center gap-1">
                    <ContenderTag tier={row.contender_tier} size="md" />
                    {row.contender_score != null ? (
                      <span className="text-xs text-bb-muted">
                        {Math.round(row.contender_score)}
                      </span>
                    ) : null}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}
