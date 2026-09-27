"""The roster of the hero game: every player of both teams, every number from the data, the featured shooter as the analysis printed him."""

import pytest

from courtlab.data import LAB

HAVE_DATA = (LAB.parent / "opendata-basketball" / "data" / "matches.json").exists() or (LAB / "data" / "opendata-basketball" / "data" / "matches.json").exists()
HERO_GAME = 191313


@pytest.fixture(scope="module")
def roster():
    if not HAVE_DATA:
        pytest.skip("open data not downloaded")
    from courtlab import roster as ro
    return ro.build(HERO_GAME)


def test_shape(roster):
    assert roster["schema"] == "courtlab.roster/1" and roster["game"]["score"] == [94, 95]
    for t in roster["teams"]:
        assert len(t["players"]) == 12
        secs = [p["game"]["seconds"] for p in t["players"]]
        assert secs == sorted(secs, reverse=True), "starters first: by minutes on the tracked play"
        for p in t["players"]:
            assert set(p) == {"id", "name", "surname", "jersey", "season", "game", "defence", "plays"}, "nothing beyond the data: no height, no birth date, no nationality"
            assert 0 <= p["game"]["seconds"] <= 48 * 60 and p["game"]["distance_ft"] >= 0
            assert p["game"]["top_speed"] is None or 5 < p["game"]["top_speed"] < 30


def test_yusta(roster):
    t = next(t for t in roster["teams"] if t["team"].endswith("Zaragoza"))
    y = next(p for p in t["players"] if p["surname"] == "Yusta")
    assert y["jersey"] == "4" and y["season"]["three"] == [45, 143] and y["season"]["games"] == 31
    assert y["game"]["shots"]["n"] == 10 and y["game"]["shots"]["made"] == 5 and y["game"]["shots"]["three"] == 6
    assert y["defence"]["guarded"][0]["who"] == "Aranitovic" and y["defence"]["closeouts"]["n"] == 12
    assert y["defence"]["extra"]["n"] > 1000 and -3 < y["defence"]["extra"]["mean"] < 6
    assert any(q["chance"] == "chance-191313-1-7" and q["side"] == "attack" for q in y["plays"])


def test_players_index():
    """The players page's index: one row per player and game of the rosters on this machine, every field from the roster."""
    from courtlab import serve
    if not serve.ROSTERS.exists() or not list(serve.ROSTERS.glob("*.json")):
        pytest.skip("no rosters written")
    d = serve.players()
    import json
    listed = sum(len(t["players"]) for p in serve.ROSTERS.glob("*.json") for t in json.loads(p.read_text())["teams"])
    assert d["games"] == len(list(serve.ROSTERS.glob("*.json"))) and len(d["rows"]) == listed
    r = next(x for x in d["rows"] if x["surname"] == "Yusta" and x["game"] == HERO_GAME)
    assert r["team"].endswith("Zaragoza") and r["opponent"].endswith("Breogan") and r["side"] == "away" and r["shots"] == 10 and r["closeouts"] == 12
    assert {"minutes", "distance_ft", "top_speed", "extra", "within_3", "price", "season_three"} <= set(r)
