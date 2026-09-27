"""Analysis 11 — what video cannot show: bodies and time. Six ideas tested, the ones that died included.

    uv run scripts/analysis_11_invisible.py

P1 drives: what separates the ones that beat the defender (speed? braking? turning? reaction? room?)
P2 ball screens as collisions (speed lost by the defender, moving screeners)            -> dropped
P3 the second and a half with the ball in the air: who crashes, who stands still, what it costs
P4 pass and move (descriptive)
P5 tired legs: close-out speed and reaction delay against quarter and minutes played      -> dropped
P6 when the rotation starts: how long after the pass leaves the closing defender starts running
Read-only, about 12 s. Intervals resample whole games; the last block moves every threshold of ours.
"""
import collections, gzip, json, re
import numpy as np
from courtlab import court
from courtlab.data import Game, game_ids, data_dir

FPS = 25
FRAME = re.compile(r'"frameIdx":\s*(\d+)')
rng = np.random.default_rng(11)
K5 = np.ones(5) / 5


def load_positions(g):
    """pid -> (frames x 4: x, y, speed, detected) for every live frame of usable chances, plus the frame offset."""
    spans = [(c["startFrame"] - 30, c["endFrame"] + 75) for c in g.events["chances"] if c["usable"]]
    lo, hi = min(a for a, _ in spans), max(b for _, b in spans)
    keep = np.zeros(hi - lo + 1, bool)
    for a, b in spans:
        keep[max(a, lo) - lo:b - lo + 1] = True
    P = collections.defaultdict(lambda: np.full((hi - lo + 1, 4), np.nan))
    with gzip.open(data_dir() / "matches" / str(g.id) / f"{g.id}_tracking_data.jsonl.gz", "rt") as fh:
        for line in fh:
            i = int(FRAME.search(line).group(1))
            if i > hi:
                break
            if i < lo or not keep[i - lo] or '"homePlayers": []' in line:
                continue
            f = json.loads(line)
            for q in f["homePlayers"] + f["awayPlayers"]:
                P[q["playerId"]][i - lo] = (q["xyz"][0], q["xyz"][1], q["speed"], q["isDetected"])
    return P, lo


def vel(xy):
    sm = np.c_[np.convolve(xy[:, 0], K5, "valid"), np.convolve(xy[:, 1], K5, "valid")]
    return np.diff(sm, axis=0) * FPS  # ft/s, vector, centred ~2.5 frames in


def auc(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[~np.isnan(a)], b[~np.isnan(b)]
    return float(np.mean([(x > b).mean() + 0.5 * (x == b).mean() for x in a]))


def ci_med(v, games):
    v, games = np.asarray(v, float), np.asarray(games)
    ids = np.unique(games)
    bt = [np.nanmedian(np.concatenate([v[games == k] for k in rng.choice(ids, len(ids))])) for _ in range(400)]
    return np.percentile(bt, [2.5, 97.5])


def ci_diff(v, games, m1, m2, stat=np.nanmean):
    v, games = np.asarray(v, float), np.asarray(games); ids = np.unique(games); out = []
    for _ in range(800):
        pick = rng.choice(ids, len(ids))
        a = np.concatenate([v[(games == k) & m1] for k in pick]); b = np.concatenate([v[(games == k) & m2] for k in pick])
        if len(a) and len(b):
            out.append(stat(a) - stat(b))
    return np.percentile(out, [2.5, 97.5])


drives, screens, air, reloc, tired, react_co = [], [], [], [], [], []
for gid in game_ids():
    g = Game.load(gid); ev = g.events
    P, lo = load_positions(g)
    chances = g.chances
    minutes = {(r["chanceId"], r["playerId"]): r["minutesPlayedBefore"] for r in ev["chance_players"]}

    def seg(pid, a, b):
        if pid not in P or a - lo < 0 or b - lo >= len(P[pid]):
            return None
        s = P[pid][a - lo:b - lo + 1]
        return None if np.isnan(s[:, 0]).any() or s[:, 3].mean() < 0.9 else s

    # ---- P1 drives: what separates the ones that beat the defender
    for d in ev["drives"]:
        if not d["ballhandlerDefId"] or d["endFrame"] - d["startFrame"] < 15:
            continue
        A, D = seg(d["ballhandlerId"], d["startFrame"] - 12, d["endFrame"]), seg(d["ballhandlerDefId"], d["startFrame"] - 12, d["endFrame"])
        if A is None or D is None:
            continue
        va, vd = vel(A[:, :2]), vel(D[:, :2])
        sa = np.hypot(*va.T)
        acc = np.diff(sa) * FPS
        acc5 = np.convolve(acc, K5, "valid")
        head = np.arctan2(va[:, 1], va[:, 0])
        turn = [abs(np.degrees(np.angle(np.exp(1j * (head[k + 10] - head[k]))))) for k in range(len(head) - 10) if sa[k] > 5 and sa[k + 10] > 5]
        aa, ad = np.diff(sa), np.diff(np.hypot(*vd.T))
        best = max(range(0, 16), key=lambda L: np.corrcoef(aa[:len(aa) - L], ad[L:])[0, 1] if len(aa) - L > 8 else -9)
        gap0 = float(np.hypot(*(A[12, :2] - D[12, :2])))
        drives.append({"game": gid, "beat": bool(d["blowby"]), "top": sa.max(), "burst": acc5.max(), "brake": -acc5.min(), "turn": max(turn) if turn else np.nan,
                       "delay": best / FPS, "gap0": gap0, "gap_early": float(np.hypot(*(A[0, :2] - D[0, :2]))), "start_speed": sa[:8].mean(), "period": d["period"], "cat": d["category"],
                       "mins": minutes.get((d["chanceId"], d["ballhandlerDefId"]), np.nan)})

    # ---- P2 screens as collisions
    for p in ev["picks"]:
        c = chances.get(p["chanceId"])
        if not c or not c["usable"] or not p["ballhandlerDefId"]:
            continue
        D, H, Sx = seg(p["ballhandlerDefId"], p["frame"] - 15, p["frame"] + 50), seg(p["ballhandlerId"], p["frame"] - 15, p["frame"] + 50), seg(p["screenerId"], p["frame"] - 5, p["frame"] + 5)
        if D is None or H is None or Sx is None:
            continue
        sd = np.hypot(*vel(D[:, :2]).T)
        before, low = sd[3:13].mean(), sd[13:28].min()
        gap = np.hypot(*(D[:, :2] - H[:, :2]).T)
        back = next((k for k in range(15, len(gap)) if gap[k] <= 4.0), None)
        screens.append({"game": gid, "cov": p["bhrDefType"], "lost": before - low, "before": before, "screener_speed": float(np.hypot(*vel(Sx[:, :2]).T).mean()),
                        "gap_peak": gap[15:45].max(), "back": (back - 15) / FPS if back is not None else np.nan})

    # ---- P3 the second and a half with the ball in the air (SkillCorner gives each player's spot at the shot and when the ball reaches the rim)
    cp = collections.defaultdict(list)
    for r in ev["chance_players"]:
        cp[r["chanceId"]].append(r)
    rebs = {r["shotId"]: r for r in ev["rebounds"] if r["fgReb"]}
    for s in ev["shots"]:  # EVERY field goal attempt: the decision to crash is taken before the ball reaches the rim, so made shots count too
        c = chances.get(s["chanceId"])
        if not c or not c["usable"] or s["fouled"] or s["blocked"]:
            continue
        okk, att, dfn = True, [], []
        for r in cp[s["chanceId"]]:
            if not r["shotLoc"] or not r["rimLoc"]:
                okk = False; break
            if r["playerId"] == s["shooterId"]:
                continue
            d0 = np.hypot(r["shotLoc"][0] - court.HOOP_X, r["shotLoc"][1]); d1 = np.hypot(r["rimLoc"][0] - court.HOOP_X, r["rimLoc"][1])
            moved = np.hypot(r["rimLoc"][0] - r["shotLoc"][0], r["rimLoc"][1] - r["shotLoc"][1])
            (att if r["offense"] else dfn).append({"id": r["playerId"], "d0": float(d0), "d1": float(d1), "gain": float(d0 - d1), "moved": float(moved)})
        if not okk or len(att) != 4 or len(dfn) != 5:
            continue
        rb = rebs.get(s["id"])
        nxt = chances.get(rb["nextChanceId"]) if rb and rb["nextChanceId"] else None
        zone = "rim" if s["region"] in ("ra", "key") else "three" if s["three"] else "midrange"
        air.append({"game": gid, "made": bool(s["outcome"]), "three": bool(s["three"]), "zone": zone, "att": att, "def": dfn,
                    "rebounded": bool(rb and rb["rebounded"]), "oreb": bool(rb and rb["rebounded"] and not rb["defensive"]), "rebounder": rb["rebounderId"] if rb else None,
                    "next_trans": bool(nxt["transition"]) if nxt and rb and rb["defensive"] else np.nan, "next_pts": (nxt["ptsScored"] or 0) if nxt and rb and rb["defensive"] else np.nan,
                    "second_pts": (nxt["ptsScored"] or 0) if nxt and rb and not rb["defensive"] else np.nan})

    # ---- P4 pass and move: what the passer does in the two seconds after the ball leaves (set offence)
    for p in ev["passes"]:
        c = chances.get(p["chanceId"])
        if not c or not c["usable"] or c["transition"] or not p["complete"] or p["inbounds"] or p["backcourt"]:
            continue
        A = seg(p["passerId"], p["startFrame"], p["startFrame"] + 50)
        if A is None:
            continue
        reloc.append({"game": gid, "moved": float(np.hypot(*(A[-1, :2] - A[0, :2]))), "top": float(np.hypot(*vel(A[:, :2]).T).max()), "pts": c["ptsScored"] or 0, "id": p["chanceId"], "passer": p["passerId"]})

    # ---- P5 tired legs: close-out top speed against the minutes the defender has played
    for co in ev["closeouts"]:
        if not co["startFrame"] or not co["endFrame"] or co["endFrame"] - co["startFrame"] < 8 or not co["startDistance"]:
            continue
        D = seg(co["ballhandlerDefId"], co["startFrame"], co["endFrame"])
        if D is None:
            continue
        tired.append({"game": gid, "peak": float(np.percentile(np.hypot(*vel(D[:, :2]).T), 95)), "start": co["startDistance"], "period": co["period"],
                      "mins": minutes.get((co["chanceId"], co["ballhandlerDefId"]), np.nan)})

    # ---- P6 how long after the pass leaves does the man who will close out start running at the shooter
    touches = {t["id"]: t for t in ev["touches"]}
    for co in ev["closeouts"]:
        t = touches.get(co["touchId"])
        if not t or not co["startDistance"] or co["startDistance"] < 10:
            continue
        feed = [p for p in ev["passes"] if p["chanceId"] == co["chanceId"] and p["complete"] and p["receiverId"] == co["ballhandlerId"] and 0 <= t["startFrame"] - p["startFrame"] <= 40]
        if not feed:
            continue
        p = max(feed, key=lambda q: q["startFrame"])
        D, R = seg(co["ballhandlerDefId"], p["startFrame"] - 5, p["startFrame"] + 45), seg(co["ballhandlerId"], p["startFrame"] - 5, p["startFrame"] + 45)
        if D is None or R is None:
            continue
        gap = np.hypot(*(D[:, :2] - R[:, :2]).T)
        closing = -np.convolve(np.diff(gap) * FPS, K5, "same")  # ft/s towards the receiver
        on = next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > 5).all()), None)
        onsets = {thr: next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > thr).all()), None) for thr in (4, 6)}
        if on is not None:
            shot = next((s for s in ev["shots"] if s["touchId"] == co["touchId"] and s["shotQuality"] is not None), None)
            react_co.append({"game": gid, "react": (on - 5) / FPS, "start": co["startDistance"], "end": co["endDistance"], "flight": (p["endFrame"] - p["startFrame"]) / FPS if p["endFrame"] else np.nan,
                             "on4": (onsets[4] - 5) / FPS if onsets[4] is not None else np.nan, "on6": (onsets[6] - 5) / FPS if onsets[6] is not None else np.nan,
                             "pps": (3 if shot["three"] else 2) * shot["shotQuality"] / 100 if shot else np.nan, "def_at_release": shot["closestDefDist"] if shot else np.nan})

col = lambda rows, k: np.array([r[k] for r in rows], float)  # noqa: E731


print(f"P1 · DRIVES — {len(drives)} with both men on camera ({int(col(drives, 'beat').sum())} beat the defender). AUC = chance that a drive which beat him has the larger value (0.50 = no information)")
b = col(drives, "beat") == 1
for k, label in (("top", "top speed, ft/s"), ("burst", "hardest acceleration, ft/s²"), ("brake", "hardest braking, ft/s²"), ("turn", "sharpest change of direction in 0.4 s, °"),
                 ("start_speed", "speed when the drive starts, ft/s"), ("gap0", "room at the start, ft"), ("delay", "defender's reaction delay, s")):
    v = col(drives, k)
    print(f"   {label:<44} beat {np.nanmedian(v[b]):6.2f} · contained {np.nanmedian(v[~b]):6.2f} · AUC {auc(v[b], v[~b]):.2f}")

print(f"\nP2 · SCREENS — {len(screens)} ball screens with handler, his defender and the screener on camera")
cov = np.array([s["cov"] for s in screens])
for k in ("over", "under", "switch"):
    m = cov == k
    a_, b_ = ci_med(col(screens, "lost")[m], col(screens, "game")[m])
    print(f"   {k:<7} n={m.sum():3d} · handler's defender loses {np.nanmedian(col(screens, 'lost')[m]):.1f} ft/s [{a_:.1f}, {b_:.1f}] of {np.nanmedian(col(screens, 'before')[m]):.1f} · room peaks at {np.nanmedian(col(screens, 'gap_peak')[m]):.1f} ft · back within 4 ft after {np.nanmedian(col(screens, 'back')[m]):.2f} s ({np.isnan(col(screens, 'back')[m]).mean() * 100:.0f} % never in 2 s)")
ss = col(screens, "screener_speed")
print(f"   the screener at the moment of the screen: median {np.median(ss):.1f} ft/s · still (< 1.5 ft/s) {np.mean(ss < 1.5) * 100:.0f} % · clearly moving (> 4 ft/s) {np.mean(ss > 4) * 100:.0f} %")
for label, m in (("screener still (< 1.5 ft/s)", ss < 1.5), ("screener moving (> 4 ft/s)", ss > 4)):
    print(f"      {label:<30} n={m.sum():3d} · defender loses {np.nanmedian(col(screens, 'lost')[m]):.1f} ft/s · room peaks at {np.nanmedian(col(screens, 'gap_peak')[m]):.1f} ft")

CRASH = (2.0, 14.0)  # a team-mate crashes when he gains this many feet towards the hoop and ends within this many: the definition that best predicts who takes the rebound (table below)
crashers = lambda a, gain=CRASH[0], within=CRASH[1]: sum(1 for q in a["att"] if q["gain"] >= gain and q["d1"] <= within)  # noqa: E731
cr = np.array([crashers(a) for a in air]); made = col(air, "made") == 1; orb = col(air, "oreb") == 1; rebd = col(air, "rebounded") == 1
zone = np.array([a["zone"] for a in air])
print(f"\nP3 · BALL IN THE AIR — {len(air)} field goal attempts with all ten players' spots at the shot and when the ball reaches the rim (fouled and blocked shots left out)")
print("   the decision: how many team-mates crash, by where the shot came from and whether it went in (they decide before they know)")
print(f"   {'':<10}{'shots':>7}{'made':>6}   {'team-mates crashing, mean':>26}   {'2+ crash':>9}   {'0 crash':>8}")
for z in ("rim", "midrange", "three"):
    for mk, label in ((False, "missed"), (True, "made")):
        m = (zone == z) & (made == mk)
        print(f"   {z:<10}{m.sum():>7}{label:>6}   {cr[m].mean():>26.2f}   {np.mean(cr[m] >= 2) * 100:8.0f}%   {np.mean(cr[m] == 0) * 100:7.0f}%")
for z in ("rim", "midrange", "three"):
    m = zone == z
    lo_, hi_ = ci_diff(cr.astype(float), col(air, "game"), m & ~made, m & made)
    print(f"   {z:<10} crashers on misses − on makes: {cr[m & ~made].mean() - cr[m & made].mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
print("   (if they waited to read the flight, misses would draw more crashers in every zone; the differences are small and change sign by zone, so crashing is decided with the shot)")

R = rebd & ~made  # the value: only a miss has a rebound
print(f"\n   the value, on the {R.sum()} rebounded misses: offensive rebound overall {orb[R].mean() * 100:.0f} %")
print(f"   {'crashing':<10}{'n':>5}{'offensive rebound':>19}{'second-chance pts':>19}{'if the defence rebounds: fast break':>37}{'next possession':>17}{'net per miss':>14}")
for k in range(4):
    m = R & (cr == k if k < 3 else cr >= 3)
    d = m & ~orb
    sc = np.nanmean(col(air, "second_pts")[m & orb]) if (m & orb).sum() else np.nan
    nx = np.nanmean(col(air, "next_pts")[d])
    print(f"   {k if k < 3 else '3+':<10}{m.sum():>5}{orb[m].mean() * 100:18.0f}%{sc:19.2f}{np.nanmean(col(air, 'next_trans')[d]) * 100:36.0f}%{nx:17.2f}{orb[m].mean() * sc - (1 - orb[m].mean()) * nx:+14.2f}")

print("\n   validation against the data itself (SkillCorner's rebounderId), in place of the film UF used:")
print(f"   {'definition (gain / ends within)':<34}{'crashers':>9}{'rebound if crashed':>20}{'if not':>8}{'lift':>6}{'AUC':>6}{'OREB 2+ − 0/1':>22}")
for gain, within in ((2, 14), (3, 12), (3, 14), (3, 16), (4, 14), (5, 14), (3, 10), (6, 12)):
    yes = no = yes_reb = no_reb = 0
    score, label = [], []
    for a in air:
        if not (a["rebounded"] and not a["made"]):
            continue
        for q in a["att"]:
            c_ = q["gain"] >= gain and q["d1"] <= within
            got = q["id"] == a["rebounder"]
            yes += c_; no += not c_; yes_reb += c_ and got; no_reb += (not c_) and got
            score.append(1.0 if c_ else 0.0); label.append(got)
    py, pn = yes_reb / max(yes, 1), no_reb / max(no, 1)
    n2 = np.array([crashers(a, gain, within) for a in air])
    lo_, hi_ = ci_diff(orb.astype(float), col(air, "game"), R & (n2 >= 2), R & (n2 <= 1))
    print(f"   {f'{gain} ft / {within} ft':<34}{yes / (yes + no) * 100:8.0f}%{py * 100:19.0f}%{pn * 100:7.0f}%{py / max(pn, 1e-9):6.1f}{auc(np.array(score)[np.array(label)], np.array(score)[~np.array(label)]):6.2f}"
          f"{orb[R & (n2 >= 2)].mean() - orb[R & (n2 <= 1)].mean():+12.2f} [{lo_:+.2f}, {hi_:+.2f}]")

print("\n   the defence while it flies: 'standing still' is two different things, boxing out under the rim or watching from far")
near = lambda a, thr=2.0: sum(1 for q in a["def"] if q["moved"] < thr and q["d0"] <= 10)  # noqa: E731
far = lambda a, thr=2.0: sum(1 for q in a["def"] if q["moved"] < thr and q["d0"] > 10)  # noqa: E731
sn, sf = np.array([near(a) for a in air]), np.array([far(a) for a in air])
got_near = got_far = got_mov = n_near = n_far = n_mov = 0
for a in air:
    if not (a["rebounded"] and not a["made"]):
        continue
    for q in a["def"]:
        kind = "near" if q["moved"] < 2 and q["d0"] <= 10 else "far" if q["moved"] < 2 else "mov"
        got = q["id"] == a["rebounder"]
        if kind == "near": n_near += 1; got_near += got
        elif kind == "far": n_far += 1; got_far += got
        else: n_mov += 1; got_mov += got
print(f"   a defender who does not move 2 ft: under the rim (≤ 10 ft) he takes the rebound {got_near / n_near * 100:.0f} % of the time (n={n_near}); far from it {got_far / n_far * 100:.0f} % (n={n_far}); a defender who moves {got_mov / n_mov * 100:.0f} % (n={n_mov})")
for label, arr in (("still FAR from the rim", sf), ("still UNDER the rim", sn)):
    for lo_k, hi_k, tag in ((0, 1, "0–1"), (2, 2, "2"), (3, 5, "3+")):
        m = R & (arr >= lo_k) & (arr <= hi_k)
        print(f"      {label:<24} {tag:<4} n={m.sum():3d} · offensive rebound conceded {orb[m].mean() * 100:3.0f} %")
lo_, hi_ = ci_diff(orb.astype(float), col(air, "game"), R & (sf >= 2), R & (sf <= 1))
print(f"   offensive rebound conceded, 2+ watching from far − 0/1: {orb[R & (sf >= 2)].mean() - orb[R & (sf <= 1)].mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
lo_, hi_ = ci_diff(orb.astype(float), col(air, "game"), R & (sn >= 2), R & (sn <= 1))
print(f"   offensive rebound conceded, 2+ still under the rim − 0/1: {orb[R & (sn >= 2)].mean() - orb[R & (sn <= 1)].mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
sa = sn + sf
lo_, hi_ = ci_diff(orb.astype(float), col(air, "game"), R & (sa >= 3), R & (sa <= 1))
print(f"   the earlier headline, 3+ defenders still anywhere − 0/1, on this sample: {orb[R & (sa >= 3)].mean() - orb[R & (sa <= 1)].mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]  (n={int((R & (sa >= 3)).sum())})")

print(f"\nP4 · PASS AND MOVE — {len(reloc)} passes in set offence")
mv = col(reloc, "moved")
print(f"   two seconds after passing the passer is {np.median(mv):.1f} ft from where he passed (middle half {np.percentile(mv, 25):.1f}–{np.percentile(mv, 75):.1f}) · stood still (< 3 ft) {np.mean(mv < 3) * 100:.0f} % · really moved (> 10 ft) {np.mean(mv > 10) * 100:.0f} %")

print(f"\nP5 · TIRED LEGS — {len(tired)} close-outs from 10+ ft" )
pk, mn, st, per = col(tired, "peak"), col(tired, "mins"), col(tired, "start"), col(tired, "period")
far = st >= 10
for q in (1, 2, 3, 4):
    m = far & (per == q)
    a_, b_ = ci_med(pk[m], col(tired, "game")[m])
    print(f"   quarter {q}: n={m.sum():3d} · top speed {np.median(pk[m]):.1f} ft/s [{a_:.1f}, {b_:.1f}]")
ok = far & ~np.isnan(mn)
print(f"   minutes already played by the defender (n={ok.sum()}): " + " · ".join(f"{a}–{b_} min: {np.median(pk[ok & (mn >= a) & (mn < b_)]):.1f} ft/s (n={(ok & (mn >= a) & (mn < b_)).sum()})" for a, b_ in ((0, 8), (8, 16), (16, 24), (24, 45))))
dm, dd = col(drives, "mins"), col(drives, "delay")
print(f"   defender's reaction delay on drives by minutes played: " + " · ".join(f"{a}–{b_}: {np.nanmedian(dd[(dm >= a) & (dm < b_)]):.2f} s (n={((dm >= a) & (dm < b_)).sum()})" for a, b_ in ((0, 8), (8, 16), (16, 24), (24, 45))))

print(f"\nP6 · WHEN THE ROTATION STARTS — {len(react_co)} close-outs from 10+ ft fed by a pass")
rc = col(react_co, "react")
print(f"   the defender starts running at the receiver {np.median(rc):+.2f} s after the pass leaves (middle half {np.percentile(rc, 25):+.2f} to {np.percentile(rc, 75):+.2f}); the pass is in the air {np.nanmedian(col(react_co, 'flight')):.2f} s")
for lo_, hi_, label in ((-1, 0.12, "already running when the pass leaves"), (0.12, 0.4, "0.1–0.4 s after"), (0.4, 9, "later than 0.4 s")):
    m = (rc >= lo_) & (rc < hi_)
    print(f"   {label:<38} n={m.sum():3d} · starts {np.median(col(react_co, 'start')[m]):.0f} ft away · at release {np.nanmedian(col(react_co, 'def_at_release')[m]):.1f} ft · expected {np.nanmean(col(react_co, 'pps')[m]):.2f}")




print("\nINTERVALS (whole games resampled)")
g_ = col(drives, "game")
for k, label in (("gap0", "room at the start: beat − contained"), ("start_speed", "speed at the start: beat − contained"), ("top", "top speed: beat − contained")):
    lo_, hi_ = ci_diff(col(drives, k), g_, b, ~b, np.nanmedian)
    print(f"   drives · {label:<40} {np.nanmedian(col(drives, k)[b]) - np.nanmedian(col(drives, k)[~b]):+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
ga = col(air, "game")
lo_, hi_ = ci_diff(orb.astype(float), ga, R & (cr >= 2), R & (cr <= 1))
print(f"   air · offensive rebound, 2+ crash − 0/1 crash: {orb[R & (cr >= 2)].mean() - orb[R & (cr <= 1)].mean():+.2f} [{lo_:+.2f}, {hi_:+.2f}]  (n={int((R & (cr >= 2)).sum())} vs {int((R & (cr <= 1)).sum())})")
nxt = col(air, "next_pts"); dreb = R & ~orb
lo_, hi_ = ci_diff(nxt, ga, dreb & (cr >= 2), dreb & (cr <= 1))
print(f"   air · points conceded on the next possession, 2+ crash − 0/1 crash: {np.nanmean(nxt[dreb & (cr >= 2)]) - np.nanmean(nxt[dreb & (cr <= 1)]):+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
gr = col(react_co, "game"); pps = col(react_co, "pps")
lo_, hi_ = ci_diff(pps, gr, rc >= 0.4, rc < 0.4)
print(f"   rotation · expected points, start later than 0.4 s − earlier: {np.nanmean(pps[rc >= 0.4]) - np.nanmean(pps[rc < 0.4]):+.2f} [{lo_:+.2f}, {hi_:+.2f}]")
for thr in (0.2, 0.3, 0.5):
    print(f"        threshold {thr:.1f} s: {np.nanmean(pps[rc >= thr]) - np.nanmean(pps[rc < thr]):+.2f} (n late = {(rc >= thr).sum()})")
three = col(air, "three") == 1
for label, m in (("after a missed three", R & three), ("after a missed two", R & ~three)):
    print(f"   air · {label}: offensive rebound with 2+ crashing {orb[m & (cr >= 2)].mean() * 100:.0f} % (n={int((m & (cr >= 2)).sum())}) · with 0/1 {orb[m & (cr <= 1)].mean() * 100:.0f} % (n={int((m & (cr <= 1)).sum())})")


print("\nMOVING OUR THRESHOLDS")
cats = np.array([d["cat"] for d in drives])
print("   drives, inside each kind (the kind alone changes how often the defender is beaten):")
for k in ("pick", "closeout", "iso", "handoff", "miscellaneous"):
    m = cats == k
    if (m & b).sum() >= 10:
        print(f"      {k:<14} n={m.sum():3d} · beaten {b[m].mean() * 100:3.0f} % · room at the start: beat {np.nanmedian(col(drives, 'gap0')[m & b]):.1f} / contained {np.nanmedian(col(drives, 'gap0')[m & ~b]):.1f} ft"
              f" · speed at the start: {np.nanmedian(col(drives, 'start_speed')[m & b]):.1f} / {np.nanmedian(col(drives, 'start_speed')[m & ~b]):.1f} ft/s")
lo_, hi_ = ci_diff(col(drives, "gap_early"), g_, b, ~b, np.nanmedian)
print(f"      room measured half a second BEFORE the labelled start: beat − contained {np.nanmedian(col(drives, 'gap_early')[b]) - np.nanmedian(col(drives, 'gap_early')[~b]):+.2f} ft [{lo_:+.2f}, {hi_:+.2f}]")
print("   rotation start, other definitions of 'running at him' (closing speed held for 0.12 s):")
for key, label in (("on4", "4 ft/s"), ("react", "5 ft/s"), ("on6", "6 ft/s")):
    r_ = col(react_co, key); okr = ~np.isnan(r_)
    lo_, hi_ = ci_diff(pps, gr, okr & (r_ >= 0.4), okr & (r_ < 0.4))
    print(f"      {label}: starts {np.nanmedian(r_):+.2f} s after the pass · late (0.4 s+) − early: {np.nanmean(pps[okr & (r_ >= 0.4)]) - np.nanmean(pps[okr & (r_ < 0.4)]):+.2f} expected points [{lo_:+.2f}, {hi_:+.2f}]")
