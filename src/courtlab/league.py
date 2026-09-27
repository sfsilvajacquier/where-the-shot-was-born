"""The league figures the chapters and the match report quote. Computed from the games on this machine, never typed in.

    uv run courtlab league        # -> outputs/league.json

Every figure carries its label, unit, sample size and the script that first established it; intervals come from a game-cluster
bootstrap with a fixed seed (whole games resampled, 600 draws) and are only given when n >= 30. `courtlab export` copies the file
into every possession, so a viewer never reads a number that was not produced here. `courtlab report` reads the same rows for one
game (`Rows`), so a match report and the league it is compared with come from one collector.
"""

from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from courtlab import court, equilibrium, glass, rotations
from courtlab.data import LAB, Game, game_ids, season_shooting

SCHEMA = "courtlab.league/1"
FPS, MIN_ROW, SEED, DRAWS = 25, 5, 7, 600
LOOK_DEF_DEG = 120  # a defender's field of view with the head still: his man and the ball both in it up to this split (docs/the_look.md)
LOOK_ATT_DEG = 60   # half of it: a closer within this bearing of the ball's direction is in the shooter's view at the catch
SET_WINDOW = 6 * FPS  # frames after the ball crosses into the front court in which we look for all five defenders back
K5 = np.ones(5) / 5
OUT = LAB / "outputs" / "league.json"
COVERAGES = ("over/show", "over/soft", "under/soft", "under/show", "switch/switch")
BRANCHES = ("shot", "pass", "foul", "turnover")
KINDS = ("late close-out", "nobody on him", "help not recovered")
_BRANCH = {"PASS": "pass", "PASS_SCR": "pass", "AST": "pass", "AST0": "pass", "AST2": "pass", "AST3": "pass", "ASTF": "pass", "ASTO": "pass",
           "FGM": "shot", "FGX": "shot", "FGM3": "shot", "FGX3": "shot", "BLK": "shot", "TO": "turnover"}


# ---------------------------------------------------------------- statistics helpers
def ci(values, games, stat=np.mean, rng=None) -> list[float] | None:
    """Percentile interval of `stat` over whole games resampled; None when the sample is too small to deserve one."""
    values, games = np.asarray(values, float), np.asarray(games)
    if len(values) < 30:
        return None
    rng = rng or np.random.default_rng(SEED)
    ids = np.unique(games)
    draws = [stat(np.concatenate([values[games == k] for k in rng.choice(ids, len(ids))])) for _ in range(DRAWS)]
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


def ci_diff(values, games, a, b, rng=None) -> list[float] | None:
    """Interval for mean(values[a]) - mean(values[b]), whole games resampled."""
    values, games, a, b = np.asarray(values, float), np.asarray(games), np.asarray(a, bool), np.asarray(b, bool)
    if a.sum() < 30 or b.sum() < 30:
        return None
    rng = rng or np.random.default_rng(SEED)
    ids, out = np.unique(games), []
    for _ in range(DRAWS):
        pick = rng.choice(ids, len(ids))
        x = np.concatenate([values[(games == k) & a] for k in pick]); y = np.concatenate([values[(games == k) & b] for k in pick])
        if len(x) and len(y):
            out.append(x.mean() - y.mean())
    lo, hi = np.percentile(out, [2.5, 97.5])
    return [round(float(lo), 3), round(float(hi), 3)]


def figure(label, value, unit, n, source, cival=None, **extra) -> dict:
    d = {"label": label, "value": round(float(value), 3), "unit": unit, "n": int(n), "source": source}
    if cival is not None:
        d["ci"] = cival
    d.update(extra)
    return d


def branch(outcomes: list[str] | None) -> str | None:
    """What the ball handler did out of the screen, from SkillCorner's outcome codes: shot, pass, foul drawn, turnover."""
    for o in outcomes or []:
        if o in _BRANCH:
            return _BRANCH[o]
        if o.startswith("FOU"):
            return "foul"
    return None


def selection(rows: list[dict]) -> dict | None:
    """Shot selection against shot making over some field-goal attempts: what the quality expected, what was scored, the gap per 100."""
    if not rows:
        return None
    exp, act = sum(r["expected"] for r in rows), sum(r["actual"] for r in rows)
    return {"shots": len(rows), "expected": exp, "actual": act, "gap_per_100": (act - exp) / len(rows) * 100}


def priced(ledger: list[dict], fit: rotations.QualityFit) -> list[dict]:
    """The ledger with its prices: the same counterfactual distance, valued with a given quality fit (the league's, or the one frozen in league.json)."""
    for r in ledger:
        r["price"] = fit.price(r["shot"], r["d_cf"])
    return ledger


# ---------------------------------------------------------------- one pass over each game
class Rows:
    """Everything the figures need, collected game by game in one read of each tracking file. Every row carries its game and, where a side
    is involved, the defending team, so the same rows serve the league and one match's report."""

    def __init__(self, ids: list[int]):
        self.games = ids
        self.season = season_shooting()
        self.feeds, self.picks, self.chains, self.passes, self.closeouts, self.onsets, self.crash, self.transition, self.shot_sel = [], [], [], [], [], [], [], [], []
        self.cos, self.rim, self.fg, self.ledger, self.look_def, self.look_att = [], [], [], [], [], []
        self.loaded = []
        for gid in ids:
            g = Game.load(gid)
            self.loaded.append(g)
            self._game(g)

    def _game(self, g: Game) -> None:
        ev, gid = g.events, g.id
        touches = {t["id"]: t for t in ev["touches"]}
        shot_by_touch = {s["touchId"]: s for s in ev["shots"]}
        rows = defaultdict(list)
        for m in ev["matchups"]:
            if m["endFrame"] - m["startFrame"] >= MIN_ROW:
                rows[m["offPlayerId"]].append((m["startFrame"], m["endFrame"], m["defPlayerId"]))
        own = lambda who, fr: next((d for a, b, d in sorted(rows[who], reverse=True) if a <= fr <= b), None)  # noqa: E731
        usable = {c["id"]: c for c in ev["chances"] if c["usable"]}
        co_by_touch = {c["touchId"]: c for c in ev["closeouts"]}

        # what each figure needs: frames
        feeds = []
        for s in ev["shots"]:
            t, c = touches.get(s["touchId"]), usable.get(s["chanceId"])
            if not t or not c or s["shotQuality"] is None or s["fouled"]:
                continue
            feed = [p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["receiverId"] == s["shooterId"]
                    and 0 <= t["startFrame"] - p["startFrame"] <= 3 * FPS]
            if feed:
                feeds.append((s, c, max(feed, key=lambda p: p["startFrame"])))
        last_pick = {}
        for p in ev["picks"]:
            c = usable.get(p["chanceId"])
            if c and not c["transition"]:
                last_pick[p["chanceId"]] = max(last_pick.get(p["chanceId"], p), p, key=lambda q: q["frame"])
        acts = defaultdict(list)
        for table, key in (("picks", "frame"), ("handoffs", "frame"), ("off_ball_screens", "frame"), ("drives", "startFrame"), ("isolations", "startFrame"), ("posts", "startFrame")):
            for e in ev[table]:
                acts[e["chanceId"]].append(e[key])
        chains = []
        for s in ev["shots"]:
            c = usable.get(s["chanceId"])
            before = [f for f in acts.get(s["chanceId"], []) if f <= s["startFrame"]]
            if not c or s["shotQuality"] is None or s["fouled"] or not before:
                continue
            chain = sorted((p for p in ev["passes"] if p["chanceId"] == s["chanceId"] and p["complete"] and p["endFrame"] is not None
                            and max(before) < p["startFrame"] <= s["startFrame"]), key=lambda p: p["startFrame"])
            chains.append((s, chain))
        passes = [p for p in ev["passes"] if p["chanceId"] in usable and p["complete"] and p["endFrame"] and not p["inbounds"] and 2 <= p["endFrame"] - p["startFrame"] <= 60]
        cos = [c for c in ev["closeouts"] if c["chanceId"] in usable and c["startFrame"] and c["endFrame"] and c["endFrame"] - c["startFrame"] >= 8 and c["startDistance"]]
        onset_jobs = []
        for co in ev["closeouts"]:
            t = touches.get(co["touchId"])
            if not t or not co["startDistance"] or co["startDistance"] < 10:
                continue
            feed = [p for p in ev["passes"] if p["chanceId"] == co["chanceId"] and p["complete"] and p["receiverId"] == co["ballhandlerId"] and 0 <= t["startFrame"] - p["startFrame"] <= 40]
            if feed:
                onset_jobs.append((co, max(feed, key=lambda q: q["startFrame"])))
        trans = [c for c in usable.values() if c["transition"] and c["frontcourtFrame"] is not None]

        need = {p["startFrame"] for _, _, p in feeds} | {s["startFrame"] for s, _, _ in feeds} | {p["frame"] + 30 for p in last_pick.values()} | {p["startFrame"] for _, ch in chains for p in ch}
        need |= {p["endFrame"] for _, _, p in feeds if p["endFrame"]}
        look_jobs = []  # every close-out whose ball handler had just caught a pass: the look at the catch (docs/the_look.md)
        for co in ev["closeouts"]:
            t, c = touches.get(co["touchId"]), usable.get(co["chanceId"])
            if not t or not c or not co["bhrAction"] or not co["startDistance"]:
                continue
            feed = [p for p in ev["passes"] if p["chanceId"] == co["chanceId"] and p["complete"] and p["receiverId"] == co["ballhandlerId"] and p["endFrame"] and 0 <= t["startFrame"] - p["startFrame"] <= 40]
            if feed:
                look_jobs.append((co, c, max(feed, key=lambda q: q["startFrame"])))
        need |= {p["startFrame"] for _, _, p in look_jobs} | {p["endFrame"] for _, _, p in look_jobs}
        need |= {p["startFrame"] for p in passes} | {p["endFrame"] for p in passes}
        for c in trans:
            need |= set(range(c["frontcourtFrame"], min(c["endFrame"], c["frontcourtFrame"] + SET_WINDOW) + 1))
        for c in cos:
            need |= set(range(c["startFrame"], c["endFrame"] + 1))
        for co, p in onset_jobs:
            need |= set(range(p["startFrame"] - 5, p["startFrame"] + 46))
        for s, _, p in feeds:  # the ledger: when the close-out on the shooter started, relative to the pass that fed him
            co = co_by_touch.get(s["touchId"])
            if co and co["startDistance"] and co["startDistance"] >= 10:
                need |= set(range(p["startFrame"] - 5, p["startFrame"] + 46))
        frames = g.frames_at(need)

        def where(f, sg):
            return {q["playerId"]: np.array(q["xyz"][:2]) * sg for q in f["homePlayers"] + f["awayPlayers"]}, np.array(f["ball"]["xyz"][:2]) * sg

        def track(pid, a, b):
            """Positions of one player over [a, b], or None when a frame is missing or he was mostly off camera."""
            out = []
            for k in range(a, b + 1):
                f = frames.get(k)
                q = next((q for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == pid), None) if f else None
                if q is None:
                    return None
                out.append((*q["xyz"][:2], q["isDetected"]))
            o = np.array(out, float)
            return o if o[:, 2].mean() >= 0.9 else None

        def path(pid, a, b):
            """Raw positions of one player over [a, b] (on camera or not), or None when a frame is missing: what the ledger reads."""
            out = []
            for k in range(a, b + 1):
                f = frames.get(k)
                q = next((q["xyz"][:2] for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == pid), None) if f else None
                if q is None:
                    return None
                out.append(q)
            return np.array(out, float)

        # feeds: the shooter's defender when the pass left (unowned shooter, open three by shooter, the report's moments and ledger)
        for s, c, p in feeds:
            f = frames.get(p["startFrame"])
            if not f:
                continue
            pos, ball = where(f, g.sign(c))
            o = pos.get(s["shooterId"])
            if o is None:
                continue
            d_id = own(s["shooterId"], p["startFrame"])
            extra = float(equilibrium.extra(o[None], ball[None], pos[d_id][None])[1][0]) if d_id is not None and d_id in pos else None
            defenders = {q: pos[q] for q in c["defPlayerIds"] if q in pos}
            nearest = min((float(np.hypot(*(o - q))) for q in defenders.values()), default=None)
            alone, left = None, None
            if d_id is None:
                ends = [b for a, b, _ in rows[s["shooterId"]] if c["startFrame"] <= b < p["startFrame"]]
                alone = (p["startFrame"] - max(ends)) / FPS if ends else (p["startFrame"] - c["startFrame"]) / FPS
                prev = [r for r in rows[s["shooterId"]] if c["startFrame"] <= r[1] < p["startFrame"]]
                if prev:  # the last defender assigned to him: when he let go, and whom he took instead
                    a, b, who = max(prev, key=lambda r: r[1])
                    took = next((o2 for o2 in c["offPlayerIds"] if o2 != s["shooterId"] and any(x <= b + FPS and y > b and d == who for x, y, d in rows[o2])), None)
                    left = {"who": who, "secs_before_shot": (s["startFrame"] - b) / FPS, "took": took}
            rec = self.season.get(s["shooterId"])
            broken = (d_id is None and alone >= 1) or (extra is not None and extra >= 6)
            self.feeds.append({"game": gid, "three": bool(s["three"]), "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100,
                               "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "nobody": d_id is None, "extra": extra, "alone": alone,
                               "pct": rec["three_made"] / rec["three_att"] if rec and rec["three_att"] >= 40 else None,
                               "def_team": s["defTeamId"], "off_team": s["offTeamId"], "chance": s["chanceId"], "shot_id": s["id"], "shooter": s["shooterId"],
                               "own": d_id, "nearest": nearest, "left": left, "broken": broken, "set": not c["transition"] and (p["startFrame"] - c["startFrame"]) / FPS >= 3,
                               "made": bool(s["outcome"]), "quality": s["shotQuality"], "period": s["period"], "clock": s["startGameClock"]})

            # the look, defence: at the pass, the angle at the shooter's defender between his man and the ball (docs/the_look.md)
            if d_id is not None and d_id in pos:
                self.look_def.append({"game": gid, "def_team": s["defTeamId"], "off_team": s["offTeamId"], "chance": s["chanceId"], "shot_id": s["id"], "defender": d_id, "shooter": s["shooterId"],
                                      "angle": angle_between(o - pos[d_id], ball - pos[d_id]), "set": not c["transition"] and (p["startFrame"] - c["startFrame"]) / FPS >= 3,
                                      "d_release": s["closestDefDist"], "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100, "pts": (3 if s["three"] else 2) * bool(s["outcome"]), "made": bool(s["outcome"])})

            # the ledger: one counterfactual per conceded shot, moving only the defender's distance at the release (scripts/analysis_09_coach.py)
            fr, co = frames.get(s["startFrame"]), co_by_touch.get(s["touchId"])
            if s["closestDefDist"] is None or s["blocked"] or not fr:
                continue
            posr, ballr = where(fr, g.sign(c))
            o_r, cf = posr.get(s["shooterId"]), None
            if co and co["startDistance"] and co["startDistance"] >= 10 and co["ballhandlerDefId"] in posr:
                D, R = path(co["ballhandlerDefId"], p["startFrame"] - 5, p["startFrame"] + 45), path(s["shooterId"], p["startFrame"] - 5, p["startFrame"] + 45)
                if D is not None and R is not None:
                    gap = np.hypot(*(D - R).T)
                    closing = -np.convolve(np.diff(gap) * FPS, K5, "same")
                    on = next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > 5).all()), None)
                    if on is not None:
                        onset = (on - 5) / FPS
                        cf = {"kind": "late close-out", "who": co["ballhandlerDefId"], "onset": onset, "d_now": s["closestDefDist"], "d_cf": rotations.on_time_distance(s, onset), "rotator": None}
            if cf is None and o_r is not None and broken:
                d_cf = rotations.normal_spot_distance(o_r, ballr, equilibrium.WEIGHTS, court.HOOP)
                rotator = rotations.who_should_rotate(o, defenders, {left["who"]}, own(p["passerId"], p["startFrame"])) if d_id is None and left else None
                cf = {"kind": "nobody on him" if d_id is None else "help not recovered", "who": d_id if d_id is not None else (rotator[0] if rotator else None),
                      "onset": None, "d_now": s["closestDefDist"], "d_cf": d_cf, "rotator": rotator}
            if cf:
                self.ledger.append({"game": gid, "def_team": s["defTeamId"], "chance": s["chanceId"], "shot_id": s["id"], "shot": s, **cf})

        # the look, attack: at the catch, the closer's bearing from the direction the ball came from (docs/the_look.md)
        for co, c, p in look_jobs:
            f0, f1 = frames.get(p["startFrame"]), frames.get(p["endFrame"])
            if not f0 or not f1:
                continue
            pos0, _ = where(f0, g.sign(c))
            pos1, _ = where(f1, g.sign(c))
            me, origin, closer = pos1.get(co["ballhandlerId"]), pos0.get(p["passerId"]), pos1.get(co["ballhandlerDefId"])
            if me is None or origin is None or closer is None:
                continue
            sh = shot_by_touch.get(co["touchId"])
            self.look_att.append({"game": gid, "off_team": co["offTeamId"], "def_team": co["defTeamId"], "chance": co["chanceId"], "shooter": co["ballhandlerId"], "closer": co["ballhandlerDefId"],
                                  "bearing": angle_between(origin - me, closer - me), "action": co["bhrAction"], "start": co["startDistance"], "end": co["endDistance"],
                                  "release_s": sh["releaseTime"] if sh else None, "d_release": sh["closestDefDist"] if sh else None,
                                  "pps": (3 if sh["three"] else 2) * sh["shotQuality"] / 100 if sh and sh["shotQuality"] is not None else None, "made": bool(sh["outcome"]) if sh else None})

        # the last ball screen of each set possession
        for cid, p in last_pick.items():
            c, f = usable[cid], frames.get(p["frame"] + 30)
            bent = None
            if f:
                pos, ball = where(f, g.sign(c))
                ex = [equilibrium.extra(pos[o][None], ball[None], pos[own(o, p["frame"] + 30)][None])[1][0] for o in c["offPlayerIds"]
                      if o != p["ballhandlerId"] and o in pos and own(o, p["frame"] + 30) in pos]
                bent = float(max(ex)) if ex else None
            self.picks.append({"game": gid, "cov": f"{p['bhrDefType']}/{p['scrDefType']}", "pts": c["ptsScored"] or 0, "bent": bent,
                               "def_team": p["defTeamId"], "branch": branch(p["bhrOutcomes"]), "chance": cid})

        # passes after the last action
        for s, chain in chains:
            self.chains.append({"game": gid, "k": min(len(chain), 3), "pps": (3 if s["three"] else 2) * s["shotQuality"] / 100, "three": bool(s["three"])})

        # the race: pass speed from the players' positions, close-out top speed, onset of the close-out
        for p in passes:
            f0, f1 = frames.get(p["startFrame"]), frames.get(p["endFrame"])
            if not f0 or not f1:
                continue
            a = next((np.array(q["xyz"][:2]) for q in f0["homePlayers"] + f0["awayPlayers"] if q["playerId"] == p["passerId"]), None)
            b = next((np.array(q["xyz"][:2]) for q in f1["homePlayers"] + f1["awayPlayers"] if q["playerId"] == p["receiverId"]), None)
            if a is not None and b is not None:
                self.passes.append({"game": gid, "ft": float(np.hypot(*(b - a))), "secs": (p["endFrame"] - p["startFrame"]) / FPS})
        for c in cos:
            tr = track(c["ballhandlerDefId"], c["startFrame"], c["endFrame"])
            if tr is None or len(tr) < 8:
                continue
            sm = np.c_[np.convolve(tr[:, 0], K5, "valid"), np.convolve(tr[:, 1], K5, "valid")]
            v = np.hypot(*np.diff(sm, axis=0).T) * FPS
            self.closeouts.append({"game": gid, "peak": float(np.percentile(v, 95)), "start": c["startDistance"], "end": c["endDistance"]})
        for co, p in onset_jobs:
            D, R = track(co["ballhandlerDefId"], p["startFrame"] - 5, p["startFrame"] + 45), track(co["ballhandlerId"], p["startFrame"] - 5, p["startFrame"] + 45)
            if D is None or R is None:
                continue
            gap = np.hypot(*(D[:, :2] - R[:, :2]).T)
            closing = -np.convolve(np.diff(gap) * FPS, K5, "same")
            on = next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > 5).all()), None)
            if on is None:
                continue
            shot = next((s for s in ev["shots"] if s["touchId"] == co["touchId"] and s["shotQuality"] is not None), None)
            self.onsets.append({"game": gid, "onset": (on - 5) / FPS, "flight": (p["endFrame"] - p["startFrame"]) / FPS if p["endFrame"] else None,
                                "pps": (3 if shot["three"] else 2) * shot["shotQuality"] / 100 if shot else None})

        # close-outs and what followed: what the attacker did once the defender arrived, and what the possession produced
        for co in ev["closeouts"]:
            c = usable.get(co["chanceId"])
            if not c or not co["startDistance"] or not co["bhrAction"]:
                continue
            sh = shot_by_touch.get(co["touchId"])
            self.cos.append({"game": gid, "def_team": co["defTeamId"], "defender": co["ballhandlerDefId"], "action": co["bhrAction"], "start": co["startDistance"], "end": co["endDistance"],
                             "pts": c["ptsScored"] or 0, "pps": (3 if sh["three"] else 2) * sh["shotQuality"] / 100 if sh and sh["shotQuality"] is not None else None,
                             "turnover": "TO" in (co["bhrOutcomes"] or [])})

        # the rim: field goals from the restricted area, by whether a defender was within 4 ft
        for s in ev["shots"]:
            c = usable.get(s["chanceId"])
            if not c or s["region"] != "ra" or s["fouled"]:
                continue
            self.rim.append({"game": gid, "def_team": s["defTeamId"], "off_team": s["offTeamId"], "made": bool(s["outcome"]),
                             "contested": s["closestDefDist"] is not None and s["closestDefDist"] <= 4, "blocked": bool(s["blocked"]), "level": s["contestLevel"]})

        # the glass
        cp = defaultdict(list)
        for r in ev["chance_players"]:
            cp[r["chanceId"]].append(r)
        rebs = {r["shotId"]: r for r in ev["rebounds"] if r["fgReb"] and r["rebounded"]}
        for s in ev["shots"]:
            c, rb = usable.get(s["chanceId"]), rebs.get(s["id"])
            if not c or s["fouled"] or s["blocked"] or s["outcome"] or not rb:
                continue
            fl = glass.flight(cp[s["chanceId"]], s["shooterId"])
            if fl:
                self.crash.append({"game": gid, "crash": fl["crash"], "oreb": not rb["defensive"], "def_team": s["defTeamId"], "off_team": s["offTeamId"]})

        # transition: defenders back when the ball crossed into the front court
        for c in trans:
            f = frames.get(c["frontcourtFrame"])
            if not f:
                continue
            pos, ball = where(f, g.sign(c))
            dfn = [q for q in c["defPlayerIds"] if q in pos]
            if len(dfn) < 5:
                continue
            seen = np.mean([next(q["isDetected"] for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == d) for d in dfn])
            behind = lambda p_, b_: [d for d in dfn if p_[d][0] < b_[0]]  # noqa: E731  between the ball and the basket they defend (at -x)
            back = behind(pos, ball)
            set_s = None  # seconds after the crossing until all five are in the half they defend (x < 0), within the window and the chance
            for k in range(c["frontcourtFrame"], min(c["endFrame"], c["frontcourtFrame"] + SET_WINDOW) + 1):
                fk = frames.get(k)
                if not fk:
                    continue
                pk, _ = where(fk, g.sign(c))
                if all(d in pk and pk[d][0] < 0 for d in dfn):
                    set_s = (k - c["frontcourtFrame"]) / FPS
                    break
            self.transition.append({"game": gid, "back": len(back), "pts": c["ptsScored"] or 0, "seen": float(seen), "def_team": c["defTeamId"], "chance": c["id"],
                                    "late": [d for d in dfn if d not in back], "set_s": set_s})

        # every field-goal attempt with a quality: shot selection against shot making, per team-game (as offence here; the report reads the defence)
        for s in ev["shots"]:
            if s["chanceId"] in usable and s["shotQuality"] is not None and not s["fouled"]:
                self.fg.append({"game": gid, "off_team": s["offTeamId"], "def_team": s["defTeamId"], "three": bool(s["three"]),
                                "expected": (3 if s["three"] else 2) * s["shotQuality"] / 100, "actual": (3 if s["three"] else 2) * bool(s["outcome"])})
        for team in (g.meta["homeTeam"]["teamId"], g.meta["awayTeam"]["teamId"]):
            sel = selection([r for r in self.fg if r["game"] == gid and r["off_team"] == team])
            if sel:
                self.shot_sel.append({"game": gid, "team": g.team_name(team), **sel})

    def fit(self) -> rotations.QualityFit:
        """The quality fit over the games loaded (the league's own); a report uses the one frozen in league.json instead."""
        return rotations.QualityFit([s for g in self.loaded for s in g.events["shots"] if g.chances.get(s["chanceId"], {}).get("usable")])


# ---------------------------------------------------------------- the figures
def angle_between(a: np.ndarray, b: np.ndarray) -> float:
    """Degrees between two vectors on the floor."""
    na, nb = np.hypot(*a), np.hypot(*b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.degrees(np.arccos(np.clip(np.dot(a, b) / (na * nb), -1, 1))))


def col(rows, k, dtype=float):
    return np.array([r[k] if r[k] is not None else np.nan for r in rows], dtype=dtype)


def compute(ids: list[int] | None = None) -> dict:
    ids = ids or game_ids()
    R = Rows(ids)
    rng = np.random.default_rng(SEED)
    stats = {}
    n_teamgames = 2 * len(ids)

    # unowned shooter
    F = R.feeds
    g_, pps = col(F, "game"), col(F, "pps")
    nobody, extra, alone = np.array([r["nobody"] for r in F]), col(F, "extra"), col(F, "alone")
    m_un = nobody & (alone >= 1)
    m_in = ~nobody & (extra < 3)
    stats["unowned_shooter"] = figure("Shot off a catch with nobody assigned to the shooter for 1 s or more", pps[m_un].mean(), "expected points per shot", m_un.sum(),
                                      "courtlab.league.unowned_shooter · scripts/analysis_09_coach.py", ci(pps[m_un], g_[m_un], rng=rng),
                                      baseline=figure("his defender in place (under 3 ft beyond his normal spot)", pps[m_in].mean(), "expected points per shot", m_in.sum(),
                                                      "scripts/analysis_09_coach.py", ci(pps[m_in], g_[m_in], rng=rng)),
                                      share=round(float(m_un.mean()), 3))

    # pick coverage, with the outcome tree: what the handler did out of the screen and what the possession produced
    P = R.picks
    covs = np.array([r["cov"] for r in P]); pts = col(P, "pts"); bent = col(P, "bent"); gp = col(P, "game"); br = np.array([r["branch"] or "" for r in P])
    rows_cov = []
    for cov in COVERAGES:
        m = covs == cov
        tree = [{"branch": b, "n": int((m & (br == b)).sum()), "points_per_possession": round(float(pts[m & (br == b)].mean()), 3) if (m & (br == b)).any() else None} for b in BRANCHES]
        rows_cov.append({"coverage": cov, "n": int(m.sum()), "stretch_ft": round(float(np.nanmean(bent[m])), 2), "points_per_possession": round(float(pts[m].mean()), 3),
                         "ci": ci(pts[m], gp[m], rng=rng), "outcomes": tree})
    stats["pick_coverage"] = {"label": "The last ball screen of each set possession, by how the two defenders played it", "unit": "points per possession; stretch = the most any team-mate is pulled beyond his normal spot 1.2 s after the screen, ft",
                              "n": len(P), "source": "courtlab.league.pick_coverage · scripts/analysis_09_coach.py", "rows": rows_cov,
                              "outcomes": [{"branch": b, "n": int((br == b).sum()), "points_per_possession": round(float(pts[br == b].mean()), 3), "ci": ci(pts[br == b], gp[br == b], rng=rng)} for b in BRANCHES]}

    # one more pass
    C = R.chains
    k, cp, gc = col(C, "k"), col(C, "pps"), col(C, "game")
    stats["one_more_pass"] = {"label": "Expected points of the shot by passes after the last labelled action", "unit": "expected points per shot", "n": len(C),
                              "source": "courtlab.league.one_more_pass · scripts/analysis_04_one_more.py",
                              "rows": [{"passes": int(kk) if kk < 3 else "3+", "n": int((k == kk).sum()), "value": round(float(cp[k == kk].mean()), 3), "ci": ci(cp[k == kk], gc[k == kk], rng=rng)} for kk in (0, 1, 2, 3)]}

    # the race
    Ps, Cs, Os = R.passes, R.closeouts, R.onsets
    speed = col(Ps, "ft") / col(Ps, "secs")
    peak = col(Cs, "peak")
    onset, opps, ogames = col(Os, "onset"), col(Os, "pps"), col(Os, "game")
    late, early = (onset >= 0.4) & ~np.isnan(opps), (onset < 0.4) & ~np.isnan(opps)
    stats["race"] = {"label": "The pass against the man closing out", "unit": "ft/s, s, expected points per shot", "n": len(Os),
                     "value": round(float(np.median(speed) / np.median(peak)), 2), "value_label": "how many times faster the pass travels than the defender runs",
                     "source": "courtlab.league.race · scripts/analysis_10_more_signal.py, scripts/analysis_11_invisible.py",
                     "pass_speed": figure("Complete pass, passer to receiver, median", np.median(speed), "ft/s", len(Ps), "scripts/analysis_10_more_signal.py"),
                     "closeout_top_speed": figure("Top speed of a labelled close-out, median", np.median(peak), "ft/s", len(Cs), "scripts/analysis_10_more_signal.py",
                                                  p95=round(float(np.percentile(peak, 95)), 2)),
                     "closeout_speed_percentiles": [round(float(v), 2) for v in np.percentile(peak, range(0, 101, 5))],
                     "onset": figure("When the closing defender starts running at the receiver, after the pass leaves, median", np.median(onset), "s", len(Os), "scripts/analysis_11_invisible.py",
                                     flight_s=round(float(np.nanmedian(col(Os, "flight"))), 2)),
                     "late_start_price": figure("Expected points of the shot when the close-out starts 0.4 s or more after the pass, minus earlier", np.nanmean(opps[late]) - np.nanmean(opps[early]),
                                                "expected points per shot", int(late.sum()), "scripts/analysis_11_invisible.py", ci_diff(np.nan_to_num(opps), ogames, late, early, rng=rng))}

    # open three by shooter
    pct = col(F, "pct"); three = np.array([r["three"] for r in F]); pts_f = col(F, "pts")
    broken = three & (nobody | (extra >= 3)) & ~np.isnan(pct)
    shooters = sorted({(r["pct"]) for r in F if r["pct"] is not None})
    lo, hi = np.percentile(shooters, [33.3, 66.7])
    rows_t = []
    for label, m in (("bottom third", pct < lo), ("middle third", (pct >= lo) & (pct < hi)), ("top third", pct >= hi)):
        m = m & broken
        rows_t.append({"tercile": label, "n": int(m.sum()), "quality_says": round(float(pps[m].mean()), 3), "scored": round(float(pts_f[m].mean()), 3), "ci": ci(pts_f[m], g_[m], rng=rng)})
    stats["open_three_by_shooter"] = {"label": "A three off a broken rotation (defender 3 ft or more out of place, or nobody on him): what SkillCorner's quality says, and what was scored, by the shooter's season accuracy",
                                      "unit": "points per shot", "n": int(broken.sum()), "thresholds": [round(float(lo), 3), round(float(hi), 3)],
                                      "source": "courtlab.league.open_three_by_shooter · scripts/analysis_09_coach.py", "rows": rows_t}

    # the glass
    G = R.crash
    cr, orb, gg = col(G, "crash"), np.array([r["oreb"] for r in G], float), col(G, "game")
    stats["crash"] = figure("Offensive rebound when two or more team-mates crash, minus when none or one does", orb[cr >= 2].mean() - orb[cr <= 1].mean(), "share of rebounded misses", len(G),
                            "courtlab.league.crash · scripts/analysis_11_invisible.py · courtlab.glass", ci_diff(orb, gg, cr >= 2, cr <= 1, rng=rng),
                            rows=[{"crashing": str(kk) if kk < 3 else "3+", "n": int((cr == kk).sum() if kk < 3 else (cr >= 3).sum()), "offensive_rebound": round(float(orb[cr == kk].mean() if kk < 3 else orb[cr >= 3].mean()), 3)} for kk in (0, 1, 2, 3)],
                            share_two_plus=round(float((cr >= 2).mean()), 3), offensive_rebound=round(float(orb.mean()), 3))

    # transition
    T = R.transition
    back, tp, tg, seen = col(T, "back"), col(T, "pts"), col(T, "game"), col(T, "seen")
    rows_tr = []
    for label, m in (("0-2", back <= 2), ("3", back == 3), ("4", back == 4), ("5", back == 5)):
        rows_tr.append({"defenders_back": label, "n": int(m.sum()), "points_per_possession": round(float(tp[m].mean()), 3) if m.any() else None, "ci": ci(tp[m], tg[m], rng=rng)})
    set_s = col(T, "set_s")
    has = ~np.isnan(set_s)
    stats["transition"] = {"label": "Transition possessions: points by how many defenders were between the ball and their basket when it crossed into the front court",
                           "unit": "points per possession", "n": len(T), "value": round(float(tp.mean()), 3), "ci": ci(tp, tg, rng=rng), "on_camera_share": round(float(seen.mean()), 3),
                           "source": "courtlab.league.transition", "rows": rows_tr,
                           "seconds_to_set": figure("Seconds after the ball crossed until all five defenders were in the half they defend, median (0 when they already were; within 6 s and the chance)",
                                                    np.median(set_s[has]), "s", int(has.sum()), "courtlab.league.transition", ci(set_s[has], tg[has], stat=np.median, rng=rng),
                                                    never_share=round(float(1 - has.mean()), 3))}

    # shot selection vs shot making
    S = R.shot_sel
    gap = col(S, "gap_per_100")
    stats["shot_selection"] = {"label": "Per team and game: points scored minus points SkillCorner's shot quality expected, per 100 field-goal attempts (fouled shots excluded)",
                               "unit": "points per 100 shots", "n": len(S), "value": round(float(np.median(gap)), 2),
                               "percentiles": {str(p): round(float(np.percentile(gap, p)), 2) for p in (10, 25, 50, 75, 90)},
                               "expected_per_shot": round(float(sum(r["expected"] for r in S) / sum(r["shots"] for r in S)), 3),
                               "source": "courtlab.league.shot_selection"}

    # close-outs: what the possession produced after one, by what the attacker did once the defender arrived
    Co = R.cos
    act, cpts, cg = np.array([r["action"] for r in Co]), col(Co, "pts"), col(Co, "game")
    stats["closeouts"] = {"label": "Possession points after a labelled close-out, by what the attacker did once the defender arrived", "unit": "points per possession", "n": len(Co),
                          "value": round(float(cpts.mean()), 3), "ci": ci(cpts, cg, rng=rng), "start_ft": round(float(np.median(col(Co, "start"))), 1), "end_ft": round(float(np.nanmedian(col(Co, "end"))), 1),
                          "source": "courtlab.league.closeouts · scripts/analysis_09_coach.py",
                          "rows": [{"action": a, "n": int((act == a).sum()), "share": round(float((act == a).mean()), 3), "points_per_possession": round(float(cpts[act == a].mean()), 3), "ci": ci(cpts[act == a], cg[act == a], rng=rng)}
                                   for a in ("shot", "drive", "pass", "other")]}

    # the rim
    Rm = R.rim
    made, cont, blk, rg = np.array([r["made"] for r in Rm], float), np.array([r["contested"] for r in Rm]), np.array([r["blocked"] for r in Rm], float), col(Rm, "game")
    stats["rim"] = {"label": "Field goals from the restricted area (no foul): made, by whether a defender was within 4 ft at the release", "unit": "share made", "n": len(Rm),
                    "value": round(float(made[cont].mean()), 3), "ci": ci(made[cont], rg[cont], rng=rng), "contested_share": round(float(cont.mean()), 3),
                    "source": "courtlab.league.rim · scripts/analysis_09_coach.py",
                    "rows": [{"defender": lab, "n": int(m.sum()), "made": round(float(made[m].mean()), 3), "blocked": round(float(blk[m].mean()), 3), "ci": ci(made[m], rg[m], rng=rng)}
                             for lab, m in (("within 4 ft", cont), ("nobody within 4 ft", ~cont))]}

    # the quality fit the rotation price uses (rotations.py): frozen here so a possession can be priced without reading every game
    fit = R.fit()
    stats["quality_fit"] = {"label": "logit(SkillCorner shot quality) ~ closest defender distance + catch-and-shoot + distance + release time + dribbles, per zone",
                            "unit": "logit per ft (beta[1])", "n": int(sum(fit.n.values())), "source": "courtlab.rotations.QualityFit · scripts/analysis_09_coach.py", "rows": fit.rows()}

    # the ledger: what late and missing rotations cost, per team and game
    L = priced(R.ledger, fit)
    kind, price, lg = np.array([r["kind"] for r in L]), col(L, "price"), col(L, "game")
    set_catch = [r for r in F if r["set"]]
    stats["rotations"] = {"label": "Conceded shots with a counterfactual (only the defender's distance at the release is moved): expected points the rotation cost, per team and game",
                          "unit": "points per team-game", "n": len(L), "value": round(float(price.sum() / n_teamgames), 3), "per_shot": round(float(price.mean()), 3),
                          "broken_share": round(float(np.mean([r["broken"] for r in set_catch])), 3), "n_set_catch": len(set_catch),
                          "source": "courtlab.league.rotations · scripts/analysis_09_coach.py · courtlab.rotations",
                          "rows": [{"kind": kk, "n": int((kind == kk).sum()), "per_team_game": round(float((kind == kk).sum() / n_teamgames), 2),
                                    "price_per_shot": round(float(price[kind == kk].mean()), 3), "ci": ci(price[kind == kk], lg[kind == kk], rng=rng),
                                    "points_per_team_game": round(float(price[kind == kk].sum() / n_teamgames), 3)} for kk in KINDS]}

    # the look (docs/the_look.md): defence, could the shooter's defender see both his man and the ball when the pass left; attack, did the closer come from in view
    LD = [r for r in R.look_def if r["set"]]
    ang, dr, lpps, lpts, lgm = col(LD, "angle"), col(LD, "d_release"), col(LD, "pps"), col(LD, "pts"), col(LD, "game")
    lost = ang > LOOK_DEF_DEG
    def group(m, rows):
        return {"n": int(m.sum()), "share": round(float(m.mean()), 3), "distance_at_release_ft": round(float(np.nanmedian(dr[m])), 2), "expected_points": round(float(lpps[m].mean()), 3),
                "ci": ci(lpps[m], lgm[m], rng=rng), "points": round(float(lpts[m].mean()), 3)}
    LA = R.look_att
    bear, act, rel, adr, apps, agm = col(LA, "bearing"), np.array([r["action"] for r in LA]), col(LA, "release_s"), col(LA, "d_release"), col(LA, "pps"), col(LA, "game")
    out_of_view = bear > LOOK_ATT_DEG
    def agroup(m):
        shots = m & (act == "shot")
        return {"n": int(m.sum()), "share": round(float(m.mean()), 3), "shot": round(float((act[m] == "shot").mean()), 3), "drive": round(float((act[m] == "drive").mean()), 3), "pass": round(float((act[m] == "pass").mean()), 3),
                "release_s": round(float(np.nanmedian(rel[shots])), 2) if shots.any() else None, "distance_at_release_ft": round(float(np.nanmedian(adr[shots])), 2) if shots.any() else None,
                "expected_points": round(float(np.nanmean(apps[shots])), 3) if shots.any() else None, "n_shots": int(shots.sum())}
    stats["look"] = {"label": "What a player could see, from positions (docs/the_look.md): the shooter's defender at the pass, the shooter at the catch", "unit": "share of catches", "n": len(LD) + len(LA), "value": round(float(lost.mean()), 3), "value_label": "share of catches where the shooter's defender had lost his man or the ball", "source": "courtlab.league.look · docs/the_look.md",
                     "defence": {"label": f"Set defence, catches that fed a shot: the angle at the receiver's assigned defender between his man and the ball when the pass left; lost one = more than {LOOK_DEF_DEG}°",
                                 "unit": "share of catches; ft; expected points per shot", "n": len(LD), "threshold_deg": LOOK_DEF_DEG, "value": round(float(lost.mean()), 3),
                                 "rows": [{"look": "both in view", **group(~lost, LD)}, {"look": "lost one", **group(lost, LD)}],
                                 "distance_diff_ft": round(float(np.nanmedian(dr[lost]) - np.nanmedian(dr[~lost])), 2), "expected_points_diff": round(float(lpps[lost].mean() - lpps[~lost].mean()), 3),
                                 "expected_points_diff_ci": ci_diff(lpps, lgm, lost, ~lost, rng=rng)},
                     "attack": {"label": f"Catches followed by a labelled close-out: the closer's bearing from the direction the ball came from; out of view = more than {LOOK_ATT_DEG}°",
                                "unit": "share of catches; s; ft; expected points per shot", "n": len(LA), "threshold_deg": LOOK_ATT_DEG, "value": round(float(out_of_view.mean()), 3),
                                "rows": [{"look": "closer in view", **agroup(~out_of_view)}, {"look": "closer out of view", **agroup(out_of_view)}]}}

    return {"schema": SCHEMA, "generated": dt.date.today().isoformat(), "games": ids, "n_games": len(ids), "seed": SEED, "draws": DRAWS, "stats": stats}


def write(path: Path = OUT) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(compute(), indent=1))
    return path


def load(path: Path = OUT) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None
