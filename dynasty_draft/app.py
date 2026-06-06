from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from dynasty_draft.builder import build_state
from dynasty_draft.config import load_config, save_config
from dynasty_draft.draft_context import build_league_team_rosters
from dynasty_draft.llm_advisor import stream_evaluate_picks
from dynasty_draft.recommender import DraftState

st.set_page_config(
    page_title="Pickbook",
    page_icon="🏈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MOBILE_CSS = """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 2rem; max-width: 720px; }
    div[data-testid="stMetric"] {
        background: #1A1F2B;
        border: 1px solid #2d3548;
        border-radius: 12px;
        padding: 0.5rem 0.75rem;
    }
    .stButton > button {
        min-height: 3rem;
        border-radius: 12px;
        font-weight: 600;
    }
    .hero-on-clock {
        background: linear-gradient(135deg, #14532d, #166534);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 1rem 0;
        font-size: 1.1rem;
        font-weight: 700;
    }
    .hero-waiting {
        background: linear-gradient(135deg, #7c2d12, #9a3412);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 1rem 0;
        font-size: 1.05rem;
        font-weight: 600;
    }
    .hero-bookend {
        background: linear-gradient(135deg, #1e3a8a, #1d4ed8);
        border-radius: 14px;
        padding: 1rem 1.1rem;
        margin: 0.5rem 0 1rem 0;
        font-size: 1.05rem;
        font-weight: 600;
    }
    [data-testid="stSidebar"] { display: none; }
</style>
"""


def _init_session() -> None:
    if "config" not in st.session_state:
        st.session_state.config = load_config()
    if "llm_result" not in st.session_state:
        st.session_state.llm_result = ""
    if "anthropic_api_key" not in st.session_state:
        st.session_state.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = True
    if "last_sync_at" not in st.session_state:
        st.session_state.last_sync_at = None
    if "llm_question_key" not in st.session_state:
        st.session_state.llm_question_key = ""


def _load_state(config: dict[str, Any]) -> DraftState | None:
    if not config.get("sleeper_username"):
        return None
    try:
        state = build_state(config, exit_on_error=False)
        st.session_state.last_sync_at = datetime.now()
        return state
    except Exception as exc:
        st.error(str(exc))
        return None


def _default_llm_question(state: DraftState) -> str:
    info = state.next_pick_info()
    picks = info.get("consecutive_picks") or []
    if len(picks) < 2:
        return ""
    gone = ", ".join(
        f"{(p.get('metadata') or {}).get('first_name', '')} {(p.get('metadata') or {}).get('last_name', '')}".strip()
        for p in sorted(state.picks, key=lambda row: row.get("pick_no", 0))
    )
    return (
        f"I have picks {picks[0]} and {picks[1]} back-to-back. "
        f"Already drafted: {gone}. "
        "I'm reserving Jeremiyah Love in the rookie draft. "
        "What's the best two-pick plan for trade value and winning in superflex?"
    )


def _render_hero(state: DraftState) -> None:
    info = state.next_pick_info()
    if info.get("is_my_pick"):
        st.markdown('<div class="hero-on-clock">ON THE CLOCK — make your pick</div>', unsafe_allow_html=True)
    elif info.get("back_to_back") and info.get("picks_until_mine", 99) <= 3:
        picks = info.get("consecutive_picks") or []
        st.markdown(
            f'<div class="hero-bookend">Bookend soon — picks #{picks[0]} & #{picks[1]} back-to-back</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="hero-waiting">Picks until yours: {info.get("picks_until_mine", "?")}</div>',
            unsafe_allow_html=True,
        )


def _render_status_metrics(state: DraftState) -> None:
    info = state.next_pick_info()
    c1, c2, c3 = st.columns(3)
    c1.metric("Pick", f"{len(state.picks)}/{info.get('total_picks', '?')}")
    c2.metric("Slot", f"1.{state.my_slot:02d}" if state.my_slot else "?")
    c3.metric("Format", "SF" if state.is_superflex() else "Std")
    if st.session_state.last_sync_at:
        st.caption(f"Synced {st.session_state.last_sync_at.strftime('%H:%M:%S')}")


def _render_llm_advisor(state: DraftState, config: dict[str, Any]) -> None:
    info = state.next_pick_info()
    question_key = f"llm_q_{len(state.picks)}_{info.get('pick_no')}"
    if st.session_state.llm_question_key != question_key:
        st.session_state.llm_question_key = question_key
        st.session_state[question_key] = _default_llm_question(state)

    question = st.text_area(
        "Question for Claude",
        height=80,
        key=question_key,
        placeholder="Pairing plan, who falls, contrarian plays…",
        label_visibility="collapsed",
    )

    if st.button("Ask Claude", type="primary", use_container_width=True, disabled=not st.session_state.anthropic_api_key):
        try:
            fresh = build_state(config, exit_on_error=False)

            def _stream() -> Any:
                yield from stream_evaluate_picks(
                    fresh,
                    st.session_state.anthropic_api_key,
                    user_question=question,
                )

            st.session_state.llm_result = st.write_stream(_stream)
        except Exception as exc:
            st.error(f"AI advisor failed: {exc}")
    elif st.session_state.llm_result:
        st.markdown(st.session_state.llm_result)


def _render_quick_picks(state: DraftState) -> None:
    by_pos = state.recommend_by_position(per_pos=5)
    for pos in ("QB", "RB", "WR", "TE"):
        rows = by_pos.get(pos) or []
        if not rows:
            continue
        with st.expander(f"{pos} — top {len(rows)}", expanded=pos in ("QB", "WR")):
            for row in rows:
                worp = f"{row['worp']:.2f}" if row.get("worp") is not None else "-"
                note = f" · {row['note']}" if row.get("note") else ""
                st.markdown(
                    f"**{row['name']}** ({row['team']}) · TV {row['trade_value']:,.0f} · WORP {worp}{note}"
                )


def _render_league_tab(state: DraftState) -> None:
    teams = build_league_team_rosters(state)
    for team in teams:
        label = f"{'★ ' if team['is_me'] else ''}{team['team_name']} ({team['pick_count']})"
        with st.expander(label, expanded=team["is_me"]):
            if team["position_counts"]:
                st.caption(" · ".join(f"{k}:{v}" for k, v in team["position_counts"].items()))
            for pick in team["picks"]:
                tv = f"TV {pick['trade_value']:,.0f}" if pick.get("trade_value") else ""
                st.markdown(f"#{pick['pick_no']} **{pick['name']}** {pick['pos']} {tv}")

    cliffs = state.tier_cliffs()
    if cliffs:
        st.subheader("Tier cliffs")
        for cliff in cliffs:
            st.markdown(
                f"**{cliff['pos']}:** {cliff['player']} → {cliff['next']} (gap {cliff['gap']:,.0f})"
            )


def _render_my_team_tab(state: DraftState) -> None:
    roster = state.roster_summary()
    if not roster:
        st.info("No picks yet.")
        return
    for row in roster:
        tv = f"TV {row['trade_value']:,.0f}" if row.get("trade_value") else ""
        status = f" · {row['status']}" if row.get("status") and row["status"] != "drafted" else ""
        pick_label = f"#{row['pick_no']}" if row.get("pick_no") else "Rookie"
        st.markdown(f"{pick_label} **{row['name']}** {row['pos']} {tv}{status}")
    needs = state.starter_needs()
    need_bits = [f"{pos}: {count}" for pos, count in needs.items() if count > 0]
    if need_bits:
        st.caption("Needs: " + ", ".join(need_bits))


def _render_settings_tab(config: dict[str, Any]) -> None:
    strategy = config.setdefault("strategy", {})
    config["sleeper_username"] = st.text_input("Sleeper username", value=config.get("sleeper_username", ""))
    config["season"] = st.text_input("Season", value=str(config.get("season", "2026")))
    config["league_id"] = st.text_input("League ID", value=config.get("league_id", ""))
    config["draft_id"] = st.text_input("Draft ID", value=config.get("draft_id", ""))
    config["trade_weight"] = st.slider("Trade value", 0.0, 1.0, float(config.get("trade_weight", 0.45)), 0.05)
    config["worp_weight"] = st.slider("WORP", 0.0, 1.0, float(config.get("worp_weight", 0.55)), 0.05)
    config["poll_seconds"] = st.number_input("Auto-refresh (sec)", 5, 120, int(config.get("poll_seconds", 20)))
    st.session_state.auto_refresh = st.checkbox("Auto-refresh", value=st.session_state.auto_refresh)
    strategy["startup_slot"] = st.number_input("Startup slot", 1, 16, int(strategy.get("startup_slot", 10)))
    strategy["rookie_draft_slot"] = st.number_input("Rookie slot", 1, 16, int(strategy.get("rookie_draft_slot", 1)))
    reserved_text = st.text_area(
        "Reserved rookies",
        value="\n".join(strategy.get("reserved_rookies") or ["Jeremiyah Love"]),
    )
    strategy["reserved_rookies"] = [line.strip() for line in reserved_text.splitlines() if line.strip()]
    if not st.session_state.anthropic_api_key:
        st.session_state.anthropic_api_key = st.text_input("Anthropic API key", type="password")
    st.caption("On Railway, set ANTHROPIC_API_KEY as a service variable instead.")
    if st.button("Save settings", use_container_width=True):
        save_config(config)
        st.success("Saved")


def _render_live_board(state: DraftState) -> None:
    _render_hero(state)
    _render_status_metrics(state)
    upcoming = state.next_pick_info().get("my_upcoming") or []
    if upcoming:
        st.caption(f"Upcoming: {', '.join(str(p) for p in upcoming[:4])}")
    for note in state.strategy.strategy_notes(state.war):
        st.info(note)
    st.subheader("Quick picks")
    _render_quick_picks(state)


def _render_draft_tab(state: DraftState, config: dict[str, Any]) -> None:
    poll = max(5, int(config.get("poll_seconds", 20)))
    refresh = timedelta(seconds=poll) if st.session_state.auto_refresh else None

    @st.fragment(run_every=refresh)
    def live_board() -> None:
        live_state = _load_state(config) or state
        _render_live_board(live_state)

    live_board()
    st.subheader("Claude")
    _render_llm_advisor(state, config)


def main() -> None:
    _init_session()
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    config = st.session_state.config
    draft_name = "Pickbook"

    top = st.columns([3, 1])
    with top[0]:
        st.title("Pickbook")
        st.caption("Dynasty draft companion")
    with top[1]:
        if st.button("Sync", type="primary", use_container_width=True):
            st.rerun()

    state = _load_state(config)
    if state is None:
        st.info("Add your Sleeper username in Settings.")
        tab_draft, tab_team, tab_league, tab_settings = st.tabs(["Draft", "My team", "League", "Settings"])
        with tab_settings:
            _render_settings_tab(config)
        return

    draft_name = (state.draft.get("metadata") or {}).get("name") or draft_name
    st.caption(draft_name)

    tab_draft, tab_team, tab_league, tab_settings = st.tabs(["Draft", "My team", "League", "Settings"])

    with tab_draft:
        _render_draft_tab(state, config)

    with tab_team:
        _render_my_team_tab(state)

    with tab_league:
        _render_league_tab(state)

    with tab_settings:
        _render_settings_tab(config)


if __name__ == "__main__":
    main()
