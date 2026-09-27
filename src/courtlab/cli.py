"""courtlab fetch | league | find | export | report | roster | serve | site — the data is downloaded and every derived file is generated on this machine.

    uv run courtlab fetch                          # clone SkillCorner's public dataset (git + git-lfs, about 400 MB)
    uv run courtlab league                         # the league figures the chapters quote, from the games on this machine (about a minute)
    uv run courtlab find [--story pick|kickout]   # possessions that tell a whole story, ranked
    uv run courtlab export 191313 chance-191313-2-31
    uv run courtlab export --best 3                # the top of `find`, straight to outputs/possessions/
    uv run courtlab export --per-game 1            # the best candidate of every game, so Home lists them all
    uv run courtlab report --all                   # every match as a defensive staff reads it: outputs/reports/<game>.json (+ the possessions of its moments, + its roster)
    uv run courtlab roster --all                   # the roster of every match on its own: outputs/rosters/<game>.json
    uv run courtlab serve                          # the viewer, on http://localhost:8000
    uv run courtlab site                           # the viewer as a static folder, outputs/site/, for GitHub Pages or any static host
"""

from __future__ import annotations

import argparse
import json

from pathlib import Path

from courtlab import data, find, league, report, roster, serve
from courtlab.data import LAB, Game
from courtlab.possession import Possession

OUT = LAB / "outputs" / "possessions"


def main() -> None:
    ap = argparse.ArgumentParser(prog="courtlab", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch", help="download the open data")
    sub.add_parser("league", help="compute the league figures into outputs/league.json")
    f = sub.add_parser("find", help="rank the possessions worth showing")
    f.add_argument("--top", type=int, default=12)
    f.add_argument("--story", choices=("all", *find.STORIES), default="all", help="pick: ball screen → passes → three · kickout: drive → pass out → three")
    e = sub.add_parser("export", help="write one possession as JSON")
    e.add_argument("game", nargs="?", type=int)
    e.add_argument("chance", nargs="?")
    e.add_argument("--best", type=int, help="export the first N of `find` instead")
    e.add_argument("--per-game", type=int, help="export the N best candidates of every game (made, then quality) and the featured play, so Home lists every game")
    e.add_argument("--story", choices=("all", *find.STORIES), default="all")
    r = sub.add_parser("report", help="write the match report of one or more games")
    r.add_argument("games", nargs="*", type=int)
    r.add_argument("--all", action="store_true", help="every game on this machine")
    r.add_argument("--moments", type=int, default=6, help="conceded shots to export per defending team (default 6)")
    ro = sub.add_parser("roster", help="write the roster of one or more games (report writes it too)")
    ro.add_argument("games", nargs="*", type=int)
    ro.add_argument("--all", action="store_true", help="every game on this machine")
    v = sub.add_parser("serve", help="open the viewer on the possessions exported here")
    v.add_argument("--port", type=int, default=8000)
    st = sub.add_parser("site", help="write the viewer and its data as a static site")
    st.add_argument("--out", default=str(LAB / "outputs" / "site"))
    st.add_argument("--clips", action="store_true", help="also publish the broadcast clips in broadcast/ (shown beside the animation, never read as data)")
    args = ap.parse_args()

    if args.cmd == "fetch":
        print("data in", data.fetch())
    elif args.cmd == "league":
        path = league.write()
        d = league.load(path)
        print(f"wrote {path.relative_to(data.LAB)}  ({len(d['stats'])} figures from {d['n_games']} games)")
    elif args.cmd == "find":
        rows = find.rank(find.candidates(args.story), args.top)
        print(f"{'game':>7} {'chance':<22} {'story':<8} {'attack':<22} {'shooter':<16} made  quality contest  def ft passes  secs  seen  peak extra")
        for r in rows:
            print(f"{r['game']:>7} {r['chance']:<22} {r['story']:<8} {r['attack'][:21]:<22} {r['shooter'][:15]:<16} {'yes' if r['made'] else 'no ':<4}  {r['quality']:6.1f} {r['contest']:<8} "
                  f"{r['defender_ft']:5.1f} {r['passes']:>5}  {r['seconds']:5.1f}  {r['seen'] * 100:3.0f}%  {r['peak_extra_ft']:+6.1f} ft")
    elif args.cmd == "report":
        if not args.games and not args.all:
            ap.error("give one or more game ids, or --all")
        for gid in (data.game_ids() if args.all else args.games):
            path = report.write(gid, args.moments)
            d = json.loads(path.read_text())
            print(f"wrote {path.relative_to(LAB)}  ({d['game']['home']} {d['game']['score'][0]}–{d['game']['score'][1]} {d['game']['away']}; {sum(len(t['moments']) for t in d['teams'])} moments exported)")
            print(f"wrote {roster.write(gid).relative_to(LAB)}")
    elif args.cmd == "roster":
        if not args.games and not args.all:
            ap.error("give one or more game ids, or --all")
        for gid in (data.game_ids() if args.all else args.games):
            print(f"wrote {roster.write(gid).relative_to(LAB)}")
    elif args.cmd == "serve":
        serve.serve(OUT, args.port)
    elif args.cmd == "site":
        out = serve.write_site(OUT, Path(args.out), clips=args.clips)
        n = sum(1 for p in out.rglob("*") if p.is_file())
        mb = sum(p.stat().st_size for p in out.rglob("*") if p.is_file()) / 1e6
        print(f"wrote {out}  ({n} files, {mb:.0f} MB) · serve it from any static host, or try it: python3 -m http.server -d {out} 8001")
    elif args.cmd == "export":
        if args.per_game:
            by_game: dict[int, list] = {}
            for r in sorted(find.candidates(args.story), key=lambda r: (-r["made"], -r["quality"])):
                by_game.setdefault(r["game"], []).append(r)
            todo = [(r["game"], r["chance"]) for rows in by_game.values() for r in rows[:args.per_game]]
            if find.FEATURED not in todo:
                todo.append(find.FEATURED)
        else:
            todo = [(r["game"], r["chance"]) for r in find.rank(find.candidates(args.story), args.best)] if args.best else [(args.game, args.chance)]
        if not args.best and not args.per_game and (args.game is None or args.chance is None):
            ap.error("give a game id and a chance id, or --best N, or --per-game N")
        games: dict[int, Game] = {}
        for gid, cid in todo:
            path = Possession.build(games.setdefault(gid, Game.load(gid)), cid).write(OUT)
            print(f"wrote {path.relative_to(LAB)}  ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
