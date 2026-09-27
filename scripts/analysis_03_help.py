"""Analysis 3 — who pays for the help?

    uv run scripts/analysis_03_help.py

For every shot taken off a pass: when the pass left the passer's hands, where was the shooter's own defender? How far beyond
his normal spot, and how much of that did he get back before the release? Intervals resample whole games. Read-only.
"""

from __future__ import annotations

import numpy as np

from courtlab import equilibrium
from courtlab.data import Game, game_ids

FPS = 25
rows = []
for gid in game_ids():
    g = Game.load(gid)
    ev = g.events
    touches = {t["id"]: t for t in ev["touches"]}
    jobs = []
    for s in ev["shots"]:
        t = touches.get(s["touchId"])
        c = g.chances.get(s["chanceId"])
        if not t or not c or not c["usable"] or s["shotQuality"] is None or s["fouled"]:
            continue
        feed = [p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["receiverId"] == s["shooterId"]
                and p["startFrame"] <= t["startFrame"] and t["startFrame"] - p["startFrame"] <= 3 * FPS]
        if feed:
            jobs.append((s, c, max(feed, key=lambda p: p["startFrame"])))
    frames = g.frames_at({j[2]["startFrame"] for j in jobs} | {j[0]["startFrame"] for j in jobs})
    guard = {}
    for m in ev["matchups"]:
        guard.setdefault(m["offPlayerId"], []).append((m["startFrame"], m["endFrame"], m["defPlayerId"]))
    own = lambda player, fr: next((d for a, b, d in guard.get(player, []) if a <= fr <= b), None)  # noqa: E731
    drives = [(d["startFrame"], d["endFrame"], d["ballhandlerId"], bool(d["blowby"])) for d in ev["drives"]]
    picks = [(p["frame"], p["ballhandlerId"], p["screenerId"]) for p in ev["picks"]]
    posts = [(p["startFrame"], p["endFrame"], p["ballhandlerId"]) for p in ev["posts"]]
    for s, c, p in jobs:
        f0, f1 = frames.get(p["startFrame"]), frames.get(s["startFrame"])
        d_id = own(s["shooterId"], p["startFrame"])
        if not f0 or not f1 or d_id is None:
            continue
        sg = g.sign(c)
        at = lambda f, who: next((np.array(q["xyz"][:2]) * sg for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == who), None)  # noqa: E731
        o0, d0, o1, d1 = at(f0, s["shooterId"]), at(f0, d_id), at(f1, s["shooterId"]), at(f1, d_id)
        passer = at(f0, p["passerId"])
        if any(v is None for v in (o0, d0, o1, d1, passer)):
            continue
        ball0 = np.array(f0["ball"]["xyz"][:2]) * sg
        gap0, extra0 = equilibrium.extra(o0[None], ball0[None], d0[None])
        fr = p["startFrame"]
        doing = ("drive" if any(a - 5 <= fr <= b + FPS and who == p["passerId"] for a, b, who, _ in drives)
                 else "ball screen" if any(0 <= fr - a <= 3 * FPS and p["passerId"] in (h, sc) for a, h, sc in picks)
                 else "post-up" if any(a <= fr <= b + FPS and who == p["passerId"] for a, b, who in posts) else "nothing labelled")
        rows.append({"game": gid, "three": s["three"], "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100,
                     "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "gap0": float(gap0[0]), "extra0": float(extra0[0]),
                     "gap1": float(np.hypot(*(d1 - o1))), "secs": (s["startFrame"] - p["startFrame"]) / FPS,
                     "to_passer": float(np.hypot(*(d0 - passer))), "doing": doing, "open": s["contestLevel"] in ("open", "light"),
                     "helped": s["closestDefId"] is not None and s["closestDefId"] != own(s["shooterId"], s["startFrame"])})

R = {k: np.array([r[k] for r in rows]) for k in rows[0]}
games = np.unique(R["game"])
rng = np.random.default_rng(3)


def ci(stat, mask):
    boot = []
    for _ in range(600):
        idx = np.concatenate([np.flatnonzero(mask & (R["game"] == g)) for g in rng.choice(games, len(games))])
        if len(idx):
            boot.append(stat(idx))
    return np.percentile(boot, [2.5, 97.5])


print(f"shots taken within 3 s of catching a pass, with tracking for shooter and defender: {len(rows)} ({R['three'].mean() * 100:.0f}% threes)\n")
print("where the shooter's own defender was when the pass left, against how the shot turned out")
print(f"{'beyond his normal spot':<26}{'n':>5}  {'threes':>6}  {'feet away':>9}  {'at release':>10}  {'got back':>8}  {'open shot':>9}  {'expected pts':>22}  {'actual':>6}")
for lo, hi, name in ((-99, 0, "closer than normal"), (0, 3, "0 to 3 ft"), (3, 6, "3 to 6 ft"), (6, 10, "6 to 10 ft"), (10, 99, "10 ft or more")):
    m = (R["extra0"] >= lo) & (R["extra0"] < hi)
    a, b = ci(lambda i: R["pps"][i].mean(), m)
    print(f"{name:<26}{m.sum():>5}  {R['three'][m].mean() * 100:5.0f}%  {np.median(R['gap0'][m]):9.1f}  {np.median(R['gap1'][m]):10.1f}  {np.median(R['gap0'][m] - R['gap1'][m]):+8.1f}"
          f"  {R['open'][m].mean() * 100:8.0f}%  {R['pps'][m].mean():8.2f} [{a:.2f}, {b:.2f}]  {R['pts'][m].mean():6.2f}")

t3 = R["three"].astype(bool)
print("\nonly threes (so the zone does not explain it):")
for lo, hi, name in ((-99, 3, "under 3 ft beyond normal"), (3, 99, "3 ft or more")):
    m = t3 & (R["extra0"] >= lo) & (R["extra0"] < hi)
    a, b = ci(lambda i: R["pps"][i].mean(), m)
    print(f"  {name:<26} n={m.sum():3d} · open {R['open'][m].mean() * 100:3.0f}% · expected {R['pps'][m].mean():.2f} [{a:.2f}, {b:.2f}] · actual {R['pts'][m].mean():.2f}")

far = R["extra0"] >= 6
print(f"\nwhen he was 6 ft or more out of place (n={far.sum()}): he stood a median {np.median(R['to_passer'][far]):.1f} ft from the passer; others {np.median(R['to_passer'][~far]):.1f} ft")
print("what the passer was doing:")
for k in ("drive", "ball screen", "post-up", "nothing labelled"):
    m = R["doing"] == k
    print(f"  {k:<18} n={m.sum():3d} · shooter's defender out of place by a median {np.median(R['extra0'][m]):+.1f} ft · 6 ft or more in {np.mean(R['extra0'][m] >= 6) * 100:3.0f}% · expected {R['pps'][m].mean():.2f}")

speed = (R["gap0"] - R["gap1"]) / np.maximum(R["secs"], 0.2)
m = R["extra0"] >= 3
print(f"\nthe race back (defender 3 ft or more out of place, n={m.sum()}): pass to release {np.median(R['secs'][m]):.2f} s · he closes {np.median(speed[m]):.1f} ft per second · arrives still {np.median(R['gap1'][m]):.1f} ft short")
for lo, hi in ((0, 8), (8, 12), (12, 16), (16, 40)):
    k = m & (R["gap0"] >= lo) & (R["gap0"] < hi)
    if k.sum() >= 15:
        print(f"  started {lo:>2}-{hi:<2} ft away: n={k.sum():3d} · at release {np.median(R['gap1'][k]):4.1f} ft · open shot {R['open'][k].mean() * 100:3.0f}% · expected {R['pps'][k].mean():.2f}")
print(f"\nclosest defender at release is somebody else's man: {R['helped'].mean() * 100:.0f}% of these shots")
