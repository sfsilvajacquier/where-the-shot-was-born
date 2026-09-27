"""Feasibility, read-only: possessions as sentences. Every chance becomes the ordered list of the actions SkillCorner labels
(pick with its coverage, hand-off, off-ball screen, drive, isolation, post-up), and the shot at the end carries SkillCorner's quality."""
import collections, json
from pathlib import Path
import numpy as np

DATA = Path("../opendata-basketball/data")
rows, grams = [], collections.defaultdict(list)
for g in json.load(open(DATA / "matches.json")):
    gid = g["id"]; ev = json.load(open(DATA / "matches" / str(gid) / f"{gid}_dynamic_events.json"))
    acts = collections.defaultdict(list)
    for p in ev["picks"]: acts[p["chanceId"]].append((p["frame"], "pick:" + str(p["bhrDefType"])))
    for k, tag in (("handoffs", "handoff"), ("off_ball_screens", "screen"), ("isolations", "iso"), ("posts", "post")):
        for e in ev[k]: acts[e["chanceId"]].append((e.get("frame") or e.get("startFrame"), tag))
    for d in ev["drives"]: acts[d["chanceId"]].append((d.get("startFrame") or d.get("frame"), "drive+" if d.get("blowby") else "drive"))
    passes = collections.defaultdict(list)
    for p in ev["passes"]: passes[p["chanceId"]].append(p.get("frame") or p.get("startFrame"))
    matchups = ev["matchups"]
    for s in ev["shots"]:
        if s.get("shotQuality") is None: continue
        t = s["endFrame"]
        chain = sorted(a for a in acts.get(s["chanceId"], []) if a[0] is not None and a[0] <= t)
        last = chain[-1] if chain else None
        n_pass_after = sum(1 for f in passes.get(s["chanceId"], []) if f is not None and last and last[0] < f <= t)
        assigned = next((m["defPlayerId"] for m in matchups if m["offPlayerId"] == s["shooterId"] and m["startFrame"] <= s["startFrame"] <= m["endFrame"]), None)
        pps = (3 if s["three"] else 2) * s["shotQuality"] / 100
        rows.append({"pps": pps, "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "last": last[1].split(":")[0] if last else "none", "cover": last[1] if last and last[1].startswith("pick:") else None,
                     "since": (t - last[0]) / 25 if last else np.nan, "passes_after": n_pass_after, "paint": bool(s["createdFromPaint"]), "cns": bool(s["catchAndShoot"]),
                     "helped": assigned is not None and s.get("closestDefId") is not None and assigned != s["closestDefId"], "has_assigned": assigned is not None,
                     "release": s.get("releaseTime"), "n_actions": len(chain), "three": bool(s["three"])})
        if len(chain) >= 2: grams[" > ".join(a[1].split(":")[0] for a in chain[-2:])].append(pps)

import pandas as pd
d = pd.DataFrame(rows); base = d.pps.mean()
print(f"shots with a quality score: {len(d)} · expected points per shot {base:.2f} · actual {d.pts.mean():.2f}\n")
print("what was the last labelled action before the shot?")
print(d.groupby("last").agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean"), secs_before=("since", "median")).sort_values("n", ascending=False).round(2))
print("\nafter a pick, by how the ball-handler's defender played it:")
print(d[d.cover.notna()].groupby("cover").agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean")).sort_values("n", ascending=False).round(2))
print("\nhow old is the advantage? seconds between the last action and the release:")
d["age"] = pd.cut(d.since, [0, 1.5, 3, 5, 8, 30])
print(d.groupby("age", observed=True).agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean")).round(2))
print("\npasses between the last action and the shot:")
print(d[d["last"] != "none"].assign(k=lambda x: x.passes_after.clip(upper=3)).groupby("k").agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean"), threes=("three", "mean")).round(2))
print("\nshot created from the paint (SkillCorner flag):")
print(d.groupby("paint").agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean")).round(2))
h = d[d.has_assigned]
print(f"\nclosest defender at the release is NOT the shooter's own man: {h.helped.mean() * 100:.0f}% of {len(h)} shots")
print(h.groupby("helped").agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean"), threes=("three", "mean")).round(2))
print("\nthe 'half-second rule' on catch-and-shoot threes: time from catch to release")
c = d[d.cns & d.three & d.release.notna()].copy(); c["rel"] = pd.cut(c.release, [0, 0.5, 0.8, 1.2, 5])
print(c.groupby("rel", observed=True).agg(n=("pps", "size"), expected=("pps", "mean"), actual=("pts", "mean")).round(2))
print("\nmost common two-action endings (n >= 25):")
for k, v in sorted(grams.items(), key=lambda kv: -len(kv[1])):
    if len(v) >= 25: print(f"  {k:<22} n={len(v):3d} · expected {np.mean(v):.2f}")
