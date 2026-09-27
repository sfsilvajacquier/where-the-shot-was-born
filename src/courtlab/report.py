"""One match, read as a defensive staff would: seven tiles per defending team and the moments worth watching again.

    uv run courtlab report 191313              # -> outputs/reports/191313.json, and the possessions of its moments in outputs/possessions/

Every number comes from the same rows the league figures are made of (`league.Rows`), so a tile and the league line under it never
disagree on a definition. Per-game numbers are counts and means; only the league figures carry intervals; nothing per player beyond
counts. See docs/contracts.md §4.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import numpy as np

from courtlab import chapters, league, rotations
from courtlab.data import LAB, Game
from courtlab.possession import Possession

SCHEMA = "courtlab.report/1"
OUT = LAB / "outputs" / "reports"
POSSESSIONS = LAB / "outputs" / "possessions"
TILES = ("transition", "shot_selection", "ball_screens", "closeouts", "rim", "glass", "rotations", "look")
THUMB = 64


def pct(x: float | None) -> str:
    return "–" if x is None or np.isnan(x) else f"{100 * x:.0f} %"


def num(x: float | None, nd: int = 2, sign: bool = False) -> str:
    return "–" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:+.{nd}f}" if sign else f"{x:.{nd}f}"


def mean(rows: list[dict], key: str) -> float | None:
    v = [r[key] for r in rows if r[key] is not None]
    return float(np.mean(v)) if v else None


def clock(period: int, secs: float) -> str:
    return f"Q{period} {int(secs // 60)}:{int(secs % 60):02d}"


def thumb(d: dict) -> list[list[float | None]]:
    """The tension strip in miniature: THUMB samples per attacker of `extra`, as the start screen draws it."""
    n = len(d["frames"]["idx"])
    picks = [round(k * (n - 1) / (THUMB - 1)) for k in range(THUMB)]
    return [[(None if (v := d["extra"][str(p["id"])][i]) is None else round(v, 1)) for i in picks] for p in d["players"] if p["side"] == "attack"]


def tile(id: str, title: str, value, unit: str, line: str, n: int, detail: list[tuple[str, str]], league: float | None = None) -> dict:
    """`league`: the league figure on the same scale as `big`, so a page can colour the comparison; higher always means more conceded."""
    return {"id": id, "title": title, "big": {"value": None if value is None or (isinstance(value, float) and np.isnan(value)) else round(float(value), 3), "unit": unit},
            "league": None if league is None else round(float(league), 3), "line": line, "n": int(n), "detail": [{"label": a, "value": b} for a, b in detail[:5]]}


# ---------------------------------------------------------------- the seven tiles of one defending team
def tiles(R: league.Rows, g: Game, team: int, lg: dict, fit: rotations.QualityFit) -> list[dict]:
    S, name = lg["stats"], g.team_name
    other = next(t for t in (g.meta["homeTeam"]["teamId"], g.meta["awayTeam"]["teamId"]) if t != team)
    who = lambda pid: chapters.surname(f"{g.players[pid]['firstName']} {g.players[pid]['lastName']}") if pid in g.players else "?"  # noqa: E731
    out = []

    # transition
    T = [r for r in R.transition if r["def_team"] == team]
    lt = {r["defenders_back"]: r for r in S["transition"]["rows"]}
    band = lambda r: "0–2 back" if r["back"] <= 2 else "3–4 back" if r["back"] <= 4 else "5 back"  # noqa: E731
    counts = Counter(band(r) for r in T)
    late = Counter(d for r in T for d in r["late"])
    sts = S["transition"]["seconds_to_set"]
    set_s = [r["set_s"] for r in T if r["set_s"] is not None]
    out.append(tile("transition", "Transition", mean(T, "pts"), "pts/poss",
                    f"League {num(S['transition']['value'])} per transition possession: {num(lt['0-2']['points_per_possession'])} with two or fewer back, {num(lt['5']['points_per_possession'])} with all five; "
                    f"a defence has all five in its half {num(sts['value'], 1)} s after the crossing (median). Defenders on camera at the crossing: {pct(mean(T, 'seen'))}.",
                    len(T), [(k, f"{counts[k]} poss · {num(mean([r for r in T if band(r) == k], 'pts'))} pts") for k in ("0–2 back", "3–4 back", "5 back") if counts[k]]
                    + [("All five in their half after (median)", f"{num(float(np.median(set_s)), 1)} s" + (f" · not before the chance ended on {len(T) - len(set_s)}" if len(T) > len(set_s) else "") if set_s else "–"),
                       ("Not back when the ball crossed", " · ".join(f"{who(d)} {n}" for d, n in late.most_common(3)) or "–")], league=S["transition"]["value"]))

    # shot selection vs shot making, as the defence: the looks they allowed against what was scored on them
    D = league.selection([r for r in R.fg if r["game"] == g.id and r["def_team"] == team]) or {"shots": 0, "expected": 0, "actual": 0, "gap_per_100": None}
    O = league.selection([r for r in R.fg if r["game"] == g.id and r["off_team"] == team])
    p = S["shot_selection"]["percentiles"]
    out.append(tile("shot_selection", "Shot selection vs shot making", D["gap_per_100"], "pts per 100 shots conceded",
                    f"Points {name(other)} scored beyond what the quality of their looks expected. League median {num(S['shot_selection']['value'], 1, True)} per 100, "
                    f"from {num(p['10'], 0, True)} (cold) to {num(p['90'], 0, True)} (hot); the looks a league defence allows are worth {num(S['shot_selection']['expected_per_shot'])} per shot.",
                    D["shots"], [("Looks allowed, expected per shot", f"{num(D['expected'] / D['shots']) if D['shots'] else '–'} pts"), ("Scored per shot", f"{num(D['actual'] / D['shots']) if D['shots'] else '–'} pts"),
                                 ("Threes conceded", f"{sum(1 for r in R.fg if r['game'] == g.id and r['def_team'] == team and r['three'])}"),
                                 (f"{name(team)} on offence", f"{num(O['gap_per_100'], 1, True)} per 100 over {O['shots']} shots" if O else "–")], league=S["shot_selection"]["value"]))

    # ball screens
    P = [r for r in R.picks if r["def_team"] == team]
    lc = {r["coverage"]: r for r in S["pick_coverage"]["rows"]}
    by_cov = Counter(r["cov"] for r in P)
    rows = [(cov, f"{n} · {num(mean([r for r in P if r['cov'] == cov], 'pts'))} pts (league {num(lc[cov]['points_per_possession'])})" if cov in lc else f"{n} · {num(mean([r for r in P if r['cov'] == cov], 'pts'))} pts")
            for cov, n in by_cov.most_common(4)]
    br = Counter(r["branch"] for r in P if r["branch"])
    out.append(tile("ball_screens", "Ball screens", mean(P, "pts"), "pts/poss after the last screen",
                    f"League: over/show {num(lc['over/show']['points_per_possession'])}, over/soft {num(lc['over/soft']['points_per_possession'])}, switch {num(lc['switch/switch']['points_per_possession'])} per possession.",
                    len(P), rows + [("The handler shot / passed / was fouled", " / ".join(str(br[b]) for b in ("shot", "pass", "foul")))],
                    league=sum(r["points_per_possession"] * r["n"] for r in S["pick_coverage"]["rows"]) / max(1, sum(r["n"] for r in S["pick_coverage"]["rows"]))))

    # close-outs
    C = [r for r in R.cos if r["def_team"] == team]
    la = {r["action"]: r for r in S["closeouts"]["rows"]}
    acts = Counter(r["action"] for r in C)
    by_def = Counter(r["defender"] for r in C)
    out.append(tile("closeouts", "Close-outs", mean(C, "pts"), "pts/poss after one",
                    f"League {num(S['closeouts']['value'])} per possession after a close-out: {num(la['shot']['points_per_possession'])} when the attacker shoots, {num(la['drive']['points_per_possession'])} when he drives, {num(la['pass']['points_per_possession'])} when he passes.",
                    len(C), [("The attacker shot / drove / passed", f"{acts['shot']} / {acts['drive']} / {acts['pass']}"),
                             ("Started from, arrived at (median)", f"{num(float(np.median([r['start'] for r in C])), 0) if C else '–'} → {num(float(np.nanmedian([r['end'] if r['end'] is not None else np.nan for r in C])), 1) if C else '–'} ft"),
                             ("Most close-outs", " · ".join(f"{who(d)} {n}" for d, n in by_def.most_common(3)))], league=S["closeouts"]["value"]))

    # the rim
    Rm = [r for r in R.rim if r["def_team"] == team]
    con = [r for r in Rm if r["contested"]]
    lr = {r["defender"]: r for r in S["rim"]["rows"]}
    made_con = mean(con, "made")
    out.append(tile("rim", "The rim", None if made_con is None else 100 * made_con, "% made with a defender within 4 ft",
                    f"League: {pct(lr['within 4 ft']['made'])} made with a defender within 4 ft, {pct(lr['nobody within 4 ft']['made'])} with nobody there; a defender is within 4 ft on {pct(S['rim']['contested_share'])} of rim attempts.",
                    len(Rm), [("Attempts conceded at the rim", f"{len(Rm)}"), ("With a defender within 4 ft", f"{len(con)} ({pct(len(con) / len(Rm)) if Rm else '–'})"),
                              ("Nobody within 4 ft: made", pct(mean([r for r in Rm if not r["contested"]], "made"))), ("Blocked", f"{sum(r['blocked'] for r in Rm)}")], league=100 * S["rim"]["value"]))

    # the glass
    Gd = [r for r in R.crash if r["game"] == g.id and r["def_team"] == team]
    Go = [r for r in R.crash if r["game"] == g.id and r["off_team"] == team]
    lgl = {r["crashing"]: r for r in S["crash"]["rows"]}
    got_back = mean(Gd, "oreb")
    out.append(tile("glass", "The glass", None if got_back is None else 100 * got_back, "% of their misses they got back",
                    f"League: an offensive rebound on {pct(S['crash']['offensive_rebound'])} of rebounded misses, {pct(lgl['0']['offensive_rebound'])} when nobody crashes and {pct(lgl['2']['offensive_rebound'])} when two do; two or more crash on {pct(S['crash']['share_two_plus'])} of misses.",
                    len(Gd), [(f"{name(other)} misses rebounded", f"{len(Gd)}"), ("They sent two or more to crash", f"{sum(r['crash'] >= 2 for r in Gd)}"), ("They took back", f"{sum(r['oreb'] for r in Gd)}"),
                              (f"{name(team)} own misses: crashed 2+ / took back", f"{sum(r['crash'] >= 2 for r in Go)} / {sum(r['oreb'] for r in Go)} of {len(Go)}")], league=100 * S["crash"]["offensive_rebound"]))

    # rotations: the ledger
    L = league.priced([r for r in R.ledger if r["def_team"] == team], fit)
    lk = {r["kind"]: r for r in S["rotations"]["rows"]}
    catch = [r for r in R.feeds if r["def_team"] == team and r["set"]]
    broken = [r for r in catch if r["broken"]]
    out.append(tile("rotations", "Rotations", sum(r["price"] for r in L), "pts the rotations cost",
                    f"League {num(S['rotations']['value'])} per team and game: late close-outs {num(lk['late close-out']['points_per_team_game'])}, nobody on the shooter {num(lk['nobody on him']['points_per_team_game'])}, help not recovered {num(lk['help not recovered']['points_per_team_game'])}. An upper bound: the defender arrives and nothing else changes.",
                    len(L), [(k.capitalize(), f"{sum(1 for r in L if r['kind'] == k)} · {num(sum(r['price'] for r in L if r['kind'] == k), 1, True)} pts") for k in league.KINDS]
                    + [("Set defence: catches off a broken rotation", f"{len(broken)} of {len(catch)} (league {pct(S['rotations']['broken_share'])})")], league=S["rotations"]["value"]))

    # the look (docs/the_look.md): at the pass, could the shooter's defender see both his man and the ball
    LD = [r for r in R.look_def if r["def_team"] == team and r["set"]]
    lost = [r for r in LD if r["angle"] > league.LOOK_DEF_DEG]
    both = [r for r in LD if r["angle"] <= league.LOOK_DEF_DEG]
    lk = {r["look"]: r for r in S["look"]["defence"]["rows"]}
    LA = [r for r in R.look_att if r["off_team"] == team]
    out_of_view = [r for r in LA if r["bearing"] > league.LOOK_ATT_DEG]
    by_def = Counter(r["defender"] for r in lost)
    out.append(tile("look", "The look", None if not LD else 100 * len(lost) / len(LD), "% of catches with ball or man out of the defender's view",
                    f"League {pct(S['look']['defence']['value'])}: a shot off a catch is worth {num(lk['lost one']['expected_points'])} expected points when the defender had lost one of them, {num(lk['both in view']['expected_points'])} when he saw both; "
                    f"the distance at the release is the same ({num(lk['lost one']['distance_at_release_ft'], 1)} v {num(lk['both in view']['distance_at_release_ft'], 1)} ft). Positions only: the data has no gaze.",
                    len(LD), [("Saw both / lost one", f"{len(both)} / {len(lost)}"),
                              ("Expected points, saw both / lost one", f"{num(mean(both, 'pps'))} / {num(mean(lost, 'pps'))}"),
                              ("Distance at the release, saw both / lost one", f"{num(float(np.nanmedian([r['d_release'] if r['d_release'] is not None else np.nan for r in both])), 1) if both else '–'} / {num(float(np.nanmedian([r['d_release'] if r['d_release'] is not None else np.nan for r in lost])), 1) if lost else '–'} ft"),
                              ("Lost sight most", " · ".join(f"{who(d)} {n}" for d, n in by_def.most_common(3)) or "–"),
                              (f"{name(team)} attacking: closer out of view at the catch", f"{len(out_of_view)} of {len(LA)} (league {pct(S['look']['attack']['value'])})")], league=100 * S["look"]["defence"]["value"]))
    return out


# ---------------------------------------------------------------- the story of the defence: when, where, who
ZONES = (("rim", "The rim", ("ra",)), ("paint", "The paint", ("key",)), ("mid", "Mid-range", ("middle two", "left wing two", "right wing two", "left corner two", "right corner two")),
         ("corner3", "Corner threes", ("left corner three", "right corner three")), ("wing3", "Wing threes", ("left wing three", "right wing three")), ("top3", "Top threes", ("middle three",)))


def story(R: league.Rows, g: Game, team: int, fit: rotations.QualityFit) -> dict:
    """What a coach asks first: when it happened (by quarter), where they shot from (every conceded shot, and six zones), who paid (the ledger by defender)."""
    who = lambda pid: chapters.surname(f"{g.players[pid]['firstName']} {g.players[pid]['lastName']}") if pid in g.players else None  # noqa: E731
    shots = [s for s in g.events["shots"] if s["defTeamId"] == team and s["chanceId"] in g.chances and g.chances[s["chanceId"]]["usable"] and not s["fouled"] and s["shotQuality"] is not None]
    L = league.priced([r for r in R.ledger if r["def_team"] == team], fit)
    catch = [r for r in R.feeds if r["def_team"] == team and r["set"]]
    quarters = []
    for p in sorted({s["period"] for s in shots} | {r["period"] for r in catch}):
        sp = [s for s in shots if s["period"] == p]
        quarters.append({"period": p, "shots": len(sp), "expected": round(sum((3 if s["three"] else 2) * s["shotQuality"] / 100 for s in sp), 1), "scored": sum((3 if s["three"] else 2) * bool(s["outcome"]) for s in sp),
                         "price": round(sum(r["price"] for r in L if r["shot"]["period"] == p), 2), "catches": sum(1 for r in catch if r["period"] == p), "broken": sum(1 for r in catch if r["period"] == p and r["broken"])})
    zone_of = {r: zid for zid, _, regions in ZONES for r in regions}
    zones = []
    for zid, title, _ in ZONES:
        sz = [s for s in shots if zone_of.get(s["region"]) == zid]
        zones.append({"id": zid, "title": title, "n": len(sz), "made": sum(bool(s["outcome"]) for s in sz), "expected_per_shot": round(float(np.mean([(3 if s["three"] else 2) * s["shotQuality"] / 100 for s in sz])), 2) if sz else None})
    plotted = [{"x": round(s["location"][0], 1), "y": round(s["location"][1], 1), "made": bool(s["outcome"]), "three": bool(s["three"]), "quality": round(s["shotQuality"]), "zone": zone_of.get(s["region"]), "period": s["period"], "shooter": who(s["shooterId"]) or "?"}
               for s in shots if s["location"] and s["region"] in zone_of]
    paid = Counter(); paid_n = Counter()
    for r in L:
        if r["who"] is not None:
            paid[r["who"]] += r["price"]; paid_n[r["who"]] += 1
    cos = Counter(r["defender"] for r in R.cos if r["def_team"] == team)
    nearest = Counter(s["closestDefId"] for s in shots if s["closestDefId"] is not None)
    players = [{"name": who(pid) or "?", "price": round(v, 2), "shots": paid_n[pid], "closeouts": cos[pid], "conceded": nearest[pid]} for pid, v in paid.most_common(6) if who(pid)]
    return {"quarters": quarters, "zones": zones, "shots": plotted, "who": players, "unpriced_to_nobody": sum(1 for r in L if r["who"] is None)}


# ---------------------------------------------------------------- the moments
def moments(R: league.Rows, g: Game, team: int, fit: rotations.QualityFit, top: int, folder: Path) -> list[dict]:
    """Conceded shots off a broken rotation in set defence, most expensive first; each one's possession is exported so the viewer can open it."""
    price = {r["shot_id"]: r for r in league.priced([r for r in R.ledger if r["def_team"] == team], fit)}
    mine = [r for r in R.feeds if r["def_team"] == team and r["set"] and r["broken"]]
    mine.sort(key=lambda r: (-(price[r["shot_id"]]["price"] if r["shot_id"] in price else -1), -r["pps"]))
    out = []
    for r in mine[:top]:
        path = Possession.build(g, r["chance"]).write(folder, role="moment")
        d = json.loads(path.read_text())
        shot = chapters.the_shot(d)
        feed = chapters.the_feed(d, shot) if shot else None
        ch = {c["id"]: c for c in d["chapters"]}
        names = {p["id"]: chapters.surname(p["name"]) for p in d["players"]}
        if r["nobody"] and r["left"]:
            rotation = f"{names.get(r['left']['who'], '?')} let go of him {r['left']['secs_before_shot']:.1f} s before the shot" + (f" to take {names.get(r['left']['took'], '?')}" if r["left"]["took"] else "") + "; nobody picked him up."
        elif r["nobody"]:
            rotation = f"Nobody was assigned to him (nearest defender {r['nearest']:.0f} ft away)." if r["nearest"] is not None else "Nobody was assigned to him."
        else:
            rotation = f"His man {names.get(r['own'], '?')} was {r['extra']:.0f} ft beyond his spot when the pass left."
        race = ch.get("race")
        closeout = race["context"] if race and race.get("at_pass_ft") is not None else None
        pr = price.get(r["shot_id"])
        if pr and pr["kind"] == "late close-out":
            note = (f"had {names.get(pr['who'], '?')} started with the pass: {pr['d_cf']:.1f} ft instead of {pr['d_now']:.1f} at the release"
                    if pr["onset"] > 0.04 else f"{names.get(pr['who'], '?')} started with the pass; the distance was the rotation's, not his")
        elif pr:
            note = f"a defender at the normal spot would be at {pr['d_cf']:.1f} ft instead of {pr['d_now']:.1f}"
            if pr.get("rotator"):
                note += f"; the free man was {names.get(pr['rotator'][0], '?')}, {pr['rotator'][1]:.0f} ft away ({pr['rotator'][2]:.1f} s at close-out speed)"
        else:
            note = None
        out.append({"chance": r["chance"], "i": feed["i"] if feed else (shot["i"] if shot else 0), "clock": clock(r["period"], r["clock"]), "shooter": names.get(r["shooter"], "?"),
                    "shot": {"three": r["three"], "made": r["made"], "quality": round(r["quality"], 0)}, "origin": chapters.came_from(d) or "No labelled action before it.",
                    "rotation": rotation, "closeout": closeout, "price": {"value": round(pr["price"], 2), "kind": pr["kind"], "note": note} if pr else {"value": None, "kind": None, "note": None},
                    "thumb": thumb(d)})
    return out


# ---------------------------------------------------------------- the report
def build(game_id: int, top: int = 6, folder: Path = POSSESSIONS) -> dict:
    lg = league.load() or league.load(league.write())
    fit = rotations.QualityFit.from_rows(lg["stats"]["quality_fit"]["rows"])
    R = league.Rows([game_id])
    g = R.loaded[0]
    folder.mkdir(parents=True, exist_ok=True)
    last = max((c for c in g.events["chances"] if c["endFrame"] is not None), key=lambda c: c["endFrame"])
    home, away = g.meta["homeTeam"]["teamId"], g.meta["awayTeam"]["teamId"]
    score = [last["homeStartScore"] + (last["ptsScored"] or 0) * (last["offTeamId"] == home), last["awayStartScore"] + (last["ptsScored"] or 0) * (last["offTeamId"] == away)]
    teams = []
    for team in (home, away):
        teams.append({"team": g.team_name(team), "side": "home" if team == home else "away", "opponent": g.team_name(away if team == home else home),
                      "tiles": tiles(R, g, team, lg, fit), "story": story(R, g, team, fit), "moments": moments(R, g, team, fit, top, folder)})
    return {"schema": SCHEMA,
            "source": {"dataset": "SkillCorner Open Data, basketball (github.com/SkillCorner/opendata-basketball, MIT)", "game_id": game_id,
                       "generated_by": "courtlab report (nothing in this file is hand-edited)", "league": {"schema": lg["schema"], "generated": lg["generated"], "n_games": lg["n_games"]}},
            "game": {"home": g.meta["homeTeam"]["teamName"], "away": g.meta["awayTeam"]["teamName"], "score": score, "date": g.meta["date"][:10],
                     "competition": f"{g.meta['competitionName']} {g.meta['seasonName']}"},
            "teams": teams}


def write(game_id: int, top: int = 6, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{game_id}.json"
    path.write_text(json.dumps(build(game_id, top), indent=1, ensure_ascii=False))
    return path


def index(folder: Path = OUT) -> list[dict]:
    """One line per report written on this machine, for the start screen's Reports tab."""
    rows = []
    for path in sorted(folder.glob("*.json")):
        d = json.loads(path.read_text())
        rot = {t["side"]: next((x["big"]["value"] for x in t["tiles"] if x["id"] == "rotations"), None) for t in d["teams"]}
        rows.append({"game": d["source"]["game_id"], **d["game"], "moments": sum(len(t["moments"]) for t in d["teams"]), "rotations": rot})
    return rows
