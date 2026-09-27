"""The viewer, served from this machine: static files from `courtlab/viewer/`, possessions from `outputs/possessions/`, reports from `outputs/reports/`,
rosters from `outputs/rosters/`, and one index of the games those make up (`/games/index.json`).

Nothing is compiled and nothing is fetched from the internet: three.js and the typeface are vendored next to the page.

Broadcast clips: if a folder `broadcast/` sits inside this lab (git-ignored; or COURTLAB_BROADCAST points to one) with a `sync.json`,
the viewer can show the real footage beside the animation. The clips never enter the repository and are never read as data.
"""

from __future__ import annotations

import json
import os
import re
import shutil
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from courtlab import chapters, court, report
from courtlab.data import LAB

VIEWER = Path(__file__).resolve().parent / "viewer"
BROADCAST = Path(os.environ.get("COURTLAB_BROADCAST", LAB / "broadcast"))
REPORTS = LAB / "outputs" / "reports"
ROSTERS = LAB / "outputs" / "rosters"
RANGE = re.compile(r"bytes=(\d*)-(\d*)")


def index(folder: Path) -> list[dict]:
    """One line per exported possession, for the games index: who, when, the story in one line, its chapters, and a miniature of the tension strip."""
    rows = []
    clips = json.loads((BROADCAST / "sync.json").read_text()) if (BROADCAST / "sync.json").exists() else {}
    moments = {m["chance"] for p in REPORTS.glob("*.json") for t in json.loads(p.read_text())["teams"] for m in t["moments"]} if REPORTS.exists() else set()
    for path in sorted(folder.glob("*.json")):
        d = json.loads(path.read_text())
        shot = next((a for a in d["actions"] if a["type"] == "shot"), None)
        names = {p["id"]: p["name"] for p in d["players"]}
        clock = d["frames"]["game_clock"][shot["i"]] if shot and shot.get("i") is not None else None
        n = len(d["frames"]["idx"])
        rows.append({"chance": path.stem, "game_id": d["source"]["game_id"], "date": d["game"]["date"], "attack": d["game"]["attack"], "defence": d["game"]["defence"], "home": d["game"]["home"], "away": d["game"]["away"],
                     "clip": path.stem in clips, "moment": d["source"].get("role", "moment" if path.stem in moments else "play") == "moment",
                     "chapters": [{"id": c["id"], "title": c["title"], "value": c["big"]["value"], "unit": c["big"]["unit"]} for c in d.get("chapters", [])],
                     "period": d["game"]["period"], "outcome": d["game"]["outcome"], "shooter": names.get(shot["player"]) if shot else None,
                     "clock": f"{int(clock // 60)}:{int(clock % 60):02d}" if clock is not None else None,
                     "story": chapters.story(d), "thumb": report.thumb(d), "release": shot["i"] / n if shot and shot.get("i") is not None else None})
    return rows


_GAMES: dict = {"key": None, "rows": []}
_PLAYERS: dict = {"key": None, "out": None}


def players() -> dict:
    """One row per player and game, from the rosters on this machine: what the players page compares. Rebuilt when a roster changes."""
    files = sorted(ROSTERS.glob("*.json")) if ROSTERS.exists() else []
    key = tuple((p.name, p.stat().st_mtime_ns) for p in files)
    if key == _PLAYERS["key"]:
        return _PLAYERS["out"]
    rows = []
    for path in files:
        d = json.loads(path.read_text())
        g = d["game"]
        for t in d["teams"]:
            other = g["away"] if t["side"] == "home" else g["home"]
            for p in t["players"]:
                gm, df, s = p["game"], p["defence"], p["season"]
                sh = gm["shots"]
                rows.append({"id": p["id"], "name": p["name"], "surname": p["surname"], "jersey": p["jersey"], "team": t["team"], "opponent": other, "game": d["source"]["game_id"], "date": g["date"], "side": t["side"],
                             "minutes": round(gm["seconds"] / 60, 1), "distance_ft": gm["distance_ft"], "top_speed": gm["top_speed"],
                             "shots": sh["n"], "made": sh["made"], "three": sh["three"], "three_made": sh["three_made"], "quality": sh["quality"], "points": sh["points"],
                             "assists": gm["assists"], "turnovers": gm["turnovers"], "closeouts": df["closeouts"]["n"] if df["closeouts"] else 0,
                             "extra": df["extra"]["mean"] if df["extra"] else None, "within_3": df["extra"]["within_3"] if df["extra"] else None,
                             "conceded": df["conceded"]["n"] if df["conceded"] else 0, "conceded_made": df["conceded"]["made"] if df["conceded"] else 0,
                             "price": df["price"]["value"] if df["price"] else 0.0, "season_three": s["three"] if s else None, "season_cns_three": s["cns_three"] if s else None, "season_games": s["games"] if s else None,
                             # derived, for the players page: intensity, the price per shot conceded (three or more), how his close-outs ended
                             "ft_per_min": round(gm["distance_ft"] / (gm["seconds"] / 60), 1) if gm["seconds"] >= 60 else None,
                             "price_per_conceded": round(df["price"]["value"] / df["conceded"]["n"], 3) if df["price"] and df["conceded"] and df["conceded"]["n"] >= 3 else (0.0 if df["conceded"] and df["conceded"]["n"] >= 3 else None),
                             "co_end": df["closeouts"]["end"] if df["closeouts"] and df["closeouts"]["n"] >= 3 else None, "co_pts": df["closeouts"]["pts"] if df["closeouts"] and df["closeouts"]["n"] >= 3 else None,
                             "conc_dist": df["conceded"]["distance"] if df["conceded"] and df["conceded"]["n"] >= 3 else None})
    out = {"schema": "courtlab.players/2", "source": {"dataset": "SkillCorner Open Data, basketball (github.com/SkillCorner/opendata-basketball, MIT)", "generated_by": "courtlab serve (from the rosters on this machine; nothing hand-edited)",
                      "unit": "one row per player and game: a player who played twice in these games has two rows"}, "games": len(files), "rows": rows}
    _PLAYERS.update(key=key, out=out)
    return out


def games(possessions: Path) -> list[dict]:
    """One row per game with something exported: its plays (the possession rows) and its report (score, rotation costs, moments).
    Rebuilt only when a file under outputs/ changed, since reading every possession takes a couple of seconds."""
    files = sorted(possessions.glob("*.json")) + (sorted(REPORTS.glob("*.json")) if REPORTS.exists() else []) + (sorted(ROSTERS.glob("*.json")) if ROSTERS.exists() else [])
    key = tuple((p.name, p.stat().st_mtime_ns) for p in files)
    if key == _GAMES["key"]:
        return _GAMES["rows"]
    by_game: dict[int, dict] = {}
    for r in index(possessions):
        g = by_game.setdefault(r["game_id"], {"game": r["game_id"], "home": r["home"], "away": r["away"], "date": r["date"], "score": None, "rotations": None, "moments": 0, "plays": []})
        g["plays"].append(r)
    for rep in (report.index(REPORTS) if REPORTS.exists() else []):
        g = by_game.setdefault(rep["game"], {"game": rep["game"], "home": rep["home"], "away": rep["away"], "date": rep["date"], "plays": []})
        g.update(score=rep["score"], rotations=rep["rotations"], moments=rep["moments"], competition=rep["competition"])
    for g in by_game.values():
        g["roster"] = (ROSTERS / f"{g['game']}.json").exists()
    rows = sorted(by_game.values(), key=lambda g: (g["date"] or "", g["game"]), reverse=True)
    _GAMES.update(key=key, rows=rows)
    return rows


def handler(possessions: Path) -> type[SimpleHTTPRequestHandler]:
    class Handler(SimpleHTTPRequestHandler):
        extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".woff2": "font/woff2", ".json": "application/json"}

        def translate_path(self, path: str) -> str:
            clean = path.split("?", 1)[0].split("#", 1)[0]
            if clean.startswith("/possessions/"):
                return str(possessions / Path(clean).name)
            if clean.startswith("/broadcast/"):
                return str(BROADCAST / Path(clean).name)
            if clean.startswith("/reports/"):
                return str(REPORTS / Path(clean).name)
            if clean.startswith("/rosters/"):
                return str(ROSTERS / Path(clean).name)
            self.directory = str(VIEWER)
            return super().translate_path(path)

        def do_HEAD(self) -> None:
            if self.path.split("?", 1)[0].startswith("/broadcast/"):
                f = BROADCAST / Path(self.path.split("?", 1)[0]).name
                if not f.is_file():
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "video/mp4" if f.suffix == ".mp4" else "application/json")
                self.send_header("Content-Length", str(f.stat().st_size))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                return
            super().do_HEAD()

        def video(self, f: Path) -> None:
            """A clip with HTTP range support, which the browser needs to seek."""
            size = f.stat().st_size
            m = RANGE.match(self.headers.get("Range", "") or "")
            start, end = (int(m.group(1) or 0), int(m.group(2) or size - 1)) if m else (0, size - 1)
            end = min(end, size - 1)
            self.send_response(206 if m else 200)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(end - start + 1))
            if m:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with open(f, "rb") as fh:
                fh.seek(start)
                left = end - start + 1
                while left > 0:
                    chunk = fh.read(min(1 << 20, left))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    left -= len(chunk)

        def do_GET(self) -> None:
            clean = self.path.split("?", 1)[0]
            if clean.startswith("/broadcast/"):
                f = BROADCAST / Path(clean).name
                if not f.is_file():
                    self.send_error(404)
                elif f.suffix == ".mp4":
                    try:
                        self.video(f)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                else:
                    super().do_GET()
                return
            made = {"/games/index.json": lambda: games(possessions), "/court.json": court.as_dict, "/players/index.json": players}
            if clean in made:
                body = json.dumps(made[clean]()).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            else:
                super().do_GET()

        def end_headers(self) -> None:
            static = self.path.startswith(("/assets/", "/vendor/"))  # the body, the crests and the libraries: kept, but checked against the file each time (304 when unchanged)
            self.send_header("Cache-Control", "no-cache" if static else "no-store")
            super().end_headers()

        def log_message(self, *args) -> None:  # quiet
            pass

    return Handler


def write_site(possessions: Path, out: Path) -> Path:
    """The viewer as a static site: the pages and their assets, and every JSON this server would answer, written as files. Any static host
    serves it (GitHub Pages, Vercel, a folder on disk); nothing in it is computed on request. No broadcast clip is ever included."""
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(VIEWER, out, ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
    (out / "games").mkdir()
    (out / "games" / "index.json").write_text(json.dumps(games(possessions), ensure_ascii=False))
    (out / "court.json").write_text(json.dumps(court.as_dict()))
    (out / "players").mkdir()
    (out / "players" / "index.json").write_text(json.dumps(players(), ensure_ascii=False))
    for name, folder in (("possessions", possessions), ("reports", REPORTS), ("rosters", ROSTERS)):
        (out / name).mkdir()
        if folder.exists():
            for p in sorted(folder.glob("*.json")):
                shutil.copy(p, out / name / p.name)
    (out / "broadcast").mkdir()
    (out / "broadcast" / "sync.json").write_text("{}")  # no clip, and no 404 when a page looks for one
    (out / ".nojekyll").write_text("")  # GitHub Pages: serve every file as is
    return out


def serve(possessions: Path, port: int = 8000) -> None:
    if not any(possessions.glob("*.json")):
        raise SystemExit(f"no possessions in {possessions}: run `courtlab export --best 3` first")
    server = ThreadingHTTPServer(("127.0.0.1", port), handler(possessions))
    clips = BROADCAST / "sync.json"
    print(f"viewer on http://localhost:{port}  (ctrl-c to stop)" + (f"  · broadcast clips from {BROADCAST}" if clips.exists() else ""))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
