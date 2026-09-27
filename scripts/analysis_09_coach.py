"""Analysis 9 — four questions a coaching staff would ask, answered with the ten games.

    uv run scripts/analysis_09_coach.py            # the four league tables
    uv run scripts/analysis_09_coach.py 191313     # ... and the breakdown log of that game, one line per shot conceded

1. Rotations: how often does a shooter catch the ball with NOBODY assigned to him, and what does it cost?
2. Help: do defences sag off the right men? (how far defenders drift from bad, average and good three-point shooters)
3. Ball screens: what does each coverage cost once the whole possession is counted, not just the next shot?
4. Close-outs: what the possession produces after one, by what the attacker does (shoots, drives, passes) — "close-out efficiency".
5. The rim: field goals at the rim with a defender within 4 ft, made and conceded.
6. The log: every shot conceded traced back to the action it came from and the defenders involved, plus the team's close-outs, rim and glass.

Intervals resample whole games. Read-only.
"""

from __future__ import annotations

import sys
from collections import defaultdict

import numpy as np

from courtlab import court, equilibrium
from courtlab import glass as glass_
from courtlab import rotations
from courtlab.data import Game, game_ids, season_shooting

FPS, STEP, MIN_ROW = 25, 10, 5
SEASON = season_shooting()
rng = np.random.default_rng(9)


def name(g: Game, pid: int | None) -> str:
    p = g.players.get(pid)
    return p["lastName"] if p else "?"


def three_pct(pid: int, min_att: int = 40) -> float | None:
    r = SEASON.get(pid)
    return r["three_made"] / r["three_att"] if r and r["three_att"] >= min_att else None


def ci(values: np.ndarray, games: np.ndarray, stat=np.mean) -> tuple[float, float]:
    ids = np.unique(games)
    boot = [stat(np.concatenate([values[games == k] for k in rng.choice(ids, len(ids))])) for _ in range(600)]
    return tuple(np.percentile(boot, [2.5, 97.5]))


shots, sags, picks, log, cos, rim, glass, ledger = [], [], [], defaultdict(list), [], [], [], []
GAMES = {gid: Game.load(gid) for gid in game_ids()}
QUALITY = rotations.QualityFit([s for g in GAMES.values() for s in g.events["shots"] if g.chances.get(s["chanceId"], {}).get("usable")])
for gid, g in GAMES.items():
    ev = g.events
    touches = {t["id"]: t for t in ev["touches"]}
    rows = defaultdict(list)  # attacker -> [(start, end, defender)], resets of under 0.2 s dropped
    for m in ev["matchups"]:
        if m["endFrame"] - m["startFrame"] >= MIN_ROW:
            rows[m["offPlayerId"]].append((m["startFrame"], m["endFrame"], m["defPlayerId"]))
    own = lambda who, fr: next((d for a, b, d in sorted(rows[who], reverse=True) if a <= fr <= b), None)  # noqa: E731
    actions = []  # (frame, kind, how it was defended, on-ball defender, other defender, attackers involved)
    for p in ev["picks"]:
        actions.append((p["frame"], "ball screen", f"{p['bhrDefType']}/{p['scrDefType']}", p["ballhandlerDefId"], p["screenerDefId"], (p["ballhandlerId"], p["screenerId"]), p["chanceId"]))
    for d in ev["drives"]:
        actions.append((d["startFrame"], "drive", "beaten" if d["blowby"] else "contained", d["ballhandlerDefId"], None, (d["ballhandlerId"],), d["chanceId"]))
    for t, kind in (("posts", "post-up"), ("isolations", "isolation")):
        for d in ev[t]:
            actions.append((d["startFrame"], kind, "", d["ballhandlerDefId"], None, (d["ballhandlerId"],), d["chanceId"]))
    for h in ev["handoffs"]:
        actions.append((h["frame"], "hand-off", h["receiverDefType"] or "", h["receiverDefId"], h["setterDefId"], (h["receiverId"], h["setterId"]), h["chanceId"]))
    for s in ev["off_ball_screens"]:
        actions.append((s["frame"], "off-ball screen", s["cutterDefType"] or "", s["cutterDefId"], s["screenerDefId"], (s["cutterId"], s["screenerId"]), s["chanceId"]))
    actions.sort(key=lambda a: a[0])
    closeouts = {c["touchId"]: c for c in ev["closeouts"]}

    # ---- which frames are needed
    jobs = []
    for s in ev["shots"]:
        t, c = touches.get(s["touchId"]), g.chances.get(s["chanceId"])
        if not t or not c or not c["usable"] or s["shotQuality"] is None or s["fouled"]:
            continue
        feed = [p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["receiverId"] == s["shooterId"]
                and p["startFrame"] <= t["startFrame"] and t["startFrame"] - p["startFrame"] <= 3 * FPS]
        if feed:
            jobs.append((s, c, max(feed, key=lambda p: p["startFrame"])))
    halfcourt = [c for c in ev["chances"] if c["usable"] and not c["transition"] and c["frontcourtFrame"] is not None]
    sample = {f for c in halfcourt for f in range(c["frontcourtFrame"] + FPS, c["endFrame"] - FPS, STEP)}
    last_pick = {}
    for p in ev["picks"]:
        c = g.chances.get(p["chanceId"])
        if c and c["usable"] and not c["transition"]:
            last_pick[p["chanceId"]] = max(last_pick.get(p["chanceId"], p), p, key=lambda q: q["frame"])
    need_onset = set()
    for s_, c_, p_ in jobs:
        if closeouts.get(s_["touchId"]):
            need_onset |= set(range(p_["startFrame"] - 5, p_["startFrame"] + 46))
    frames = g.frames_at(sample | {j[2]["startFrame"] for j in jobs} | {j[0]["startFrame"] for j in jobs} | {p["frame"] + 30 for p in last_pick.values()} | need_onset)

    def where(f: dict, sg: int) -> tuple[dict, np.ndarray]:
        return {q["playerId"]: np.array(q["xyz"][:2]) * sg for q in f["homePlayers"] + f["awayPlayers"]}, np.array(f["ball"]["xyz"][:2]) * sg

    # ---- 1 and 4: the shooter when the pass leaves
    fed = {}
    for s, c, p in jobs:
        f = frames.get(p["startFrame"])
        if not f:
            continue
        pos, ball = where(f, g.sign(c))
        o = pos.get(s["shooterId"])
        if o is None:
            continue
        d_id = own(s["shooterId"], p["startFrame"])
        defenders = [pos[q] for q in c["defPlayerIds"] if q in pos]
        nearest = min((float(np.hypot(*(o - q))) for q in defenders), default=np.nan)
        extra = None
        if d_id is not None and d_id in pos:
            extra = float(equilibrium.extra(o[None], ball[None], pos[d_id][None])[1][0])
        pps = (3 if s["three"] else 2) * s["shotQuality"] / 100
        alone = np.nan  # seconds he had been nobody's man when the pass left
        if d_id is None:
            ends = [b for a, b, _ in rows[s["shooterId"]] if c["startFrame"] <= b < p["startFrame"]]
            alone = (p["startFrame"] - max(ends)) / FPS if ends else (p["startFrame"] - c["startFrame"]) / FPS
        rec = {"game": gid, "three": bool(s["three"]), "pps": pps, "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "nobody": d_id is None,
               "extra": extra, "nearest": nearest, "open": s["contestLevel"] in ("open", "light"), "alone": alone,
               "age": (p["startFrame"] - c["startFrame"]) / FPS, "pct": three_pct(s["shooterId"]) or np.nan}
        shots.append(rec)
        fed[s["chanceId"]] = rec

        # the log: where it came from
        before = [a for a in actions if a[6] == s["chanceId"] and a[0] <= p["startFrame"] and a[1] != "off-ball screen"] or [a for a in actions if a[6] == s["chanceId"] and a[0] <= p["startFrame"]]
        origin = before[-1] if before else None
        n_pass = sum(1 for q in ev["passes"] if q["chanceId"] == s["chanceId"] and q["complete"] and origin and origin[0] < q["startFrame"] <= p["startFrame"])
        left = None  # the last defender assigned to the shooter, when he let go and whom he took instead
        if d_id is None:
            prev = [r for r in rows[s["shooterId"]] if r[1] < p["startFrame"] and r[1] >= c["startFrame"]]
            if prev:
                a, b, who = max(prev, key=lambda r: r[1])
                took = next((o2 for o2 in c["offPlayerIds"] if o2 != s["shooterId"] and any(x <= b + FPS and y > b and d == who for x, y, d in rows[o2])), None)
                left = (who, (s["startFrame"] - b) / FPS, took)
        co = closeouts.get(s["touchId"])

        # the ledger: one counterfactual per conceded shot, moving only the defender's distance at the release
        cf = None
        fr = frames.get(s["startFrame"])
        if s["closestDefDist"] is not None and not s["fouled"] and not s["blocked"] and fr:
            posr, ballr = where(fr, g.sign(c))
            o_r = posr.get(s["shooterId"])
            if co and co["startDistance"] and co["startDistance"] >= 10 and co["ballhandlerDefId"] in posr:  # late start of the close-out
                D = [next((q["xyz"][:2] for q in frames[k]["homePlayers"] + frames[k]["awayPlayers"] if q["playerId"] == co["ballhandlerDefId"]), None) if k in frames else None for k in range(p["startFrame"] - 5, p["startFrame"] + 46)]
                R = [next((q["xyz"][:2] for q in frames[k]["homePlayers"] + frames[k]["awayPlayers"] if q["playerId"] == s["shooterId"]), None) if k in frames else None for k in range(p["startFrame"] - 5, p["startFrame"] + 46)]
                if all(D) and all(R):
                    gap = np.hypot(*(np.array(D) - np.array(R)).T)
                    closing = -np.convolve(np.diff(gap) * FPS, np.ones(5) / 5, "same")
                    on = next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > 5).all()), None)
                    if on is not None:
                        onset = (on - 5) / FPS
                        d_cf = rotations.on_time_distance(s, onset)
                        cf = {"kind": "late close-out", "who": co["ballhandlerDefId"], "onset": onset, "d_now": s["closestDefDist"], "d_cf": d_cf, "price": QUALITY.price(s, d_cf)}
            if cf is None and o_r is not None and (d_id is None and (alone >= 1) or (extra is not None and extra >= 6)):  # a man left alone, or help never recovered
                d_cf = rotations.normal_spot_distance(o_r, ballr, equilibrium.WEIGHTS, court.HOOP)
                kind = "nobody on him" if d_id is None else "help not recovered"
                who_ = None
                if d_id is None and left:
                    holder_def = own(p["passerId"], p["startFrame"])
                    who_ = rotations.who_should_rotate(o, {q: pos[q] for q in c["defPlayerIds"] if q in pos}, {left[0]}, holder_def)
                cf = {"kind": kind, "who": d_id if d_id is not None else (who_[0] if who_ else None), "onset": None, "d_now": s["closestDefDist"], "d_cf": d_cf, "price": QUALITY.price(s, d_cf), "rotator": who_}
        if cf:
            ledger.append({"game": gid, "def_team": s["defTeamId"], **cf})
        log[gid].append({"rec": rec, "shot": s, "chance": c, "origin": origin, "passes": n_pass, "own": d_id, "left": left, "closeout": co, "cf": cf,
                         "secs": (s["startFrame"] - origin[0]) / FPS if origin else None})

    # ---- 2: how far defenders drift from spot-up shooters, by how well those shoot
    holder = {}
    for t in ev["touches"]:
        for f in range(t["startFrame"] - t["startFrame"] % STEP, t["endFrame"] + 1, STEP):
            holder[f] = t["playerId"]
    for c in halfcourt:
        sg = g.sign(c)
        for fr in range(c["frontcourtFrame"] + FPS, c["endFrame"] - FPS, STEP):
            f = frames.get(fr)
            if not f:
                continue
            pos, ball = where(f, sg)
            for o_id in c["offPlayerIds"]:
                pct, d_id = three_pct(o_id), own(o_id, fr)
                if pct is None or d_id is None or o_id not in pos or d_id not in pos or holder.get(fr - fr % STEP) == o_id:
                    continue
                o = pos[o_id]
                if np.hypot(o[0] - court.HOOP_X, o[1]) < court.THREE_RADIUS or o[0] > 0:  # spot-up men only: beyond the arc, in the front court
                    continue
                gap, extra = equilibrium.extra(o[None], ball[None], pos[d_id][None])
                sags.append((gid, pct, float(extra[0]), float(gap[0]), float(np.hypot(*(o - ball)))))

    # ---- 3: the last ball screen of each possession, by how it was defended
    for cid, p in last_pick.items():
        c, f = g.chances[cid], frames.get(p["frame"] + 30)
        bent = np.nan
        if f:
            pos, ball = where(f, g.sign(c))
            ex = [equilibrium.extra(pos[o][None], ball[None], pos[own(o, p["frame"] + 30)][None])[1][0] for o in c["offPlayerIds"]
                  if o != p["ballhandlerId"] and o in pos and own(o, p["frame"] + 30) in pos]
            bent = float(max(ex)) if ex else np.nan
        sh = fed.get(cid)
        picks.append({"game": gid, "cov": f"{p['bhrDefType']}/{p['scrDefType']}", "clock": p["shotClock"] if p["shotClock"] is not None else np.nan, "pts": c["ptsScored"] or 0, "bent": bent, "turnover": c["outcome"] == "TO" or "TO" in str(c["outcome"]),
                      "fed": sh is not None, "pps": sh["pps"] if sh else np.nan, "broken": bool(sh and (sh["nobody"] or (sh["extra"] or 0) >= 6))})

    # ---- 4: close-outs and what followed
    shot_by_touch = {s["touchId"]: s for s in ev["shots"]}
    for co in ev["closeouts"]:
        c = g.chances.get(co["chanceId"])
        if not c or not c["usable"] or not co["startDistance"] or not co["bhrAction"]:
            continue
        sh = shot_by_touch.get(co["touchId"])
        cos.append({"game": gid, "def_team": co["defTeamId"], "defender": co["ballhandlerDefId"], "action": co["bhrAction"], "start": co["startDistance"], "end": co["endDistance"] or np.nan,
                    "pts": c["ptsScored"] or 0, "pps": (3 if sh["three"] else 2) * sh["shotQuality"] / 100 if sh and sh["shotQuality"] is not None else np.nan,
                    "turnover": any(o in ("TO",) for o in (co["bhrOutcomes"] or []))})
    # ---- 5: the rim
    for s in ev["shots"]:
        c = g.chances.get(s["chanceId"])
        if not c or not c["usable"] or s["region"] != "ra" or s["fouled"]:
            continue
        rim.append({"game": gid, "def_team": s["defTeamId"], "off_team": s["offTeamId"], "made": bool(s["outcome"]), "contested": s["closestDefDist"] is not None and s["closestDefDist"] <= 4,
                    "blocked": bool(s["blocked"]), "level": s["contestLevel"]})
    # ---- 6: the glass (courtlab.glass: a team-mate gains 2 ft towards the hoop and ends within 14)
    cp = defaultdict(list)
    for r in ev["chance_players"]:
        cp[r["chanceId"]].append(r)
    rebs = {r["shotId"]: r for r in ev["rebounds"] if r["fgReb"] and r["rebounded"]}
    for s in ev["shots"]:
        c, rb = g.chances.get(s["chanceId"]), rebs.get(s["id"])
        if not c or not c["usable"] or s["fouled"] or s["blocked"] or s["outcome"] or not rb:
            continue
        f = glass_.flight(cp[s["chanceId"]], s["shooterId"])
        if not f:
            continue
        glass.append({"game": gid, "def_team": s["defTeamId"], "off_team": s["offTeamId"], "crash": f["crash"], "oreb": not rb["defensive"]})

# ================================================================== 1
S = {k: np.array([r[k] for r in shots], dtype=float if k not in ("nobody", "three", "open") else bool) for k in ("game", "three", "pps", "pts", "nobody", "nearest", "open", "alone", "age", "pct")}
ex = np.array([np.nan if r["extra"] is None else r["extra"] for r in shots])
print(f"1 · ROTATIONS — shots within 3 s of a catch: {len(shots)}")
print(f"{'when the pass left, the shooter…':<42}{'n':>5}{'share':>7}{'threes':>8}{'nearest defender':>18}{'open shot':>11}{'expected pts':>22}{'actual':>8}")
for label, m in (("had his defender in place (< 3 ft out)", ~S["nobody"] & (ex < 3)), ("had his defender 3–6 ft out of place", ~S["nobody"] & (ex >= 3) & (ex < 6)),
                 ("had his defender 6 ft or more out", ~S["nobody"] & (ex >= 6)), ("had NOBODY assigned to him", S["nobody"]),
                 ("   … for under a second", S["nobody"] & (S["alone"] < 1)), ("   … for one second or more", S["nobody"] & (S["alone"] >= 1)),
                 ("   … in a possession under 3 s old", S["nobody"] & (S["age"] < 3))):
    a, b = ci(S["pps"][m], S["game"][m])
    print(f"{label:<42}{m.sum():>5}{m.mean() * 100:6.0f}%{S['three'][m].mean() * 100:7.0f}%{np.nanmedian(S['nearest'][m]):15.1f} ft{S['open'][m].mean() * 100:10.0f}%{S['pps'][m].mean():10.2f} [{a:.2f}, {b:.2f}]{S['pts'][m].mean():8.2f}")
per_game = [S["nobody"][S["game"] == k].sum() for k in np.unique(S["game"])]
print(f"   shots conceded to a man nobody owned, per game (both teams): median {np.median(per_game):.0f}, range {min(per_game)}–{max(per_game)}")

# ================================================================== 2
G = np.array(sags)
lo, hi = np.percentile(G[:, 1], [33.3, 66.7])
print(f"\n2 · HELP — off-ball attackers standing beyond the arc, sampled every {STEP / FPS:.1f} s: {len(G)} (shooters with 40+ threes attempted this season)")
print(f"{'season three-point accuracy':<34}{'n':>7}{'his defender beyond normal':>30}{'6 ft or more out':>18}{'feet away':>11}")
for label, m in ((f"bottom third (under {lo * 100:.0f} %)", G[:, 1] < lo), (f"middle third", (G[:, 1] >= lo) & (G[:, 1] < hi)), (f"top third ({hi * 100:.0f} % or better)", G[:, 1] >= hi)):
    a, b = ci(G[m, 2], G[m, 0])
    print(f"{label:<34}{m.sum():>7}{G[m, 2].mean():+14.2f} ft [{a:+.2f}, {b:+.2f}]{np.mean(G[m, 2] >= 6) * 100:16.1f}%{np.median(G[m, 3]):9.1f} ft")
slope = np.polyfit(G[:, 1] * 100, G[:, 2], 1)[0]
a, b = ci(np.arange(len(G)), G[:, 0], stat=lambda i: np.polyfit(G[i.astype(int), 1] * 100, G[i.astype(int), 2], 1)[0])
print(f"   per +10 points of accuracy his defender stands {slope * 10:+.2f} ft [{a * 10:+.2f}, {b * 10:+.2f}] relative to normal")
print("   and what the three is worth when the rotation is broken (defender 3 ft or more out, or nobody on him):")
broken3 = S["three"] & (S["nobody"] | (ex >= 3)) & ~np.isnan(S["pct"])
for label, m in (("bottom third", S["pct"] < lo), ("middle third", (S["pct"] >= lo) & (S["pct"] < hi)), ("top third", S["pct"] >= hi)):
    m = m & broken3
    a, b = ci(S["pts"][m], S["game"][m])
    print(f"     {label:<14} n={m.sum():3d} · SkillCorner's quality says {S['pps'][m].mean():.2f} points · they scored {S['pts'][m].mean():.2f} [{a:.2f}, {b:.2f}]")

# ================================================================== 3
P = {k: np.array([r[k] for r in picks]) for k in picks[0]}
print(f"\n3 · BALL SCREENS — the last one of each half-court possession: {len(picks)}")
print(f"{'handler’s man / screener’s man':<32}{'n':>5}{'most stretched team-mate, +1.2 s':>34}{'points per possession':>30}{'turnover':>10}{'shot off a broken rotation':>28}{'shot clock':>12}")
for cov in ("over/show", "over/soft", "under/soft", "under/show", "switch/switch"):
    m = P["cov"] == cov
    a, b = ci(P["pts"][m].astype(float), P["game"][m])
    print(f"{cov:<32}{m.sum():>5}{np.nanmean(P['bent'][m]):+27.1f} ft{'':4}{P['pts'][m].mean():16.2f} [{a:.2f}, {b:.2f}]{P['turnover'][m].mean() * 100:9.0f}%{P['broken'][m].mean() * 100:26.0f}%{np.nanmean(P['clock'][m]):10.1f} s")
early = P["clock"] >= 10
print("   with 10 s or more on the shot clock, so the clock does not explain it:")
for cov in ("over/show", "over/soft", "switch/switch"):
    m = (P["cov"] == cov) & early
    a, b = ci(P["pts"][m].astype(float), P["game"][m])
    print(f"     {cov:<16} n={m.sum():3d} · {P['pts'][m].mean():.2f} points per possession [{a:.2f}, {b:.2f}]")

# ================================================================== 4
C = {k: np.array([r[k] for r in cos]) for k in cos[0]}
print(f"\n4 · CLOSE-OUTS — {len(cos)} labelled by SkillCorner, by what the attacker did once the defender arrived")
print(f"{'the attacker…':<16}{'n':>5}{'share':>7}{'defender starts':>16}{'arrives at':>11}{'possession points':>28}{'turnover':>10}{'shot expected':>15}")
for act, label in (("shot", "shoots"), ("drive", "drives"), ("pass", "passes"), ("other", "other")):
    m = C["action"] == act
    a, b = ci(C["pts"][m].astype(float), C["game"][m])
    xp = C["pps"][m][~np.isnan(C["pps"][m])]  # no shot on that touch when he passes: nothing to expect
    print(f"{label:<16}{m.sum():>5}{m.mean() * 100:6.0f}%{np.median(C['start'][m]):13.0f} ft{np.nanmedian(C['end'][m]):8.1f} ft{C['pts'][m].mean():14.2f} [{a:.2f}, {b:.2f}]{C['turnover'][m].mean() * 100:9.0f}%{(f'{xp.mean():.2f}' if len(xp) else '–'):>15}")
a, b = ci(C["pts"].astype(float), C["game"])
print(f"   all close-outs: the possession produced {C['pts'].mean():.2f} points [{a:.2f}, {b:.2f}]; a set possession in these games produced {np.mean([r['pts'] for r in picks]):.2f} after its last ball screen, for scale")

# ================================================================== 5
Rm = {k: np.array([r[k] for r in rim]) for k in rim[0]}
print(f"\n5 · THE RIM — {len(rim)} field goals from the restricted area (no foul)")
for label, m in (("defender within 4 ft", Rm["contested"]), ("nobody within 4 ft", ~Rm["contested"])):
    a, b = ci(Rm["made"][m].astype(float), Rm["game"][m])
    print(f"   {label:<22} n={m.sum():3d} ({m.mean() * 100:2.0f} %) · made {Rm['made'][m].mean() * 100:3.0f} % [{a * 100:.0f}, {b * 100:.0f}] · blocked {Rm['blocked'][m].mean() * 100:.0f} %")
print("   by SkillCorner's own contest level: " + " · ".join(f"{lv}: {Rm['made'][Rm['level'] == lv].mean() * 100:.0f} % (n={(Rm['level'] == lv).sum()})" for lv in ("open", "light", "average", "plus")))

# ================================================================== the ledger
L = {k: np.array([r[k] for r in ledger]) for k in ("game", "def_team", "kind", "price")}
n_teamgames = 2 * len(GAMES)
print(f"\nTHE LEDGER — {len(ledger)} conceded shots with a counterfactual (the defender's distance at the release is the only thing moved)")
print(f"   quality fit per zone (logit of SkillCorner's quality per foot of defender distance, the shot's own covariates held): " + " · ".join(f"{z} {QUALITY.beta[z][1]:+.3f}/ft (n={QUALITY.n[z]})" for z in ("rim", "mid", "three")))
print(f"{'what went wrong':<22}{'n':>5}{'per team-game':>15}{'price per shot':>16}{'points per team-game':>22}")
for kind in ("late close-out", "nobody on him", "help not recovered"):
    m = L["kind"] == kind
    a, b = ci(L["price"][m].astype(float), L["game"][m])
    print(f"{kind:<22}{m.sum():>5}{m.sum() / n_teamgames:15.1f}{L['price'][m].mean():10.2f} [{a:.2f}, {b:.2f}]{L['price'][m].sum() / n_teamgames:22.2f}")
print(f"   all three: {L['price'].sum() / n_teamgames:.2f} points per team and game. Read it as an upper bound: the counterfactual defender arrives and nothing else changes.")

# ================================================================== 6
if len(sys.argv) > 1:
    gid = int(sys.argv[1])
    g = Game.load(gid)
    print(f"\n6 · THE LOG — {g.meta['homeTeam']['teamName']} v {g.meta['awayTeam']['teamName']}")
    for team in (g.meta["homeTeam"], g.meta["awayTeam"]):
        tid = team["teamId"]
        mc = (C["game"] == gid) & (C["def_team"] == tid)
        mr = (Rm["game"] == gid) & (Rm["def_team"] == tid)
        mg = np.array([r["game"] == gid and r["def_team"] == tid for r in glass]); mo = np.array([r["game"] == gid and r["off_team"] == tid for r in glass])
        gl = [r for r in glass if r["game"] == gid]
        print(f"\n  {team['teamName']} defending — the numbers a staff reads first")
        print(f"    close-outs: {mc.sum()} · the attacker shot {np.mean(C['action'][mc] == 'shot') * 100:.0f} %, drove {np.mean(C['action'][mc] == 'drive') * 100:.0f} %, passed {np.mean(C['action'][mc] == 'pass') * 100:.0f} % · "
              f"{C['pts'][mc].mean():.2f} points per possession after one (league {C['pts'].mean():.2f})")
        by_def = defaultdict(list)
        for r in cos:
            if r["game"] == gid and r["def_team"] == tid:
                by_def[r["defender"]].append(r["pts"])
        print("      by defender: " + " · ".join(f"{name(g, d)} {len(v)} ({np.mean(v):.1f} pts each)" for d, v in sorted(by_def.items(), key=lambda kv: -len(kv[1]))[:5]) + "  (counts, no intervals)")
        print(f"    the rim: {mr.sum()} attempts conceded · with a defender within 4 ft {Rm['contested'][mr].mean() * 100:.0f} % of them, made {Rm['made'][mr & Rm['contested']].mean() * 100:.0f} % (league {Rm['made'][Rm['contested']].mean() * 100:.0f} %) · "
              f"nobody within 4 ft: made {Rm['made'][mr & ~Rm['contested']].mean() * 100:.0f} %")
        gd = [r for r in gl if r["def_team"] == tid]; go = [r for r in gl if r["off_team"] == tid]
        print(f"    the glass: opponent misses {len(gd)}, they sent 2+ to crash on {sum(r['crash'] >= 2 for r in gd)} and took {sum(r['oreb'] for r in gd)} offensive rebounds · "
              f"own misses {len(go)}, sent 2+ on {sum(r['crash'] >= 2 for r in go)}, took {sum(r['oreb'] for r in go)} back (league: 2+ on {np.mean([r['crash'] >= 2 for r in glass]) * 100:.0f} % of misses)")
        total = [e for e in log[gid] if e["shot"]["defTeamId"] == team["teamId"] and not e["chance"]["transition"] and e["rec"]["age"] >= 3]  # set defence only
        mine = [e for e in total if (e["rec"]["nobody"] and e["rec"]["alone"] >= 1) or (e["rec"]["extra"] or 0) >= 6]
        lt = (L["game"] == gid) & (L["def_team"] == tid)
        print("    the ledger: " + " · ".join(f"{k} {L['price'][lt & (L['kind'] == k)].sum():+.1f} pts ({int((lt & (L['kind'] == k)).sum())})" for k in ("late close-out", "nobody on him", "help not recovered")) + f" · total {L['price'][lt].sum():+.1f} points")
        print(f"    set defence: {len(mine)} of {len(total)} shots off a catch came off a broken rotation "
              f"({sum(e['rec']['pts'] for e in mine)} points conceded, {sum(e['rec']['pps'] for e in mine):.1f} expected)")
        for e in sorted(mine, key=lambda e: -e["rec"]["pps"])[:8]:
            s, o = e["shot"], e["origin"]
            clock = f"Q{s['period']} {int(s['startGameClock'] // 60)}:{int(s['startGameClock'] % 60):02d}"
            pct = three_pct(s["shooterId"], 20)
            who = f"{name(g, s['shooterId'])} {'three' if s['three'] else 'two'} ({'made' if s['outcome'] else 'missed'}), quality {s['shotQuality']:.0f}" + (f", a {pct * 100:.0f} % shooter" if pct and s["three"] else "")
            if o:
                come = (f"{o[1]} by {' / '.join(name(g, x) for x in o[5])}, {e['secs']:.1f} s and {e['passes']} pass{'es' if e['passes'] != 1 else ''} earlier; "
                        f"defended{' ' + o[2] if o[2] else ''} by {name(g, o[3])}{' and ' + name(g, o[4]) if o[4] else ''}")
            else:
                come = "no labelled action before it"
            if e["left"]:
                d, secs, took = e["left"]
                rot = f"{name(g, d)} let go of him {secs:.1f} s before the shot{' to take ' + name(g, took) if took else ''}; nobody picked him up"
            elif e["own"] is None:
                rot = f"nobody was assigned to him (nearest defender {e['rec']['nearest']:.0f} ft away)"
            else:
                rot = f"his man {name(g, e['own'])} was {e['rec']['extra']:.0f} ft beyond his spot when the pass left"
            co = e["closeout"]
            run = f"; {name(g, co['ballhandlerDefId'])} closed out from {co['startDistance']:.0f} ft and arrived at {co['endDistance']:.0f}" if co and co["startDistance"] else ""
            cf = e["cf"]
            if cf and cf["kind"] == "late close-out":
                bill = (f"price: {cf['price']:+.2f} pts · {name(g, cf['who'])} started {cf['onset']:.2f} s after the pass; with the pass he is at {cf['d_cf']:.1f} ft instead of {cf['d_now']:.1f} at the release"
                        if cf["onset"] > 0.04 else f"price: 0 · {name(g, cf['who'])} started with the pass; the distance was the rotation's, not his")
            elif cf:
                r_ = cf.get("rotator")
                bill = f"price: {cf['price']:+.2f} pts · a defender at the normal spot would be at {cf['d_cf']:.1f} ft instead of {cf['d_now']:.1f}"
                if r_:
                    bill += f"; the free man was {name(g, r_[0])}, {r_[1]:.0f} ft away ({r_[2]:.1f} s at close-out speed)"
            else:
                bill = "price: –"
            print(f"   {clock} · {who}\n        from: {come}\n        rotation: {rot}{run}\n        {bill}")
