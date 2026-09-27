"""The second and a half while a shot is in the air: who crashes the offensive glass, who boxes out, who watches.

SkillCorner's `chance_players` table gives every player's spot at the shot (`shotLoc`) and when the ball reaches the rim
(`rimLoc`). A team-mate of the shooter CRASHES when he gains at least 2 ft towards the hoop and ends within 14 ft of it.
Those two numbers were not chosen by eye: among eight candidate definitions they are the ones that best predict who takes the
rebound (`rebounderId`), which is the check `tests/test_courtlab.py` keeps. Prior art: UF Sports Analytics Lab with SkillCorner
(2026), who classified crashing per player against film; the definition here is public and validated on the data itself.
"""

from __future__ import annotations

import math

from courtlab import court

CRASH = (2.0, 14.0)   # feet gained towards the hoop, and feet from the hoop at the rim
STILL = 2.0           # a player who moves less than this while the ball flies is standing still
UNDER_RIM = 10.0      # a still defender this close to the hoop is boxing out, not watching


def movement(row: dict) -> dict | None:
    """Distance to the hoop at the shot and at the rim, feet gained, and feet moved, for one `chance_players` row."""
    if not row.get("shotLoc") or not row.get("rimLoc"):
        return None
    (x0, y0), (x1, y1) = row["shotLoc"], row["rimLoc"]
    d0, d1 = math.hypot(x0 - court.HOOP_X, y0), math.hypot(x1 - court.HOOP_X, y1)
    return {"id": row["playerId"], "offense": bool(row["offense"]), "d0": d0, "d1": d1, "gain": d0 - d1, "moved": math.hypot(x1 - x0, y1 - y0)}


def crashes(m: dict, gain: float = CRASH[0], within: float = CRASH[1]) -> bool:
    return m["gain"] >= gain and m["d1"] <= within


def still_under_rim(m: dict) -> bool:
    return m["moved"] < STILL and m["d0"] <= UNDER_RIM


def still_far(m: dict) -> bool:
    return m["moved"] < STILL and m["d0"] > UNDER_RIM


def flight(rows: list[dict], shooter_id: int) -> dict | None:
    """What the other nine did while the ball flew, or None when a spot is missing."""
    ms = [movement(r) for r in rows if r["playerId"] != shooter_id]
    if len(ms) != 9 or any(m is None for m in ms):
        return None
    att, dfn = [m for m in ms if m["offense"]], [m for m in ms if not m["offense"]]
    return {"attack": att, "defence": dfn, "crash": sum(crashes(m) for m in att), "box_out": sum(still_under_rim(m) for m in dfn), "watch": sum(still_far(m) for m in dfn)}
