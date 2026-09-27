"""Does the basketball open data match its documentation? A read-only check over the 10 games.

    uv run scripts/probe_data.py

Prints, per game: frames, live share, detected share, players per live frame, whether the final score is
reproduced from shots + free throws, and how event coordinates relate to tracking coordinates.
Then: event volumes and how SkillCorner's own shotQuality score behaves against outcomes.
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


def main() -> None:
    games = json.load(open(DATA / "matches.json"))
    shots_all, volumes = [], collections.Counter()
    print("game    frames  live%  det%  5v5%  score  shots  =tracking  =mirrored  unplaced  hoop the home team attacks, by period")
    for g in games:
        gid = g["id"]
        folder = DATA / "matches" / str(gid)
        ev = json.load(open(folder / f"{gid}_dynamic_events.json"))
        meta = json.load(open(folder / f"{gid}_game_data.json"))
        home = {p["playerId"] for p in meta["homeTeam"]["players"]}
        for k, v in ev.items():
            volumes[k] += len(v)

        pts = collections.Counter()
        for s in ev["shots"]:
            pts[s["offTeamId"]] += (3 if s["three"] else 2) * bool(s["outcome"])
        for ft in ev["free_throws"]:
            pts[ft["offTeamId"]] += str(ft["outcome"]).lower() == "true"
        score_ok = (pts[meta["homeTeam"]["teamId"]], pts[meta["awayTeam"]["teamId"]]) == (g["home_score"], g["away_score"])

        want = {s["startFrame"]: s for s in ev["shots"]}
        n = live = det = seen = full = 0
        got = {}
        with gzip.open(folder / f"{gid}_tracking_data.jsonl.gz", "rt") as fh:
            for line in fh:
                n += 1
                if '"homePlayers": []' in line or '"homePlayers":[]' in line:
                    continue  # dead time: clocks only
                live += 1
                idx = int(FRAME.search(line).group(1))
                if live % 25 and idx not in want:
                    continue  # quality is sampled once a second; shot frames are always read
                f = json.loads(line)
                if live % 25 == 0:
                    players = f["homePlayers"] + f["awayPlayers"]
                    det += sum(p["isDetected"] for p in players)
                    seen += len(players)
                    full += len(f["homePlayers"]) == 5 and len(f["awayPlayers"]) == 5
                if idx in want:
                    got[idx] = f

        same = mirrored = unplaced = 0
        sides: dict[int, set[str]] = {}
        for fr, s in want.items():
            f = got.get(fr)
            p = f and next((q for q in f["homePlayers"] + f["awayPlayers"] if q["playerId"] == s["shooterId"]), None)
            if not p or not s.get("location"):
                unplaced += 1
                continue
            (ex, ey), (tx, ty) = s["location"], p["xyz"][:2]
            if np.hypot(ex - tx, ey - ty) < 0.5:
                same, sign = same + 1, 1
            elif np.hypot(ex + tx, ey + ty) < 0.5:
                mirrored, sign = mirrored + 1, -1
            else:
                unplaced += 1
                continue
            attacks_negative = (sign > 0) == (s["shooterId"] in home)  # events always put the offensive hoop at -x
            sides.setdefault(s["period"], set()).add("-x" if attacks_negative else "+x")
        print(f"{gid}  {n:6d}  {live / n * 100:4.0f}  {det / seen * 100:4.0f}  {full / (live // 25) * 100:4.0f}  {'ok' if score_ok else 'NO':>5}  "
              f"{len(ev['shots']):5d}  {same:9d}  {mirrored:9d}  {unplaced:8d}  " + " ".join(f"{k}:{'/'.join(sorted(v))}" for k, v in sorted(sides.items())))
        shots_all += ev["shots"]

    print("\nevents in the 10 games:", dict(volumes))
    scored = [s for s in shots_all if s.get("shotQuality") is not None]
    sq = np.array([s["shotQuality"] for s in scored])
    made = np.array([bool(s["outcome"]) for s in scored])
    points = np.array([(3 if s["three"] else 2) * bool(s["outcome"]) for s in scored])
    print(f"\nshots {len(shots_all)} · with shotQuality {len(scored)} · made {np.mean([bool(s['outcome']) for s in shots_all]) * 100:.1f}% · threes {np.mean([s['three'] for s in shots_all]) * 100:.0f}%")
    edges = np.quantile(sq, [0, 0.2, 0.4, 0.6, 0.8, 1])
    for a, b in zip(edges[:-1], edges[1:]):
        m = (sq >= a) & (sq <= b)
        print(f"  shotQuality {a:5.1f}-{b:5.1f}: n={m.sum():4d} · mean {sq[m].mean():5.1f} · made {made[m].mean() * 100:4.1f}% · points per shot {points[m].mean():.2f}")
    for level in ("open", "light", "average", "plus", "blocked"):
        m = [s for s in shots_all if s["contestLevel"] == level]
        dist = [s["closestDefDist"] for s in m if s.get("closestDefDist") is not None]
        print(f"  contest {level:<8} n={len(m):4d} · made {np.mean([bool(s['outcome']) for s in m]) * 100:4.1f}% · closest defender, median {np.median(dist):.1f} ft")


if __name__ == "__main__":
    main()
