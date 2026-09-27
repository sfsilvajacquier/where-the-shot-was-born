"""Analysis 10 — what else is in the data? Six candidate layers, each checked before anything is drawn.

    uv run scripts/analysis_10_more_signal.py

A. The shot in the air: is the tracked ball physical? (fit gravity on every shot's flight) -> release height, apex, entry angle
B. The passes: length, flight time, speed
C. The close-out: how fast defenders actually run at a shooter
D. Spacing: area of the attack's and the defence's hull, defenders in the paint, when the pass to the shooter leaves
E. Hand-overs: how many times the defence changes assignments in a possession, and what that costs
Read-only. Intervals resample whole games.
"""

from __future__ import annotations

from collections import defaultdict

import numpy as np

from courtlab import court
from courtlab.data import Game, game_ids

FPS, G_FT = 25, 32.174
rng = np.random.default_rng(10)
PAINT_X, PAINT_Y = -court.LENGTH / 2 + 19.03, 16.08 / 2


def hull_area(pts: np.ndarray) -> float:
    p = sorted(map(tuple, pts))
    if len(p) < 3:
        return 0.0
    cross = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])  # noqa: E731
    lo, up = [], []
    for q in p:
        while len(lo) >= 2 and cross(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(up) >= 2 and cross(up[-2], up[-1], q) <= 0:
            up.pop()
        up.append(q)
    h = np.array(lo[:-1] + up[:-1])
    return 0.5 * abs(np.dot(h[:, 0], np.roll(h[:, 1], -1)) - np.dot(h[:, 1], np.roll(h[:, 0], -1)))


def ci(values, games, stat=np.mean):
    values, games = np.asarray(values, float), np.asarray(games)
    ids = np.unique(games)
    boot = [stat(np.concatenate([values[games == k] for k in rng.choice(ids, len(ids))])) for _ in range(500)]
    return tuple(np.percentile(boot, [2.5, 97.5]))


arcs, passes, runs, space, hand = [], [], [], [], []
for gid in game_ids():
    g = Game.load(gid)
    ev = g.events
    touches = {t["id"]: t for t in ev["touches"]}
    usable = {c["id"]: c for c in ev["chances"] if c["usable"]}
    need = set()
    flights = [s for s in ev["shots"] if s["chanceId"] in usable and not s["blocked"] and s["endFrame"] and s["endFrame"] - s["startFrame"] >= 12]
    for s in flights:
        need |= set(range(s["startFrame"], s["endFrame"] + 1))
    pss = [p for p in ev["passes"] if p["chanceId"] in usable and p["complete"] and p["endFrame"] and not p["inbounds"] and 2 <= p["endFrame"] - p["startFrame"] <= 60]
    for p in pss:
        need |= {p["startFrame"], p["endFrame"]}
    cos = [c for c in ev["closeouts"] if c["chanceId"] in usable and c["startFrame"] and c["endFrame"] and c["endFrame"] - c["startFrame"] >= 8]
    for c in cos:
        need |= set(range(c["startFrame"], c["endFrame"] + 1))
    feeds = []
    for s in ev["shots"]:
        t, c = touches.get(s["touchId"]), usable.get(s["chanceId"])
        if not t or not c or c["transition"] or s["shotQuality"] is None or s["fouled"]:
            continue
        feed = [p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["receiverId"] == s["shooterId"] and 0 <= t["startFrame"] - p["startFrame"] <= 3 * FPS]
        if feed:
            feeds.append((s, c, max(feed, key=lambda p: p["startFrame"])))
    need |= {f[2]["startFrame"] for f in feeds}
    frames = g.frames_at(need)

    # A — the ball in the air
    for s in flights:
        c = usable[s["chanceId"]]
        sg = g.sign(c)
        rows = [(f["frameIdx"], *f["ball"]["xyz"], f["ball"]["isDetected"]) for k in range(s["startFrame"], s["endFrame"] + 1) if (f := frames.get(k))]
        if len(rows) < 12:
            continue
        a = np.array(rows, float)
        seen_share = float(a[:, 4].mean())
        t = (a[:, 0] - s["startFrame"]) / FPS
        x, y, z = a[:, 1] * sg, a[:, 2] * sg, a[:, 3]
        d = np.hypot(x - court.HOOP_X, y)
        fly = d > 1.5  # before it reaches the rim: after that it is the net, the board or a rebound
        if fly.sum() < 10:
            continue
        cz = np.polyfit(t[fly], z[fly], 2)
        res = float(np.sqrt(np.mean((np.polyval(cz, t[fly]) - z[fly]) ** 2)))
        vh = np.hypot(np.polyfit(t[fly], x[fly], 1)[0], np.polyfit(t[fly], y[fly], 1)[0])
        disc = cz[1] ** 2 - 4 * cz[0] * (cz[2] - court.RIM_HEIGHT)
        entry = np.nan
        if cz[0] < 0 and disc > 0:
            tr = (-cz[1] - np.sqrt(disc)) / (2 * cz[0])  # the later root: on the way down
            entry = float(np.degrees(np.arctan2(-(2 * cz[0] * tr + cz[1]), vh)))
        arcs.append({"game": gid, "g": -2 * cz[0], "res": res, "release": float(np.polyval(cz, 0)), "apex": float(cz[2] - cz[1] ** 2 / (4 * cz[0])) if cz[0] < 0 else np.nan,
                     "entry": entry, "three": bool(s["three"]), "made": bool(s["outcome"]), "dist": s["distance"] or 0.0, "n": int(fly.sum()), "id": s["chanceId"], "sq": s["shotQuality"], "seen": seen_share})

    # B — passes
    for p in pss:
        f0, f1 = frames.get(p["startFrame"]), frames.get(p["endFrame"])
        if f0 and f1:  # the ball's isDetected flag is 0 in every frame of the release, so it cannot be used as a filter
            b0, b1 = np.array(f0["ball"]["xyz"]), np.array(f1["ball"]["xyz"])
            secs = (p["endFrame"] - p["startFrame"]) / FPS
            passes.append({"game": gid, "ft": float(np.hypot(*(b1 - b0)[:2])), "secs": secs, "id": p["chanceId"], "i": p["startFrame"]})

    # C — close-outs: the defender's own path
    for c in cos:
        path = [next((q["xyz"][:2] for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == c["ballhandlerDefId"] and q["isDetected"]), None)
                for k in range(c["startFrame"], c["endFrame"] + 1) if (f := frames.get(k))]
        path = np.array([q for q in path if q is not None], float)
        if len(path) < 8 or not c["startDistance"]:
            continue
        k = np.ones(5) / 5
        sm = np.c_[np.convolve(path[:, 0], k, "valid"), np.convolve(path[:, 1], k, "valid")]
        v = np.hypot(*np.diff(sm, axis=0).T) * FPS
        runs.append({"game": gid, "start": c["startDistance"], "end": c["endDistance"], "secs": (c["endFrame"] - c["startFrame"]) / FPS, "peak": float(np.percentile(v, 95)),
                     "mean": float(v.mean()), "id": c["chanceId"], "def": c["ballhandlerDefId"]})

    # D — shape of both teams when the pass to the shooter leaves
    for s, c, p in feeds:
        f = frames.get(p["startFrame"])
        if not f:
            continue
        sg = g.sign(c)
        pos = {q["playerId"]: np.array(q["xyz"][:2]) * sg for q in f["homePlayers"] + f["awayPlayers"]}
        att, dfn = [pos[i] for i in c["offPlayerIds"] if i in pos], [pos[i] for i in c["defPlayerIds"] if i in pos]
        if len(att) < 5 or len(dfn) < 5:
            continue
        in_paint = sum(1 for q in dfn if q[0] <= PAINT_X and abs(q[1]) <= PAINT_Y)
        space.append({"game": gid, "att": hull_area(np.array(att)), "def": hull_area(np.array(dfn)), "paint": in_paint, "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100,
                      "three": bool(s["three"]), "id": s["chanceId"]})

    # E — changes of assignment inside a possession
    starts = defaultdict(list)
    for m in ev["matchups"]:
        if m["endFrame"] - m["startFrame"] >= 5:
            starts[m["chanceId"]].append((m["offPlayerId"], m["startFrame"], m["defPlayerId"]))
    for cid, c in usable.items():
        if c["transition"] or c["frontcourtFrame"] is None:
            continue
        per = defaultdict(list)
        for o, fr, d in sorted(starts.get(cid, []), key=lambda r: r[1]):
            per[o].append(d)
        changes = sum(sum(1 for a, b in zip(v, v[1:]) if a != b) for v in per.values())
        hand.append({"game": gid, "changes": changes, "pts": c["ptsScored"] or 0, "id": cid})

HERO = "chance-191313-1-7"
col = lambda rows, k: np.array([r[k] for r in rows])  # noqa: E731

print(f"A · THE BALL IN THE AIR — {len(arcs)} shots with 10+ ball frames before the rim")
seen = col(arcs, "seen")
print(f"   share of the flight in which the ball is actually DETECTED: median {np.median(seen) * 100:.0f} % · flights with no detected frame at all: {np.mean(seen == 0) * 100:.0f} %")
gfit, res = col(arcs, "g"), col(arcs, "res")
print(f"   gravity recovered from the ball's height: median {np.median(gfit):.1f} ft/s² (real: {G_FT:.1f}) · middle half {np.percentile(gfit, 25):.1f}–{np.percentile(gfit, 75):.1f} · fit error {np.median(res):.2f} ft")
ok = (np.abs(gfit - G_FT) < 6) & (res < 0.5)
print(f"   flights that behave like a thrown ball (gravity within 6 ft/s², error under half a foot): {ok.mean() * 100:.0f} %")
A = [a for a, k in zip(arcs, ok) if k]
for label, m in (("threes", col(A, "three")), ("twos from 8 ft or more", ~col(A, "three") & (col(A, "dist") >= 8))):
    e, ap, rl, md = col(A, "entry")[m], col(A, "apex")[m], col(A, "release")[m], col(A, "made")[m]
    print(f"   {label}: n={m.sum()} · release {np.nanmedian(rl):.1f} ft · apex {np.nanmedian(ap):.1f} ft · entry angle {np.nanmedian(e):.0f}° (middle half {np.nanpercentile(e, 25):.0f}–{np.nanpercentile(e, 75):.0f}°)")
    for lo, hi in ((0, 40), (40, 45), (45, 50), (50, 90)):
        k = (e >= lo) & (e < hi)
        if k.sum() >= 25:
            a_, b_ = ci(md[k], col(A, "game")[m][k])
            print(f"        entry {lo:>2}–{hi:<2}°: n={k.sum():3d} · made {md[k].mean() * 100:3.0f} % [{a_ * 100:.0f}, {b_ * 100:.0f}]")
h = [a for a in arcs if a["id"] == HERO]
if h:
    print(f"   the hero shot: gravity {h[0]['g']:.1f} · release {h[0]['release']:.1f} ft · apex {h[0]['apex']:.1f} ft · entry {h[0]['entry']:.0f}° · fit error {h[0]['res']:.2f} ft")

print(f"\nB · PASSES — {len(passes)} complete passes")
ft, secs = col(passes, "ft"), col(passes, "secs")
print(f"   length {np.median(ft):.0f} ft (middle half {np.percentile(ft, 25):.0f}–{np.percentile(ft, 75):.0f}) · in the air {np.median(secs):.2f} s · speed {np.median(ft / secs):.0f} ft/s (middle half {np.percentile(ft / secs, 25):.0f}–{np.percentile(ft / secs, 75):.0f})")
for p in sorted([p for p in passes if p["id"] == HERO], key=lambda p: p["i"]):
    print(f"   hero: {p['ft']:4.1f} ft in {p['secs']:.2f} s = {p['ft'] / p['secs']:3.0f} ft/s")

print(f"\nC · CLOSE-OUTS — {len(runs)}")
pk, st, en = col(runs, "peak"), col(runs, "start"), col(runs, "end")
print(f"   start {np.median(st):.0f} ft away, end {np.median(en):.0f} ft · top speed {np.median(pk):.1f} ft/s (middle half {np.percentile(pk, 25):.1f}–{np.percentile(pk, 75):.1f}; 95th percentile {np.percentile(pk, 95):.1f})")
for lo, hi in ((0, 12), (12, 18), (18, 40)):
    k = (st >= lo) & (st < hi)
    print(f"   starting {lo:>2}–{hi:<2} ft away: n={k.sum():3d} · top speed {np.median(pk[k]):.1f} ft/s · arrives at {np.median(en[k]):.1f} ft")
for r in runs:
    if r["id"] == HERO:
        print(f"   hero: from {r['start']:.0f} to {r['end']:.0f} ft in {r['secs']:.2f} s · top speed {r['peak']:.1f} ft/s = faster than {np.mean(pk < r['peak']) * 100:.0f} % of close-outs")

print(f"\nD · SHAPE when the pass to the shooter leaves — {len(space)} shots off a catch, set offence")
at, df, pn, pps = col(space, "att"), col(space, "def"), col(space, "paint"), col(space, "pps")
print(f"   attack's hull {np.median(at):.0f} ft² · defence's hull {np.median(df):.0f} ft² · defenders in the paint: " + " · ".join(f"{k}: {np.mean(pn == k) * 100:.0f} %" for k in range(5)))
for k in range(4):
    m = pn == k if k < 3 else pn >= 3
    a_, b_ = ci(pps[m], col(space, "game")[m])
    print(f"   {k if k < 3 else '3+'} defenders in the paint: n={m.sum():3d} · threes {col(space, 'three')[m].mean() * 100:3.0f} % · expected {pps[m].mean():.2f} [{a_:.2f}, {b_:.2f}]")
q = np.percentile(df, [33, 67])
for label, m in (("defence compact (smallest third)", df < q[0]), ("middle", (df >= q[0]) & (df < q[1])), ("defence spread (largest third)", df >= q[1])):
    a_, b_ = ci(pps[m], col(space, "game")[m])
    print(f"   {label:<34} hull {np.median(df[m]):4.0f} ft² · expected {pps[m].mean():.2f} [{a_:.2f}, {b_:.2f}]")
for s in space:
    if s["id"] == HERO:
        print(f"   hero: attack {s['att']:.0f} ft² · defence {s['def']:.0f} ft² · {s['paint']} defenders in the paint")

print(f"\nE · CHANGES OF ASSIGNMENT per set possession — {len(hand)}")
ch, pts = col(hand, "changes"), col(hand, "pts")
for lo, hi, label in ((0, 0, "none"), (1, 2, "1–2"), (3, 4, "3–4"), (5, 99, "5 or more")):
    m = (ch >= lo) & (ch <= hi)
    a_, b_ = ci(pts[m], col(hand, "game")[m])
    print(f"   {label:<10} n={m.sum():4d} ({m.mean() * 100:2.0f} %) · {pts[m].mean():.2f} points per possession [{a_:.2f}, {b_:.2f}]")
print(f"   hero: {next(r['changes'] for r in hand if r['id'] == HERO)} changes")
