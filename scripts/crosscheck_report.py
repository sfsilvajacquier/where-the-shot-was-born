"""Cross-check of the research report against the data (read-only).
(1) Franks' exact filter: only frames with all ten players in the offensive half. Do our weights move towards his 0.62/0.11/0.27?
(2) Does SkillCorner's shotQuality know who is shooting? Test with the shooter's season three-point accuracy (aggregates, 293 games).
    Intervals by resampling whole games (cluster bootstrap), as the report recommends."""
import collections, csv, gzip, json, re
from pathlib import Path
import numpy as np

DATA = Path("../opendata-basketball/data")
FRAME = re.compile(r'"frameIdx":\s*(\d+)')
STEP, H = 5, np.array([-40.75, 0.0])
rows = []; threes = []
alias = {int(r["player_id"]): int(r["canonical_player_id"]) for r in csv.DictReader(open(DATA / "player_id_aliases.csv"))}
season = collections.defaultdict(lambda: [0, 0])
for r in csv.DictReader(open(DATA / "aggregates" / "acb_shotsaggregates_20252026.csv")):
    if r["team_name"] == "total": continue  # per-team rows already add up to the player's season
    pid = alias.get(int(r["player_id"]), int(r["player_id"]))
    season[pid][0] += float(r["three_mades"] or 0); season[pid][1] += float(r["three_attempts"] or 0)
league = sum(v[0] for v in season.values()) / sum(v[1] for v in season.values())

for g in json.load(open(DATA / "matches.json")):
    gid = g["id"]; folder = DATA / "matches" / str(gid)
    ev = json.load(open(folder / f"{gid}_dynamic_events.json"))
    chances = {c["id"]: c for c in ev["chances"]}
    shots_at = {s["startFrame"]: s for s in ev["shots"]}
    pairs = collections.defaultdict(list)
    for m in ev["matchups"]:
        c = chances.get(m["chanceId"])
        if not c or not c["usable"] or c["frontcourtFrame"] is None: continue
        a = max(m["startFrame"], c["frontcourtFrame"])
        for f in range(a - a % STEP + STEP, m["endFrame"] + 1, STEP):
            pairs[f].append((m["defPlayerId"], m["offPlayerId"], c["period"], c["offTeamId"]))
    need = set(pairs) | set(shots_at); frames = {}
    with gzip.open(folder / f"{gid}_tracking_data.jsonl.gz", "rt") as fh:
        for line in fh:
            if '"homePlayers": []' in line: continue
            i = int(FRAME.search(line).group(1))
            if i in need:
                f = json.loads(line)
                if f["ball"]: frames[i] = ({p["playerId"]: p["xyz"][:2] for p in f["homePlayers"] + f["awayPlayers"]}, f["ball"]["xyz"][:2])
    votes = collections.defaultdict(list)
    for fr, s in shots_at.items():
        if fr in frames and s.get("location") and s["shooterId"] in frames[fr][0]:
            votes[(s["period"], s["offTeamId"])].append(1 if abs(frames[fr][0][s["shooterId"]][0] - s["location"][0]) < 0.5 else -1)
    sign = {k: int(np.sign(np.sum(v))) for k, v in votes.items()}
    for fr, plist in pairs.items():
        if fr not in frames: continue
        pos, ball = frames[fr]
        for d_id, o_id, per, team in plist:
            sg = sign.get((per, team))
            if sg is None or d_id not in pos or o_id not in pos: continue
            all_in_half = all(p[0] * sg < 0 for p in pos.values())
            rows.append((gid, all_in_half, *(np.array(pos[o_id]) * sg), *(np.array(ball) * sg), *(np.array(pos[d_id]) * sg)))
    for s in ev["shots"]:
        if s["three"] and s.get("shotQuality") is not None and not s["fouled"]:
            pid = alias.get(s["shooterId"], s["shooterId"]); m, a = season.get(pid, (0, 0))
            if a >= 50: threes.append((gid, s["shotQuality"] / 100, bool(s["outcome"]), m / a, a))

R = np.array(rows, float); game = R[:, 0]; half = R[:, 1].astype(bool)
O, B, D = R[:, 2:4] - H, R[:, 4:6] - H, R[:, 6:8] - H
def fit(mask):
    X = np.c_[np.r_[O[mask, 0], O[mask, 1]], np.r_[B[mask, 0], B[mask, 1]]]; y = np.r_[D[mask, 0], D[mask, 1]]
    g, *_ = np.linalg.lstsq(X, y, rcond=None); return g[0], g[1], 1 - g[0] - g[1]
print("(1) defender = a·man + b·ball + c·hoop            Franks et al., NBA 2013-14: 0.62 / 0.11 / 0.27 (±0.02 / 0.01 / 0.02)")
for name, mask in (("ball in the offensive half (what I used)", np.ones(len(R), bool)), ("all ten players in the offensive half (Franks' filter)", half)):
    a, b, c = fit(mask)
    games = np.unique(game); boot = []
    rng = np.random.default_rng(7)
    for _ in range(300):
        pick = rng.choice(games, len(games)); m = np.concatenate([np.flatnonzero((game == gg) & mask) for gg in pick])
        mm = np.zeros(len(R), bool); idx, cnt = np.unique(m, return_counts=True)
        X = np.c_[np.r_[np.repeat(O[idx, 0], cnt), np.repeat(O[idx, 1], cnt)], np.r_[np.repeat(B[idx, 0], cnt), np.repeat(B[idx, 1], cnt)]]
        y = np.r_[np.repeat(D[idx, 0], cnt), np.repeat(D[idx, 1], cnt)]
        gg_, *_ = np.linalg.lstsq(X, y, rcond=None); boot.append((gg_[0], gg_[1], 1 - gg_[0] - gg_[1]))
    lo, hi = np.percentile(boot, [2.5, 97.5], axis=0)
    print(f"  {name:<56} n={mask.sum():>7,}  man {a:.3f} [{lo[0]:.3f}-{hi[0]:.3f}] · ball {b:.3f} [{lo[1]:.3f}-{hi[1]:.3f}] · hoop {c:.3f} [{lo[2]:.3f}-{hi[2]:.3f}]")

T = np.array(threes, float); gT = T[:, 0]; sq, made, skill = T[:, 1], T[:, 2], T[:, 3]
print(f"\n(2) threes with a quality score, not fouled, shooter with 50+ season attempts: {len(T)} · league three-point accuracy {league * 100:.1f}% · made here {made.mean() * 100:.1f}% · mean quality {sq.mean() * 100:.1f}")
def logit(p): return np.log(p / (1 - p))
def irls(X, y):
    b = np.zeros(X.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ b)); W = p * (1 - p) + 1e-9
        b += np.linalg.solve(X.T @ (X * W[:, None]) + 1e-8 * np.eye(len(b)), X.T @ (y - p))
    return b
X = np.c_[np.ones(len(T)), logit(np.clip(sq, .02, .98)), (skill - league) * 10]  # skill in steps of 10 percentage points
b = irls(X, made); rng = np.random.default_rng(11); bs = []
for _ in range(1000):
    pick = rng.choice(np.unique(gT), len(np.unique(gT))); idx = np.concatenate([np.flatnonzero(gT == gg) for gg in pick])
    bs.append(irls(X[idx], made[idx]))
lo, hi = np.percentile(bs, [2.5, 97.5], axis=0)
print(f"  made ~ quality + shooter's season accuracy:  quality slope {b[1]:.2f} [{lo[1]:.2f}, {hi[1]:.2f}] · shooter, per +10 points of season accuracy: {b[2]:+.2f} [{lo[2]:+.2f}, {hi[2]:+.2f}] in log-odds")
print(f"  correlation between the quality score and the shooter's season accuracy: {np.corrcoef(sq, skill)[0, 1]:+.2f}")
for name, m in (("bottom third of shooters", skill <= np.quantile(skill, 1 / 3)), ("middle third", (skill > np.quantile(skill, 1 / 3)) & (skill <= np.quantile(skill, 2 / 3))), ("top third", skill > np.quantile(skill, 2 / 3))):
    print(f"  {name:<26} n={m.sum():3d} · season {skill[m].mean() * 100:4.1f}% · quality said {sq[m].mean() * 100:4.1f}% · made {made[m].mean() * 100:4.1f}%")
