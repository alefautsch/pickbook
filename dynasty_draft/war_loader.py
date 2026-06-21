"""Load player value universe — API-first with optional CSV supplement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from dynasty_draft.dynasty_daddy import DynastyDaddyStore
from dynasty_draft.war_data import WarData


def _append_csv_only(war: WarData, csv_war: WarData) -> WarData:
    """Add CSV players missing from the API universe (deep stashes, name gaps)."""
    players = list(war.players)
    value_inputs = dict(war.value_inputs_by_name)
    for key, player in csv_war.by_name.items():
        if key in war.by_name:
            continue
        players.append(player)
        inputs = dict(csv_war.lookup_value_inputs(player.name))
        dd = dict(inputs.get("dynasty_daddy") or {})
        dd.setdefault("source", "war_csv")
        inputs["dynasty_daddy"] = dd
        value_inputs[key] = inputs
    players.sort(key=lambda row: row.trade_value, reverse=True)
    war.replace_players(players, value_inputs_by_name=value_inputs)
    return war


def load_war_data(
    settings: dict[str, Any],
    *,
    league_row: Any | None = None,
    superflex: bool | None = None,
    force_refresh: bool = False,
) -> tuple[WarData, dict[str, Any]]:
    """
    API-first player store. Dynasty Daddy supplies trade values + league WORP when
  available; war.csv supplements players the API misses. CSV is not required at runtime.
    """
    csv_path = Path(str(settings.get("war_csv", "war.csv")))
    dd_config = settings.get("dynasty_daddy") or {}
    force = force_refresh or bool(settings.get("_force_metric_refresh"))
    sf = superflex
    if sf is None and league_row is not None:
        sf = bool(getattr(league_row, "superflex", False))
    if sf is None:
        sf = True

    meta: dict[str, Any] = {
        "source": "none",
        "api_players": 0,
        "csv_supplement": 0,
        "csv_fallback": False,
    }

    war = WarData.empty()
    api_ok = False

    if bool(dd_config.get("enabled", True)):
        try:
            if league_row is not None:
                store = DynastyDaddyStore.load(
                    league_row=league_row,
                    superflex=sf,
                    config=dd_config,
                    force_refresh=force,
                )
            else:
                store = DynastyDaddyStore.load_values_only(
                    superflex=sf,
                    config=dd_config,
                    force_refresh=force,
                )
            war = store.to_war_data(war)
            api_ok = bool(war.players)
            meta["api_players"] = len(war.players)
        except Exception:
            api_ok = False

    if api_ok:
        meta["source"] = "api"
        if csv_path.exists():
            before = len(war.by_name)
            war = _append_csv_only(war, WarData(csv_path))
            meta["csv_supplement"] = len(war.by_name) - before
            if meta["csv_supplement"]:
                meta["source"] = "api+csv"
        return war, meta

    # Offline / API failure — full CSV path
    if not csv_path.exists():
        raise FileNotFoundError(
            "No player values available: Dynasty Daddy API failed and "
            f"war.csv not found at {csv_path}"
        )

    war = WarData(csv_path)
    meta["csv_fallback"] = True
    meta["source"] = "csv"
    if league_row is not None and bool(dd_config.get("enabled", True)):
        try:
            store = DynastyDaddyStore.load(
                league_row=league_row,
                superflex=sf,
                config=dd_config,
                force_refresh=force,
            )
            war = store.to_war_data(war)
            meta["source"] = "csv+api"
            meta["api_players"] = sum(
                1
                for inputs in war.value_inputs_by_name.values()
                if (inputs.get("dynasty_daddy") or {}).get("source") == "api"
            )
        except Exception:
            pass

    if not war.players:
        raise ValueError("Player value store is empty after load")

    return war, meta
