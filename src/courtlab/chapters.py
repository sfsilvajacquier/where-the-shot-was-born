"""One possession told in up to four chapters, from its own JSON: the action, the help, the race, the shot.

Each chapter is a contiguous window of frames with one number (`big`), one sentence of context and the key of the league figure it
quotes. Windows and numbers are functions of SkillCorner's labels and of the positions already in the file, so the same code runs at
export time and on a JSON read back later. See docs/contracts.md §2.2.
"""

from __future__ import annotations

import math

import numpy as np

from courtlab import rotations

FPS = 25
ON_BALL = ("pick", "handoff", "drive", "isolation", "post")
LABEL = {"pick": "Ball screen", "handoff": "Hand-off", "drive": "Drive", "isolation": "Isolation", "post": "Post-up", "screen": "Off-ball screen"}
KIND = {"catchAndShoot": "Catch and shoot", "dribblePullUp": "Pull-up", "offMove": "Shot off a move", "layup": "Layup", "floater": "Floater", "hook": "Hook shot", "dunk": "Dunk",
        "tip": "Tip-in", "stepback": "Step-back", "postFadeaway": "Post fadeaway", "lob": "Lob", "heave": "Heave", "shakeAndRaise": "Shake and raise", "leaner": "Leaner"}
K5 = np.ones(5) / 5


def surname(name: str) -> str:
    parts = (name or "").split()
    return " ".join(parts[-2:]) if len(parts) > 2 and len(parts[-1]) < 4 else (parts[-1] if parts else "?")


def the_shot(d: dict) -> dict | None:
    shots = [a for a in d["actions"] if a["type"] == "shot" and a.get("i") is not None]
    return shots[-1] if shots else None


def the_feed(d: dict, shot: dict) -> dict | None:
    """The last complete pass to the shooter before the release."""
    feeds = [a for a in d["actions"] if a["type"] == "pass" and a.get("complete") and a.get("to") == shot["player"] and a.get("i") is not None and a["i"] <= shot["i"]]
    return feeds[-1] if feeds else None


def _handler(a: dict):
    """Who had the ball in an on-ball action."""
    return a.get("handler") if a["type"] == "pick" else a.get("receiver") if a["type"] == "handoff" else a.get("player")


def origin(d: dict, shot: dict, feed: dict | None) -> dict | None:
    """The one rule for where the shot came from: the last on-ball action before the pass that fed the shooter, or, when the shooter
    ran the action himself after the catch, before the shot; failing that, the first off-ball screen before the feed; failing that, nothing."""
    limit = feed["i"] if feed else shot["i"]
    acts = [a for a in d["actions"] if a.get("i") is not None and a["i"] <= shot["i"]]
    on = [a for a in acts if a["type"] in ON_BALL and (a["i"] <= limit or _handler(a) == shot["player"])]
    if on:
        return on[-1]
    off = [a for a in acts if a["type"] == "screen" and a["i"] <= limit]
    return off[0] if off else None


def story(d: dict) -> str | None:
    """The possession in one line, for the start screen: origin → passes → shooter, shot, chance of scoring."""
    shot = the_shot(d)
    if not shot:
        return None
    names = {p["id"]: surname(p["name"]) for p in d["players"]}
    who = f"{names.get(shot['player'], '?')}, {'three' if shot['three'] else 'two'}" + (f", {shot['quality']:.0f} %" if shot.get("quality") is not None else "")
    feed = the_feed(d, shot)
    o = origin(d, shot, feed)
    if o is None:
        return f"Pass from {names.get(feed['from'], '?')} → {who}" if feed and feed.get("from") in names else who
    label = LABEL[o["type"]] + (f" · {o['coverage']}" if o["type"] == "pick" and o.get("coverage") else "")
    passes = sum(1 for a in d["actions"] if a["type"] == "pass" and a.get("complete") and a.get("i") is not None and o["i"] < a["i"] <= shot["i"])
    return f"{label} → {'no pass' if passes == 0 else f'{passes} pass{chr(101) + chr(115) if passes != 1 else chr(0)}'.rstrip(chr(0))} → {who}"


def came_from(d: dict) -> str | None:
    """Where the shot came from, in one sentence for the report: the origin, who ran it, how it was defended, how long and how many passes before the shot."""
    shot = the_shot(d)
    if not shot:
        return None
    names = {p["id"]: surname(p["name"]) for p in d["players"]}
    o = origin(d, shot, the_feed(d, shot))
    if o is None:
        return None
    n = lambda pid: names.get(pid, "?")  # noqa: E731
    if o["type"] == "pick":
        who, how = f"{n(o['handler'])} / {n(o['screener'])}", f"defended {o['coverage']}/{o['screener_coverage']} by {n(o['handler_def'])} and {n(o['screener_def'])}" if o.get("coverage") else ""
    elif o["type"] == "handoff":
        who, how = f"{n(o['receiver'])} / {n(o['setter'])}", f"defended {o['coverage']}" if o.get("coverage") else ""
    elif o["type"] == "screen":
        who, how = f"{n(o['cutter'])} / {n(o['screener'])}", f"defended {o['coverage']}" if o.get("coverage") else ""
    else:
        who, how = n(o.get("player")), ("his man beaten" if o.get("beat_his_man") else "contained") if o["type"] == "drive" else ""
    passes = sum(1 for a in d["actions"] if a["type"] == "pass" and a.get("complete") and a.get("i") is not None and o["i"] < a["i"] <= shot["i"])
    secs = (shot["i"] - o["i"]) / FPS
    when = "straight into the shot" if passes == 0 and secs < 1 else f"{secs:.1f} s and {passes} pass{'es' if passes != 1 else ''} before the shot"
    return f"{LABEL[o['type']]} by {who}, {when}" + (f"; {how}" if how else "") + "."


# ---------------------------------------------------------------- helpers over the arrays in the file
def _xy(d: dict, pid: int, i: int):
    p = next((p for p in d["players"] if p["id"] == pid), None)
    v = p["xy"][i] if p and 0 <= i < len(p["xy"]) else None
    return None if not v or v[0] is None else v


def _extra(d: dict, pid: int, i: int):
    v = d["extra"].get(str(pid))
    return None if v is None or not 0 <= i < len(v) else v[i]


def _speed(d: dict, pid: int, i0: int, i1: int) -> np.ndarray | None:
    """Speed of a player over [i0, i1] from positions smoothed over five frames, ft/s."""
    pts = [_xy(d, pid, i) for i in range(max(0, i0), min(len(d["holder"]), i1 + 1))]
    if len(pts) < 8 or any(p is None for p in pts):
        return None
    a = np.array(pts, float)
    sm = np.c_[np.convolve(a[:, 0], K5, "valid"), np.convolve(a[:, 1], K5, "valid")]
    return np.hypot(*np.diff(sm, axis=0).T) * FPS


def _gap(d: dict, a: int, b: int, i0: int, i1: int) -> np.ndarray | None:
    pts = [(_xy(d, a, i), _xy(d, b, i)) for i in range(max(0, i0), min(len(d["holder"]), i1 + 1))]
    if any(p is None or q is None for p, q in pts):
        return None
    return np.array([math.hypot(p[0] - q[0], p[1] - q[1]) for p, q in pts])


def _nearest_defender(d: dict, pid: int, i: int):
    """The closest defender to an attacker at frame i: (id, feet), or None."""
    me = _xy(d, pid, i)
    if me is None:
        return None
    best = None
    for p in d["players"]:
        if p["side"] != "defence":
            continue
        q = _xy(d, p["id"], i)
        if q is None:
            continue
        dist = math.hypot(q[0] - me[0], q[1] - me[1])
        if best is None or dist < best[1]:
            best = (p["id"], dist)
    return best


def _angle(a, b) -> float | None:
    """Degrees between two floor vectors (None when either is zero)."""
    na, nb = math.hypot(*a), math.hypot(*b)
    return None if na == 0 or nb == 0 else math.degrees(math.acos(max(-1.0, min(1.0, (a[0] * b[0] + a[1] * b[1]) / (na * nb)))))


def look_at_pass(d: dict, shot: dict, feed: dict, names: dict, stats: dict) -> dict | None:
    """The look, defence: at the pass, the angle at the shooter's defender between his man and the ball (docs/the_look.md)."""
    g = d["guard"][str(shot["player"])]
    d_id = g[feed["i"]] if feed["i"] < len(g) else 0
    me, him, ball = _xy(d, shot["player"], feed["i"]), _xy(d, d_id, feed["i"]) if d_id else None, d["ball"]["xyz"][feed["i"]]
    if not d_id or not me or not him or not ball or ball[0] is None:
        return None
    ang = _angle((me[0] - him[0], me[1] - him[1]), (ball[0] - him[0], ball[1] - him[1]))
    if ang is None:
        return None
    limit = stats.get("look", {}).get("defence", {}).get("threshold_deg", 120)
    lost = ang > limit
    text = f"At the pass, {names.get(d_id, 'his defender')} had {names.get(shot['player'])} and the ball {ang:.0f}° apart: " + ("one of them out of view." if lost else "both in view.")
    return {"angle_deg": round(ang, 0), "lost": lost, "text": text}


def look_at_catch(d: dict, shot: dict, feed: dict, names: dict, stats: dict) -> dict | None:
    """The look, attack: at the catch, the closer's bearing from the direction the ball came from (docs/the_look.md)."""
    co = next((a for a in d["actions"] if a["type"] == "closeout" and a.get("player") == shot["player"] and a.get("defender") and a.get("i") is not None and a["i"] <= shot["i"]), None)
    caught = feed.get("i_end") or feed["i"]
    me, origin, closer = _xy(d, shot["player"], caught), _xy(d, feed["from"], feed["i"]), _xy(d, co["defender"], caught) if co else None
    if not co or not me or not origin or not closer:
        return None
    ang = _angle((origin[0] - me[0], origin[1] - me[1]), (closer[0] - me[0], closer[1] - me[1]))
    if ang is None:
        return None
    limit = stats.get("look", {}).get("attack", {}).get("threshold_deg", 60)
    out = ang > limit
    text = f"At the catch, {names.get(co['defender'])} came from {ang:.0f}° off the ball: " + ("outside the shooter's view." if out else "in the shooter's view.")
    return {"bearing_deg": round(ang, 0), "out_of_view": out, "text": text}


def _percentile_of(value: float, ladder: list[float]) -> int:
    """Where a value sits on a ladder of the 0, 5, …, 100th percentiles."""
    below = sum(1 for v in ladder if v <= value)
    return min(100, max(0, (below - 1) * 5))


def _pos(name: str) -> str:
    """Possessive: Kurucs' top speed, Yusta's man."""
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def _ft(v: float) -> str:
    return f"{v:+.1f} ft" if v is not None else "?"


def _clip(text: str, n: int = 110) -> str:
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


# ---------------------------------------------------------------- the chapters
def build(d: dict, league: dict | None) -> list[dict]:
    n = len(d["holder"])
    shot = the_shot(d)
    if not shot:
        return []
    names = {p["id"]: surname(p["name"]) for p in d["players"]}
    feed = the_feed(d, shot)
    o = origin(d, shot, feed)
    stats = (league or {}).get("stats", {})
    out: list[dict] = []
    cursor = 0

    # 1 · the action
    if o is not None:
        after_catch = feed is not None and feed["i"] < o["i"]  # the shooter created the shot himself after receiving
        i0, i1 = max(0, o["i"] - FPS), min((feed["i"] if feed and not after_catch else shot["i"]) - 1, o["i"] + 30)
        if o["type"] == "pick":
            star, verb = o["screener"], "the screener"
        elif o["type"] == "handoff":
            star, verb = o["setter"], "the man who handed off"
        elif o["type"] == "screen":
            star, verb = o["cutter"], "the cutter"
        else:  # drive, isolation, post: the help that gets pulled
            handler = o.get("player")
            others = [(pid, _extra(d, pid, i1)) for pid in (int(k) for k in d["extra"]) if pid != handler]
            others = [(pid, v) for pid, v in others if v is not None]
            star, verb = (max(others, key=lambda t: t[1])[0] if others else handler), "the most pulled team-mate"
        start, end = _extra(d, star, o["i"]), _extra(d, star, i1)
        label = LABEL[o["type"]] + (f" · defended {o['coverage']}" if o["type"] == "pick" and o.get("coverage") else "")
        near = _nearest_defender(d, star, i1) if end is None else None
        if end is not None:
            big = {"value": round(end, 1), "unit": "ft", "label": f"{verb} beyond his normal spot 1.2 s after the {LABEL[o['type']].lower()}"}
            ctx = f"{label}. {names.get(star, '?')} goes from {_ft(start)} to {_ft(end)} beyond normal in 1.2 s." if start is not None else f"{label}. {names.get(star, '?')} is {_ft(end)} beyond normal 1.2 s later."
        elif near is not None:  # nobody assigned to him: the normal spot has no owner, so the nearest defender stands in
            big = {"value": round(near[1], 1), "unit": "ft", "label": f"nearest defender to {verb} 1.2 s after the {LABEL[o['type']].lower()} · nobody assigned to him"}
            ctx = f"{label}. Nobody on {names.get(star, '?')} 1.2 s later; nearest defender {names.get(near[0], '?')} at {near[1]:.1f} ft."
        else:
            big, ctx = {"value": None, "unit": "ft", "label": f"{verb} beyond his normal spot 1.2 s after the {LABEL[o['type']].lower()}"}, f"{label}."
        out.append({"id": "action", "title": "The action", "i0": i0, "i1": i1, "big": big, "context": _clip(ctx),
                    "league_key": "pick_coverage" if o["type"] == "pick" and "pick_coverage" in stats else "one_more_pass"})
        cursor = i1 + 1

    # 2 · the help (with no labelled action it runs from the start of the file: the stretch in which the shooter got free)
    if feed is not None and feed["i"] - 1 >= cursor + (0 if o is not None else FPS):
        i0, i1 = cursor, feed["i"] - 1
        g = d["guard"][str(shot["player"])]
        first = next((i for i in range(i0, shot["i"] + 1) if g[i] == 0), None)  # the first moment nobody is assigned to the shooter
        last = next((i for i in range(first, shot["i"] + 1) if g[i] != 0), shot["i"] + 1) - 1 if first is not None else None  # the stretch may run on into the race
        if first is not None and last - first + 1 >= FPS:
            secs = (last - first + 1) / FPS
            prev = next((g[i] for i in range(first - 1, -1, -1) if g[i]), None)
            took = next((int(a) for a, arr in d["guard"].items() if int(a) != shot["player"] and arr[min(first + 2, n - 1)] == prev), None) if prev else None
            when = (first - shot["i"]) / FPS
            ctx = f"Nobody assigned to {names.get(shot['player'])} for {secs:.1f} s." + (f" {names.get(prev)} let go at {when:+.1f} s" + (f" to take {names.get(took)}." if took else ".") if prev else "")
            big = {"value": round(secs, 1), "unit": "s", "label": f"with nobody assigned to {names.get(shot['player'])}"}
        else:
            ex = [(i, _extra(d, shot["player"], i)) for i in range(i0, i1 + 1)]
            ex = [(i, v) for i, v in ex if v is not None]
            if ex:
                i_peak, peak = max(ex, key=lambda t: t[1])
                who = names.get(g[i_peak], "his defender")
                big = {"value": round(peak, 1), "unit": "ft", "label": f"{who} beyond his normal spot, at most"}
                ctx = (f"{who} is pulled up to {_ft(peak)} beyond normal at {(i_peak - shot['i']) / FPS:+.1f} s while the ball moves." if peak >= 0
                       else f"{who} stays tighter than normal on the shooter ({_ft(peak)} at most) while the ball moves.")
            else:
                big, ctx = {"value": None, "unit": "ft", "label": "the shooter's defender beyond his normal spot"}, "The ball moves; the shooter's defender is not readable."
        out.append({"id": "help", "title": "The help", "i0": i0, "i1": i1, "big": big, "context": _clip(ctx), "league_key": "unowned_shooter"})
        cursor = i1 + 1

    # 3 · the race (or, when the shooter ran the action himself after the catch, what he did with the ball from there)
    if feed is not None and shot["i"] - 1 >= max(cursor, feed["i"]):
        i0, i1 = max(cursor, feed["i"]), shot["i"] - 1
        co = next((a for a in d["actions"] if a["type"] == "closeout" and a.get("player") == shot["player"] and a.get("i") is not None and a["i"] <= shot["i"]), None)
        race = stats.get("race", {})
        ladder = race.get("closeout_speed_percentiles")
        big, ctx, extra = None, None, {}
        self_made = o is not None and feed["i"] < o["i"]
        if self_made:
            hoop = d["court"]["hoop"]
            me = _xy(d, shot["player"], i0)
            d0 = math.hypot(me[0] - hoop[0], me[1] - hoop[1]) if me else None
            secs = (shot["i"] - i0) / FPS
            big = {"value": round(secs, 1), "unit": "s", "label": f"on the ball from the {LABEL[o['type']].lower()} to the shot"}
            ctx = f"{names.get(shot['player'])} keeps the ball {secs:.1f} s after the {LABEL[o['type']].lower()}" + (f": {d0:.0f} → {shot.get('feet_to_hoop') or 0:.0f} ft from the hoop." if d0 is not None else ".")
        elif co and co.get("defender"):
            gap = _gap(d, co["defender"], shot["player"], feed["i"] - 5, feed["i"] + 45)
            sp = _speed(d, co["defender"], feed["i"], shot["i"] + 5)
            if gap is not None and len(gap) > 12 and sp is not None:
                closing = -np.convolve(np.diff(gap) * FPS, K5, "same")
                on = next((k for k in range(5, len(closing) - 3) if (closing[k:k + 3] > 5).all()), None)
                onset = (on - 5) / FPS if on is not None else None
                top = float(np.percentile(sp, 95))
                pct = _percentile_of(top, ladder) if ladder else None
                at_pass, at_release = float(gap[5]), shot.get("closest_def_ft") or float(gap[-1])
                big = {"value": round(top, 1), "unit": "ft/s", "label": f"{_pos(names.get(co['defender'], 'the defender'))} top speed closing out" + (f" · faster than {pct} % of close-outs" if pct is not None else "")}
                started = f"started {onset:+.2f} s after the pass" if onset is not None else "was already running"
                ctx = f"{names.get(co['defender'])} {started}: {at_pass:.0f} → {at_release:.1f} ft at the release."
                extra = {"onset_s": round(onset, 2) if onset is not None else None, "top_speed_pct": pct, "at_pass_ft": round(at_pass, 1), "at_release_ft": round(float(at_release), 1)}
        if big is None:
            caught = feed.get("i_end") or feed["i"]
            a, b = _xy(d, feed["from"], feed["i"]), _xy(d, feed["to"], caught)
            secs = (caught - feed["i"]) / FPS
            held = (shot["i"] - caught) / FPS
            if a and b and held >= 2:  # he kept the ball: what he did with it, not how fast it came
                hoop = d["court"]["hoop"]
                d0 = math.hypot(b[0] - hoop[0], b[1] - hoop[1])
                big = {"value": round(held, 1), "unit": "s", "label": "on the ball from the catch to the shot · no close-out labelled"}
                ctx = f"{names.get(feed['from'])} to {names.get(feed['to'])}: {math.hypot(b[0] - a[0], b[1] - a[1]):.0f} ft. Then {held:.1f} s on the ball, {d0:.0f} → {shot.get('feet_to_hoop') or 0:.0f} ft from the hoop."
            elif a and b and secs > 0:
                ft = math.hypot(b[0] - a[0], b[1] - a[1])
                big = {"value": round(ft / secs, 0), "unit": "ft/s", "label": "the pass to the shooter"}
                ctx = f"{names.get(feed['from'])} to {names.get(feed['to'])}: {ft:.0f} ft in {secs:.2f} s. No close-out labelled."
            else:
                big, ctx = {"value": None, "unit": "ft/s", "label": "the pass to the shooter"}, "No close-out labelled."
        look = None if self_made else look_at_pass(d, shot, feed, names, stats)
        out.append({"id": "race", "title": "The race", "i0": i0, "i1": i1, "big": big, "context": _clip(ctx), "league_key": "one_more_pass" if self_made and "one_more_pass" in stats else "race", **extra, **({"look": look} if look else {})})
        cursor = i1 + 1

    # 4 · the shot
    i0, i1 = max(cursor, shot["i"]), n - 1
    shooter = next((p for p in d["players"] if p["id"] == shot["player"]), None)
    s3 = shooter.get("season_three") if shooter else None
    kind = KIND.get(shot.get("kind"), "Shot")
    bits = [f"{kind} from {shot['feet_to_hoop']:.0f} ft" if shot.get("feet_to_hoop") is not None else kind]
    if shot.get("closest_def_ft") is not None:
        bits.append(f"{names.get(shot.get('closest_def'), 'defender')} at {shot['closest_def_ft']:.1f} ft")
    if shot.get("three") and s3 and s3.get("attempts"):
        bits.append(f"{names.get(shot['player'])} {s3['made']} of {s3['attempts']} threes ({100 * s3['made'] / s3['attempts']:.0f} %)")
    chapter = {"id": "shot", "title": "The shot", "i0": i0, "i1": i1,
               "big": {"value": round(shot["quality"], 0) if shot.get("quality") is not None else None, "unit": "%", "label": "chance of scoring, by SkillCorner's shot model"},
               "context": _clip(". ".join(bits) + "."), "league_key": "open_three_by_shooter" if shot.get("three") and "open_three_by_shooter" in stats else "shot_selection"}
    price = _price(d, shot, feed, out, stats)
    if price:
        chapter["price"] = price
    look = look_at_catch(d, shot, feed, names, stats) if feed else None
    if look:
        chapter["look"] = look
    out.append(chapter)
    return out


def _price(d: dict, shot: dict, feed: dict | None, chapters: list[dict], stats: dict) -> dict | None:
    """The rotation price of this shot, from the quality fit frozen in the league file (rotations.py; docs/glossary.md, "Price of the rotation")."""
    fit = stats.get("quality_fit")
    if not fit or shot.get("quality") is None or shot.get("closest_def_ft") is None or feed is None:
        return None
    q = rotations.QualityFit.from_rows(fit["rows"])
    region = shot.get("region") or ("ra" if (shot.get("feet_to_hoop") or 99) <= 4 else "three" if shot["three"] else "mid")
    s = {"three": shot["three"], "shotQuality": shot["quality"], "closestDefDist": shot["closest_def_ft"], "region": region,
         "catchAndShoot": shot.get("kind") == "catchAndShoot", "distance": shot.get("feet_to_hoop"), "releaseTime": shot.get("release_s"), "dribblesBefore": 0}
    race = next((c for c in chapters if c["id"] == "race"), None)
    help_ = next((c for c in chapters if c["id"] == "help"), None)
    if race and race.get("onset_s") is not None and race["onset_s"] > 0.04:
        d_cf = rotations.on_time_distance(s, race["onset_s"])
        return {"value": round(q.price(s, d_cf), 2), "kind": "late close-out", "note": f"had the close-out started with the pass: {d_cf:.1f} ft instead of {shot['closest_def_ft']:.1f}"}
    nobody = (help_ is not None and help_["big"]["unit"] == "s") or d["guard"][str(shot["player"])][feed["i"]] == 0  # unowned at the pass, as the ledger reads it
    left_out = _extra(d, shot["player"], feed["i"])
    if nobody or (left_out is not None and left_out >= 6):  # a man left alone, or help never recovered: a defender at the normal spot, at the release
        man, ball = _xy(d, shot["player"], shot["i"]), d["ball"]["xyz"][shot["i"]]
        if man and ball and ball[0] is not None:
            d_cf = rotations.normal_spot_distance(man, ball[:2], d["model"]["normal_spot"], d["court"]["hoop"])
            return {"value": round(q.price(s, d_cf), 2), "kind": "nobody on him" if nobody else "help not recovered",
                    "note": f"a defender at the normal spot would have been at {d_cf:.1f} ft instead of {shot['closest_def_ft']:.1f}"}
    return None
