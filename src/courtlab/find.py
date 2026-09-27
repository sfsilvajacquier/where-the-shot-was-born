"""Which possessions tell a whole story? Two families, ranked by how open the shot was and how well the play was seen.

* `pick`: a ball screen defended over the top, the ball moving on at least twice, and a three taken by somebody who was not the handler.
* `kickout`: a drive, then a pass out of it, and a three taken within three seconds by somebody other than the driver.
"""

from __future__ import annotations

import numpy as np

from courtlab.data import Game, game_ids
from courtlab.possession import FPS, Possession

POOL = 24  # how many of the best candidates get their tracking read
STORIES = ("pick", "kickout")
FEATURED = (191313, "chance-191313-1-7")  # the play the README, the stills and the start screen are built on: always exported


def candidates(story: str = "all", coverage: str = "over", min_passes: int = 2) -> list[dict]:
    out = []
    for gid in game_ids():
        g = Game.load(gid)
        by = lambda table: {k: [e for e in g.events[table] if e["chanceId"] == k] for k in g.chances}  # noqa: E731
        picks, passes, shots, drives = by("picks"), by("passes"), by("shots"), by("drives")
        for cid, c in g.chances.items():
            three = next((s for s in shots[cid] if s["three"] and s["shotQuality"] is not None), None)
            if not c["usable"] or c["transition"] or not three or c["frontcourtFrame"] is None:
                continue
            base = {"game": gid, "chance": cid, "made": bool(three["outcome"]), "quality": three["shotQuality"], "contest": three["contestLevel"],
                    "defender_ft": three["closestDefDist"], "shooter": g.players[three["shooterId"]]["lastName"], "attack": g.team_name(c["offTeamId"]), "period": c["period"]}
            if story in ("pick", "all"):
                first = next((p for p in sorted(picks[cid], key=lambda p: p["frame"]) if p["bhrDefType"] == coverage and three["startFrame"] - p["frame"] >= 2 * FPS), None)
                if first and three["shooterId"] != first["ballhandlerId"]:
                    moved = [p for p in passes[cid] if p["complete"] and first["frame"] < p["startFrame"] <= three["startFrame"]]
                    if len(moved) >= min_passes:
                        out.append({**base, "story": "pick", "passes": len(moved), "seconds": (three["startFrame"] - first["frame"]) / FPS, "start_i": first["frame"]})
            if story in ("kickout", "all"):
                drive = next((d for d in sorted(drives[cid], key=lambda d: d["startFrame"]) if d["endType"] == "kickout" and d["ballhandlerId"] != three["shooterId"]
                              and 0 < three["startFrame"] - d["endFrame"] <= 3 * FPS), None)
                if drive:
                    moved = [p for p in passes[cid] if p["complete"] and drive["startFrame"] <= p["startFrame"] <= three["startFrame"]]
                    out.append({**base, "story": "kickout", "passes": len(moved), "seconds": (three["startFrame"] - drive["startFrame"]) / FPS, "start_i": drive["startFrame"]})
    return out


def rank(rows: list[dict], top: int = 12) -> list[dict]:
    """Made, open and well seen come first. The share of positions seen on camera needs the tracking, so only the best few are measured."""
    rows = sorted(rows, key=lambda r: (-r["made"], -r["quality"]))[:POOL]  # a fixed pool, so `find` and `export --best` agree
    games: dict[int, Game] = {}
    for r in rows:
        p = Possession.build(games.setdefault(r["game"], Game.load(r["game"])), r["chance"])
        r["seen"] = float(np.mean([v.mean() for v in p.seen.values()]))
        r["frames"] = len(p.idx)
        acts = p.actions()
        at = {int(i): k for k, i in enumerate(p.idx)}
        a = at.get(int(min(max(r["start_i"], p.idx[0]), p.idx[-1])), 0)
        b = next(x["i"] for x in acts if x["type"] == "shot" and x["three"])
        peak = [np.nanmax(v[a:b + 1]) if np.isfinite(v[a:b + 1]).any() else np.nan for v in p.extra.values()]
        r["peak_extra_ft"] = float(np.nanmax(peak))  # the most anybody was left open between the action and the shot
    return sorted(rows, key=lambda r: (-r["made"], -(r["quality"] / 100 + r["seen"])))[:top]
