from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from dynasty_draft.builder import build_state
from dynasty_draft.config import load_config, save_config
from dynasty_draft.draft_context import build_league_team_rosters
from dynasty_draft.llm_advisor import stream_evaluate_picks
from dynasty_draft.pick_projector import project_next_picks
from dynasty_draft.recommender import DraftState

st.set_page_config(
    page_title="Pickbook",
    page_icon="🏈",
    layout="centered",
    initial_sidebar_state="collapsed",
)

MOBILE_CSS = """
<style>
    .block-container { padding-top: 0.75rem; padding-bottom: 2rem; max-width: 680px; }
    h1 { font-size: 1.75rem !important; margin-bottom: 0 !important; }
    [data-testid="stTabs"] button { font-size: 0.95rem; font-weight: 600; }
    .stButton > button {
        min-height: 2.75rem;
        border-radius: 10px;
        font-weight: 600;
    }
    .hero {
        border-radius: 12px;
        padding: 0.85rem 1rem;
        margin: 0.75rem 0;
        font-size: 1rem;
        font-weight: 600;
        color: #fff !important;
    }
    .hero-clock { background: linear-gradient(135deg, #15803d, #16a34a); }
    .hero-wait  { background: linear-gradient(135deg, #c2410c, #ea580c); }
    .hero-book  { background: linear-gradient(135deg, #1d4ed8, #2563eb); }
    .stat-row {
        display: flex;
        gap: 0.5rem;
        margin: 0.5rem 0 0.75rem 0;
    }
    .stat-card {
        flex: 1;
        background: #f1f5f9;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 0.6rem 0.75rem;
        text-align: center;
    }
    .stat-label { font-size: 0.7rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.04em; }
    .stat-value { font-size: 1.1rem; font-weight: 700; color: #0f172a; }
    .player-row {
        padding: 0.55rem 0;
        border-bottom: 1px solid #e2e8f0;
        font-size: 0.92rem;
        color: #0f172a;
    }
    .note-box {
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 10px;
        padding: 0.65rem 0.85rem;
        margin: 0.4rem 0;
        font-size: 0.88rem;
        color: #1e3a5f;
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
    gone = ", ".join(
        f"{(p.get('metadata') or {}).get('first_name', '')} {(p.get('metadata') or {}).get('last_name', '')}".strip()
        for p in sorted(state.picks, key=lambda row: row.get("pick_no", 0))
    )
    if len(picks) >= 2:
        return (
            f"I have picks {picks[0]} and {picks[1]} back-to-back. Already drafted: {gone}. "
            f"Reserving Jeremiyah Love in rookie draft. "
            f"Use the pick_projection data — who is gone before my next turn after pick {picks[-1]}? "
            "Best two-pick plan for trade value (65%) and winning (35%) in superflex."
        )
    return (
        f"Already drafted: {gone}. Use pick_projection to see who's gone in the next 18 picks. "
        "What should I target at my next bookend?"
    )


def _render_hero(state: DraftState) -> None:
    info = state.next_pick_info()
    if info.get("is_my_pick"):
        st.markdown('<div class="hero hero-clock">ON THE CLOCK</div>', unsafe_allow_html=True)
    elif info.get("back_to_back") and info.get("picks_until_mine", 99) <= 3:
        picks = info.get("consecutive_picks") or []
        st.markdown(
            f'<div class="hero hero-book">Bookend — picks #{picks[0]} & #{picks[1]}</div>',
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            f'<div class="hero hero-wait">Picks until yours: {info.get("picks_until_mine", "?")}</div>',
            unsafe_allow_html=True,
        )


def _render_stats(state: DraftState) -> None:
    info = state.next_pick_info()
    synced = (
        f'<div style="font-size:0.75rem;color:#64748b;margin-top:0.35rem">'
        f'Synced {st.session_state.last_sync_at.strftime("%H:%M:%S")}</div>'
        if st.session_state.last_sync_at
        else ""
    )
    upcoming = info.get("my_upcoming") or []
    upcoming_html = (
        f'<div style="font-size:0.8rem;color:#475569;margin-top:0.25rem">'
        f'Next: {", ".join(str(p) for p in upcoming[:4])}</div>'
        if upcoming
        else ""
    )
    st.markdown(
        f"""
        <div class="stat-row">
          <div class="stat-card"><div class="stat-label">Pick</div>
            <div class="stat-value">{len(state.picks)}/{info.get("total_picks", "?")}</div></div>
          <div class="stat-card"><div class="stat-label">Slot</div>
            <div class="stat-value">1.{state.my_slot:02d}</div></div>
          <div class="stat-card"><div class="stat-label">Format</div>
            <div class="stat-value">{"SF" if state.is_superflex() else "Std"}</div></div>
        </div>
        {synced}{upcoming_html}
        """,
        unsafe_allow_html=True,
    )


def _render_projection_preview(state: DraftState) -> None:
    proj = project_next_picks(state)
    window = f"{proj['simulated_from_pick']}–{proj['simulated_through_pick']}"
    next_pick = proj.get("your_next_pick_after_window")
    st.caption(f"Projected picks {window} (ADP + team needs) · your next pick after: #{next_pick or '?'}")
    if proj.get("user_hypothetical_picks"):
        yours = ", ".join(f"{p['name']} ({p['pos']})" for p in proj["user_hypothetical_picks"])
        st.caption(f"Assuming you take: {yours}")
    gone = proj.get("projected_off_board") or []
    if gone:
        top_gone = ", ".join(f"{g['name']}" for g in gone[:8])
        st.caption(f"Likely gone: {top_gone}")


def _render_llm_tab(state: DraftState, config: dict[str, Any]) -> None:
    _render_hero(state)
    _render_stats(state)
    _render_projection_preview(state)

    info = state.next_pick_info()
    question_key = f"llm_q_{len(state.picks)}_{info.get('pick_no')}"
    if st.session_state.llm_question_key != question_key:
        st.session_state.llm_question_key = question_key
        st.session_state[question_key] = _default_llm_question(state)

    question = st.text_area(
        "Question",
        height=88,
        key=question_key,
        label_visibility="collapsed",
        placeholder="Ask about pairings, who falls, what to grab before they're gone…",
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

    with st.expander("18-pick projection detail"):
        proj = project_next_picks(state)
        for row in proj.get("projected_picks") or []:
            st.markdown(f"#{row['pick_no']} **{row['team']}** → {row['name']} ({row['pos']})")


def _player_line(row: dict[str, Any]) -> str:
    worp = f" · WORP {row['worp']:.2f}" if row.get("worp") is not None else ""
    note = f" · {row['note']}" if row.get("note") else ""
    return f"**{row['name']}** ({row['team']}) · TV {row['trade_value']:,.0f}{worp}{note}"


def _render_quick_picks(state: DraftState) -> None:
    by_pos = state.recommend_by_position(per_pos=8)
    for pos in ("QB", "RB", "WR", "TE"):
        rows = by_pos.get(pos) or []
        if not rows:
            continue
        with st.expander(f"{pos} — top {len(rows)}", expanded=pos in ("QB", "WR")):
            for row in rows:
                st.markdown(f'<div class="player-row">{_player_line(row)}</div>', unsafe_allow_html=True)


def _render_draft_tab(state: DraftState, config: dict[str, Any]) -> None:
    poll = max(5, int(config.get("poll_seconds", 20)))
    refresh = timedelta(seconds=poll) if st.session_state.auto_refresh else None

    @st.fragment(run_every=refresh)
    def live_board() -> None:
        live_state = _load_state(config) or state
        _render_hero(live_state)
        _render_stats(live_state)
        for note in live_state.strategy.strategy_notes(live_state.war):
            st.markdown(f'<div class="note-box">{note}</div>', unsafe_allow_html=True)
        st.subheader("Quick picks")
        _render_quick_picks(live_state)

    live_board()


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
    config["trade_weight"] = st.slider("Trade value", 0.0, 1.0, float(config.get("trade_weight", 0.65)), 0.05)
    config["worp_weight"] = st.slider("WORP", 0.0, 1.0, float(config.get("worp_weight", 0.35)), 0.05)
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
    if st.button("Save settings", use_container_width=True):
        save_config(config)
        st.success("Saved")


def main() -> None:
    _init_session()
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    config = st.session_state.config
    header = st.columns([4, 1])
    with header[0]:
        st.title("Pickbook")
    with header[1]:
        if st.button("Sync", type="primary", use_container_width=True):
            st.rerun()

    state = _load_state(config)
    if state is None:
        st.info("Add your Sleeper username in Settings.")
        tab_ask, tab_draft, tab_team, tab_league, tab_settings = st.tabs(
            ["Ask", "Draft", "Team", "League", "Settings"]
        )
        with tab_settings:
            _render_settings_tab(config)
        return

    draft_name = (state.draft.get("metadata") or {}).get("name") or "Draft"
    st.caption(draft_name)

    tab_ask, tab_draft, tab_team, tab_league, tab_settings = st.tabs(
        ["Ask", "Draft", "Team", "League", "Settings"]
    )

    with tab_ask:
        _render_llm_tab(state, config)

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
