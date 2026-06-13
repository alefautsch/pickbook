import type { LeagueTile } from "@/lib/api";
import { formatPpg, formatTv, ordinal } from "@/lib/format";
import { ContenderTag } from "./ContenderTag";
import { OvrBadge } from "./OvrBadge";

type SummaryCardsProps = {
  league: LeagueTile;
};

export function SummaryCards({ league }: SummaryCardsProps) {
  const cards = [
    {
      label: "My Team Rank",
      value: league.my_dynasty_rank ? `#${league.my_dynasty_rank}` : "—",
      sub: league.total_rosters ? `of ${league.total_rosters}` : undefined,
    },
    {
      label: "Team OVR",
      value: league.my_roster_ovr ?? "—",
      delta: league.my_roster_ovr_delta,
      badge: true,
    },
    {
      label: "Starter Σ PPG",
      value: formatPpg(league.my_starter_ppg),
      sub: league.my_starter_ppg_rank
        ? `${ordinal(league.my_starter_ppg_rank)} in league`
        : undefined,
    },
    {
      label: "Player Value",
      value: formatTv(league.my_total_trade_value),
      sub: league.my_tv_rank ? `${ordinal(league.my_tv_rank)} in league` : undefined,
    },
    {
      label: "Pick Value",
      value: formatTv(league.my_draft_pick_value),
    },
    {
      label: "Contender Index",
      value: league.my_contender_tier ?? "—",
      sub:
        league.my_contender_score != null
          ? `Score: ${Math.round(league.my_contender_score)}`
          : undefined,
      contender: true,
    },
  ];

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-2 sm:gap-3 xl:grid-cols-6">
      {cards.map((card) => (
        <article
          key={card.label}
          className="bb-panel px-3 py-2.5 sm:px-4 sm:py-3.5"
        >
          <p className="text-[10px] uppercase tracking-wider text-bb-muted sm:text-xs">{card.label}</p>
          <div className="mt-1.5 flex items-center gap-2 sm:mt-2">
            {card.badge ? (
              <OvrBadge ovr={typeof card.value === "number" ? card.value : null} size="md" />
            ) : card.contender ? (
              <ContenderTag tier={String(card.value)} />
            ) : (
              <p className="text-xl font-semibold text-white sm:text-2xl">{card.value}</p>
            )}
            {card.delta != null && card.delta !== 0 ? (
              <span
                className={`text-xs font-medium ${
                  card.delta > 0 ? "text-emerald-400" : "text-red-300"
                }`}
              >
                {card.delta > 0 ? "+" : ""}
                {card.delta}
              </span>
            ) : null}
          </div>
          {card.sub ? <p className="mt-1 text-xs text-bb-muted">{card.sub}</p> : null}
        </article>
      ))}
    </div>
  );
}
