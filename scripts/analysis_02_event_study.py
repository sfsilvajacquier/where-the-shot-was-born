"""Analysis 2 — what does each action cost the defence? An event study.

    uv run scripts/analysis_02_event_study.py

For every ball screen and every drive, line up the seconds around it and follow two distances for the attackers involved:
how far his assigned defender is (SkillCorner's matchups), and how much farther that is than the defender's normal spot
(0.62·man + 0.15·ball + 0.23·hoop). Read-only.
"""

from __future__ import annotations

import collections
import gzip
import json
import re
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[2] / "opendata-basketball" / "data"
FRAME = re.compile(r'"frameIdx":\s*(\d+)')
STEP, HOOP, W = 5, np.array([-40.75, 0.0]), (0.62, 0.15, 0.23)
TAUS = np.arange(-2.0, 4.01, 0.2)


def main() -> None:
    curves = collections.defaultdict(list)  # key -> list of (game, gap series, extra series)
    for g in json.load(open(DATA / "matches.json")):
        gid = g["id"]
        folder = DATA / "matches" / str(gid)
        ev = json.load(open(folder / f"{gid}_dynamic_events.json"))
        chances = {c["id"]: c for c in ev["chances"]}
        guard = collections.defaultdict(dict)  # frame -> attacker -> defender
        for m in ev["matchups"]:
            a = m["startFrame"]
            for f in range(a - a % STEP + STEP, m["endFrame"] + 1, STEP):
                guard[f][m["offPlayerId"]] = m["defPlayerId"]
        events = []
        for p in ev["picks"]:
            c = chances.get(p["chanceId"])
            if c and c["usable"]:
                events.append((p["frame"], "pick " + str(p["bhrDefType"]), p["ballhandlerId"], p["screenerId"], c))
        for d in ev["drives"]:
            c = chances.get(d["chanceId"])
            f0 = d.get("startFrame") or d.get("frame")
            if c and c["usable"] and f0:
                events.append((f0, "drive, beat his man" if d.get("blowby") else "drive, contained", d.get("ballhandlerId") or d.get("driverId") or d.get("playerId"), None, c))
        need = set()
        for f0, *_ in events:
            base = f0 - f0 % STEP
            need |= {base + int(round(t * 25 / STEP)) * STEP for t in TAUS}
        shots = {s["startFrame"]: s for s in ev["shots"]}
        need |= set(shots)
        frames = {}
        with gzip.open(folder / f"{gid}_tracking_data.jsonl.gz", "rt") as fh:
            for line in fh:
                if '"homePlayers": []' in line:
                    continue
                i = int(FRAME.search(line).group(1))
                if i in need:
                    f = json.loads(line)
                    if f["ball"]:
                        frames[i] = ({p["playerId"]: np.array(p["xyz"][:2]) for p in f["homePlayers"] + f["awayPlayers"]}, np.array(f["ball"]["xyz"][:2]))
        votes = collections.defaultdict(list)
        for fr, s in shots.items():
            if fr in frames and s.get("location") and s["shooterId"] in frames[fr][0]:
                votes[(s["period"], s["offTeamId"])].append(1 if abs(frames[fr][0][s["shooterId"]][0] - s["location"][0]) < 0.5 else -1)
        sign = {k: int(np.sign(np.sum(v))) for k, v in votes.items()}

        def follow(attacker, f0, sg, c):
            gap, extra = np.full(len(TAUS), np.nan), np.full(len(TAUS), np.nan)
            base = f0 - f0 % STEP
            for k, t in enumerate(TAUS):
                fr = base + int(round(t * 25 / STEP)) * STEP
                if fr not in frames or not (c["startFrame"] <= fr <= c["endFrame"]):
                    continue
                pos, ball = frames[fr]
                d_id = guard.get(fr, {}).get(attacker)
                if attacker not in pos or d_id not in pos:
                    continue
                O, D, B = pos[attacker] * sg, pos[d_id] * sg, ball * sg
                spot = W[0] * O + W[1] * B + W[2] * HOOP
                gap[k] = np.hypot(*(D - O))
                extra[k] = gap[k] - np.hypot(*(spot - O))
            return gap, extra

        for f0, kind, first, second, c in events:
            sg = sign.get((c["period"], c["offTeamId"]))
            if sg is None or first is None:
                continue
            curves[kind + " · the ball-handler"].append((gid, *follow(first, f0, sg, c)))
            if second is not None:
                curves[kind + " · the screener"].append((gid, *follow(second, f0, sg, c)))
            mates = [p for p in c["offPlayerIds"] if p not in (first, second)]
            rest = [follow(p, f0, sg, c) for p in mates]
            if rest:  # the most open of the other attackers: is somebody left alone?
                with np.errstate(all="ignore"):
                    curves[kind + " · most open team-mate"].append((gid, np.nanmax([r[0] for r in rest], 0), np.nanmax([r[1] for r in rest], 0)))

    marks = [-1.0, 0.0, 0.6, 1.2, 2.0, 3.0]
    idx = [int(np.argmin(np.abs(TAUS - m))) for m in marks]
    print("feet between an attacker and his assigned defender · in brackets, how much farther than the defender's normal spot")
    print(f"{'':<46}{'n':>5}  " + "  ".join(f"{m:+.1f} s".rjust(13) for m in marks) + "   spread across games at +1.2 s")
    for key in sorted(curves):
        rows = curves[key]
        if len(rows) < 40:
            continue
        game = np.array([r[0] for r in rows]); gap = np.array([r[1] for r in rows]); extra = np.array([r[2] for r in rows])
        with np.errstate(all="ignore"):
            med_g, med_e = np.nanmedian(gap, 0), np.nanmedian(extra, 0)
            per = [np.nanmedian(extra[game == g][:, idx[3]]) for g in np.unique(game) if (game == g).sum() >= 8]
        print(f"{key:<46}{len(rows):>5}  " + "  ".join(f"{med_g[i]:4.1f} ({med_e[i]:+4.1f})".rjust(13) for i in idx) + f"   {np.nanmin(per):+.1f} to {np.nanmax(per):+.1f} ft")


if __name__ == "__main__":
    main()
