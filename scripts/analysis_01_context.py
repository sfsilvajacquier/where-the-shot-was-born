"""Analysis 1 — where does a defender stand, depending on the context?

    uv run scripts/analysis_01_context.py

Franks et al. (2015) fit one set of weights (his man / the ball / the hoop) for every defender. Here the weights are allowed to change
with the situation, and each richer model is scored on a game it has not seen (leave one game out). Read-only.
"""

from __future__ import annotations

import collections
import gzip
import json
import re
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "opendata-basketball" / "data"
FRAME = re.compile(r'"frameIdx":\s*(\d+)')
STEP, HOOP = 5, np.array([-40.75, 0.0])


def load() -> dict[str, np.ndarray]:
    out = collections.defaultdict(list)
    for g in json.load(open(DATA / "matches.json")):
        gid = g["id"]
        folder = DATA / "matches" / str(gid)
        ev = json.load(open(folder / f"{gid}_dynamic_events.json"))
        chances = {c["id"]: c for c in ev["chances"]}
        pairs = collections.defaultdict(list)
        for m in ev["matchups"]:
            c = chances.get(m["chanceId"])
            if not c or not c["usable"] or c["frontcourtFrame"] is None:
                continue
            a = max(m["startFrame"], c["frontcourtFrame"])
            for f in range(a - a % STEP + STEP, m["endFrame"] + 1, STEP):
                pairs[f].append((m["defPlayerId"], m["offPlayerId"], c["period"], c["offTeamId"]))
        holder = {}
        for t in ev["touches"]:
            for f in range(t["startFrame"] - t["startFrame"] % STEP, t["endFrame"] + 1, STEP):
                holder[f] = t["playerId"]
        pick = {}  # frame -> (handler, screener, coverage) within a second either side of the screen
        for p in ev["picks"]:
            for f in range(p["frame"] - 25 - (p["frame"] - 25) % STEP, p["frame"] + 26, STEP):
                pick[f] = (p["ballhandlerId"], p["screenerId"], p["bhrDefType"])
        shots = {s["startFrame"]: s for s in ev["shots"]}
        need = set(pairs) | set(shots)
        frames = {}
        with gzip.open(folder / f"{gid}_tracking_data.jsonl.gz", "rt") as fh:
            for line in fh:
                if '"homePlayers": []' in line:
                    continue
                i = int(FRAME.search(line).group(1))
                if i in need:
                    f = json.loads(line)
                    if f["ball"]:
                        frames[i] = ({p["playerId"]: (p["xyz"][0], p["xyz"][1], p["isDetected"]) for p in f["homePlayers"] + f["awayPlayers"]}, f["ball"]["xyz"][:2])
        votes = collections.defaultdict(list)
        for fr, s in shots.items():
            if fr in frames and s.get("location") and s["shooterId"] in frames[fr][0]:
                votes[(s["period"], s["offTeamId"])].append(1 if abs(frames[fr][0][s["shooterId"]][0] - s["location"][0]) < 0.5 else -1)
        sign = {k: int(np.sign(np.sum(v))) for k, v in votes.items()}
        for fr, plist in pairs.items():
            if fr not in frames:
                continue
            pos, ball = frames[fr]
            for d_id, o_id, per, team in plist:
                sg = sign.get((per, team))
                if sg is None or d_id not in pos or o_id not in pos or any(p[0] * sg > 0 for p in pos.values()):
                    continue  # Franks' filter: all ten players in the offensive half
                pk = pick.get(fr)
                out["game"].append(gid)
                out["O"].append((pos[o_id][0] * sg, pos[o_id][1] * sg))
                out["D"].append((pos[d_id][0] * sg, pos[d_id][1] * sg))
                out["B"].append((ball[0] * sg, ball[1] * sg))
                out["seen"].append(pos[o_id][2] and pos[d_id][2])
                out["on_ball"].append(holder.get(fr) == o_id)
                out["in_air"].append(fr not in holder)
                out["pick_role"].append(0 if not pk else 1 if pk[0] == o_id else 2 if pk[1] == o_id else 0)
                out["cover"].append(pk[2] if pk else "")
    return {k: np.array(v) for k, v in out.items()}


def fit(O, B, D):
    X = np.c_[np.r_[O[:, 0], O[:, 1]], np.r_[B[:, 0], B[:, 1]]]
    g, *_ = np.linalg.lstsq(X, np.r_[D[:, 0], D[:, 1]], rcond=None)
    return g


def main() -> None:
    d = load()
    O, B, D = d["O"] - HOOP, d["B"] - HOOP, d["D"] - HOOP
    game = d["game"]
    n = len(game)
    man_ball = np.hypot(*(d["O"] - d["B"]).T)
    man_hoop = np.hypot(*O.T)
    weak = (np.sign(d["O"][:, 1]) != np.sign(d["B"][:, 1])) & (np.abs(d["B"][:, 1]) > 4)  # across the rim line from the ball
    print(f"defender samples, all ten players in the half court: {n:,} · both players seen on camera: {d['seen'].mean() * 100:.0f}%\n")

    # ---- how the weights move with the situation
    def show(name, mask):
        a, b = fit(O[mask], B[mask], D[mask])
        per = [fit(O[mask & (game == g)], B[mask & (game == g)], D[mask & (game == g)]) for g in np.unique(game) if (mask & (game == g)).sum() > 200]
        lo, hi = np.min(per, 0), np.max(per, 0)
        res = D[mask] - (a * O[mask] + b * B[mask])
        print(f"  {name:<44} n={mask.sum():>7,} · man {a:.2f} ({lo[0]:.2f}-{hi[0]:.2f}) · ball {b:.2f} ({lo[1]:.2f}-{hi[1]:.2f}) · hoop {1 - a - b:.2f} · miss {np.sqrt(np.mean(np.sum(res ** 2, 1))):.1f} ft")

    off = ~d["on_ball"] & ~d["in_air"]
    print("weights by situation (in brackets: lowest and highest single game)")
    show("everyone", np.ones(n, bool))
    show("guarding the ball", d["on_ball"])
    for lo_, hi_ in ((0, 10), (10, 16), (16, 22), (22, 30), (30, 60)):
        show(f"off the ball, his man {lo_}-{hi_} ft from the ball", off & (man_ball >= lo_) & (man_ball < hi_))
    show("off the ball, strong side", off & ~weak)
    show("off the ball, weak side", off & weak)
    show("off the ball, his man inside 10 ft of the hoop", off & (man_hoop < 10))
    show("off the ball, his man beyond 20 ft of the hoop", off & (man_hoop >= 20))
    print("\n  within a second of a ball screen:")
    for cover in ("over", "under", "switch"):
        show(f"    handler's defender, coverage '{cover}'", (d["pick_role"] == 1) & (d["cover"] == cover))
        show(f"    screener's defender, coverage '{cover}'", (d["pick_role"] == 2) & (d["cover"] == cover))

    # ---- does context actually predict better on a game the model has not seen?
    bins = np.digitize(man_ball, [10, 16, 22, 30])
    ctx = {
        "one model for everyone (Franks)": np.zeros(n, int),
        "on ball / off ball": d["on_ball"].astype(int),
        "+ distance of his man to the ball": np.where(d["on_ball"], 0, 1 + bins),
        "+ strong / weak side": np.where(d["on_ball"], 0, 1 + bins + 5 * weak),
        "+ his man near the hoop": np.where(d["on_ball"], 0, 1 + bins + 5 * weak + 10 * (man_hoop < 10)),
        "+ ball screen role and coverage": np.where(d["pick_role"] > 0, 100 + d["pick_role"] * 10 + np.array([{"over": 1, "under": 2, "switch": 3}.get(c, 0) for c in d["cover"]]),
                                                    np.where(d["on_ball"], 0, 1 + bins + 5 * weak + 10 * (man_hoop < 10))),
    }
    print("\nleave one game out: typical miss of the predicted spot, in feet (all samples · only when both players are seen on camera)")
    for name, key in ctx.items():
        err = np.zeros(n)
        for g in np.unique(game):
            test = game == g
            for k in np.unique(key):
                tr, te = ~test & (key == k), test & (key == k)
                if te.sum() == 0:
                    continue
                a, b = fit(O[tr], B[tr], D[tr]) if tr.sum() > 200 else fit(O[~test], B[~test], D[~test])
                err[te] = np.sum((D[te] - (a * O[te] + b * B[te])) ** 2, 1)
        print(f"  {name:<40} {np.sqrt(err.mean()):.2f} · {np.sqrt(err[d['seen'].astype(bool)].mean()):.2f}   ({len(np.unique(key))} situations)")


if __name__ == "__main__":
    main()
