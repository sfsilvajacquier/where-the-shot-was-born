"""Checks against what SkillCorner itself measures. They need the open data (`courtlab fetch`); without it they are skipped."""

import json

import numpy as np
import pytest

from courtlab import court, equilibrium
from courtlab.possession import Possession, smooth

try:
    from courtlab.data import Game, data_dir
    data_dir()
    HAVE_DATA = True
except SystemExit:
    HAVE_DATA = False

needs_data = pytest.mark.skipif(not HAVE_DATA, reason="open data not downloaded")
GAME, CHANCE = 191313, "chance-191313-1-7"  # Zaragoza's three after a ball screen defended over the top


def test_hoop_where_fiba_puts_it():
    assert abs(court.HOOP_X - (-40.76)) < 0.01


def test_weights_sum_to_one_and_spot_sits_between():
    assert abs(sum(equilibrium.WEIGHTS.values()) - 1) < 1e-9
    man, ball = np.array([[-20.0, 10.0]]), np.array([[-15.0, -5.0]])
    s = equilibrium.spot(man, ball)[0]
    assert court.HOOP_X < s[0] < -15 and -5 < s[1] < 10


def test_fit_recovers_known_weights():
    rng = np.random.default_rng(0)
    man, ball = rng.uniform(-45, 0, (500, 2)), rng.uniform(-45, 0, (500, 2))
    got = equilibrium.fit(man, ball, equilibrium.spot(man, ball))
    assert all(abs(got[k] - v) < 1e-6 for k, v in equilibrium.WEIGHTS.items())


def test_smoothing_keeps_a_still_player_still_and_survives_gaps():
    still = np.tile([3.0, -2.0], (40, 1))
    assert np.allclose(smooth(still, np.full(40, 1.0)), still)
    holed = still.copy(); holed[10:13] = np.nan
    assert np.allclose(smooth(holed, np.full(40, 1.0)), still)


@needs_data
def test_possession_agrees_with_skillcorner():
    p = Possession.build(Game.load(GAME), CHANCE)
    shot = next(a for a in p.actions() if a["type"] == "shot")
    me = p.xy[shot["player"]][shot["i"]]
    assert np.hypot(*(me - np.array(shot["xy"]))) < 0.25          # orientation and smoothing: same place as the event
    assert abs(p.gap[shot["player"]][shot["i"]] - shot["closest_def_ft"]) < 0.3  # our gap is their closest-defender distance
    assert all(len(v) == len(p.idx) for v in p.xy.values()) and len(p.xy) == 10
    assert np.all(np.diff(p.idx) == 1)


@needs_data
def test_json_is_complete_and_plain(tmp_path):
    path = Possession.build(Game.load(GAME), CHANCE).write(tmp_path)
    d = json.loads(path.read_text())
    assert d["schema"] == "courtlab.possession/2" and len(d["players"]) == 10
    n = len(d["frames"]["idx"])
    assert all(len(pl["xy"]) == n for pl in d["players"]) and len(d["ball"]["xyz"]) == n and len(d["holder"]) == n
    assert {"pick", "pass", "shot"} <= {a["type"] for a in d["actions"]}
    assert path.stat().st_size < 400_000


@needs_data
def test_crash_definition_predicts_the_rebounder():
    """A team-mate who crashes by our definition takes the rebound several times more often than one who does not (events only, all games)."""
    from courtlab import glass
    from courtlab.data import Game, game_ids
    yes = no = yes_reb = no_reb = 0
    for gid in game_ids():
        g = Game.load(gid)
        rows = {}
        for r in g.events["chance_players"]:
            rows.setdefault(r["chanceId"], []).append(r)
        rebs = {r["shotId"]: r for r in g.events["rebounds"] if r["fgReb"] and r["rebounded"]}
        for s in g.events["shots"]:
            rb, c = rebs.get(s["id"]), g.chances.get(s["chanceId"])
            if not rb or not c or not c["usable"] or s["outcome"] or s["fouled"] or s["blocked"]:
                continue
            f = glass.flight(rows.get(s["chanceId"], []), s["shooterId"])
            if not f:
                continue
            for m in f["attack"]:
                got = m["id"] == rb["rebounderId"]
                if glass.crashes(m):
                    yes += 1; yes_reb += got
                else:
                    no += 1; no_reb += got
    lift = (yes_reb / yes) / (no_reb / no)
    print(f"crashers {yes} (rebound {yes_reb / yes * 100:.0f} %) · others {no} (rebound {no_reb / no * 100:.0f} %) · lift {lift:.1f}")
    assert yes > 300 and no > 900
    assert lift > 2.5, f"crashers take the rebound only {lift:.1f}x more often than non-crashers"
