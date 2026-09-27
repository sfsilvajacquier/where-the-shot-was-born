"""The match report of the hero game reproduces what scripts/analysis_09_coach.py prints for it (its part 6), tile by tile."""

import json
from pathlib import Path

import pytest

from courtlab.data import LAB

HAVE_DATA = (LAB.parent / "opendata-basketball" / "data" / "matches.json").exists() or (LAB / "data" / "opendata-basketball" / "data" / "matches.json").exists()
HERO_GAME = 191313


@pytest.fixture(scope="module")
def report(tmp_path_factory):
    if not HAVE_DATA:
        pytest.skip("open data not downloaded")
    from courtlab import report as rp
    return rp.build(HERO_GAME, top=8, folder=tmp_path_factory.mktemp("possessions"))


def tiles(report, team):
    t = next(t for t in report["teams"] if t["team"].endswith(team))
    return t, {tile["id"]: tile for tile in t["tiles"]}


def test_shape(report):
    assert report["schema"] == "courtlab.report/1"
    assert report["game"]["home"].endswith("Breogan") and report["game"]["away"].endswith("Zaragoza") and report["game"]["score"] == [94, 95]
    for t in report["teams"]:
        assert [x["id"] for x in t["tiles"]] == ["transition", "shot_selection", "ball_screens", "closeouts", "rim", "glass", "rotations", "look"]
        look = next(x for x in t["tiles"] if x["id"] == "look")
        assert look["n"] > 0 and 0 <= look["big"]["value"] <= 100 and look["detail"][0]["label"] == "Saw both / lost one"
        assert len(t["moments"]) == 8
        for m in t["moments"]:
            assert len(m["thumb"]) == 5 and all(len(row) == 64 for row in m["thumb"])
            assert m["price"]["kind"] in ("late close-out", "nobody on him", "help not recovered")
        prices = [m["price"]["value"] for m in t["moments"]]
        assert prices == sorted(prices, reverse=True), "most expensive first"
        s = t["story"]
        assert [q["period"] for q in s["quarters"]] == [1, 2, 3, 4] and all(q["scored"] >= 0 and q["expected"] >= 0 for q in s["quarters"])
        assert sum(z["n"] for z in s["zones"]) == len(s["shots"]) and all(s2["zone"] for s2 in s["shots"]) and s["who"] == sorted(s["who"], key=lambda r: -r["price"])
        assert sum(q["shots"] for q in s["quarters"]) == next(x for x in t["tiles"] if x["id"] == "shot_selection")["n"], "the quarters and the shot-selection tile count the same shots"


def test_breogan_defending_matches_the_script(report):
    t, x = tiles(report, "Breogan")
    assert x["closeouts"]["n"] == 30 and abs(x["closeouts"]["big"]["value"] - 1.033) < 0.01
    assert x["rim"]["n"] == 15 and x["rim"]["big"]["value"] == 50.0
    assert x["glass"]["n"] == 23 and abs(x["glass"]["big"]["value"] - 100 * 8 / 23) < 0.01
    assert x["rotations"]["n"] == 24 and abs(x["rotations"]["big"]["value"] - 2.42) < 0.02
    kinds = {r["label"]: r["value"] for r in x["rotations"]["detail"]}
    assert kinds["Late close-out"].startswith("15 ·") and kinds["Nobody on him"].startswith("8 ·") and kinds["Help not recovered"].startswith("1 ·")
    assert kinds["Set defence: catches off a broken rotation"].startswith("15 of 39")
    assert x["shot_selection"]["n"] == 57 and abs(x["shot_selection"]["big"]["value"] - 15.3) < 0.1
    labels = [r["label"] for r in x["transition"]["detail"]]
    assert "All five in their half after (median)" in labels and "Not back when the ball crossed" in labels and len(labels) <= 5


def test_zaragoza_defending_matches_the_script(report):
    t, x = tiles(report, "Zaragoza")
    assert x["closeouts"]["n"] == 33 and abs(x["closeouts"]["big"]["value"] - 0.848) < 0.01
    assert x["rim"]["n"] == 11 and abs(x["rim"]["big"]["value"] - 100 * 2 / 7) < 0.01
    assert x["glass"]["n"] == 28 and abs(x["glass"]["big"]["value"] - 100 * 11 / 28) < 0.01
    assert x["rotations"]["n"] == 38 and abs(x["rotations"]["big"]["value"] - 5.94) < 0.02
    assert {r["label"]: r["value"] for r in x["rotations"]["detail"]}["Set defence: catches off a broken rotation"].startswith("23 of 37")


def test_every_moment_is_priced_like_its_chapter(report, tmp_path_factory):
    """The report's price (the ledger, raw frames) and the play's shot chapter (the file's smoothed positions) agree on kind and value."""
    from courtlab import league, rotations
    lg = league.load()
    fit = rotations.QualityFit.from_rows(lg["stats"]["quality_fit"]["rows"])
    R = league.Rows([HERO_GAME])
    ledger = {r["chance"]: r for r in league.priced(R.ledger, fit)}
    folder = next(p for p in tmp_path_factory.getbasetemp().rglob("possessions*") if p.is_dir())
    seen = 0
    for team in report["teams"]:
        for m in team["moments"]:
            d = json.loads((folder / f"{m['chance']}.json").read_text())
            price = next(c for c in d["chapters"] if c["id"] == "shot").get("price")
            if not price or m["chance"] not in ledger:
                continue
            assert price["kind"] == m["price"]["kind"] == ledger[m["chance"]]["kind"], m["chance"]
            assert abs(price["value"] - m["price"]["value"]) < 0.05, m["chance"]
            seen += 1
    assert seen >= 10


def test_the_hero_possession_is_priced_like_its_chapter(report):
    """The ledger (raw frames) and the shot chapter (the possession file) value the hero's late close-out alike."""
    from courtlab import league, rotations
    lg = league.load()
    fit = rotations.QualityFit.from_rows(lg["stats"]["quality_fit"]["rows"])
    R = league.Rows([HERO_GAME])
    row = next(r for r in league.priced(R.ledger, fit) if r["chance"] == "chance-191313-1-7")
    assert row["kind"] == "late close-out" and abs(row["price"] - 0.06) < 0.02
    hero = LAB / "outputs" / "possessions" / "chance-191313-1-7.json"
    if hero.exists():
        chapter = next(c for c in json.loads(hero.read_text())["chapters"] if c["id"] == "shot")
        assert chapter["price"]["kind"] == row["kind"] and abs(chapter["price"]["value"] - row["price"]) < 0.03
