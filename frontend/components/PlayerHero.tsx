import type { PlayerCard } from "@/lib/api";
import { ExpendabilityBadge } from "@/components/ExpendabilityBadge";
import { OvrBadge } from "@/components/OvrBadge";
import { OvrGauge } from "@/components/OvrGauge";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { PositionTag } from "@/components/PositionPill";
import { projectionSourceLabel } from "@/lib/archetype";
import {
  formatActvGames,
  formatDecimal,
  formatExp,
  formatHeight,
  formatPpg,
  formatTv,
  formatWorpPpg,
  ordinal,
} from "@/lib/format";
import { tierLabels, ovrTier } from "@/lib/ovr";

type PlayerHeroProps = {
  player: PlayerCard;
};

export function PlayerHero({ player }: PlayerHeroProps) {
  const tier = ovrTier(player.ovr);

  const keyStats = [
    {
      label: "Proj",
      value: formatPpg(player.projected_ppg),
      sub: `HPPG ${formatPpg(player.hppg)}`,
      title: projectionSourceLabel(player.projection_source),
    },
    { label: "W/g", value: formatWorpPpg(player.worp_ppg) },
    { label: "TV", value: formatTv(player.trade_value) },
    {
      label: "ACTV",
      value: formatActvGames(
        player.healthy_games,
        player.total_games,
        player.availability,
      ),
    },
  ];

  const desktopStats: {
    label: string;
    value: string | number;
    sub?: string;
    title?: string;
    featured?: boolean;
  }[] = [
    ...keyStats.map((stat) => ({
      label: stat.label === "Proj" ? "Proj PPG" : stat.label,
      value: stat.value,
      sub: stat.sub,
      title: stat.title,
      featured: stat.label === "Proj",
    })),
    { label: "WORP", value: formatDecimal(player.season_worp, 2) },
    { label: "FLEX", value: player.lenses.flex_rating ?? "—" },
    { label: "PORP", value: player.porp != null ? Math.round(player.porp) : "—" },
  ];

  return (
    <section className="bb-card mb-4 overflow-hidden p-4 sm:mb-6 sm:p-6">
      {/* Mobile / tablet */}
      <div className="lg:hidden">
        <div className="flex items-start gap-3">
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className="h-16 w-16 shrink-0 rounded-full sm:h-20 sm:w-20"
            sizes="80px"
          />
          <div className="min-w-0 flex-1">
            <p className="text-[10px] uppercase tracking-wider text-bb-muted">
              {player.league_name}
            </p>
            <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
              <h1 className="text-xl font-bold tracking-tight text-white sm:text-2xl">
                {player.player_name}
              </h1>
              {player.position ? <PositionTag position={player.position} /> : null}
            </div>
            <p className="mt-0.5 text-xs text-bb-muted sm:text-sm">{player.nfl_team}</p>
            {player.trade_tag ? (
              <div className="mt-1.5">
                <ExpendabilityBadge
                  tag={player.trade_tag}
                  lineupDelta={player.lineup_delta_ppg}
                  size="md"
                />
              </div>
            ) : null}
          </div>
          <OvrBadge
            ovr={player.ovr}
            expected={player.hppg_expected}
            size="md"
            className="mt-1"
          />
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-2">
            {player.ranks.position_rank ? (
              <div className="rounded-lg bg-white/4 px-2.5 py-1.5 text-center ring-1 ring-inset ring-white/[0.07]">
                <p className="text-sm font-bold tabular-nums text-white">
                  {ordinal(player.ranks.position_rank)}
                </p>
                <p className="text-[9px] uppercase tracking-wider text-bb-muted">
                  {player.position}
                </p>
              </div>
            ) : null}
            {player.ranks.overall_rank ? (
              <div className="rounded-lg bg-white/4 px-2.5 py-1.5 text-center ring-1 ring-inset ring-white/[0.07]">
                <p className="text-sm font-bold tabular-nums text-bb-gold">
                  {ordinal(player.ranks.overall_rank)}
                </p>
                <p className="text-[9px] uppercase tracking-wider text-bb-muted">OVR</p>
              </div>
            ) : null}
            <span className="rounded-full bg-bb-gold/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-bb-gold">
              {tierLabels[tier]}
            </span>
          </div>

        <div className="mt-3 grid grid-cols-4 gap-1.5 border-t border-bb-border/40 pt-3">
          {keyStats.map((stat) => (
            <div
              key={stat.label}
              title={stat.title}
              className="rounded-lg bg-white/4 px-2 py-1.5 text-center ring-1 ring-inset ring-white/[0.07]"
            >
              <p className="text-[9px] uppercase tracking-wide text-bb-muted">{stat.label}</p>
              <p className="mt-0.5 text-sm font-bold tabular-nums text-white">{stat.value}</p>
              {stat.sub ? (
                <p className="mt-0.5 truncate text-[9px] text-bb-muted">{stat.sub}</p>
              ) : null}
            </div>
          ))}
        </div>

        <dl className="mt-2 grid grid-cols-4 gap-1.5">
          {[
            { label: "Age", value: player.age ?? "—" },
            { label: "Ht", value: formatHeight(player.bio.height) },
            { label: "Wt", value: player.bio.weight ? `${player.bio.weight}` : "—" },
            {
              label: "Exp",
              value: formatExp(player.bio.years_exp, player.dynasty_rookie),
            },
          ].map(({ label, value }) => (
            <div key={label} className="rounded-md bg-black/20 px-2 py-1.5 text-center">
              <dd className="text-sm font-semibold text-white">{value}</dd>
              <dt className="text-[8px] uppercase tracking-wider text-bb-muted">{label}</dt>
            </div>
          ))}
        </dl>
      </div>

      {/* Desktop */}
      <div className="hidden flex-col gap-4 lg:flex lg:flex-row lg:items-start">
        <PlayerHeadshot
          src={player.headshot_url}
          alt={player.player_name ?? "Player"}
          position={player.position}
          className="h-40 w-40 shrink-0"
          sizes="160px"
        />

        <div className="min-w-0 flex-1">
          <p className="text-xs uppercase tracking-wider text-bb-muted">{player.league_name}</p>
          <div className="mt-1 flex flex-wrap items-center gap-2">
            <h1 className="text-4xl font-bold tracking-tight text-white">
              {player.player_name}
            </h1>
            {player.position ? <PositionTag position={player.position} /> : null}
            {player.trade_tag ? (
              <ExpendabilityBadge
                tag={player.trade_tag}
                lineupDelta={player.lineup_delta_ppg}
                size="md"
              />
            ) : null}
          </div>
          <p className="mt-1 text-sm font-medium text-bb-muted">{player.nfl_team}</p>

          <dl className="mt-4 flex flex-wrap gap-4">
            {[
              { label: "Age", value: player.age ?? "—" },
              { label: "Height", value: formatHeight(player.bio.height) },
              { label: "Weight", value: player.bio.weight ? `${player.bio.weight}` : "—" },
              {
                label: "Exp",
                value: formatExp(player.bio.years_exp, player.dynasty_rookie),
              },
              { label: "College", value: player.bio.college ?? "—" },
            ].map(({ label, value }) => (
              <div key={label}>
                <dd className="text-base font-semibold text-white">{value}</dd>
                <dt className="text-[9px] uppercase tracking-widest text-bb-muted">{label}</dt>
              </div>
            ))}
          </dl>
        </div>

        <div className="flex shrink-0 flex-col items-center gap-3">
          <OvrGauge ovr={player.ovr} expected={player.hppg_expected} size="hero" />
          <div className="flex gap-2">
            {player.ranks.position_rank ? (
              <div className="rounded-lg bg-white/4 px-4 py-2.5 text-center ring-1 ring-inset ring-white/[0.07]">
                <p className="text-xl font-bold tabular-nums text-white">
                  {ordinal(player.ranks.position_rank)}
                </p>
                <p className="mt-0.5 text-[9px] uppercase tracking-wider text-bb-muted">
                  {player.position} rank
                </p>
              </div>
            ) : null}
            {player.ranks.overall_rank ? (
              <div className="rounded-lg bg-white/4 px-4 py-2.5 text-center ring-1 ring-inset ring-white/[0.07]">
                <p className="text-xl font-bold tabular-nums text-bb-gold">
                  {ordinal(player.ranks.overall_rank)}
                </p>
                <p className="mt-0.5 text-[9px] uppercase tracking-wider text-bb-muted">
                  overall
                </p>
              </div>
            ) : null}
          </div>
          <span className="rounded-full bg-bb-gold/10 px-3 py-0.5 text-[10px] font-bold uppercase tracking-widest text-bb-gold">
            {tierLabels[tier]}
          </span>
        </div>
      </div>

      <div className="mt-6 hidden grid-cols-7 gap-2 border-t border-bb-border/50 pt-4 lg:grid">
        {desktopStats.map((stat) => (
          <div
            key={stat.label}
            title={stat.title}
            className="rounded-lg bg-white/4 px-2.5 py-2 ring-1 ring-inset ring-white/[0.07]"
          >
            <p className="truncate text-[9px] uppercase tracking-wider text-bb-muted">
              {stat.label}
            </p>
            <p
              className={`mt-0.5 font-bold tabular-nums text-white ${
                stat.featured ? "text-xl" : "text-base"
              }`}
            >
              {stat.value}
            </p>
            {stat.sub ? <p className="mt-0.5 text-[10px] text-bb-muted">{stat.sub}</p> : null}
          </div>
        ))}
      </div>
    </section>
  );
}
