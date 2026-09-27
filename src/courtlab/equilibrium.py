"""Where a defender normally stands: a fixed mix of his man, the ball and the hoop (Franks, Miller, Bornn and Goldsberry, 2015).

Fitted on the ten ACB games with their filter (all ten players in the half court), using SkillCorner's own matchups:
0.623 [0.615-0.632] his man, 0.147 [0.141-0.153] the ball, 0.230 [0.225-0.235] the hoop. NBA 2013-14 in the paper: 0.62 / 0.11 / 0.27.
Letting the weights change with the situation (29 contexts) does not predict an unseen game better: 5.00 -> 4.90 ft.
What is left is not unmodelled context. It is the play, and that is what `extra` measures.
"""

from __future__ import annotations

import numpy as np

from courtlab.court import HOOP

WEIGHTS = {"man": 0.62, "ball": 0.15, "hoop": 0.23}


def spot(man: np.ndarray, ball: np.ndarray) -> np.ndarray:
    """The defender's normal spot, given where his man and the ball are. Arrays of shape (n, 2), in feet."""
    return WEIGHTS["man"] * man + WEIGHTS["ball"] * ball + WEIGHTS["hoop"] * np.asarray(HOOP)


def extra(man: np.ndarray, ball: np.ndarray, defender: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(gap, extra): feet between an attacker and his defender, and how much farther that is than the normal spot would be."""
    gap = np.hypot(*(defender - man).T)
    return gap, gap - np.hypot(*(spot(man, ball) - man).T)


def fit(man: np.ndarray, ball: np.ndarray, defender: np.ndarray) -> dict[str, float]:
    """Least squares with the weights summing to one: (D - H) = a (O - H) + b (B - H)."""
    h = np.asarray(HOOP)
    x = np.c_[np.r_[man[:, 0] - h[0], man[:, 1] - h[1]], np.r_[ball[:, 0] - h[0], ball[:, 1] - h[1]]]
    (a, b), *_ = np.linalg.lstsq(x, np.r_[defender[:, 0] - h[0], defender[:, 1] - h[1]], rcond=None)
    return {"man": float(a), "ball": float(b), "hoop": float(1 - a - b)}
