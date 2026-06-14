import Link from "next/link";
import type { PlayerCard as PlayerCardData } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import { formatActv, formatPpg, formatTv, formatWorpPpg } from "@/lib/format";
import { OvrBadge } from "./OvrBadge";
import { RookieBadge } from "./RookieBadge";
import { ExpendabilityBadge } from "./ExpendabilityBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";
import { PlayerName } from "./PlayerName";
import { PositionTag } from "./PositionPill";

type PlayerCardProps = {
  player: PlayerCardData;
  size?: "hero" | "compact";
  showLeague?: boolean;
  link?: boolean;
};

export function PlayerCard({
  player,
  size = "compact",
  showLeague = false,
  link = true,
}: PlayerCardProps) {
  const isHero = size === "hero";
  const inner = (
    <article
      className={`bb-card group relative overflow-hidden transition hover:-translate-y-0.5 hover:shadow-xl ${
        isHero ? "p-5" : "p-3"
      }`}
    >
      <div className={`flex gap-4 ${isHero ? "items-start" : "items-center"}`}>
        <div className="relative shrink-0">
          <PlayerHeadshot
            src={player.headshot_url}
            alt={player.player_name ?? "Player"}
            position={player.position}
            className={isHero ? "h-28 w-28" : "h-16 w-16"}
            sizes={isHero ? "112px" : "64px"}
          />
          <div className="absolute -right-1 -top-1">
            <OvrBadge
              ovr={player.ovr}
              expected={player.hppg_expected}
              size={isHero ? "md" : "sm"}
            />
          </div>
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <PlayerName as="h3" size={isHero ? "lg" : "base"} className={isHero ? "text-2xl" : ""}>
              {player.player_name ?? "Unknown"}
            </PlayerName>
            {player.dynasty_rookie ? <RookieBadge /> : null}
            {player.position ? <PositionTag position={player.position} /> : null}
            {[player.nfl_team, player.age != null ? String(player.age) : null]
              .filter(Boolean)
              .join(" · ") ? (
              <span className="text-xs text-bb-muted">
                {[player.nfl_team, player.age != null ? String(player.age) : null]
                  .filter(Boolean)
                  .join(" · ")}
              </span>
            ) : null}
            <ExpendabilityBadge
              tag={player.trade_tag}
              lineupDelta={player.lineup_delta_ppg}
              size={isHero ? "md" : "sm"}
            />
          </div>

          {showLeague ? (
            <p className="mt-1 text-xs text-bb-gold">{player.league_name}</p>
          ) : null}

          <dl
            className={`mt-2 grid grid-cols-4 gap-2 text-xs ${
              isHero ? "text-sm" : ""
            }`}
          >
            <div>
              <dt className="text-bb-muted">Proj PPG</dt>
              <dd
                className="text-base font-semibold text-white"
                title={projectionSourceLabel(player.projection_source)}
              >
                {formatPpg(player.projected_ppg)}
              </dd>
              <dd className="text-[10px] text-bb-muted">
                HPPG {formatPpg(player.hppg)}
                {player.hppg_expected ? (
                  <span className="ml-0.5 text-bb-gold">e</span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt className="text-bb-muted">W/g</dt>
              <dd className="font-medium text-white">
                {formatWorpPpg(player.worp_ppg)}
              </dd>
            </div>
            <div>
              <dt className="text-bb-muted">Actv</dt>
              <dd className="font-medium text-white">
                {formatActv(player.availability)}
              </dd>
            </div>
            <div>
              <dt className="text-bb-muted">TV</dt>
              <dd className="font-medium text-white">
                {formatTv(player.trade_value)}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </article>
  );

  if (!link) return inner;

  return (
    <Link
      href={`/players/${player.player_id}?league_id=${player.league_id}`}
      className="block"
    >
      {inner}
    </Link>
  );
}
