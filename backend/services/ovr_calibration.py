"""OVR calibration checks — surface TV vs production rank divergences at sync."""

from __future__ import annotations

from typing import Any


DEFAULT_DIVERGENCE_THRESHOLD = 25


def _rank_by(rows: list[dict[str, Any]], key: str, *, reverse: bool = True) -> dict[str, int]:
    sortable = [row for row in rows if row.get(key) is not None]
    sortable.sort(key=lambda row: row[key], reverse=reverse)
    return {row["player_id"]: index + 1 for index, row in enumerate(sortable)}


def build_calibration_report(
    rows: list[dict[str, Any]],
    *,
    divergence_threshold: int = DEFAULT_DIVERGENCE_THRESHOLD,
    top_n: int = 15,
) -> dict[str, Any]:
    """
    Flag players where market rank and OVR rank diverge materially.
    Catches hype-without-production and production-without-market patterns.
    """
    if not rows:
        return {
            "divergence_threshold": divergence_threshold,
            "player_count": 0,
            "divergences": [],
            "summary": {},
        }

    tv_rank = _rank_by(rows, "trade_value")
    ovr_rank = _rank_by(rows, "dynasty_rating")
    hppg_rank = _rank_by(rows, "hppg")

    divergences: list[dict[str, Any]] = []
    for row in rows:
        player_id = row["player_id"]
        tv_r = tv_rank.get(player_id)
        ovr_r = ovr_rank.get(player_id)
        if tv_r is None or ovr_r is None:
            continue
        gap = tv_r - ovr_r
        if abs(gap) < divergence_threshold:
            continue
        components = row.get("components_json") or {}
        detail = components.get("production_detail") or {}
        divergences.append(
            {
                "player_id": player_id,
                "player_name": row.get("player_name"),
                "position": row.get("position"),
                "trade_value": row.get("trade_value"),
                "dynasty_rating": row.get("dynasty_rating"),
                "tv_rank": tv_r,
                "ovr_rank": ovr_r,
                "hppg_rank": hppg_rank.get(player_id),
                "rank_gap": gap,
                "pattern": "market_ahead" if gap < 0 else "production_ahead",
                "hppg": row.get("hppg"),
                "production": components.get("production"),
                "per_game": components.get("per_game"),
                "season_worp_norm": detail.get("season_worp"),
            }
        )

    divergences.sort(key=lambda item: abs(item["rank_gap"]), reverse=True)

    api_sources = 0
    csv_sources = 0
    for row in rows:
        source = ((row.get("value_inputs_json") or {}).get("dynasty_daddy") or {}).get("source")
        if source == "api":
            api_sources += 1
        elif source == "war_csv":
            csv_sources += 1

    return {
        "divergence_threshold": divergence_threshold,
        "player_count": len(rows),
        "divergence_count": len(divergences),
        "value_sources": {
            "api": api_sources,
            "war_csv": csv_sources,
        },
        "divergences": divergences[:top_n],
        "summary": {
            "market_ahead": sum(1 for d in divergences if d["pattern"] == "market_ahead"),
            "production_ahead": sum(1 for d in divergences if d["pattern"] == "production_ahead"),
        },
    }
