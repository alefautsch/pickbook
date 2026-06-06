from __future__ import annotations

import argparse
import sys
import time

from dynasty_draft.builder import build_state
from dynasty_draft.config import load_config, save_config
from dynasty_draft.sleeper_client import SleeperClient
from dynasty_draft.war_data import WarData
from pathlib import Path


def format_money(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.0f}"


def render_board(state, limit: int) -> str:
    info = state.next_pick_info()
    lines: list[str] = []
    draft_name = (state.draft.get("metadata") or {}).get("name") or "Sleeper Draft"
    status = state.draft.get("status", "unknown")
    phase = state.strategy.draft_phase
    lines.append(f"=== {draft_name} ({status}) | {phase} draft ===")
    lines.append(
        f"Pick {len(state.picks)}/{info.get('total_picks', '?')} | "
        f"Next overall: #{info.get('pick_no', '?')} (round {info.get('round', '?')})"
    )
    if state.my_slot is not None:
        if info.get("is_my_pick"):
            lines.append(">>> ON THE CLOCK — your pick <<<")
        else:
            lines.append(f"Your slot: 1.{state.my_slot:02d} | Picks until yours: {info.get('picks_until_mine', '?')}")
    upcoming = info.get("my_upcoming") or []
    if upcoming:
        lines.append(f"Your upcoming picks: {', '.join(str(p) for p in upcoming)}")

    for note in state.strategy.strategy_notes(state.war):
        lines.append(f"Strategy: {note}")

    my_roster = state.roster_summary()
    if my_roster:
        lines.append("")
        lines.append("Your roster:")
        for row in my_roster:
            status_label = row.get("status", "")
            suffix = f" [{status_label}]" if status_label and status_label != "drafted" else ""
            lines.append(
                f"  {str(row.get('pick_no') or 'R'):>3}. {row['name']:<26} {row['pos']:<3} "
                f"TV {format_money(row['trade_value']):>6}  WORP {row['worp'] if row['worp'] is not None else '-'}{suffix}"
            )
        needs = state.starter_needs()
        need_bits = [f"{pos}:{count}" for pos, count in needs.items() if count > 0]
        if need_bits:
            lines.append(f"Starter needs: {', '.join(need_bits)}")

    cliffs = state.tier_cliffs()
    if cliffs:
        lines.append("")
        lines.append("Tier cliffs (consider before they fall):")
        for cliff in cliffs:
            lines.append(
                f"  {cliff['pos']}: {cliff['player']} -> {cliff['next']} "
                f"(TV gap {cliff['gap']:,.0f})"
            )

    recs = state.recommend(limit=limit)
    lines.append("")
    lines.append("Top recommendations (trade value + WORP + roster fit):")
    lines.append(f"{'#':>2} {'Player':<26} {'Pos':<3} {'TV':>6} {'WORP':>5} {'Tier':>4} {'Score':>6}")
    for idx, row in enumerate(recs, start=1):
        worp = f"{row['worp']:.2f}" if row["worp"] is not None else "-"
        tier = str(row["worp_tier"]) if row["worp_tier"] is not None else "-"
        note = f"  ({row['note']})" if row.get("note") else ""
        lines.append(
            f"{idx:>2} {row['name']:<26} {row['pos']:<3} "
            f"{row['trade_value']:>6,.0f} {worp:>5} {tier:>4} {row['score']:>6.3f}{note}"
        )

    lines.append("")
    lines.append(
        f"Weights: trade={state.trade_weight:.0%} worp={state.worp_weight:.0%} "
        "(edit config.json)"
    )
    return "\n".join(lines)


def cmd_setup(_: argparse.Namespace) -> None:
    config = load_config()
    username = input("Sleeper username: ").strip() or config.get("sleeper_username", "")
    if not username:
        print("Username required.")
        sys.exit(1)
    client = SleeperClient()
    user = client.get_user(username)
    user_id = str(user["user_id"])
    leagues = client.get_user_leagues(user_id)
    active = [lg for lg in leagues if lg.get("status") in {"pre_draft", "drafting", "in_season"}]
    print("\nYour leagues:")
    for idx, league in enumerate(active, start=1):
        print(
            f"  {idx}. {league.get('name')} | status={league.get('status')} "
            f"| league_id={league.get('league_id')} | draft_id={league.get('draft_id')}"
        )
    choice = input("\nLeague number to track (blank to skip): ").strip()
    league_id = ""
    draft_id = ""
    if choice.isdigit() and 1 <= int(choice) <= len(active):
        selected = active[int(choice) - 1]
        league_id = str(selected.get("league_id") or "")
        draft_id = str(selected.get("draft_id") or "")
    trade_weight = input("Trade value weight 0-1 [0.45]: ").strip() or "0.45"
    worp_weight = input("WORP weight 0-1 [0.55]: ").strip() or "0.55"
    startup_slot = input("Startup slot round 1 [10]: ").strip() or "10"
    config.update(
        {
            "sleeper_username": username,
            "league_id": league_id,
            "draft_id": draft_id,
            "trade_weight": float(trade_weight),
            "worp_weight": float(worp_weight),
            "poll_seconds": int(config.get("poll_seconds", 20)),
            "war_csv": config.get("war_csv", "war.csv"),
        }
    )
    config.setdefault("strategy", {})["startup_slot"] = int(startup_slot)
    config["strategy"]["reserved_rookies"] = config.get("strategy", {}).get(
        "reserved_rookies", ["Jeremiyah Love"]
    )
    save_config(config)
    print(f"\nSaved config.json")


def cmd_leagues(args: argparse.Namespace) -> None:
    config = load_config()
    username = (args.username or config.get("sleeper_username") or "").strip()
    if not username:
        print("Provide --username or set sleeper_username in config.json")
        sys.exit(1)
    client = SleeperClient()
    user = client.get_user(username)
    leagues = client.get_user_leagues(str(user["user_id"]), season=args.season)
    for league in leagues:
        print(
            f"{league.get('name')} | status={league.get('status')} | "
            f"league_id={league.get('league_id')} | draft_id={league.get('draft_id')}"
        )


def cmd_sync(args: argparse.Namespace) -> None:
    config = load_config()
    state = build_state(config)
    print(render_board(state, limit=args.limit))


def cmd_watch(args: argparse.Namespace) -> None:
    config = load_config()
    interval = args.interval or int(config.get("poll_seconds", 20))
    previous_pick_count = -1
    while True:
        state = build_state(config)
        if len(state.picks) != previous_pick_count:
            if previous_pick_count >= 0:
                print("\n--- draft update ---\n")
            print(render_board(state, limit=args.limit))
            previous_pick_count = len(state.picks)
            if state.draft.get("status") == "complete":
                print("\nDraft complete.")
                break
            if state.next_pick_info().get("is_my_pick"):
                print("\n*** YOUR PICK IS UP ***")
        else:
            info = state.next_pick_info()
            print(
                f"\rWaiting... pick {len(state.picks)} | "
                f"next #{info.get('pick_no')} | "
                f"picks until yours: {info.get('picks_until_mine', '?')}   ",
                end="",
                flush=True,
            )
        time.sleep(interval)


def cmd_insights(_: argparse.Namespace) -> None:
    war = WarData(Path("war.csv"))
    print("Vet startup at 1.10 with Jeremiyah Love at rookie 1.01:\n")
    print("Deprioritize early RB. Target QB/WR/TE with trade value + WORP.\n")
    candidates = [
        p
        for p in war.players
        if p.trade_value >= 3500
        and p.worp is not None
        and p.worp >= 0.5
        and p.pos in {"QB", "WR", "TE"}
    ]
    candidates.sort(key=lambda p: (p.trade_value * 0.45 + (p.worp or 0) * 2000 * 0.55), reverse=True)
    for idx, player in enumerate(candidates[:15], start=1):
        print(
            f"{idx:>2}. {player.name:<26} {player.pos:<3} "
            f"TV {player.trade_value:>6,.0f}  WORP {player.worp:.2f}  tier {player.worp_tier}"
        )
    print("\nVet RB targets for rounds 5+ (after Love reserved):")
    rbs = [
        p
        for p in war.players
        if p.pos == "RB" and p.worp is not None and p.worp >= 0.5 and 2500 <= p.trade_value <= 5000
    ]
    rbs.sort(key=lambda p: p.worp, reverse=True)
    for player in rbs[:8]:
        print(f"  {player.name:<26} TV {player.trade_value:>6,.0f}  WORP {player.worp:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Dynasty startup draft assistant for Sleeper")
    sub = parser.add_subparsers(dest="command", required=True)

    setup_parser = sub.add_parser("setup", help="Interactive config setup")
    setup_parser.set_defaults(func=cmd_setup)

    leagues_parser = sub.add_parser("leagues", help="List Sleeper leagues for your user")
    leagues_parser.add_argument("--username", help="Sleeper username")
    leagues_parser.add_argument("--season", default="2025")
    leagues_parser.set_defaults(func=cmd_leagues)

    sync_parser = sub.add_parser("sync", help="Sync draft and print recommendations")
    sync_parser.add_argument("--limit", type=int, default=15)
    sync_parser.set_defaults(func=cmd_sync)

    watch_parser = sub.add_parser("watch", help="Poll draft and refresh recommendations")
    watch_parser.add_argument("--limit", type=int, default=15)
    watch_parser.add_argument("--interval", type=int, help="Seconds between polls")
    watch_parser.set_defaults(func=cmd_watch)

    insights_parser = sub.add_parser("insights", help="Static strategy notes from war.csv")
    insights_parser.set_defaults(func=cmd_insights)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
