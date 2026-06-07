"""Formula fingerprint for snapshot history (§15.1)."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def compute_formula_version(settings: dict[str, Any]) -> str:
    """Hash dynasty weights + rating curve — changes when re-grade should rerun."""
    payload = {
        "dynasty_weights": settings.get("dynasty_weights"),
        "dynasty_rating_curve": settings.get("dynasty_rating_curve"),
    }
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
    return digest[:16]
