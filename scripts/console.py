"""The browser console of the viewer, for a few URLs: prints every error, warning and uncaught exception. Run it after any change to the viewer.

    uv run --with websockets scripts/console.py                       # the default URLs: the three HUD levels, the start screen, the old parameters, playing, match pages, roster pages
    uv run --with websockets scripts/console.py "?chance=...&i=200"   # your own
    uv run --with websockets scripts/console.py --site outputs/site     # the static site (courtlab site), served as a plain folder

Starts its own `courtlab serve` on a free port and a headless Chrome with the DevTools protocol; stops both. Exit code 1 if anything was printed.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect

from courtlab.data import LAB

CHROME = os.environ.get("CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
HERO = "chance-191313-1-7"
DEFAULT = [f"?chance={HERO}&motion=0&i=200", f"?chance={HERO}&motion=0&hud=minimal&cam=auto&view=figures&i=300", f"?chance={HERO}&motion=0&hud=none&i=290",
           "?start=1&motion=0&i=290", f"?chance={HERO}&motion=0&fold=1&panel=0&i=200", f"?chance={HERO}&play=1&bc=1&tv=1", f"?chance={HERO}&motion=0&i=1&cam=top",
           "report.html?game=191313&focus=play:chance-191313-1-7&motion=0", "report.html?game=188630&motion=0", "report.html?game=191313&team=away&focus=moment:1&motion=0", "report.html?game=191313&focus=tile:glass",
           "roster.html?game=191313&team=away&player=59205&motion=0", "roster.html?game=114086&motion=0",
           "players.html?motion=0", "players.html?motion=0&view=custom&team=Casademont%20Zaragoza&x=fg&y=season_three&min=20", "players.html?motion=0&view=closeouts&pin=35222:191313",
           "reference.html?motion=0", "reference.html?motion=0&from=lab"]
SETTLE_S = 6


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def watch(ws, url: str) -> list[str]:
    """Navigate and collect what the page complains about for a few seconds."""
    bad: list[str] = []
    ws.send(json.dumps({"id": 1, "method": "Page.navigate", "params": {"url": url}}))
    t0 = time.time()
    while time.time() - t0 < SETTLE_S:
        try:
            msg = json.loads(ws.recv(timeout=0.5))
        except TimeoutError:
            continue
        m, p = msg.get("method"), msg.get("params", {})
        if m == "Runtime.exceptionThrown":
            d = p["exceptionDetails"]
            bad.append(f"exception  {d.get('text', '')} {str(d.get('exception', {}).get('description', ''))[:300]}")
        elif m == "Runtime.consoleAPICalled" and p["type"] in ("error", "warning"):
            bad.append(f"{p['type']:10} " + " ".join(str(a.get("value", a.get("description", ""))) for a in p["args"])[:300])
        elif m == "Log.entryAdded" and p["entry"]["level"] in ("error", "warning"):
            bad.append(f"{p['entry']['level']:10} {p['entry']['text'][:300]}")
    return bad


def main() -> None:
    args = sys.argv[1:]
    site = Path(args[args.index("--site") + 1]) if "--site" in args else None
    urls = [a for a in args if not a.startswith("--") and (site is None or a != str(site))] or DEFAULT
    if not Path(CHROME).exists():
        raise SystemExit(f"Chrome not found at {CHROME}; set CHROME=/path/to/chrome")
    port, cdp = free_port(), free_port()
    profile = LAB / "outputs" / ".chrome-profile-console"
    server = subprocess.Popen([sys.executable, "-m", "http.server", "-d", str(site), str(port)] if site else [sys.executable, "-m", "courtlab.cli", "serve", "--port", str(port)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    chrome = subprocess.Popen([CHROME, "--headless=new", "--use-angle=metal", "--enable-gpu", "--window-size=1920,1080", f"--remote-debugging-port={cdp}", f"--user-data-dir={profile}", "about:blank"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    failed = 0
    try:
        tabs = None
        for _ in range(60):
            try:
                tabs = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{cdp}/json").read())
                break
            except Exception:
                time.sleep(0.25)
        if not tabs:
            raise SystemExit("Chrome did not answer on the DevTools port")
        tab = next(t for t in tabs if t.get("type") == "page")  # the first target can be a browser_ui or a service worker
        with connect(tab["webSocketDebuggerUrl"], max_size=None) as ws:
            for k, method in enumerate(("Runtime.enable", "Log.enable", "Page.enable"), start=10):
                ws.send(json.dumps({"id": k, "method": method}))
            for q in urls:
                bad = watch(ws, f"http://localhost:{port}/{q}")
                failed += bool(bad)
                print(f"{'BAD' if bad else 'OK '}  {q}")
                for b in bad:
                    print(f"       {b}")
    finally:
        chrome.kill()
        server.terminate()
    print(f"{len(urls) - failed} of {len(urls)} pages clean")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
