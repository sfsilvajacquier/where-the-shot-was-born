"""The rotation ledger: what a late or missing rotation cost, in points, with a counterfactual a coach can argue with.

Three ingredients, all measured on the open data:

* how SkillCorner's `shotQuality` moves with the closest defender's distance, per zone, holding the rest of the shot fixed
  (catch-and-shoot, distance, release time, dribbles): a least-squares fit in logit space, refitted on the games at hand;
* how fast a defender closes out (league median top speed, `CLOSEOUT_FT_S`), and when he started relative to the pass;
* where the shooter's defender would have stood had he been at his normal spot (`equilibrium.spot`).

The counterfactual moves ONE thing, the defender's distance at the release, and keeps the shot's own quality as the anchor:
only the distance effect of the fit is applied to it. The price is the change in expected points. It is a model on top of
SkillCorner's model, and it is reported as such.
"""

from __future__ import annotations

import math

import numpy as np

CLOSEOUT_FT_S = 10.4   # median top speed of a labelled close-out over the ten games (analysis 10)
MIN_DIST = 2.0         # a defender cannot end closer than this without a foul
MAX_DIST = 20.0        # beyond this SkillCorner's quality no longer moves with distance


def zone(shot: dict) -> str:
    return "rim" if shot["region"] in ("ra", "key") else "three" if shot["three"] else "mid"


def _features(shot: dict, def_dist: float) -> list[float]:
    return [1.0, min(def_dist, MAX_DIST), float(bool(shot["catchAndShoot"])), shot["distance"] or 0.0, min(shot["releaseTime"] or 0.0, 3.0), min(shot["dribblesBefore"] or 0, 6)]


def _logit(p: float) -> float:
    p = min(max(p, 0.01), 0.99)
    return math.log(p / (1 - p))


def _sigmoid(x: float) -> float:
    return 1 / (1 + math.exp(-x))


class QualityFit:
    """logit(quality) ~ defender distance + the shot's own covariates, one fit per zone."""

    def __init__(self, shots: list[dict]):
        self.beta: dict[str, np.ndarray] = {}
        self.n: dict[str, int] = {}
        for z in ("rim", "mid", "three"):
            rows = [s for s in shots if zone(s) == z and s["shotQuality"] is not None and s["closestDefDist"] is not None and s["distance"] is not None and not s["fouled"] and not s["blocked"]]
            X = np.array([_features(s, s["closestDefDist"]) for s in rows])
            y = np.array([_logit(s["shotQuality"] / 100) for s in rows])
            self.beta[z], *_ = np.linalg.lstsq(X, y, rcond=None)
            self.n[z] = len(rows)

    @classmethod
    def from_rows(cls, rows: list[dict]) -> "QualityFit":
        """A fit rebuilt from the betas frozen in league.json, so no game has to be read."""
        self = cls.__new__(cls)
        self.beta = {r["zone"]: np.array(r["beta"], float) for r in rows}
        self.n = {r["zone"]: int(r["n"]) for r in rows}
        return self

    def rows(self) -> list[dict]:
        return [{"zone": z, "beta": [round(float(b), 5) for b in self.beta[z]], "n": self.n[z]} for z in ("rim", "mid", "three")]

    def slope(self, shot: dict) -> float:
        """Logit of quality gained per foot of defender distance, in this shot's zone."""
        return float(self.beta[zone(shot)][1])

    def quality_if(self, shot: dict, def_dist: float) -> float:
        """The shot's quality (0-1) had the closest defender been `def_dist` feet away, everything else as it was."""
        d0, d1 = min(shot["closestDefDist"], MAX_DIST), min(max(def_dist, MIN_DIST), MAX_DIST)
        return _sigmoid(_logit(shot["shotQuality"] / 100) + self.slope(shot) * (d1 - d0))

    def price(self, shot: dict, def_dist: float) -> float:
        """Expected points the shot would have LOST had the defender been at `def_dist` (positive = the rotation cost this much)."""
        pts = 3 if shot["three"] else 2
        return pts * (shot["shotQuality"] / 100 - self.quality_if(shot, def_dist))


def on_time_distance(shot: dict, onset_s: float) -> float:
    """Where the closing defender would have been at the release had he started with the pass instead of `onset_s` later."""
    return max(MIN_DIST, shot["closestDefDist"] - max(0.0, onset_s) * CLOSEOUT_FT_S)


def normal_spot_distance(man_xy, ball_xy, w: dict, hoop) -> float:
    """How far a defender standing at his normal spot would be from his man."""
    a, b, c = w["man"], w["ball"], w["hoop"]
    sx, sy = a * man_xy[0] + b * ball_xy[0] + c * hoop[0], a * man_xy[1] + b * ball_xy[1] + c * hoop[1]
    return max(MIN_DIST, math.hypot(man_xy[0] - sx, man_xy[1] - sy))


def who_should_rotate(shooter_xy, defenders: dict, exclude: set, ball_holder_def) -> tuple | None:
    """The free defender nearest to the abandoned shooter: not on the ball, not the one who left. Returns (id, feet, seconds at close-out speed)."""
    best = None
    for did, xy in defenders.items():
        if did in exclude or did == ball_holder_def:
            continue
        d = math.hypot(xy[0] - shooter_xy[0], xy[1] - shooter_xy[1])
        if best is None or d < best[1]:
            best = (did, d, d / CLOSEOUT_FT_S)
    return best
