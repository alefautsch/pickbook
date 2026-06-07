import Link from "next/link";
import type { PlayerCard as PlayerCardData } from "@/lib/api";
import { projectionSourceLabel } from "@/lib/archetype";
import { formatActv, formatDecimal, formatPpg, formatTv } from "@/lib/format";
import { positionColor } from "@/lib/ovr";
import { OvrBadge } from "./OvrBadge";
import { PlayerHeadshot } from "./PlayerHeadshot";

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
            <h3
              className={`truncate font-semibold text-white ${
                isHero ? "text-2xl" : "text-base"
              }`}
            >
              {player.player_name ?? "Unknown"}
            </h3>
            {player.position ? (
              <span
                className="rounded px-1.5 py-0.5 text-xs font-semibold"
                style={{
                  background: `color-mix(in srgb, ${positionColor(player.position)} 20%, transparent)`,
                  color: positionColor(player.position),
                }}
              >
                {player.position}
              </span>
            ) : null}
            {player.nfl_team ? (
              <span className="text-xs text-bb-muted">{player.nfl_team}</span>
            ) : null}
            {player.age != null ? (
              <span className="text-xs text-bb-muted">Age {player.age}</span>
            ) : null}
          </div>

          {showLeague ? (
            <p className="mt-1 text-xs text-bb-gold">{player.league_name}</p>
          ) : null}

          <dl
            className={`mt-2 grid grid-cols-5 gap-2 text-xs ${
              isHero ? "text-sm" : ""
            }`}
          >
            <div>
              <dt className="text-bb-muted">HPPG</dt>
              <dd className="font-medium text-white">
                {formatPpg(player.hppg)}
                {player.hppg_expected ? (
                  <span className="ml-0.5 text-bb-gold">e</span>
                ) : null}
              </dd>
            </div>
            <div>
              <dt className="text-bb-muted">Proj</dt>
              <dd className="font-medium text-white" title={projectionSourceLabel(player.projection_source)}>
                {formatPpg(player.projected_ppg)}
              </dd>
            </div>
            <div>
              <dt className="text-bb-muted">W/g</dt>
              <dd className="font-medium text-white">
                {formatDecimal(player.worp_ppg, 3)}
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
