"""The league figures on the ten public games reproduce what the analysis scripts established (scripts/analysis_*.py; docs/what_did_not_hold.md). Values, not just structure."""

from pathlib import Path

import pytest

from courtlab.data import LAB

HAVE_DATA = (LAB.parent / "opendata-basketball" / "data" / "matches.json").exists() or (LAB / "data" / "opendata-basketball" / "data" / "matches.json").exists()
PUBLIC = {114086, 114099, 114169, 114234, 114243, 178442, 179612, 184439, 188630, 191313}


@pytest.mark.skipif(not HAVE_DATA, reason="open data not downloaded")
def test_league_figures_on_the_public_games():
    from courtlab import league
    from courtlab.data import game_ids
    if set(game_ids()) != PUBLIC:
        pytest.skip("the snapshot is for the ten public games")
    s = league.compute()["stats"]
    assert abs(s["unowned_shooter"]["value"] - 1.10) < 0.03 and s["unowned_shooter"]["n"] == 182
    assert abs(s["unowned_shooter"]["baseline"]["value"] - 0.93) < 0.02 and s["unowned_shooter"]["baseline"]["n"] == 352
    cov = {r["coverage"]: r for r in s["pick_coverage"]["rows"]}
    assert abs(cov["over/show"]["points_per_possession"] - 0.91) < 0.02 and abs(cov["over/show"]["stretch_ft"] - 7.5) < 0.3
    assert abs(cov["switch/switch"]["points_per_possession"] - 0.73) < 0.03
    passes = {r["passes"]: r["value"] for r in s["one_more_pass"]["rows"]}
    assert abs(passes[0] - 0.88) < 0.02 and abs(passes[1] - 1.09) < 0.02 and abs(passes[2] - 1.16) < 0.03
    assert abs(s["race"]["closeout_top_speed"]["value"] - 10.4) < 0.3 and abs(s["race"]["pass_speed"]["value"] - 51) < 2
    assert abs(s["race"]["late_start_price"]["value"] - 0.07) < 0.03
    terc = {r["tercile"]: r for r in s["open_three_by_shooter"]["rows"]}
    assert abs(terc["bottom third"]["scored"] - 0.71) < 0.05 and terc["bottom third"]["scored"] < terc["middle third"]["scored"]
    assert abs(s["crash"]["value"] - 0.16) < 0.03 and s["crash"]["ci"][0] > 0
    back = {r["defenders_back"]: r["points_per_possession"] for r in s["transition"]["rows"]}
    assert back["0-2"] > back["5"]
    assert 0 <= s["transition"]["seconds_to_set"]["value"] < 6 and s["transition"]["seconds_to_set"]["n"] >= 30
    assert s["shot_selection"]["n"] == 20
    assert s["closeouts"]["n"] == 566 and abs(s["closeouts"]["value"] - 0.86) < 0.02
    assert s["rim"]["n"] == 295 and abs(s["rim"]["value"] - 0.56) < 0.02 and s["rim"]["rows"][1]["made"] > s["rim"]["rows"][0]["made"]
    assert s["rotations"]["n"] == 512 and abs(s["rotations"]["value"] - 2.36) < 0.03
    assert [r["n"] for r in s["rotations"]["rows"]] == [299, 146, 67]
    look = s["look"]
    assert look["defence"]["n"] == 694 and abs(look["defence"]["value"] - 0.159) < 0.01 and look["defence"]["expected_points_diff"] > 0 and look["defence"]["expected_points_diff_ci"][0] > 0
    assert look["attack"]["n"] == 562 and abs(look["attack"]["value"] - 0.189) < 0.01
    rows = {r["look"]: r for r in look["attack"]["rows"]}
    assert rows["closer out of view"]["shot"] < rows["closer in view"]["shot"]  # the prediction A3 held the other way: written up in docs/the_look.md
    tree = {r["branch"]: r for r in s["pick_coverage"]["outcomes"]}
    assert tree["pass"]["n"] + tree["shot"]["n"] + tree["foul"]["n"] + tree["turnover"]["n"] <= s["pick_coverage"]["n"]
