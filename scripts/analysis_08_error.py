"""Analysis 8 — how much does the tracking error shake the main result?

    uv run scripts/analysis_08_error.py

The ladder of analysis 3 (how far out of place the shooter's own defender is when the pass leaves -> expected points of the shot),
repeated (a) using only positions seen on camera, and (b) 300 times with every position moved by its own expected error
(SkillCorner's predError is a 90 % radius: sigma per axis = predError / 2.146). Noise is added on top of the noise already in the
data, so this is the pessimistic case. Read-only.
"""

from __future__ import annotations

import numpy as np

from courtlab import equilibrium
from courtlab.data import Game, game_ids

FPS, BINS = 25, [(-99, 0), (0, 3), (3, 6), (6, 10), (10, 99)]
rows = []
for gid in game_ids():
    g = Game.load(gid)
    ev = g.events
    touches = {t["id"]: t for t in ev["touches"]}
    guard = {}
    for m in ev["matchups"]:
        guard.setdefault(m["offPlayerId"], []).append((m["startFrame"], m["endFrame"], m["defPlayerId"]))
    jobs = []
    for s in ev["shots"]:
        t, c = touches.get(s["touchId"]), g.chances.get(s["chanceId"])
        if not t or not c or not c["usable"] or s["shotQuality"] is None or s["fouled"]:
            continue
        feed = [p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["receiverId"] == s["shooterId"]
                and p["startFrame"] <= t["startFrame"] and t["startFrame"] - p["startFrame"] <= 3 * FPS]
        if feed:
            jobs.append((s, c, max(feed, key=lambda p: p["startFrame"])))
    frames = g.frames_at({j[2]["startFrame"] for j in jobs})
    for s, c, p in jobs:
        f = frames.get(p["startFrame"])
        d_id = next((d for a, b, d in guard.get(s["shooterId"], []) if a <= p["startFrame"] <= b), None)
        if not f or d_id is None:
            continue
        who = {q["playerId"]: q for q in f["homePlayers"] + f["awayPlayers"]}
        if s["shooterId"] not in who or d_id not in who:
            continue
        sg, o, d, b = g.sign(c), who[s["shooterId"]], who[d_id], f["ball"]
        rows.append((gid, (3 if s["three"] else 2) * s["shotQuality"] / 100, o["xyz"][0] * sg, o["xyz"][1] * sg, d["xyz"][0] * sg, d["xyz"][1] * sg,
                     b["xyz"][0] * sg, b["xyz"][1] * sg, o["predError"], d["predError"], b["predError"], o["isDetected"] and d["isDetected"]))

R = np.array(rows, float)
pps, O, D, B, err, seen = R[:, 1], R[:, 2:4], R[:, 4:6], R[:, 6:8], R[:, 8:11] / 2.146, R[:, 11].astype(bool)
ladder = lambda extra, mask: [pps[mask & (extra >= lo) & (extra < hi)].mean() for lo, hi in BINS]  # noqa: E731
_, base = equilibrium.extra(O, B, D)
print(f"shots off a pass: {len(R)} · shooter and his defender both on camera when the pass leaves: {seen.mean() * 100:.0f}%")
print(f"typical position error (sigma per axis): shooter {np.median(err[:, 0]):.2f} ft · defender {np.median(err[:, 1]):.2f} ft · ball {np.median(err[:, 2]):.2f} ft\n")
names = ["closer than normal", "0 to 3 ft", "3 to 6 ft", "6 to 10 ft", "10 ft or more"]
all_, cam = ladder(base, np.ones(len(R), bool)), ladder(base, seen)
rng, sims, moved = np.random.default_rng(8), [], []
for _ in range(300):
    noisy = equilibrium.extra(O + rng.normal(0, 1, O.shape) * err[:, [0]], B + rng.normal(0, 1, B.shape) * err[:, [2]], D + rng.normal(0, 1, D.shape) * err[:, [1]])[1]
    sims.append(ladder(noisy, np.ones(len(R), bool)))
    moved.append(np.mean(np.digitize(noisy, [0, 3, 6, 10]) != np.digitize(base, [0, 3, 6, 10])))
sims = np.array(sims)
print(f"{'defender beyond his normal spot':<34}{'as measured':>12}{'on camera only':>16}{'with the error added (300 runs)':>36}")
for k, name in enumerate(names):
    lo, hi = np.percentile(sims[:, k], [2.5, 97.5])
    print(f"{name:<34}{all_[k]:>12.2f}{cam[k]:>16.2f}{sims[:, k].mean():>20.2f} [{lo:.2f}, {hi:.2f}]")
print(f"\nstep from the first to the last rung: measured {all_[-1] - all_[0]:+.2f} · on camera only {cam[-1] - cam[0]:+.2f} · with the error added {np.mean(sims[:, -1] - sims[:, 0]):+.2f} "
      f"[{np.percentile(sims[:, -1] - sims[:, 0], 2.5):+.2f}, {np.percentile(sims[:, -1] - sims[:, 0], 97.5):+.2f}]")
print(f"the ladder keeps rising rung by rung in {np.mean(np.all(np.diff(sims, axis=1) > 0, axis=1)) * 100:.0f}% of the runs · shots that change rung when the error is added: {np.mean(moved) * 100:.0f}%")
print(f"noise in the measure itself: adding the error moves 'extra' by a typical {np.sqrt(np.mean((equilibrium.extra(O + rng.normal(0, 1, O.shape) * err[:, [0]], B, D + rng.normal(0, 1, D.shape) * err[:, [1]])[1] - base) ** 2)):.1f} ft")
