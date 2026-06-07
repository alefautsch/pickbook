from __future__ import annotations

import html
import os
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
import streamlit as st

from dynasty_draft.builder import build_state
from dynasty_draft.config import load_config, save_config
from dynasty_draft.draft_context import (
    build_draft_timeline,
    build_league_rankings,
    build_my_team_lineup,
)
from dynasty_draft.llm_advisor import (
    ADVISOR_MODELS,
    advisor_model_by_id,
    build_advisor_context,
    build_followup_context_snippet,
    build_initial_user_message,
    stream_advisor_reply,
)
from dynasty_draft.fall_analysis import build_fall_analysis
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
    :root { color-scheme: light; }
    header[data-testid="stHeader"] { display: none; }
    [data-testid="stToolbar"] { display: none; }
    .stApp,
    [data-testid="stAppViewContainer"],
    .main .block-container {
        margin-top: 0;
        background-color: #ffffff !important;
        color: #0f172a !important;
        color-scheme: light !important;
    }
    .block-container {
        padding-top: max(1.25rem, calc(env(safe-area-inset-top, 0px) + 0.75rem)) !important;
        padding-left: max(1rem, env(safe-area-inset-left, 0px)) !important;
        padding-right: max(1rem, env(safe-area-inset-right, 0px)) !important;
        padding-bottom: 2rem;
        max-width: 680px;
    }
    .app-header {
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.25rem;
    }
    .app-title {
        font-size: 1.65rem;
        font-weight: 800;
        color: #0f172a;
        line-height: 1.15;
        letter-spacing: -0.02em;
    }
    .app-subtitle {
        font-size: 0.85rem;
        color: #64748b;
        margin-top: 0.15rem;
    }
    div[data-testid="column"]:last-child {
        padding-top: 0.2rem;
    }
    div[data-testid="column"]:last-child .stButton > button {
        min-height: 2.35rem;
        padding: 0.35rem 0.85rem;
        font-size: 0.85rem;
        border-radius: 999px;
    }
    [data-testid="stTabs"] { margin-top: 0.25rem; }
    [data-testid="stTabs"] button {
        font-size: 0.95rem;
        font-weight: 600;
        color: #475569 !important;
        background-color: transparent !important;
    }
    [data-testid="stTabs"] button[aria-selected="true"] {
        color: #2563eb !important;
        border-color: #2563eb !important;
    }
    [data-testid="stCaptionContainer"],
    [data-testid="stCaptionContainer"] p,
    .stCaption {
        color: #475569 !important;
        font-size: 0.84rem !important;
        font-weight: 500 !important;
    }
    [data-testid="stExpander"] {
        margin-bottom: 0.5rem;
        border: none !important;
    }
    [data-testid="stExpander"] details {
        background: #ffffff !important;
        border: 1px solid #cbd5e1 !important;
        border-radius: 12px !important;
        overflow: hidden;
        box-shadow: 0 1px 3px rgba(15, 23, 42, 0.06);
    }
    [data-testid="stExpander"] summary {
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%) !important;
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
        font-weight: 700 !important;
        font-size: 0.92rem !important;
        line-height: 1.35 !important;
        padding: 0.85rem 1rem !important;
        list-style: none;
        cursor: pointer;
    }
    [data-testid="stExpander"] summary:hover {
        background: linear-gradient(180deg, #eff6ff 0%, #e0e7ff 100%) !important;
    }
    [data-testid="stExpander"] details[open] summary {
        border-bottom: 1px solid #e2e8f0 !important;
        background: linear-gradient(180deg, #eff6ff 0%, #dbeafe 100%) !important;
    }
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary div {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
        background: #ffffff !important;
        color: #0f172a !important;
        padding: 0.65rem 0.75rem 1rem !important;
    }
    [data-testid="stExpander"] [data-testid="stExpanderDetails"] * {
        color: inherit;
    }
    [data-testid="stChatMessage"] {
        background-color: #ffffff !important;
        border: 1px solid #e2e8f0;
        border-radius: 14px !important;
        color: #0f172a !important;
        margin-bottom: 0.6rem;
        padding: 0.35rem 0.5rem;
        max-width: 96%;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {
        margin-left: auto;
        background: #eff6ff !important;
        border-color: #bfdbfe !important;
    }
    [data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-assistant"]) {
        margin-right: auto;
        background: #f8fafc !important;
    }
    [data-testid="stChatInput"] {
        border-top: 1px solid #e2e8f0;
        padding-top: 0.65rem;
        margin-top: 0.25rem;
    }
    .ask-toolbar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-wrap: wrap;
        gap: 0.45rem 0.75rem;
        padding: 0.6rem 0.85rem;
        margin-bottom: 0.65rem;
        background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%);
        border: 1px solid #e2e8f0;
        border-radius: 12px;
    }
    .ask-toolbar-left { display: flex; align-items: center; gap: 0.55rem; flex-wrap: wrap; }
    .ask-status {
        font-size: 0.8rem;
        font-weight: 800;
        padding: 0.22rem 0.6rem;
        border-radius: 999px;
        white-space: nowrap;
        letter-spacing: 0.01em;
    }
    .ask-status-clock { background: #dcfce7; color: #166534; }
    .ask-status-book { background: #dbeafe; color: #1e40af; }
    .ask-status-wait { background: #ffedd5; color: #9a3412; }
    .ask-meta {
        font-size: 0.76rem;
        color: #64748b;
        font-weight: 600;
        white-space: nowrap;
    }
    .ask-empty {
        text-align: center;
        padding: 1.5rem 0.75rem 0.75rem;
        margin-bottom: 0.25rem;
    }
    .ask-empty-title {
        font-size: 1.12rem;
        font-weight: 800;
        color: #0f172a;
        margin-bottom: 0.3rem;
        letter-spacing: -0.01em;
    }
    .ask-empty-sub {
        font-size: 0.84rem;
        color: #64748b;
        line-height: 1.45;
        max-width: 22rem;
        margin: 0 auto;
    }
    div[data-testid="stVerticalBlock"]:has(> div .ask-chips-marker) .stButton > button {
        min-height: 2.35rem;
        font-size: 0.82rem;
        font-weight: 600;
        background: #ffffff !important;
        color: #1e40af !important;
        border: 1px solid #bfdbfe !important;
        border-radius: 999px !important;
        box-shadow: none !important;
    }
    div[data-testid="stVerticalBlock"]:has(> div .ask-chips-marker) .stButton > button:hover {
        background: #eff6ff !important;
        border-color: #93c5fd !important;
    }
    .ask-controls .stButton > button {
        min-height: 2.35rem;
        font-size: 0.8rem;
        border-radius: 10px;
    }
    .ask-controls [data-baseweb="select"] > div {
        min-height: 2.35rem !important;
        font-size: 0.82rem !important;
    }
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"],
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] p,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] li,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ul,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] ol,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h1,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h2,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h3,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] h4,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] strong,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] em,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] span,
    [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] div,
    [data-testid="stMarkdownContainer"] p,
    [data-testid="stMarkdownContainer"] li,
    [data-testid="stMarkdownContainer"] h1,
    [data-testid="stMarkdownContainer"] h2,
    [data-testid="stMarkdownContainer"] h3,
    [data-testid="stMarkdownContainer"] h4,
    [data-testid="stMarkdownContainer"] strong,
    [data-testid="stMarkdownContainer"] em,
    [data-testid="stMarkdownContainer"] span {
        color: #0f172a !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    [data-testid="stMarkdownContainer"] a {
        color: #2563eb !important;
        -webkit-text-fill-color: #2563eb !important;
    }
    [data-testid="stMarkdownContainer"] code {
        color: #0f172a !important;
        background-color: #f1f5f9 !important;
        -webkit-text-fill-color: #0f172a !important;
    }
    [data-testid="stMarkdownContainer"] pre {
        background-color: #f1f5f9 !important;
        color: #0f172a !important;
    }
    [data-testid="stChatInput"] textarea {
        color: #0f172a !important;
        background-color: #f8fafc !important;
        -webkit-text-fill-color: #0f172a !important;
        caret-color: #0f172a !important;
    }
    .thinking-line {
        color: #64748b !important;
        font-style: italic;
    }
    .stButton > button {
        min-height: 2.75rem;
        border-radius: 10px;
        font-weight: 600;
    }
    .stButton > button[kind="primary"],
    .stButton > button[data-testid="stBaseButton-primary"] {
        background: linear-gradient(135deg, #1d4ed8, #2563eb) !important;
        border: none !important;
        color: #ffffff !important;
        box-shadow: 0 2px 8px rgba(37, 99, 235, 0.28);
    }
    .stButton > button[kind="primary"]:hover {
        background: linear-gradient(135deg, #1e40af, #1d4ed8) !important;
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
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
        margin: 0.5rem 0 0.75rem 0;
    }
    @media (min-width: 520px) {
        .stat-row { grid-template-columns: repeat(3, minmax(0, 1fr)); }
    }
    @media (min-width: 680px) {
        .stat-row { grid-template-columns: repeat(5, minmax(0, 1fr)); }
    }
    .stat-card {
        background: #ffffff;
        border: 1px solid #cbd5e1;
        border-radius: 10px;
        padding: 0.65rem 0.75rem;
        text-align: center;
        box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04);
    }
    .stat-label {
        font-size: 0.68rem;
        color: #475569;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.06em;
    }
    .stat-value { font-size: 1.15rem; font-weight: 800; color: #0f172a; line-height: 1.2; }
    .team-chip-row {
        display: flex;
        flex-wrap: wrap;
        gap: 0.35rem;
        margin: 0 0 0.65rem 0;
    }
    .team-chip {
        display: inline-block;
        font-size: 0.72rem;
        font-weight: 700;
        color: #1e3a8a;
        background: #eff6ff;
        border: 1px solid #bfdbfe;
        border-radius: 999px;
        padding: 0.2rem 0.55rem;
        white-space: nowrap;
    }
    .team-chip-muted { color: #475569; background: #f8fafc; border-color: #e2e8f0; }
    .section-title {
        font-size: 1.05rem;
        font-weight: 800;
        color: #0f172a;
        margin: 1.15rem 0 0.55rem 0;
        padding-bottom: 0.35rem;
        border-bottom: 2px solid #e2e8f0;
        letter-spacing: -0.01em;
    }
    .table-wrap {
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        border: 1px solid #e2e8f0;
        border-radius: 10px;
        margin-bottom: 0.75rem;
        background: #fff;
    }
    .pick-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.82rem;
    }
    .pick-table th {
        background: #e2e8f0 !important;
        color: #1e293b !important;
        font-weight: 800;
        text-transform: uppercase;
        font-size: 0.68rem;
        letter-spacing: 0.06em;
        padding: 0.6rem 0.5rem;
        border-bottom: 2px solid #cbd5e1 !important;
        text-align: left;
        white-space: nowrap;
    }
    .pick-table td {
        padding: 0.55rem 0.5rem;
        border-bottom: 1px solid #f1f5f9;
        color: #0f172a !important;
        background: #ffffff !important;
        vertical-align: middle;
    }
    .pick-table tr:last-child td { border-bottom: none; }
    .pick-table .num { text-align: right; font-variant-numeric: tabular-nums; color: #334155; }
    .pick-table .age { color: #64748b; font-size: 0.78rem; text-align: center; }
    .pick-table .pos {
        font-size: 0.68rem;
        font-weight: 700;
        color: #475569;
        background: #f1f5f9;
        border-radius: 4px;
        padding: 0.1rem 0.35rem;
    }
    .pick-table tr.row-me { background: #eff6ff; }
    .pick-table tr.row-clock { background: #fff7ed; }
    .pick-table tr.row-clock td:first-child {
        box-shadow: inset 3px 0 0 #ea580c;
    }
    .pick-table tr.row-mine td:first-child {
        box-shadow: inset 3px 0 0 #2563eb;
    }
    .pick-table .player { font-weight: 600; }
    .pick-table .muted { color: #94a3b8; font-style: italic; }
    .pick-table .note { font-size: 0.72rem; color: #64748b; max-width: 7rem; }
    .pick-table .adp { font-variant-numeric: tabular-nums; font-weight: 600; white-space: nowrap; }
    .pick-table .adp-steal { color: #15803d; background: #f0fdf4; border-radius: 4px; padding: 0.1rem 0.35rem; }
    .pick-table .adp-fair { color: #475569; }
    .pick-table .adp-reach { color: #b45309; background: #fffbeb; border-radius: 4px; padding: 0.1rem 0.35rem; }
    .pick-table .adp-unknown { color: #94a3b8; }
    .pick-table .worp-proj { color: #7c3aed; font-weight: 700; }
    .pick-table .dynasty { font-variant-numeric: tabular-nums; font-weight: 800; }
    .pick-table .dynasty-high { color: #1d4ed8; }
    .pick-table .dynasty-mid { color: #475569; }
    .pick-table .dynasty-low { color: #94a3b8; }
    .lineup-table .slot-label {
        width: 2.75rem;
        font-size: 0.68rem;
        font-weight: 800;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        white-space: nowrap;
    }
    .lineup-table tr.row-empty td { color: #94a3b8; font-style: italic; }
    .lineup-table tr.row-reserved { background: #faf5ff; }
    .lineup-table .tv { font-weight: 700; color: #1d4ed8; }
    .lineup-table .worp { font-weight: 700; color: #15803d; }
    .pick-table tr.row-you { background: #eff6ff; }
    .rank-badge {
        display: inline-block;
        min-width: 1.5rem;
        font-weight: 800;
        color: #64748b;
    }
    .rank-you .rank-badge { color: #1d4ed8; }
    .lineup-table .age { color: #64748b; font-size: 0.78rem; }
    .lineup-divider td {
        background: #f8fafc;
        color: #64748b;
        font-size: 0.65rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding: 0.45rem 0.5rem;
        border-bottom: 1px solid #e2e8f0;
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

    @media (prefers-color-scheme: dark) {
        .stApp,
        [data-testid="stAppViewContainer"],
        .main .block-container {
            background-color: #ffffff !important;
            color: #0f172a !important;
        }
        .table-wrap { background: #ffffff !important; border-color: #e2e8f0 !important; }
        .pick-table th {
            background: #f1f5f9 !important;
            color: #334155 !important;
        }
        .pick-table td { color: #0f172a !important; background: #ffffff !important; }
        .stat-card { background: #f1f5f9 !important; border-color: #cbd5e1 !important; }
        .stat-value, .section-title, .app-title { color: #0f172a !important; }
        [data-testid="stTabs"] button { color: #475569 !important; }
        [data-testid="stTabs"] button[aria-selected="true"] { color: #2563eb !important; }
        [data-testid="stExpander"] details {
            background: #ffffff !important;
            border-color: #cbd5e1 !important;
        }
        [data-testid="stExpander"] summary {
            background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%) !important;
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
        }
        [data-testid="stExpander"] summary span,
        [data-testid="stExpander"] summary p,
        [data-testid="stExpander"] summary div {
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
        }
        [data-testid="stExpander"] [data-testid="stExpanderDetails"] {
            background: #ffffff !important;
            color: #0f172a !important;
        }
        [data-testid="stChatMessage"] {
            background-color: #f8fafc !important;
            color: #0f172a !important;
        }
        [data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] *,
        [data-testid="stMarkdownContainer"] p,
        [data-testid="stMarkdownContainer"] li,
        [data-testid="stMarkdownContainer"] h1,
        [data-testid="stMarkdownContainer"] h2,
        [data-testid="stMarkdownContainer"] h3,
        [data-testid="stMarkdownContainer"] strong,
        [data-testid="stMarkdownContainer"] span {
            color: #0f172a !important;
            -webkit-text-fill-color: #0f172a !important;
        }
        [data-testid="stChatInput"] textarea {
            color: #0f172a !important;
            background-color: #f8fafc !important;
            -webkit-text-fill-color: #0f172a !important;
        }
    }
</style>
"""


def _init_session() -> None:
    if "config" not in st.session_state:
        st.session_state.config = load_config()
    if "anthropic_api_key" not in st.session_state:
        st.session_state.anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if "moonshot_api_key" not in st.session_state:
        st.session_state.moonshot_api_key = os.environ.get("MOONSHOT_API_KEY", "").strip()
    if "advisor_model_id" not in st.session_state:
        st.session_state.advisor_model_id = ADVISOR_MODELS[0]["id"]
    if "llm_thread_key" not in st.session_state:
        st.session_state.llm_thread_key = ""
    if "llm_messages" not in st.session_state:
        st.session_state.llm_messages = []
    if "llm_generating" not in st.session_state:
        st.session_state.llm_generating = False
    if "auto_refresh" not in st.session_state:
        st.session_state.auto_refresh = True
    if "last_sync_at" not in st.session_state:
        st.session_state.last_sync_at = None


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


def _ask_status_badge(state: DraftState) -> tuple[str, str]:
    info = state.next_pick_info()
    if info.get("is_my_pick"):
        return "On the clock", "ask-status-clock"
    picks = info.get("consecutive_picks") or []
    if info.get("back_to_back") and info.get("picks_until_mine", 99) <= 3 and len(picks) >= 2:
        return f"Bookend · #{picks[0]} & #{picks[1]}", "ask-status-book"
    until = info.get("picks_until_mine")
    return f"{until} picks away" if until is not None else "Waiting", "ask-status-wait"


def _ask_suggestion_prompts(state: DraftState) -> list[tuple[str, str]]:
    return [
        ("Bookend plan", _default_llm_question(state)),
        (
            "Bookend targets",
            "Use bookend_dynasty_targets and dynasty_rating (not just falls_to_you sim). "
            "Best two-pick plan at my bookend for superflex startup — prioritize youth and dynasty OVR, "
            "especially at QB. Compare top_by_dynasty_rating vs sim board.",
        ),
        (
            "Roster needs",
            "Review my_roster, starter_needs, bookend_dynasty_targets, and league_rankings. "
            "What positions and players should I prioritize at my next bookend in this superflex startup?",
        ),
        (
            "Value check",
            "Compare bpa_recommendations vs need_adjusted_recommendations and value_pivot.take_bpa_over_need. "
            "Should I take BPA when a player falls (adp_delta >= 6) even if I have roster needs elsewhere? "
            "Include trade-market path to fill holes.",
        ),
    ]


def _render_ask_toolbar(state: DraftState) -> None:
    info = state.next_pick_info()
    status, status_class = _ask_status_badge(state)
    slot = f"1.{state.my_slot:02d}" if state.my_slot else "?"
    fmt = "SF" if state.is_superflex() else "1QB"
    pick_prog = f"{len(state.picks)}/{info.get('total_picks', '?')}"
    st.markdown(
        f"""
        <div class="ask-toolbar">
          <div class="ask-toolbar-left">
            <span class="ask-status {status_class}">{html.escape(status)}</span>
            <span class="ask-meta">Pick {pick_prog} · Slot {slot} · {fmt}</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_ask_chip_prompts(state: DraftState, config: dict[str, Any]) -> None:
    prompts = _ask_suggestion_prompts(state)
    st.markdown('<div class="ask-chips-marker"></div>', unsafe_allow_html=True)
    cols = st.columns(len(prompts))
    for col, (label, prompt) in zip(cols, prompts):
        with col:
            if st.button(label, key=f"ask_chip_{label}", use_container_width=True):
                if _queue_advisor_message(state, config, prompt):
                    st.rerun()


def _bookend_window_label(
    pick_rows: list[dict[str, Any]],
    *,
    yours_at: list[int] | None = None,
) -> str:
    if not pick_rows:
        return ""
    start = pick_rows[0].get("pick_no")
    end = pick_rows[-1].get("pick_no")
    if start is None or end is None:
        return f" ({len(pick_rows)} picks)"
    window = f"#{start}" if start == end else f"#{start}–#{end}"
    if yours_at:
        yours = f"#{yours_at[0]}" + (f" & #{yours_at[1]}" if len(yours_at) > 1 else "")
        return f" ({window} → yours at {yours})"
    return f" ({window})"


def _render_bookend_projection_sections(proj: dict[str, Any], *, detailed: bool = False) -> None:
    """Bookend sim: before your turn → your pair → between → next pair."""
    current = proj.get("current_bookend") or {}
    nxt = proj.get("next_bookend") or {}
    before = current.get("picks_before") or []
    cur_nums = current.get("pick_numbers") or []
    between = (proj.get("between_bookends") or {}).get("projected_picks") or []
    nxt_nums = nxt.get("pick_numbers") or []

    if before:
        heading = "**Before your bookend**" + _bookend_window_label(before, yours_at=cur_nums)
        if detailed:
            st.markdown(heading)
            for row in before:
                team = html.escape(str(row.get("team") or ""))
                st.markdown(f"#{row['pick_no']} **{team}** → {_fmt_player_brief(row)}")
        else:
            names = ", ".join(_fmt_player_brief(r) for r in before[:6])
            if len(before) > 6:
                names += f" +{len(before) - 6} more"
            st.caption(f"Before your bookend{_bookend_window_label(before, yours_at=cur_nums)}: {names}")

    if current.get("planned_picks"):
        yours_nums = " & ".join(f"#{n}" for n in cur_nums) if cur_nums else ""
        if detailed:
            st.markdown(f"**Your bookend{' ' + yours_nums if yours_nums else ''}**")
            for row in current["planned_picks"]:
                st.markdown(f"#{row['pick_no']} **{_fmt_player_brief(row)}**")
        else:
            yours = ", ".join(_fmt_player_brief(p) for p in current["planned_picks"])
            st.caption(f"Your bookend ({yours_nums}): assuming {yours}")

    if between:
        bet_nums = nxt_nums or []
        heading = "**Between bookends**" + _bookend_window_label(
            between,
            yours_at=bet_nums if bet_nums else None,
        )
        if detailed:
            st.markdown(heading)
            for row in between:
                team = html.escape(str(row.get("team") or ""))
                st.markdown(f"#{row['pick_no']} **{team}** → {_fmt_player_brief(row)}")
        else:
            gone = (proj.get("between_bookends") or {}).get("likely_off_board") or []
            if gone:
                top_gone = ", ".join(f"{g['name']}" for g in gone[:8])
                st.caption(
                    f"Likely gone before next bookend"
                    f"{_bookend_window_label(between, yours_at=bet_nums)}: {top_gone}"
                )

    if nxt.get("planned_picks"):
        nxt_label = " & ".join(f"#{n}" for n in nxt_nums) if nxt_nums else ""
        if detailed:
            st.markdown(f"**Next bookend{' ' + nxt_label if nxt_label else ''}**")
            for row in nxt["planned_picks"]:
                st.markdown(f"#{row['pick_no']} **{_fmt_player_brief(row)}**")
        elif nxt_label:
            nxt_yours = ", ".join(_fmt_player_brief(p) for p in nxt["planned_picks"])
            st.caption(f"Next bookend ({nxt_label}): projected {nxt_yours}")


def _render_ask_draft_context(state: DraftState) -> None:
    with st.expander("Draft context", expanded=False):
        _render_hero(state)
        _render_stats(state)
        _render_bpa_comparison(state, compact=True)
        _render_bookend_projection_sections(project_next_picks(state), detailed=True)


def _default_llm_question(state: DraftState) -> str:
    info = state.next_pick_info()
    picks = info.get("consecutive_picks") or []
    gone = ", ".join(
        f"{(p.get('metadata') or {}).get('first_name', '')} {(p.get('metadata') or {}).get('last_name', '')}".strip()
        for p in sorted(state.picks, key=lambda row: row.get("pick_no", 0))
    )
    proj = project_next_picks(state)
    nxt = proj.get("next_bookend") or {}
    next_picks = nxt.get("pick_numbers") or []
    next_label = f"{next_picks[0]} & {next_picks[1]}" if len(next_picks) >= 2 else "?"
    if len(picks) >= 2:
        return (
            f"I have picks {picks[0]} and {picks[1]} back-to-back. Already drafted: {gone}. "
            f"Reserving Jeremiyah Love in rookie draft. Superflex startup — lead with "
            f"bookend_dynasty_targets and dynasty_rating (age + WORP* + TV), not TV-only sim. "
            f"Best two-pick plan at this bookend, then who to target at my NEXT bookend (picks {next_label}). "
            "Favor young upside at QB over aging win-now vets."
        )
    return (
        f"Already drafted: {gone}. Superflex startup — use bookend_dynasty_targets and dynasty_rating. "
        f"Who should I target at my next bookend (picks {next_label}) and the one after?"
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
    _render_bookend_projection_sections(project_next_picks(state), detailed=False)


def _llm_thread_key(state: DraftState) -> str:
    info = state.next_pick_info()
    return f"advisor_v4_{len(state.picks)}_{info.get('pick_no')}"


def _sync_llm_thread(state: DraftState) -> None:
    thread_key = _llm_thread_key(state)
    if st.session_state.llm_thread_key != thread_key:
        st.session_state.llm_thread_key = thread_key
        st.session_state.llm_messages = []
        st.session_state.llm_generating = False


def _advisor_api_key(provider: str) -> str:
    if provider == "moonshot":
        return st.session_state.moonshot_api_key
    return st.session_state.anthropic_api_key


def _queue_advisor_message(state: DraftState, config: dict[str, Any], user_text: str) -> bool:
    user_text = user_text.strip()
    if not user_text:
        return False

    model_row = advisor_model_by_id(st.session_state.advisor_model_id)
    if not _advisor_api_key(model_row["provider"]):
        st.error(f"Add a {model_row['label']} API key in Settings or .env.")
        return False

    fresh = build_state(config, exit_on_error=False)
    is_first_turn = not st.session_state.llm_messages
    if is_first_turn:
        context = build_advisor_context(fresh)
        user_content = build_initial_user_message(context, user_text)
    else:
        snippet = build_followup_context_snippet(fresh)
        user_content = f"{snippet}\n\n{user_text}"

    st.session_state.llm_messages.append(
        {"role": "user", "content": user_content, "label": user_text}
    )
    st.session_state.llm_generating = True
    return True


def _awaiting_advisor_reply() -> bool:
    msgs = st.session_state.llm_messages
    return bool(st.session_state.llm_generating and msgs and msgs[-1]["role"] == "user")


def _complete_advisor_reply(config: dict[str, Any]) -> None:
    model_row = advisor_model_by_id(st.session_state.advisor_model_id)
    provider = model_row["provider"]
    api_key = _advisor_api_key(provider)
    api_messages = [
        {"role": m["role"], "content": m["content"]}
        for m in st.session_state.llm_messages
        if m["role"] in ("user", "assistant")
    ]

    try:
        with st.chat_message("assistant"):
            output = st.empty()
            output.markdown('<p class="thinking-line">Thinking…</p>', unsafe_allow_html=True)
            chunks: list[str] = []
            for chunk in stream_advisor_reply(
                api_key,
                provider=provider,  # type: ignore[arg-type]
                model=model_row["model"],
                messages=api_messages,
            ):
                chunks.append(chunk)
                output.markdown("".join(chunks) + " ▍")
            reply = "".join(chunks)
            output.markdown(reply)
        st.session_state.llm_messages.append({"role": "assistant", "content": reply})
    except Exception as exc:
        st.session_state.llm_messages.pop()
        st.error(f"AI advisor failed: {exc}")
    finally:
        st.session_state.llm_generating = False


def _render_llm_tab(state: DraftState, config: dict[str, Any]) -> None:
    _sync_llm_thread(state)
    _render_ask_toolbar(state)

    st.markdown('<div class="ask-controls">', unsafe_allow_html=True)
    controls = st.columns([3, 1])
    with controls[0]:
        model_labels = {row["id"]: row["label"] for row in ADVISOR_MODELS}
        st.selectbox(
            "Model",
            options=list(model_labels.keys()),
            format_func=lambda key: model_labels[key],
            label_visibility="collapsed",
            key="advisor_model_id",
        )
    with controls[1]:
        if st.button("New chat", use_container_width=True):
            st.session_state.llm_messages = []
            st.session_state.llm_generating = False
            st.rerun()
    st.markdown("</div>", unsafe_allow_html=True)

    model_row = advisor_model_by_id(st.session_state.advisor_model_id)
    if not _advisor_api_key(model_row["provider"]):
        env_key = "MOONSHOT_API_KEY" if model_row["provider"] == "moonshot" else "ANTHROPIC_API_KEY"
        st.warning(f"Add {env_key} in Settings to use the advisor.")

    history = st.session_state.llm_messages
    busy = st.session_state.llm_generating

    if not history and not busy:
        st.markdown(
            """
            <div class="ask-empty">
              <div class="ask-empty-title">What do you want to know?</div>
              <div class="ask-empty-sub">
                Bookend strategy, fallers, roster fit — answers use your live draft and league data.
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        _render_ask_chip_prompts(state, config)

    for i, msg in enumerate(history):
        if _awaiting_advisor_reply() and i == len(history) - 1 and msg["role"] == "user":
            continue
        with st.chat_message(msg["role"]):
            shown = msg.get("label") if msg["role"] == "user" and msg.get("label") else msg["content"]
            st.markdown(shown)

    if _awaiting_advisor_reply():
        last = history[-1]
        with st.chat_message("user"):
            st.markdown(last.get("label") or last["content"])
        _complete_advisor_reply(config)
        st.rerun()

    prompt = st.chat_input("Ask about your draft…", disabled=busy)
    if prompt and not busy:
        if _queue_advisor_message(state, config, prompt):
            st.rerun()

    if not history and not busy:
        _render_bpa_comparison(state, compact=True)

    _render_ask_draft_context(state)


def _fmt_tv(value: float | int | None) -> str:
    return f"{value:,.0f}" if value is not None else "—"


def _fmt_worp(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "—"


def _fmt_worp_cell(row: dict[str, Any]) -> str:
    effective = row.get("effective_worp")
    if effective is None and row.get("projected_worp") is not None:
        effective = row.get("projected_worp")
    if effective is not None:
        historical = row.get("worp")
        uses_projection = bool(row.get("worp_uses_projection"))
        show_star = uses_projection or historical is None or abs(effective - historical) > 0.02
        if show_star:
            return (
                f'<span class="num worp-proj" title="Blended WORP (historical + Sleeper projection)">'
                f"{effective:.2f}*</span>"
            )
        return f'<span class="num">{effective:.2f}</span>'
    return f'<span class="num">{_fmt_worp(row.get("worp"))}</span>'


def _dynasty_class(rating: int | None) -> str:
    """50–99 Madden-style tiers."""
    if rating is None:
        return "dynasty-low"
    if rating >= 90:
        return "dynasty-high"
    if rating >= 78:
        return "dynasty-mid"
    return "dynasty-low"


def _fmt_dynasty_rating(
    rating: int | None,
    *,
    components: dict[str, Any] | None = None,
    raw_score: float | None = None,
    age: int | None = None,
    rookie: bool = False,
) -> str:
    if rating is None:
        return '<span class="dynasty dynasty-low">—</span>'
    comp = components or {}
    title = (
        f"TV {comp.get('tv', '—')} · WORP {comp.get('worp', '—')} · "
        f"upside {comp.get('upside', '—')} · age {comp.get('age', '—')} · "
        f"trajectory {comp.get('trajectory', '—')}"
    )
    if raw_score is not None:
        title += f" · raw {raw_score:.2f}"
    if age is not None:
        title += f" · player age {age}"
    if rookie:
        title += " · rookie projection (no historical WORP)"
    cls = _dynasty_class(rating)
    suffix = "*" if rookie else ""
    return (
        f'<span class="dynasty {cls}" title="{html.escape(title)}">{rating}{suffix}</span>'
    )


def _fmt_dynasty_cell(row: dict[str, Any]) -> str:
    return _fmt_dynasty_rating(
        row.get("dynasty_rating"),
        components=row.get("dynasty_components"),
        raw_score=row.get("dynasty_score"),
        age=row.get("age"),
        rookie=bool(row.get("dynasty_rookie")),
    )


def _fmt_adp_cell(row: dict[str, Any]) -> str:
    adp_pick = row.get("adp_pick")
    if adp_pick is None:
        return '<span class="adp adp-unknown">—</span>'
    delta = row.get("adp_delta")
    cls = row.get("adp_class") or "adp-fair"
    label = f"#{adp_pick}"
    if delta is not None and delta != 0:
        sign = "+" if delta > 0 else ""
        label = f"#{adp_pick} ({sign}{delta})"
    return f'<span class="adp {cls}">{html.escape(label)}</span>'


def _fmt_age(value: int | None) -> str:
    return str(value) if value is not None else "—"


def _fmt_age_cell(row: dict[str, Any]) -> str:
    return f'<span class="age">{_fmt_age(row.get("age"))}</span>'


def _fmt_player_brief(row: dict[str, Any]) -> str:
    bits = [row.get("pos") or ""]
    if row.get("age") is not None:
        bits.append(str(row["age"]))
    if row.get("dynasty_rating") is not None:
        bits.append(f"Dyn {row['dynasty_rating']}")
    return f"{row['name']} ({', '.join(bits)})"


def _fmt_porp(value: float | None) -> str:
    return f"{value:.0f}" if value is not None else "—"


def _fmt_porp_cell(row: dict[str, Any]) -> str:
    return f'<span class="num">{_fmt_porp(row.get("porp"))}</span>'


def _fmt_flex_cell(row: dict[str, Any]) -> str:
    rating = row.get("flex_rating")
    if rating is None:
        return '<span class="num muted">—</span>'
    rank = row.get("flex_rank")
    title = f' title="Flex #{rank}"' if rank else ""
    return f'<span class="num"{title}>{rating}</span>'


def _html_table(
    headers: list[str],
    body_rows: list[list[str]],
    row_classes: list[str] | None = None,
    *,
    table_class: str = "pick-table",
) -> str:
    head = "".join(f"<th>{html.escape(h)}</th>" for h in headers)
    rows_html: list[str] = []
    for i, cells in enumerate(body_rows):
        cls = row_classes[i] if row_classes else ""
        class_attr = f' class="{cls}"' if cls else ""
        tds = "".join(f"<td>{cell}</td>" for cell in cells)
        rows_html.append(f"<tr{class_attr}>{tds}</tr>")
    return (
        f'<div class="table-wrap"><table class="{table_class}">'
        f"<thead><tr>{head}</tr></thead>"
        f"<tbody>{''.join(rows_html)}</tbody></table></div>"
    )


def _recommendation_table_rows(
    rows: list[dict[str, Any]],
    *,
    include_pos: bool = False,
    include_adp: bool = False,
) -> list[list[str]]:
    body: list[list[str]] = []
    for row in rows:
        note = html.escape(row["note"]) if row.get("note") else ""
        pos_cell = f'<span class="pos">{html.escape(row.get("pos") or "")}</span>'
        cells = [
            f'<span class="player">{html.escape(row["name"])}</span>',
            *( [pos_cell] if include_pos else [] ),
            html.escape(row.get("team") or ""),
            _fmt_age_cell(row),
            *([_fmt_adp_cell(row)] if include_adp else []),
            _fmt_dynasty_cell(row),
            f'<span class="num">{_fmt_tv(row.get("trade_value"))}</span>',
            _fmt_worp_cell(row),
            _fmt_flex_cell(row),
            _fmt_porp_cell(row),
            f'<span class="note">{note}</span>' if note else "",
        ]
        body.append(cells)
    return body


def _render_bpa_comparison(state: DraftState, *, compact: bool = False) -> None:
    """Side-by-side BPA (VBD) vs need-adjusted rankings."""
    limit = 6 if compact else 12
    bpa = state.bpa_recommendations(limit=limit)
    need = state.recommend(limit=limit)
    if not bpa and not need:
        return

    ref = state._adp_reference_pick()
    pivot = state.value_pivot_summary(limit=6)
    overrides = pivot.get("take_bpa_over_need") or []
    wait = pivot.get("wait_for_later") or []

    if not compact:
        st.markdown('<div class="section-title">Best available</div>', unsafe_allow_html=True)
    st.caption(
        f"Pick #{ref}. ADP source: {html.escape(state._adp_index().source_label)}. "
        "BPA = cross-position value with ADP bonus/penalty (reach = negative delta). "
        "Need-adjusted = starter-need nudges."
    )
    if wait:
        wait_text = ", ".join(
            f"{row['name']} (ADP #{row.get('adp_pick')})" for row in wait[:4]
        )
        st.warning(f"Wait for later bookend: {wait_text}")
    if overrides:
        override_text = ", ".join(
            f"{row['name']} (BPA #{row['bpa_rank']} vs need #{row['need_rank']})"
            for row in overrides[:4]
        )
        st.info(f"Value override: {override_text}")

    headers = ["Player", "Pos", "Tm", "Age", "ADP", "Dyn", "TV", "WORP", "Flex", "PORP", "Note"]
    if compact:
        headers = ["Player", "Pos", "ADP", "Dyn", "Flex", "PORP", "Note"]

    def _compact_rows(rows: list[dict[str, Any]]) -> list[list[str]]:
        if not compact:
            return _recommendation_table_rows(rows, include_pos=True, include_adp=True)
        body: list[list[str]] = []
        for row in rows:
            note = html.escape(row.get("note") or "")
            body.append(
                [
                    f'<span class="player">{html.escape(row["name"])}</span>',
                    f'<span class="pos">{html.escape(row.get("pos") or "")}</span>',
                    _fmt_adp_cell(row),
                    _fmt_dynasty_cell(row),
                    _fmt_flex_cell(row),
                    _fmt_porp_cell(row),
                    f'<span class="note">{note}</span>' if note else "",
                ]
            )
        return body

    col_bpa, col_need = st.columns(2)
    with col_bpa:
        st.markdown("**BPA (VBD)**")
        if bpa:
            st.markdown(_html_table(headers, _compact_rows(bpa)), unsafe_allow_html=True)
    with col_need:
        st.markdown("**Need-adjusted**")
        if need:
            st.markdown(_html_table(headers, _compact_rows(need)), unsafe_allow_html=True)


def _render_best_available(state: DraftState) -> None:
    _render_bpa_comparison(state, compact=False)


def _render_fall_preview(state: DraftState) -> None:
    fall = build_fall_analysis(state)
    blocks = fall.get("at_each_pick") or []
    if not blocks:
        return
    st.markdown('<div class="section-title">Who could fall to you</div>', unsafe_allow_html=True)
    st.caption("Sim board vs dynasty-ranked targets at each bookend pick.")
    for block in blocks:
        pick_no = block.get("pick_no")
        dyn_top = block.get("top_by_dynasty_rating") or []
        values = block.get("value_vs_adp") or []
        fallers = block.get("likely_fallers") or []
        if not dyn_top:
            continue
        names = ", ".join(_fmt_player_brief(row) for row in dyn_top[:6])
        st.markdown(f"**Pick #{pick_no}** — dynasty top: {html.escape(names)}")
        if values:
            val_names = ", ".join(
                f"{row['name']} (+{row.get('adp_delta')} ADP)" for row in values[:4]
            )
            st.markdown(f'<span class="note-box">VBD value: {html.escape(val_names)}</span>', unsafe_allow_html=True)
        if fallers:
            fall_names = ", ".join(_fmt_player_brief(row) for row in fallers[:4])
            st.markdown(f'<span class="note-box">Likely fallers: {html.escape(fall_names)}</span>', unsafe_allow_html=True)


def _render_quick_picks(state: DraftState) -> None:
    bpa_by_pos = state.bpa_by_position(per_pos=8)
    need_by_pos = state.recommend_by_position(per_pos=8)
    for pos in ("QB", "RB", "WR", "TE"):
        bpa_rows = bpa_by_pos.get(pos) or []
        need_rows = need_by_pos.get(pos) or []
        if not bpa_rows and not need_rows:
            continue
        with st.expander(f"{pos} — BPA vs need", expanded=pos in ("QB", "WR")):
            col_bpa, col_need = st.columns(2)
            headers = ["Player", "Tm", "Age", "ADP", "Dyn", "TV", "WORP", "Flex", "PORP", "Note"]
            with col_bpa:
                st.markdown("**BPA**")
                if bpa_rows:
                    st.markdown(
                        _html_table(headers, _recommendation_table_rows(bpa_rows, include_adp=True)),
                        unsafe_allow_html=True,
                    )
            with col_need:
                st.markdown("**Need-adjusted**")
                if need_rows:
                    st.markdown(
                        _html_table(headers, _recommendation_table_rows(need_rows, include_adp=True)),
                        unsafe_allow_html=True,
                    )


def _render_draft_timeline(state: DraftState) -> None:
    timeline = build_draft_timeline(state, past=8, upcoming=10)
    if not timeline:
        return
    st.markdown('<div class="section-title">Draft timeline</div>', unsafe_allow_html=True)
    body: list[list[str]] = []
    row_classes: list[str] = []
    for row in timeline:
        status = row.get("status", "done")
        if status == "on_clock":
            row_classes.append("row-clock")
        elif row.get("is_me"):
            row_classes.append("row-me" if status == "done" else "row-me row-mine")
        else:
            row_classes.append("")

        pick_label = f"#{row['pick_no']}"
        if status == "on_clock":
            pick_label = f"#{row['pick_no']} ●"

        team = html.escape(str(row.get("team") or ""))
        if row.get("is_me") and status != "done":
            team = f"<strong>{team}</strong>"

        if row.get("name"):
            player = (
                f'<span class="player">{html.escape(row["name"])}</span> '
                f'<span class="pos">{html.escape(row.get("pos") or "")}</span>'
            )
            ovr = _fmt_dynasty_cell(row)
            worp = _fmt_worp_cell(row)
            flex = _fmt_flex_cell(row)
            porp = f'<span class="num">{_fmt_porp(row.get("porp"))}</span>'
            age = _fmt_age_cell(row)
            tv = f'<span class="num">{_fmt_tv(row.get("trade_value"))}</span>'
        else:
            player = '<span class="muted">On the clock</span>' if status == "on_clock" else '<span class="muted">—</span>'
            ovr = '<span class="num muted">—</span>'
            age = '<span class="num muted">—</span>'
            worp = '<span class="num muted">—</span>'
            flex = '<span class="num muted">—</span>'
            porp = '<span class="num muted">—</span>'
            tv = '<span class="num muted">—</span>'

        body.append(
            [
                pick_label,
                str(row.get("round") or ""),
                team,
                player,
                age,
                ovr,
                worp,
                flex,
                porp,
                tv,
            ]
        )
    st.markdown(
        _html_table(["Pick", "Rd", "Team", "Player", "Age", "OVR", "WORP", "Flex", "PORP", "TV"], body, row_classes),
        unsafe_allow_html=True,
    )


def _render_draft_tab(state: DraftState, config: dict[str, Any]) -> None:
    poll = max(5, int(config.get("poll_seconds", 20)))
    refresh = timedelta(seconds=poll) if st.session_state.auto_refresh else None

    @st.fragment(run_every=refresh)
    def live_board() -> None:
        live_state = _load_state(config) or state
        _render_hero(live_state)
        _render_stats(live_state)
        for note in live_state.strategy.strategy_notes(
            live_state.war, tv_fn=live_state.blended_trade_value
        ):
            st.markdown(f'<div class="note-box">{note}</div>', unsafe_allow_html=True)
        _render_draft_timeline(live_state)
        _render_best_available(live_state)
        _render_fall_preview(live_state)
        st.markdown('<div class="section-title">Quick picks</div>', unsafe_allow_html=True)
        _render_quick_picks(live_state)

    live_board()


def _lineup_player_cells(player: dict[str, Any] | None) -> tuple[list[str], str]:
    if not player:
        return (
            [
                '<span class="muted">Empty</span>',
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
            ],
            "row-empty",
        )
    status = player.get("status")
    note = ' <span class="note">(reserved)</span>' if status == "reserved" else ""
    row_class = "row-reserved" if status == "reserved" else ""
    dynasty_cell = (
        _fmt_dynasty_cell(player)
        if player.get("dynasty_rating") is not None
        else '<span class="muted">—</span>'
    )
    return (
        [
            f'<span class="player">{html.escape(player["name"])}</span>{note}',
            f'<span class="pos">{html.escape(player.get("pos") or "")}</span>',
            html.escape(player.get("team") or ""),
            _fmt_age_cell(player),
            dynasty_cell,
            f'<span class="num tv">{_fmt_tv(player.get("trade_value"))}</span>',
            _fmt_worp_cell(player),
            _fmt_flex_cell(player),
            _fmt_porp_cell(player),
        ],
        row_class,
    )


def _render_lineup_stats(lineup: dict[str, Any], *, team_count: int = 10) -> None:
    dynasty_rank = lineup.get("dynasty_rank")
    rank_text = f"#{dynasty_rank} / {team_count}" if dynasty_rank else "—"
    avg_ovr = lineup.get("avg_dynasty_rating")
    ovr_cls = _dynasty_class(avg_ovr) if avg_ovr else ""
    ovr_text = str(avg_ovr) if avg_ovr else "—"
    ovr_html = (
        f'<div class="stat-value dynasty {ovr_cls}">{ovr_text}</div>'
        if avg_ovr
        else '<div class="stat-value">—</div>'
    )
    st.markdown(
        f"""
        <div class="stat-row">
          <div class="stat-card"><div class="stat-label">Dynasty rank</div>
            <div class="stat-value">{rank_text}</div></div>
          <div class="stat-card"><div class="stat-label">Team OVR</div>
            {ovr_html}</div>
          <div class="stat-card"><div class="stat-label">Picks</div>
            <div class="stat-value">{lineup["pick_count"]}</div></div>
          <div class="stat-card"><div class="stat-label">Trade value</div>
            <div class="stat-value">{lineup["total_trade_value"]:,.0f}</div></div>
          <div class="stat-card"><div class="stat-label">Starter WORP</div>
            <div class="stat-value">{_fmt_worp(lineup.get("starter_worp"))}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_lineup_table(lineup: dict[str, Any]) -> None:
    body: list[list[str]] = []
    row_classes: list[str] = []
    for row in lineup["starters"]:
        cells, row_class = _lineup_player_cells(row.get("player"))
        body.append([f'<span class="slot-label">{html.escape(row["slot"])}</span>', *cells])
        row_classes.append(row_class)

    body.append(['<span class="slot-label">BENCH</span>', "", "", "", "", "", "", "", "", ""])
    row_classes.append("lineup-divider")

    if lineup["bench"]:
        for player in lineup["bench"]:
            cells, row_class = _lineup_player_cells(player)
            body.append(["", *cells])
            row_classes.append(row_class)
    else:
        body.append(["", '<span class="muted">No bench players yet</span>', "", "", "", "", "", "", "", ""])
        row_classes.append("row-empty")

    st.markdown(
        _html_table(
            ["", "Player", "Pos", "Tm", "Age", "OVR", "TV", "WORP", "Flex", "PORP"],
            body,
            row_classes,
            table_class="pick-table lineup-table",
        ),
        unsafe_allow_html=True,
    )


def _render_my_team_tab(state: DraftState) -> None:
    lineup = build_my_team_lineup(state)
    if lineup["pick_count"] == 0 and lineup["reserved_count"] == 0:
        st.info("No picks yet.")
        return

    _render_lineup_stats(lineup, team_count=state._teams())
    if lineup["reserved_count"]:
        st.caption(f"{lineup['reserved_count']} reserved for rookie draft")
    _render_lineup_table(lineup)

    needs = state.starter_needs()
    need_bits = [f"{pos}: {count}" for pos, count in needs.items() if count > 0]
    if need_bits:
        st.caption("Starter needs: " + ", ".join(need_bits))

    st.markdown('<div class="section-title">Pick targets</div>', unsafe_allow_html=True)
    _render_bpa_comparison(state, compact=True)


def _team_expander_label(team: dict[str, Any]) -> str:
    slot = f"1.{team['draft_slot']:02d}" if team.get("draft_slot") else "?"
    prefix = "★ " if team["is_me"] else ""
    ovr = team.get("avg_dynasty_rating")
    ovr_bit = f" · OVR {ovr}" if ovr else ""
    return f"{prefix}{team['team_name']} · {slot}{ovr_bit}"


def _render_team_chips(team: dict[str, Any]) -> None:
    chips = [
        f"Dyn #{team['dynasty_rank']}" if team.get("dynasty_rank") else None,
        f"OVR {team['avg_dynasty_rating']}" if team.get("avg_dynasty_rating") else None,
        f"{team.get('pick_count', 0)} picks",
        f"TV {team.get('total_trade_value', 0):,.0f}",
        f"WORP {_fmt_worp(team.get('starter_worp'))}",
    ]
    visible = [chip for chip in chips if chip]
    chip_html = "".join(
        f'<span class="team-chip{" team-chip-muted" if i > 1 else ""}">{html.escape(text)}</span>'
        for i, text in enumerate(visible)
    )
    st.markdown(f'<div class="team-chip-row">{chip_html}</div>', unsafe_allow_html=True)


def _render_league_tab(state: DraftState) -> None:
    teams = build_league_rankings(state)
    st.caption("Tap a team for full lineup · optimal starters by trade value")
    for team in teams["by_trade_value"]:
        with st.expander(_team_expander_label(team), expanded=team["is_me"]):
            _render_team_chips(team)
            if team.get("reserved_count"):
                st.caption(f"{team['reserved_count']} reserved for rookie draft")
            _render_lineup_table(team)


def _render_board_tab(state: DraftState, config: dict[str, Any]) -> None:
    poll = max(5, int(config.get("poll_seconds", 20)))
    refresh = timedelta(seconds=poll) if st.session_state.auto_refresh else None

    @st.fragment(run_every=refresh)
    def live_board() -> None:
        live_state = _load_state(config) or state
        rows = live_state.available_board_rows()
        if not rows:
            st.info("No undrafted players in the pool.")
            return

        flex_rows = [
            row for row in rows if row.get("pos") in ("RB", "WR", "TE") and row.get("flex_rating")
        ]
        flex_rows.sort(key=lambda row: row.get("flex_rating") or 0, reverse=True)
        flex_slots = sum(1 for slot in live_state.roster_positions if slot == "FLEX")

        st.markdown('<div class="section-title">Flex pool</div>', unsafe_allow_html=True)
        st.caption(
            f"RB/WR/TE ranked together for flex decisions ({flex_slots} flex slot"
            f"{'s' if flex_slots != 1 else ''} in league). "
            "Flex rating = WORP* + PORP on a shared 50–99 scale among undrafted skill players."
        )
        if flex_rows:
            flex_df = pd.DataFrame(flex_rows[:40])
            flex_df["Player"] = flex_df.apply(
                lambda row: f"{row['name']}*" if row.get("dynasty_rookie") else row["name"],
                axis=1,
            )
            flex_df["WORP"] = flex_df["effective_worp"].where(
                flex_df["effective_worp"].notna(),
                flex_df["worp"],
            )
            flex_table = flex_df.rename(
                columns={
                    "flex_rank": "Flex #",
                    "flex_rating": "Flex",
                    "pos": "Pos",
                    "team": "Tm",
                    "age": "Age",
                    "dynasty_rating": "OVR",
                    "trade_value": "TV",
                    "porp": "PORP",
                }
            )[
                ["Flex #", "Player", "Pos", "Tm", "Flex", "OVR", "WORP", "PORP", "TV"]
            ]
            st.dataframe(
                flex_table,
                use_container_width=True,
                hide_index=True,
                height=min(420, 38 + len(flex_table) * 35),
                column_config={
                    "Flex #": st.column_config.NumberColumn("Flex #", format="%d"),
                    "Flex": st.column_config.NumberColumn(
                        "Flex",
                        help="Cross-position flex rating (RB/WR/TE pool)",
                        format="%d",
                    ),
                    "OVR": st.column_config.NumberColumn("OVR", format="%d"),
                    "WORP": st.column_config.NumberColumn("WORP", format="%.2f"),
                    "PORP": st.column_config.NumberColumn("PORP", format="%d"),
                    "TV": st.column_config.NumberColumn("TV", format="%d"),
                },
            )
        else:
            st.info("No flex-eligible players left on the board.")

        st.markdown('<div class="section-title">All available</div>', unsafe_allow_html=True)
        ref = live_state._adp_reference_pick()
        st.caption(
            f"{len(rows)} undrafted · pick #{ref} · ADP: "
            f"{html.escape(live_state._adp_index().source_label)}"
        )

        filter_row = st.columns([2, 2, 2])
        with filter_row[0]:
            pos_filter = st.multiselect(
                "Position",
                options=["QB", "RB", "WR", "TE"],
                default=[],
                placeholder="All positions",
            )
        with filter_row[1]:
            search = st.text_input("Search", placeholder="Player name…")
        with filter_row[2]:
            sort_by = st.selectbox(
                "Sort by",
                options=["Flex", "OVR", "TV", "WORP", "PORP", "ADP", "Name"],
                index=0,
            )

        with st.expander("Metric filters", expanded=False):
            min_ovr, max_ovr = st.slider("OVR range", 50, 99, (50, 99))
            min_flex = st.slider("Min flex rating", 50, 99, 50)
            min_tv = st.number_input("Min TV", min_value=0, value=0, step=500)
            min_worp = st.number_input("Min WORP", min_value=0.0, value=0.0, step=0.1, format="%.1f")
            min_porp = st.number_input("Min PORP", min_value=0, value=0, step=5)
            skill_only = st.checkbox("Skill positions only (RB/WR/TE)")
            rookies_only = st.checkbox("Rookie projections only (N*)")

        df = pd.DataFrame(rows)
        df["Player"] = df.apply(
            lambda row: f"{row['name']}*" if row.get("dynasty_rookie") else row["name"],
            axis=1,
        )
        df["WORP"] = df["effective_worp"].where(
            df["effective_worp"].notna(),
            df["worp"],
        )
        display = df.rename(
            columns={
                "pos": "Pos",
                "team": "Tm",
                "age": "Age",
                "adp_pick": "ADP",
                "adp_delta": "Δ",
                "dynasty_rating": "OVR",
                "trade_value": "TV",
                "porp": "PORP",
                "flex_rating": "Flex",
                "flex_rank": "Flex #",
            }
        )

        if pos_filter:
            display = display[display["Pos"].isin(pos_filter)]
        if skill_only:
            display = display[display["Pos"].isin(["RB", "WR", "TE"])]
        if search.strip():
            needle = search.strip().lower()
            display = display[display["name"].str.lower().str.contains(needle, na=False)]
        if min_ovr > 50 or max_ovr < 99:
            display = display[display["OVR"].between(min_ovr, max_ovr, inclusive="both")]
        if min_flex > 50:
            display = display[display["Flex"].fillna(0) >= min_flex]
        if min_tv > 0:
            display = display[display["TV"] >= min_tv]
        if min_worp > 0:
            display = display[display["WORP"].fillna(0) >= min_worp]
        if min_porp > 0:
            display = display[display["PORP"].fillna(0) >= min_porp]
        if rookies_only:
            display = display[display["dynasty_rookie"]]

        sort_cols = {
            "Flex": ("Flex", False),
            "OVR": ("OVR", False),
            "TV": ("TV", False),
            "WORP": ("WORP", False),
            "PORP": ("PORP", False),
            "ADP": ("ADP", True),
            "Name": ("Player", True),
        }
        col_name, ascending = sort_cols[sort_by]
        display = display.sort_values(
            by=col_name,
            ascending=ascending,
            na_position="last",
        )

        table = display[
            ["Player", "Pos", "Tm", "Age", "Flex #", "Flex", "ADP", "Δ", "OVR", "TV", "WORP", "PORP"]
        ].reset_index(drop=True)

        st.dataframe(
            table,
            use_container_width=True,
            hide_index=True,
            height=min(640, 38 + len(table) * 35),
            column_config={
                "Player": st.column_config.TextColumn("Player", width="medium"),
                "Pos": st.column_config.TextColumn("Pos", width="small"),
                "Tm": st.column_config.TextColumn("Tm", width="small"),
                "Age": st.column_config.NumberColumn("Age", format="%d"),
                "Flex #": st.column_config.NumberColumn("Flex #", format="%d"),
                "Flex": st.column_config.NumberColumn(
                    "Flex",
                    help="Cross-position rating vs undrafted RB/WR/TE",
                    format="%d",
                ),
                "ADP": st.column_config.NumberColumn("ADP", format="%d"),
                "Δ": st.column_config.NumberColumn("Δ", help="ADP minus your next pick. Positive = value."),
                "OVR": st.column_config.NumberColumn("OVR", format="%d"),
                "TV": st.column_config.NumberColumn("TV", format="%d"),
                "WORP": st.column_config.NumberColumn("WORP", format="%.2f"),
                "PORP": st.column_config.NumberColumn("PORP", format="%d"),
            },
        )
        st.caption(f"Showing {len(table)} of {len(rows)} · click column headers to re-sort")

    live_board()


def _render_rankings_tab(state: DraftState) -> None:
    rankings = build_league_rankings(state)

    st.markdown('<div class="section-title">Dynasty OVR</div>', unsafe_allow_html=True)
    st.caption(
        "50–99 player ratings (TV + proj WORP + ceiling + age + trajectory). "
        "Teams ranked by roster average OVR."
    )
    dyn_body: list[list[str]] = []
    dyn_classes: list[str] = []
    for team in rankings["by_dynasty"]:
        row_class = "row-you rank-you" if team["is_me"] else ""
        dyn_body.append(
            [
                f'<span class="rank-badge">{team["dynasty_rank"]}</span>',
                f"<strong>{html.escape(team['team_name'])}</strong>" if team["is_me"] else html.escape(team["team_name"]),
                str(team.get("pick_count") or 0),
                _fmt_dynasty_rating(team.get("avg_dynasty_rating")),
                _fmt_dynasty_rating(team.get("starter_avg_dynasty_rating")),
                f'<span class="num tv">{_fmt_tv(team.get("total_trade_value"))}</span>',
            ]
        )
        dyn_classes.append(row_class)
    st.markdown(
        _html_table(["#", "Team", "Picks", "OVR", "Starters", "TV"], dyn_body, dyn_classes),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Win now</div>', unsafe_allow_html=True)
    st.caption("Ranked by optimal starter WORP + PORP/100 (position projection)")
    win_body: list[list[str]] = []
    win_classes: list[str] = []
    for team in rankings["by_win_now"]:
        row_class = "row-you rank-you" if team["is_me"] else ""
        win_body.append(
            [
                f'<span class="rank-badge">{team["win_rank"]}</span>',
                f"<strong>{html.escape(team['team_name'])}</strong>" if team["is_me"] else html.escape(team["team_name"]),
                str(team.get("pick_count") or 0),
                f'<span class="num worp">{_fmt_worp(team.get("starter_worp"))}</span>',
                f'<span class="num">{_fmt_porp(team.get("starter_porp"))}</span>',
                f'<span class="num">{_fmt_worp(team.get("win_now_score"))}</span>',
            ]
        )
        win_classes.append(row_class)
    st.markdown(
        _html_table(["#", "Team", "Picks", "WORP", "PORP", "Score"], win_body, win_classes),
        unsafe_allow_html=True,
    )

    st.markdown('<div class="section-title">Trade value</div>', unsafe_allow_html=True)
    st.caption("Ranked by total roster trade value (market dynasty capital)")
    tv_body: list[list[str]] = []
    tv_classes: list[str] = []
    for team in rankings["by_trade_value"]:
        row_class = "row-you rank-you" if team["is_me"] else ""
        tv_body.append(
            [
                f'<span class="rank-badge">{team["tv_rank"]}</span>',
                f"<strong>{html.escape(team['team_name'])}</strong>" if team["is_me"] else html.escape(team["team_name"]),
                str(team.get("pick_count") or 0),
                f'<span class="num tv">{_fmt_tv(team.get("total_trade_value"))}</span>',
                _fmt_dynasty_rating(team.get("avg_dynasty_rating")),
                f'<span class="num worp">{_fmt_worp(team.get("starter_worp"))}</span>',
            ]
        )
        tv_classes.append(row_class)
    st.markdown(
        _html_table(["#", "Team", "Picks", "Total TV", "OVR", "WORP"], tv_body, tv_classes),
        unsafe_allow_html=True,
    )


def _render_settings_tab(config: dict[str, Any]) -> None:
    strategy = config.setdefault("strategy", {})
    config["sleeper_username"] = st.text_input("Sleeper username", value=config.get("sleeper_username", ""))
    config["season"] = st.text_input("Season", value=str(config.get("season", "2026")))
    config["league_id"] = st.text_input("League ID", value=config.get("league_id", ""))
    config["draft_id"] = st.text_input("Draft ID", value=config.get("draft_id", ""))
    config["trade_weight"] = st.slider("Trade value", 0.0, 1.0, float(config.get("trade_weight", 0.65)), 0.05)
    config["worp_weight"] = st.slider("WORP", 0.0, 1.0, float(config.get("worp_weight", 0.35)), 0.05)
    rating_curve = config.setdefault("dynasty_rating_curve", {})
    rating_curve["exponent"] = st.slider(
        "Dynasty rating curve",
        0.20,
        1.00,
        float(rating_curve.get("exponent", 0.54)),
        0.02,
        help="Lower compresses the top end (fewer 90s); higher spreads elites upward.",
    )
    adp_cfg = config.setdefault("adp", {})
    adp_options = {
        "auto": "Auto (Sleeper dynasty 2QB for superflex, Sleeper redraft for 1QB)",
        "sleeper_dynasty_2qb": "Sleeper dynasty 2QB ADP",
        "sleeper_dynasty_1qb": "Sleeper dynasty 1QB ADP",
        "sleeper_redraft_half_ppr": "Sleeper redraft half-PPR ADP",
        "beatadp_sleeper": "BeatADP Sleeper redraft ADP",
        "dlf_superflex": "DLF superflex mock ADP",
        "trade_value": "Trade value rank (legacy)",
    }
    current = str(adp_cfg.get("source", "auto"))
    if current.startswith("dynastyprocess_"):
        current = "auto"
    adp_cfg["source"] = st.selectbox(
        "ADP source",
        options=list(adp_options.keys()),
        index=list(adp_options.keys()).index(current) if current in adp_options else 0,
        format_func=lambda key: adp_options[key],
        help="Used for reach/value badges and league pick simulation. Auto picks the best available fetch.",
    )
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
    if not st.session_state.moonshot_api_key:
        st.session_state.moonshot_api_key = st.text_input("Moonshot API key (Kimi)", type="password")
    if st.button("Save settings", use_container_width=True):
        save_config(config)
        st.success("Saved")


def main() -> None:
    _init_session()
    st.markdown(MOBILE_CSS, unsafe_allow_html=True)

    config = st.session_state.config
    state = _load_state(config)
    draft_name = (
        (state.draft.get("metadata") or {}).get("name") if state else None
    ) or "Dynasty draft companion"
    subtitle = html.escape(draft_name)

    header = st.columns([5, 1])
    with header[0]:
        st.markdown(
            f'<div class="app-header"><div><div class="app-title">Pickbook</div>'
            f'<div class="app-subtitle">{subtitle}</div></div></div>',
            unsafe_allow_html=True,
        )
    with header[1]:
        if st.button("Sync", type="primary", use_container_width=True):
            st.rerun()

    if state is None:
        st.info("Add your Sleeper username in Settings.")
        tab_ask, tab_draft, tab_board, tab_team, tab_league, tab_rankings, tab_settings = st.tabs(
            ["Ask", "Draft", "Board", "Team", "League", "Rankings", "Settings"]
        )
        with tab_settings:
            _render_settings_tab(config)
        return

    tab_ask, tab_draft, tab_board, tab_team, tab_league, tab_rankings, tab_settings = st.tabs(
        ["Ask", "Draft", "Board", "Team", "League", "Rankings", "Settings"]
    )

    with tab_ask:
        _render_llm_tab(state, config)

    with tab_draft:
        _render_draft_tab(state, config)

    with tab_board:
        _render_board_tab(state, config)

    with tab_team:
        _render_my_team_tab(state)

    with tab_league:
        _render_league_tab(state)

    with tab_rankings:
        _render_rankings_tab(state)

    with tab_settings:
        _render_settings_tab(config)


if __name__ == "__main__":
    main()
