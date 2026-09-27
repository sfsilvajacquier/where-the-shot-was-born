"""Analysis 4 — why is one more pass worth what it is worth?

    uv run scripts/analysis_04_one_more.py

After the last labelled action of a chance (ball screen, hand-off, off-ball screen, drive, isolation, post-up), follow every pass up to the
shot: how far out of place the receiver's own defender is when each pass leaves, how fast the ball travels, how fast defenders move.
Then take the shot apart: more threes, more room, or a better shooter? Intervals resample whole games. Read-only.
"""

from __future__ import annotations

import numpy as np

from courtlab import equilibrium
from courtlab.data import Game, game_ids, season_shooting

FPS = 25
season = season_shooting()
league3 = sum(v["three_made"] for v in season.values()) / sum(v["three_att"] for v in season.values())
shots, links, ball_speed, run_speed = [], [], [], []
for gid in game_ids():
    g = Game.load(gid)
    ev = g.events
    acts = {}
    for table, key in (("picks", "frame"), ("handoffs", "frame"), ("off_ball_screens", "frame"), ("drives", "startFrame"), ("isolations", "startFrame"), ("posts", "startFrame")):
        for e in ev[table]:
            acts.setdefault(e["chanceId"], []).append(e[key])
    passes = {}
    for p in ev["passes"]:
        if p["complete"] and p["endFrame"] is not None:
            passes.setdefault(p["chanceId"], []).append(p)
            secs = (p["endFrame"] - p["startFrame"]) / FPS
            if secs >= 0.2 and p["distance"]:
                ball_speed.append(p["distance"] / secs)
    guard = {}
    for m in ev["matchups"]:
        guard.setdefault(m["offPlayerId"], []).append((m["startFrame"], m["endFrame"], m["defPlayerId"]))
    own = lambda player, fr: next((d for a, b, d in guard.get(player, []) if a <= fr <= b), None)  # noqa: E731
    jobs = []
    for s in ev["shots"]:
        c = g.chances.get(s["chanceId"])
        before = [f for f in acts.get(s["chanceId"], []) if f <= s["startFrame"]]
        if not c or not c["usable"] or s["shotQuality"] is None or s["fouled"] or not before:
            continue
        chain = sorted((p for p in passes.get(s["chanceId"], []) if max(before) < p["startFrame"] <= s["startFrame"]), key=lambda p: p["startFrame"])
        jobs.append((s, c, chain))
    frames = g.frames_at({p["startFrame"] for _, _, ch in jobs for p in ch} | {c["startFrame"] for c in ev["closeouts"]} | {c["endFrame"] for c in ev["closeouts"]})
    for c in ev["closeouts"]:  # how fast does a defender actually run when he closes out?
        a, b = frames.get(c["startFrame"]), frames.get(c["endFrame"])
        if a and b and c["endFrame"] > c["startFrame"]:
            pa = next((q["xyz"][:2] for q in a["homePlayers"] + a["awayPlayers"] if q["playerId"] == c["ballhandlerDefId"]), None)
            pb = next((q["xyz"][:2] for q in b["homePlayers"] + b["awayPlayers"] if q["playerId"] == c["ballhandlerDefId"]), None)
            if pa and pb:
                run_speed.append(np.hypot(pa[0] - pb[0], pa[1] - pb[1]) / ((c["endFrame"] - c["startFrame"]) / FPS))
    for s, c, chain in jobs:
        sg = g.sign(c)
        rec = season.get(s["shooterId"])
        shots.append({"game": gid, "k": min(len(chain), 3), "three": bool(s["three"]), "cns": bool(s["catchAndShoot"]), "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100,
                      "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "def_ft": s["closestDefDist"] if s["closestDefDist"] is not None else np.nan,
                      "clock": s["shotClock"] if s["shotClock"] is not None else np.nan,
                      "skill": rec["three_made"] / rec["three_att"] if rec and rec["three_att"] >= 50 else np.nan})
        for n, p in enumerate(chain):
            f = frames.get(p["startFrame"])
            d_id = own(p["receiverId"], p["startFrame"])
            if not f or d_id is None:
                continue
            at = lambda who: next((np.array(q["xyz"][:2]) * sg for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == who), None)  # noqa: E731
            o, d = at(p["receiverId"]), at(d_id)
            if o is None or d is None:
                continue
            gap, ext = equilibrium.extra(o[None], (np.array(f["ball"]["xyz"][:2]) * sg)[None], d[None])
            links.append({"game": gid, "order": n + 1, "of": len(chain), "from_end": len(chain) - n, "extra": float(ext[0]), "gap": float(gap[0])})

S = {k: np.array([r[k] for r in shots]) for k in shots[0]}
L = {k: np.array([r[k] for r in links]) for k in links[0]}
games, rng = np.unique(S["game"]), np.random.default_rng(5)


def ci(values, game, mask):
    boot = [np.nanmean(values[np.concatenate([np.flatnonzero(mask & (game == g)) for g in rng.choice(games, len(games))])]) for _ in range(600)]
    return np.nanpercentile(boot, [2.5, 97.5])


print(f"shots after a labelled action: {len(shots)} · passes followed: {len(links)}\n")
print("passes between the last action and the shot")
print(f"{'':<10}{'n':>5}  {'expected points':>22}  {'actual':>6}  {'threes':>6}  {'catch & shoot':>13}  {'defender, ft':>12}  {'shot clock':>10}")
for k in range(4):
    m = S["k"] == k
    a, b = ci(S["pps"], S["game"], m)
    print(f"{('3 or more' if k == 3 else str(k)):<10}{m.sum():>5}  {S['pps'][m].mean():10.2f} [{a:.2f}, {b:.2f}]  {S['pts'][m].mean():6.2f}  {S['three'][m].mean() * 100:5.0f}%  {S['cns'][m].mean() * 100:12.0f}%  {np.nanmedian(S['def_ft'][m]):12.1f}  {np.nanmedian(S['clock'][m]):10.1f}")

print("\nthe same, inside one kind of shot (so the mix does not explain it):")
for name, base in (("threes", S["three"]), ("catch-and-shoot threes", S["three"] & S["cns"]), ("twos", ~S["three"])):
    row = []
    for k in range(4):
        m = base & (S["k"] == k)
        row.append(f"{('3+' if k == 3 else k)}: {S['pps'][m].mean():.2f} (n={m.sum()}, def {np.nanmedian(S['def_ft'][m]):.1f} ft)" if m.sum() >= 15 else f"{k}: n<15")
    print(f"  {name:<24}", " · ".join(row))
m3 = S["three"] & ~np.isnan(S["skill"])
print("\nwho ends up shooting the three? season accuracy of the shooter, league", f"{league3 * 100:.1f}%:")
print("  " + " · ".join(f"{('3+' if k == 3 else k)} passes: {np.nanmean(S['skill'][m3 & (S['k'] == k)]) * 100:.1f}% (n={(m3 & (S['k'] == k)).sum()})" for k in range(4)))

print("\nhow far out of place is the receiver's own defender when each pass leaves?  (median ft beyond his normal spot · feet away)")
for back, name in ((1, "the pass to the shooter"), (2, "the pass before it"), (3, "two passes before")):
    m = L["from_end"] == back
    a, b = ci(L["extra"], L["game"], m)
    print(f"  {name:<24} n={m.sum():4d} · {np.median(L['extra'][m]):+.1f} ft (mean {L['extra'][m].mean():+.1f} [{a:+.1f}, {b:+.1f}]) · {np.median(L['gap'][m]):.1f} ft away")
two = L["of"] >= 2
print("  in chains of two or more:  first pass", f"{np.median(L['extra'][two & (L['order'] == 1)]):+.1f} ft", "→ last pass", f"{np.median(L['extra'][two & (L['from_end'] == 1)]):+.1f} ft")

print(f"\nthe race: a pass travels at a median {np.median(ball_speed):.0f} ft/s (n={len(ball_speed)}) · a defender closing out runs {np.median(run_speed):.1f} ft/s, fastest tenth {np.percentile(run_speed, 90):.1f} (n={len(run_speed)})")
