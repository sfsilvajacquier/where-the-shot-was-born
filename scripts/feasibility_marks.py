"""Feasibility, read-only. (1) Where does a defender stand? Franks et al. (2015) model a defender's position as a weighted mix of
his man, the ball and the hoop. SkillCorner gives the matchups, so the weights can be fitted directly on ACB data.
(2) Does the distance from that 'equilibrium' say something about shot quality?"""
import collections, gzip, json, re
from pathlib import Path
import numpy as np

DATA = Path("../opendata-basketball/data")
FRAME = re.compile(r'"frameIdx":\s*(\d+)')
STEP = 5  # 5 samples a second
rows = []        # per defender-sample: game, on_ball, O-H (2), B-H (2), D-H (2)
shot_rows = []   # per shot: SQ, contest, residual of the shooter's defender at release, closestDefDist
hoop_fit = []
for g in json.load(open(DATA / "matches.json")):
    gid = g["id"]; folder = DATA / "matches" / str(gid)
    ev = json.load(open(folder / f"{gid}_dynamic_events.json"))
    chances = {c["id"]: c for c in ev["chances"]}
    shots_at = {s["startFrame"]: s for s in ev["shots"]}
    pairs = collections.defaultdict(list)
    for m in ev["matchups"]:
        c = chances.get(m["chanceId"])
        if not c or not c["usable"] or c["frontcourtFrame"] is None: continue
        a, b = max(m["startFrame"], c["frontcourtFrame"]), m["endFrame"]
        for f in range(a - a % STEP + STEP, b + 1, STEP):
            pairs[f].append((m["defPlayerId"], m["offPlayerId"], c["period"], c["offTeamId"]))
    holder = {}
    for t in ev["touches"]:
        for f in range(t["startFrame"] - t["startFrame"] % STEP, t["endFrame"] + 1, STEP): holder[f] = t["playerId"]
    matchup_at_shot = {}
    for m in ev["matchups"]:
        for fr, s in shots_at.items():
            if m["offPlayerId"] == s["shooterId"] and m["startFrame"] <= fr <= m["endFrame"]: matchup_at_shot[fr] = m["defPlayerId"]
    need = set(pairs) | set(shots_at)
    frames = {}
    with gzip.open(folder / f"{gid}_tracking_data.jsonl.gz", "rt") as fh:
        for line in fh:
            if '"homePlayers": []' in line: continue
            i = int(FRAME.search(line).group(1))
            if i in need:
                f = json.loads(line)
                if f["ball"]: frames[i] = ({p["playerId"]: p["xyz"][:2] for p in f["homePlayers"] + f["awayPlayers"]}, f["ball"]["xyz"][:2])
    # which way each (period, team) attacks: events put the attacked hoop at -x
    sign = {}
    votes = collections.defaultdict(list)
    for fr, s in shots_at.items():
        if fr in frames and s.get("location") and s["shooterId"] in frames[fr][0]:
            p = frames[fr][0][s["shooterId"]]
            votes[(s["period"], s["offTeamId"])].append(1 if abs(p[0] - s["location"][0]) < 0.5 else -1)
            if s.get("distance"): hoop_fit.append((s["location"][0], s["location"][1], s["distance"]))
    sign = {k: int(np.sign(np.sum(v))) for k, v in votes.items()}
    H = np.array([-41.0, 0.0])  # refined below from the shots' own distances; first pass
    for fr, plist in pairs.items():
        if fr not in frames: continue
        pos, ball = frames[fr]
        for d_id, o_id, per, team in plist:
            sg = sign.get((per, team))
            if sg is None or d_id not in pos or o_id not in pos: continue
            D, O, B = (np.array(pos[d_id]) * sg, np.array(pos[o_id]) * sg, np.array(ball) * sg)
            if B[0] > 0: continue  # half-court only
            rows.append((gid, holder.get(fr) == o_id, *O, *B, *D))
    for fr, s in shots_at.items():
        d_id = matchup_at_shot.get(fr)
        if fr in frames and d_id in frames[fr][0] and s["shooterId"] in frames[fr][0] and s.get("shotQuality") is not None:
            sg = sign.get((s["period"], s["offTeamId"]))
            if sg is None: continue
            pos, ball = frames[fr]
            shot_rows.append((s["shotQuality"], s["contestLevel"], s["three"], bool(s["outcome"]), *(np.array(pos[s["shooterId"]]) * sg), *(np.array(ball) * sg), *(np.array(pos[d_id]) * sg), s.get("closestDefDist") or np.nan))

hf = np.array(hoop_fit)
xs = np.linspace(-44, -38, 121)
best = xs[np.argmin([np.median(np.abs(np.hypot(hf[:, 0] - x, hf[:, 1]) - hf[:, 2])) for x in xs])]
print(f"hoop x implied by the shots' own 'distance' field: {best:.2f} ft (FIBA geometry says -40.76)")
H = np.array([best, 0.0])
R = np.array([r[1:] for r in rows], float); game = np.array([r[0] for r in rows])
on = R[:, 0].astype(bool); O, B, D = R[:, 1:3] - H, R[:, 3:5] - H, R[:, 5:7] - H

def fit(mask):
    X = np.c_[np.r_[O[mask, 0], O[mask, 1]], np.r_[B[mask, 0], B[mask, 1]]]
    y = np.r_[D[mask, 0], D[mask, 1]]
    g, *_ = np.linalg.lstsq(X, y, rcond=None)
    res = y - X @ g
    n = mask.sum()
    return g[0], g[1], 1 - g[0] - g[1], float(np.sqrt(np.mean(res[:n] ** 2 + res[n:] ** 2))), n

print(f"\ndefender samples (half-court, usable chances, 5 per second): {len(R):,}")
print("where a defender stands = a·his man + b·the ball + c·the hoop      (NBA, Franks et al. 2015: 0.62 / 0.11 / 0.27)")
for name, mask in (("all defenders", np.ones(len(R), bool)), ("guarding the ball", on), ("off the ball", ~on)):
    a, b, c, rmse, n = fit(mask)
    print(f"  {name:<18} man {a:.2f} · ball {b:.2f} · hoop {c:.2f} · typical miss {rmse:.1f} ft · n={n:,}")
per = [fit((game == gid) & ~on)[:3] for gid in np.unique(game)]
print("  off the ball, game by game: man", " ".join(f"{p[0]:.2f}" for p in per), "| hoop", " ".join(f"{p[2]:.2f}" for p in per))

# (2) at the release: how far is the shooter's assigned defender from where the model says he would normally be?
a, b, c, *_ = fit(on)
S = np.array([(r[0], r[2], r[3], *r[4:]) for r in shot_rows], float); lvl = np.array([r[1] for r in shot_rows])
Os, Bs, Ds = S[:, 3:5] - H, S[:, 5:7] - H, S[:, 7:9] - H
expected = a * Os + b * Bs
gap = np.hypot(*(Ds - Os).T)                       # assigned defender to shooter
late = np.hypot(*(Ds - expected).T)                # assigned defender to his normal spot
print(f"\nshots with an assigned defender in the tracking: {len(S)} of 1459")
print("assigned defender = SkillCorner's closest defender distance?  median |difference|", round(float(np.nanmedian(np.abs(gap - S[:, 9]))), 2), "ft · same within 1 ft:", f"{np.nanmean(np.abs(gap - S[:, 9]) < 1) * 100:.0f}%")
for L in ("open", "light", "average", "plus", "blocked"):
    m = lvl == L
    print(f"  contest {L:<8} n={m.sum():4d} · assigned defender {np.median(gap[m]):4.1f} ft from the shooter · {np.median(late[m]):4.1f} ft from his normal spot · SkillCorner quality {np.mean(S[m, 0]):.0f}")
from numpy import corrcoef
ok = ~np.isnan(S[:, 0])
def spearman(x, y):
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y)); return corrcoef(rx, ry)[0, 1]
for three in (0, 1):
    m = S[:, 1] == three
    print(f"  {'threes' if three else 'twos  '}: rank correlation of shot quality with defender-to-shooter distance {spearman(gap[m], S[m, 0]):+.2f} · with distance from his normal spot {spearman(late[m], S[m, 0]):+.2f}")
