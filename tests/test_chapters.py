"""The chapters of the hero possession say what the analyses found (scripts/analysis_*.py), and a play from the other family also gets chapters."""

import json
from pathlib import Path

import pytest

from courtlab import chapters
from courtlab.data import LAB

HERO = LAB / "outputs" / "possessions" / "chance-191313-1-7.json"
KICKOUT = LAB / "outputs" / "possessions" / "chance-114234-3-126.json"


@pytest.mark.skipif(not HERO.exists(), reason="run `courtlab export 191313 chance-191313-1-7` first")
def test_hero_chapters():
    d = json.loads(HERO.read_text())
    ch = {c["id"]: c for c in d["chapters"]}
    assert [c["id"] for c in d["chapters"]] == ["action", "help", "race", "shot"]
    assert abs(ch["action"]["big"]["value"] - 9.4) < 0.3 and "Olaseni" in ch["action"]["context"]      # the screener freed 1.2 s after the screen
    assert ch["help"]["big"]["unit"] == "s" and abs(ch["help"]["big"]["value"] - 3.4) < 0.15            # nobody on Yusta, as the strip says
    assert "Aranitovic" in ch["help"]["context"]
    assert abs(ch["race"]["onset_s"] - 0.16) < 0.05 and ch["race"]["top_speed_pct"] >= 90 and "Kurucs" in ch["race"]["context"]
    assert ch["shot"]["big"]["value"] == 41 and ch["shot"]["price"]["kind"] == "late close-out" and 0 < ch["shot"]["price"]["value"] < 0.2
    assert chapters.story(d).startswith("Ball screen · over → 5 passes → Yusta")
    assert chapters.build(d, d["league"]) == d["chapters"]  # the same code on the file gives the same chapters


@pytest.mark.skipif(not KICKOUT.exists(), reason="run `courtlab export --best 7` first")
def test_kickout_play_has_chapters():
    d = json.loads(KICKOUT.read_text())
    ids = [c["id"] for c in d["chapters"]]
    assert ids[0] == "action" and ids[-1] == "shot" and d["chapters"][0]["league_key"] == "one_more_pass"
