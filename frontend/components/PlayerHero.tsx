import type { PlayerCard } from "@/lib/api";
import { ExpendabilityBadge } from "@/components/ExpendabilityBadge";
import { OvrGauge } from "@/components/OvrGauge";
import { RookieBadge } from "@/components/RookieBadge";
import { PlayerHeadshot } from "@/components/PlayerHeadshot";
import { PlayerName } from "@/components/PlayerName";
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
import { TeamLogoWatermark } from "@/components/TeamLogoWatermark";
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

  const bioStats = [
    { label: "Age", value: player.age ?? "—" },
    { label: "Ht", value: formatHeight(player.bio.height) },
    { label: "Wt", value: player.bio.weight ? `${player.bio.weight}` : "—" },
    {
      label: "Exp",
      value: formatExp(player.bio.years_exp, player.dynasty_rookie),
    },
  ];

  const rankChips = (
    <div className="flex flex-wrap items-center gap-2">
      {player.ranks.position_rank ? (
        <div className="rounded-lg bg-white/4 px-2.5 py-1.5 text-center ring-1 ring-inset ring-white/[0.07] sm:px-3 sm:py-2">
          <p className="text-sm font-bold tabular-nums text-white sm:text-base">
            {ordinal(player.ranks.position_rank)}
          </p>
          <p className="text-[9px] uppercase tracking-wider text-bb-muted">
            {player.position}
          </p>
        </div>
      ) : null}
      {player.ranks.overall_rank ? (
        <div className="rounded-lg bg-white/4 px-2.5 py-1.5 text-center ring-1 ring-inset ring-white/[0.07] sm:px-3 sm:py-2">
          <p className="text-sm font-bold tabular-nums text-bb-gold sm:text-base">
            {ordinal(player.ranks.overall_rank)}
          </p>
          <p className="text-[9px] uppercase tracking-wider text-bb-muted">OVR</p>
        </div>
      ) : null}
      <span className="rounded-full bg-bb-gold/10 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider text-bb-gold">
        {tierLabels[tier]}
      </span>
    </div>
  );

  return (
    <section className="bb-panel relative mb-3 overflow-hidden md:mb-5">
      <TeamLogoWatermark
        team={player.nfl_team}
        className="right-0 top-1/2 h-44 w-44 -translate-y-1/2 opacity-[0.12] sm:h-56 sm:w-56 sm:opacity-[0.14] lg:right-4 lg:h-72 lg:w-72 lg:opacity-[0.18]"
      />
      <div
        aria-hidden
        className="pointer-events-none absolute inset-0 bg-[linear-gradient(105deg,#0d1117_0%,#0d1117_38%,rgba(13,17,23,0.72)_62%,rgba(13,17,23,0.15)_100%)]"
      />

      <div className="relative p-3 sm:p-4 lg:p-5">
        {/* Mobile / tablet */}
        <div className="lg:hidden">
          <div className="grid grid-cols-[auto_minmax(0,1fr)_auto] items-start gap-3 sm:items-center sm:gap-4">
            <PlayerHeadshot
              src={player.headshot_url}
              alt={player.player_name ?? "Player"}
              position={player.position}
              className="h-28 w-28 shrink-0 rounded-2xl shadow-lg ring-1 ring-white/10 sm:h-36 sm:w-36"
              sizes="(max-width: 640px) 112px, 144px"
            />
            <div className="min-w-0 self-center">
              <p className="truncate text-[10px] uppercase tracking-wider text-bb-muted sm:text-xs">
                {player.league_name}
              </p>
              <div className="mt-0.5 flex flex-wrap items-center gap-1.5">
                <PlayerName as="h1" size="hero">
                  {player.player_name}
                </PlayerName>
                {player.dynasty_rookie ? <RookieBadge /> : null}
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
            <div className="shrink-0 self-start sm:self-center">
              <OvrGauge ovr={player.ovr} expected={player.hppg_expected} size="sm" />
            </div>
          </div>

          <div className="mt-3">{rankChips}</div>

          <div className="mt-3 grid grid-cols-4 gap-1.5 border-t border-white/8 pt-3">
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
            {bioStats.map(({ label, value }) => (
              <div key={label} className="rounded-md bg-black/25 px-2 py-1.5 text-center">
                <dd className="text-sm font-semibold text-white">{value}</dd>
                <dt className="text-[8px] uppercase tracking-wider text-bb-muted">{label}</dt>
              </div>
            ))}
          </dl>
        </div>

        {/* Desktop */}
        <div className="relative hidden lg:grid lg:grid-cols-[13rem_minmax(0,1fr)_auto] lg:items-center lg:gap-6">
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className="h-52 w-52 shrink-0 rounded-2xl shadow-lg ring-1 ring-white/10"
            sizes="208px"
          />

          <div className="min-w-0">
            <p className="text-xs uppercase tracking-wider text-bb-muted">{player.league_name}</p>
            <div className="mt-1 flex flex-wrap items-center gap-2">
              <PlayerName as="h1" size="hero">
                {player.player_name}
              </PlayerName>
              {player.dynasty_rookie ? <RookieBadge /> : null}
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

            <div className="mt-4">{rankChips}</div>

            <dl className="mt-4 flex flex-wrap gap-x-6 gap-y-3">
              {[
                ...bioStats,
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
          </div>
        </div>

        <div className="mt-4 hidden grid-cols-7 gap-2 border-t border-white/8 pt-4 lg:grid">
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
      </div>
    </section>
  );
}
