"""The reference stills of the viewer, regenerated with headless Chrome. Run it after any change to the viewer and look at them.

    uv run scripts/stills.py                 # writes outputs/stills/*.png
    uv run scripts/stills.py --tag before    # writes outputs/stills/before/*.png, to compare with the next run

Starts its own `courtlab serve` on a free port and stops it. Needs Google Chrome (macOS path below, or CHROME=/path/to/chrome).
"""

from __future__ import annotations

import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from courtlab.data import LAB

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
HERO = "chance-191313-1-7"
STILLS = [  # name, frame, extra query (frame None: the query is the whole path, for the other pages)
    ("1_defence_stretched", 202, ""),
    ("2_pass_beats_the_closeout", 290, ""),
    ("3_the_shot", 345, ""),
    ("4_mannequins_defence_stretched", 202, "&view=figures"),
    ("5_mannequins_the_release", 324, "&view=figures"),
    ("6_camera_top_down", 282, "&cam=top"),
    ("7_camera_eyes_of_kurucs", 297, "&cam=eyes&eyes=59105&view=figures"),
    ("8_camera_behind_the_basket", 282, "&cam=baseline&view=figures"),
    ("9_tv_side_matches_the_broadcast", 324, "&tv=1&view=figures"),
    ("10_broadcast_beside_the_animation", 324, "&tv=1&bc=1"),  # only when a clip sits in broadcast/
    ("11_hud_minimal_director", 300, "&hud=minimal&cam=auto&view=figures"),
    ("12_story_at_the_shot_with_clip", 345, "&bc=1"),
    ("13_hud_none_director", 290, "&hud=none&cam=auto&view=figures"),
    ("0_start_screen", 290, "&start=1&view=figures"),
    ("14_story_action", 150, ""),
    ("15_story_help", 230, ""),
    ("16_story_race", 300, ""),
    ("17_story_shot", 350, ""),
    ("18_hud_full_director", 300, "&hud=full&cam=auto&view=figures"),
    ("19_hud_minimal_broadcast", 300, "&hud=minimal"),
    ("20_hud_none_broadcast", 290, "&hud=none"),
    ("21_report_home_defending", None, "report.html?game=191313&team=home&motion=0"),
    ("22_report_away_moment", None, "report.html?game=191313&team=away&focus=moment:2&motion=0"),
    ("23_report_tile_focused", None, "report.html?game=191313&team=home&focus=tile:rotations&motion=0"),
    ("24_match_featured_play", None, "report.html?game=191313&focus=play:chance-191313-1-7&motion=0"),
    ("25_roster_yusta", None, "roster.html?game=191313&team=away&player=59205&motion=0"),
    ("26_match_the_look", None, "report.html?game=191313&team=home&focus=tile:look&motion=0"),
    ("27_players_discipline", None, "players.html?motion=0&view=discipline&focus=59205:191313"),
    ("28_players_making_pinned", None, "players.html?motion=0&view=making&focus=59205:191313&pin=35222:191313"),
    ("29_references", None, "reference.html?motion=0"),
]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def shoot(port: int, out: Path, frame: int | None, query: str, profile: Path, timeout: float = 40) -> None:
    """Chrome sometimes never exits after --screenshot, so it is killed once the file exists."""
    out.unlink(missing_ok=True)
    url = f"http://localhost:{port}/{query}" if frame is None else f"http://localhost:{port}/?chance={HERO}&i={frame}&motion=0{query}"  # motion=0: no boot fade, no entrance, so a still is a still
    cmd = [CHROME, "--headless=new", "--use-angle=metal", "--enable-gpu", "--hide-scrollbars", "--window-size=1920,1080", "--force-device-scale-factor=1",
           "--virtual-time-budget=6000", f"--user-data-dir={profile}", f"--screenshot={out}", url]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t0 = time.time()
    while time.time() - t0 < timeout and not (out.exists() and out.stat().st_size > 0):
        time.sleep(0.5)
    time.sleep(0.7)
    proc.kill()
    if not out.exists():
        raise SystemExit(f"no screenshot for {out.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--tag", help="write into outputs/stills/<tag>/ instead of outputs/stills/")
    args = ap.parse_args()
    if not Path(CHROME).exists():
        raise SystemExit(f"Chrome not found at {CHROME}; set CHROME=/path/to/chrome")
    folder = LAB / "outputs" / "stills" / (args.tag or "")
    folder.mkdir(parents=True, exist_ok=True)
    profile = LAB / "outputs" / ".chrome-profile"
    port = free_port()
    server = subprocess.Popen([sys.executable, "-m", "courtlab.cli", "serve", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        time.sleep(1.5)
        for name, frame, query in STILLS:
            shoot(port, folder / f"{name}.png", frame, query, profile)
            print(f"  {name}.png")
    finally:
        server.terminate()
        subprocess.run(["pkill", "-f", f"user-data-dir={profile} "], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)  # this profile only: the film's Chrome has its own
    print(f"{len(STILLS)} stills in {folder.relative_to(LAB)}")


if __name__ == "__main__":
    main()
