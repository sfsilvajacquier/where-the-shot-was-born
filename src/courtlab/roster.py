"""The roster of one match: every player of both teams with what the tracking and the labels say about him in this game, and the
season counts SkillCorner publishes. Nothing biographical: the data carries a name, a jersey number and an id, and so does this file.

    uv run courtlab roster 191313          # -> outputs/rosters/191313.json (courtlab report writes it too)

Per player: minutes on the tracked play, distance and top speed (from the positions, sampled five times a second); shots, assists,
turnovers, drives, screens (SkillCorner's labels); whom he guarded and for how long (SkillCorner's matchups); how far beyond his normal
spot he stood on average (the same `extra` the play's bands show); his close-outs; the shots conceded with him nearest; what his
rotations cost (the ledger); and the plays exported on this machine he appears in. See docs/contracts.md §6.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

from courtlab import chapters, equilibrium, league, rotations
from courtlab.data import LAB, Game, season_aggregates

SCHEMA = "courtlab.roster/1"
OUT = LAB / "outputs" / "rosters"
POSSESSIONS = LAB / "outputs" / "possessions"
FPS, STEP = 25, 5  # positions sampled every STEP frames (0.2 s) for minutes, distance and speed
ASSIST = {"AST", "AST2", "AST3"}


def _med(v) -> float | None:
    v = [x for x in v if x is not None]
    return round(float(np.median(v)), 2) if v else None


def _mean(v) -> float | None:
    v = [x for x in v if x is not None]
    return round(float(np.mean(v)), 3) if v else None


def physical(g: Game, usable: dict) -> tuple[dict, dict]:
    """From the sampled positions: per player {seconds, distance_ft, top_speed}; per defender the `extra` samples while he had a man."""
    rows = defaultdict(list)
    for m in g.events["matchups"]:
        if m["endFrame"] - m["startFrame"] >= league.MIN_ROW:
            rows[m["defPlayerId"]].append((m["startFrame"], m["endFrame"], m["offPlayerId"]))
    wanted = set()
    for c in usable.values():
        wanted |= set(range(c["startFrame"], c["endFrame"] + 1, STEP))
    frames = g.frames_at(wanted)
    secs, dist, speeds, extra = Counter(), Counter(), defaultdict(list), defaultdict(list)
    for c in usable.values():
        sg, prev = g.sign(c), {}
        for k in range(c["startFrame"], c["endFrame"] + 1, STEP):
            f = frames.get(k)
            if not f:
                prev = {}
                continue
            pos = {q["playerId"]: (np.array(q["xyz"][:2]) * sg, bool(q["isDetected"])) for q in f["homePlayers"] + f["awayPlayers"]}
            ball = np.array(f["ball"]["xyz"][:2]) * sg
            for pid, (xy, seen) in pos.items():
                secs[pid] += STEP / FPS
                if pid in prev:
                    d = float(np.hypot(*(xy - prev[pid][0])))
                    dist[pid] += d
                    if seen and prev[pid][1]:
                        speeds[pid].append(d / (STEP / FPS))
            for d_id, spans in rows.items():
                man = next((o for a, b, o in spans if a <= k <= b), None)
                if man is not None and man in pos and d_id in pos:
                    extra[d_id].append(float(equilibrium.extra(pos[man][0][None], ball[None], pos[d_id][0][None])[1][0]))
            prev = pos
    phys = {pid: {"seconds": round(secs[pid], 1), "distance_ft": round(dist[pid], 0), "top_speed": round(float(np.percentile(speeds[pid], 98)), 1) if len(speeds[pid]) >= 25 else None} for pid in secs}
    return phys, extra


def build(game_id: int, possessions: Path = POSSESSIONS) -> dict:
    lg = league.load() or league.load(league.write())
    fit = rotations.QualityFit.from_rows(lg["stats"]["quality_fit"]["rows"])
    R = league.Rows([game_id])
    g, ev = R.loaded[0], R.loaded[0].events
    usable = {c["id"]: c for c in ev["chances"] if c["usable"]}
    phys, extra = physical(g, usable)
    season = season_aggregates()
    name = lambda pid: f"{g.players[pid]['firstName']} {g.players[pid]['lastName']}".strip() if pid in g.players else "?"  # noqa: E731
    priced = league.priced(R.ledger, fit)
    guarded = defaultdict(Counter)
    for m in ev["matchups"]:
        if m["chanceId"] in usable:
            guarded[m["defPlayerId"]][m["offPlayerId"]] += (m["endFrame"] - m["startFrame"]) / FPS
    plays = defaultdict(list)
    for path in sorted(possessions.glob("*.json")):
        d = json.loads(path.read_text())
        if d["source"]["game_id"] != game_id:
            continue
        shot = chapters.the_shot(d)
        clock = d["frames"]["game_clock"][shot["i"]] if shot else None
        for p in d["players"]:
            plays[p["id"]].append({"chance": path.stem, "role": d["source"].get("role", "play"), "side": p["side"], "period": d["game"]["period"],
                                  "clock": f"{int(clock // 60)}:{int(clock % 60):02d}" if clock is not None else None, "story": chapters.story(d)})
    home, away = g.meta["homeTeam"]["teamId"], g.meta["awayTeam"]["teamId"]
    last = max((c for c in ev["chances"] if c["endFrame"] is not None), key=lambda c: c["endFrame"])
    score = [last["homeStartScore"] + (last["ptsScored"] or 0) * (last["offTeamId"] == home), last["awayStartScore"] + (last["ptsScored"] or 0) * (last["offTeamId"] == away)]

    def player(pid: int) -> dict:
        shots = [s for s in ev["shots"] if s["shooterId"] == pid and s["chanceId"] in usable and not s["fouled"]]
        threes = [s for s in shots if s["three"]]
        touches = [t for t in ev["touches"] if t["playerId"] == pid and t["chanceId"] in usable]
        drives = [e for e in ev["drives"] if e["ballhandlerId"] == pid and e["chanceId"] in usable]
        conceded = [s for s in ev["shots"] if s["closestDefId"] == pid and s["chanceId"] in usable and not s["fouled"]]
        cos = [r for r in R.cos if r["defender"] == pid]
        paid = [r for r in priced if r["who"] == pid]
        rb = [r for r in ev["rebounds"] if r["rebounderId"] == pid and r["rebounded"]]
        ex = extra.get(pid, [])
        rec = season.get(pid)
        sh, pk, dr = (rec or {}).get("shots"), (rec or {}).get("picks"), (rec or {}).get("drives")
        return {"id": pid, "name": name(pid), "surname": chapters.surname(name(pid)), "jersey": g.players[pid]["jersey"],
                "season": None if not sh else {"games": sh["games_played"], "fg": [sh["mades"], sh["attempts"]], "three": [sh["three_mades"], sh["three_attempts"]], "cns_three": [sh["cns_three_mades"], sh["cns_three_attempts"]],
                                               "contested": [sh["contested_mades"], sh["contested_attempts"]], "points": sh["total_points"],
                                               "picks": {"n": pk["handler_total_picks"], "points": pk["handler_points"], "turnovers": pk["handler_turnover"]} if pk else None,
                                               "drives": {"n": dr["total_drives"], "blowby": dr["blowby_count"], "points": dr["points"], "assists": dr["assists"]} if dr else None},
                "game": {**phys.get(pid, {"seconds": 0, "distance_ft": 0, "top_speed": None}),
                         "shots": {"n": len(shots), "made": sum(bool(s["outcome"]) for s in shots), "three": len(threes), "three_made": sum(bool(s["outcome"]) for s in threes),
                                   "quality": _mean([s["shotQuality"] for s in shots]), "points": sum((3 if s["three"] else 2) * bool(s["outcome"]) for s in shots)},
                         "assists": sum(1 for t in touches if set(t["outcomes"] or []) & ASSIST), "turnovers": sum(1 for e in ev["turnovers"] if e["turnedOverId"] == pid and e["chanceId"] in usable),
                         "passes": sum(1 for p in ev["passes"] if p["passerId"] == pid and p["complete"] and p["chanceId"] in usable and not p["inbounds"]),
                         "drives": len(drives), "blowby": sum(bool(e["blowby"]) for e in drives),
                         "picks_handler": sum(1 for e in ev["picks"] if e["ballhandlerId"] == pid and e["chanceId"] in usable),
                         "screens": sum(1 for e in ev["picks"] if e["screenerId"] == pid and e["chanceId"] in usable) + sum(1 for e in ev["off_ball_screens"] if e["screenerId"] == pid and e["chanceId"] in usable),
                         "rebounds": [sum(1 for r in rb if not r["defensive"]), sum(1 for r in rb if r["defensive"])],
                         "fouls": sum(1 for e in ev["fouls"] if e["foulerId"] == pid)},
                "defence": {"guarded": [{"who": chapters.surname(name(o)), "seconds": round(s, 0)} for o, s in guarded[pid].most_common(3)],
                            "extra": {"mean": round(float(np.mean(ex)), 2), "within_3": round(float(np.mean(np.array(ex) < 3)), 3), "n": len(ex)} if ex else None,
                            "closeouts": {"n": len(cos), "start": _med([r["start"] for r in cos]), "end": _med([r["end"] for r in cos]), "pts": _mean([r["pts"] for r in cos]), "actions": dict(Counter(r["action"] for r in cos))} if cos else None,
                            "conceded": {"n": len(conceded), "made": sum(bool(s["outcome"]) for s in conceded), "distance": _med([s["closestDefDist"] for s in conceded]), "quality": _mean([s["shotQuality"] for s in conceded])} if conceded else None,
                            "price": {"value": round(sum(r["price"] for r in paid), 2), "n": len(paid), "kinds": dict(Counter(r["kind"] for r in paid))} if paid else None},
                "plays": plays.get(pid, [])}

    teams = []
    for team in (home, away):
        ids = [p for p, who in g.players.items() if who["teamId"] == team]
        players = sorted((player(p) for p in ids), key=lambda r: -r["game"]["seconds"])
        teams.append({"team": g.team_name(team), "side": "home" if team == home else "away", "players": players})
    return {"schema": SCHEMA,
            "source": {"dataset": "SkillCorner Open Data, basketball (github.com/SkillCorner/opendata-basketball, MIT)", "game_id": game_id,
                       "generated_by": "courtlab roster (nothing in this file is hand-edited; no data beyond SkillCorner's)",
                       "season": "SkillCorner's ACB 2025-2026 aggregates (shots, ball screens, drives)", "league": {"schema": lg["schema"], "generated": lg["generated"], "n_games": lg["n_games"]}},
            "game": {"home": g.meta["homeTeam"]["teamName"], "away": g.meta["awayTeam"]["teamName"], "score": score, "date": g.meta["date"][:10],
                     "competition": f"{g.meta['competitionName']} {g.meta['seasonName']}"},
            "teams": teams}


def write(game_id: int, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{game_id}.json"
    path.write_text(json.dumps(build(game_id), indent=1, ensure_ascii=False))
    return path
