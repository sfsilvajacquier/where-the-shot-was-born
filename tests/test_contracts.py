"""The files the package writes match docs/contracts.md. Structure and units, not values (values are tested elsewhere)."""

import json
from pathlib import Path

import pytest

LAB = Path(__file__).resolve().parents[1]
HERO = LAB / "outputs" / "possessions" / "chance-191313-1-7.json"

POSSESSION_V1 = {
    "schema": str, "source": dict, "game": dict, "court": dict, "tv_sideline_y": int, "tv_attack": str, "model": dict, "fps": int,
    "frames": dict, "players": list, "ball": dict, "holder": list, "guard": dict, "ghost": dict, "gap": dict, "extra": dict, "actions": list,
}
POSSESSION_V2 = {**POSSESSION_V1, "chapters": list, "league": dict}
CHAPTER_IDS = ("action", "help", "race", "shot")


def check(obj: dict, spec: dict, where: str) -> None:
    for key, kind in spec.items():
        assert key in obj, f"{where}: missing '{key}'"
        assert isinstance(obj[key], kind), f"{where}: '{key}' should be {kind.__name__}"


@pytest.mark.skipif(not HERO.exists(), reason="run `courtlab export 191313 chance-191313-1-7` first")
def test_possession_matches_the_contract():
    for path in sorted(HERO.parent.glob("*.json")):  # every file exported on this machine, the hero included
        possession_matches_the_contract(json.loads(path.read_text()), path.name)


def possession_matches_the_contract(d: dict, name: str) -> None:
    version = d["schema"].rsplit("/", 1)[-1]
    check(d, POSSESSION_V2 if version == "2" else POSSESSION_V1, "possession")
    n = len(d["frames"]["idx"])
    assert d["fps"] == 25 and n > 0
    assert len(d["frames"]["game_clock"]) == n and len(d["frames"]["shot_clock"]) == n
    assert len(d["players"]) == 10 and {p["side"] for p in d["players"]} == {"attack", "defence"}
    for p in d["players"]:
        assert len(p["xy"]) == n and len(p["seen"]) == n and len(p["err"]) == n
        assert set(p["seen"]) <= {0, 1}
    assert len(d["ball"]["xyz"]) == n and len(d["holder"]) == n
    attackers = {str(p["id"]) for p in d["players"] if p["side"] == "attack"}
    assert set(d["guard"]) == attackers == set(d["gap"]) == set(d["extra"])
    assert all(len(v) == n for v in d["guard"].values())
    assert d["tv_sideline_y"] in (1, -1) and d["tv_attack"] in ("left", "right")
    assert set(d["model"]["normal_spot"]) == {"man", "ball", "hoop"}
    for a in d["actions"]:
        assert "type" in a and "i" in a
        assert a["i"] is None or 0 <= a["i"] < n
    if version == "2":
        assert d["source"].get("role", "play") in ("play", "moment"), name
        ids = [c["id"] for c in d["chapters"]]
        assert ids == [c for c in CHAPTER_IDS if c in ids], f"{name}: chapters out of order"
        assert "shot" in ids and len(ids) >= 3, f"{name}: a play tells at least three chapters"
        shot = next(a for a in d["actions"] if a["type"] == "shot")
        assert shot["i"] < n - 5, f"{name}: the shot sits at the very end of the file (a fragment)"
        last = -1
        for c in d["chapters"]:
            check(c, {"id": str, "title": str, "i0": int, "i1": int, "big": dict, "context": str, "league_key": str}, f"{name} chapter {c.get('id')}")
            assert last <= c["i0"] <= c["i1"] < n, f"{name}: chapters must be contiguous and inside the possession"
            assert len(c["context"]) <= 110 and not c["context"].endswith("…"), f"{name}: chapter {c['id']} context clipped"
            assert c["league_key"] in d["league"]["stats"]
            last = c["i1"]
        check(d["league"], {"schema": str, "generated": str, "games": list, "stats": dict}, "league")


@pytest.mark.skipif(not (LAB / "outputs" / "league.json").exists(), reason="run `courtlab league` first")
def test_league_matches_the_contract():
    d = json.loads((LAB / "outputs" / "league.json").read_text())
    check(d, {"schema": str, "generated": str, "games": list, "n_games": int, "stats": dict}, "league")
    for key, s in d["stats"].items():
        check(s, {"label": str, "unit": str, "source": str}, f"stat {key}")
        assert "value" in s or "rows" in s, f"stat {key}: needs a value or rows"
        if "ci" in s:
            assert s["n"] >= 30 and s["ci"][0] <= s["value"] <= s["ci"][1], f"stat {key}: an interval needs n >= 30 and must contain the value"


@pytest.mark.skipif(not list((LAB / "outputs" / "reports").glob("*.json")) if (LAB / "outputs" / "reports").exists() else True, reason="run `courtlab report <game>` first")
def test_report_matches_the_contract():
    for path in (LAB / "outputs" / "reports").glob("*.json"):
        d = json.loads(path.read_text())
        check(d, {"schema": str, "source": dict, "game": dict, "teams": list}, path.name)
        for team in d["teams"]:
            assert [t["id"] for t in team["tiles"]] == ["transition", "shot_selection", "ball_screens", "closeouts", "rim", "glass", "rotations", "look"]
            for t in team["tiles"]:
                check(t, {"id": str, "title": str, "big": dict, "line": str, "n": int, "detail": list}, f"{path.name} tile {t['id']}")
                assert len(t["detail"]) <= 5
            for m in team["moments"]:
                check(m, {"chance": str, "i": int, "clock": str, "shooter": str, "shot": dict, "origin": str, "rotation": str, "price": dict, "thumb": list}, f"{path.name} moment")


@pytest.mark.skipif(not list((LAB / "outputs" / "possessions").glob("*.json")) if (LAB / "outputs" / "possessions").exists() else True,
                    reason="run `courtlab export` first")
@pytest.mark.parametrize("clips", [False, True])
def test_the_site_never_advertises_a_clip_it_does_not_carry(tmp_path, clips):
    """Home and the match page tag a play `TV clip` straight from the games index. The index is built on this machine, where the
    clips live, so a site written without them used to promise a clip whose viewer had none to show."""
    from courtlab import serve

    out = serve.write_site(LAB / "outputs" / "possessions", tmp_path / "site", clips=clips)
    index = json.loads((out / "games" / "index.json").read_text())
    sync = json.loads((out / "broadcast" / "sync.json").read_text())
    for game in index:
        for play in game["plays"]:
            if play["clip"]:
                entry = sync.get(play["chance"])
                assert entry, f"{play['chance']}: tagged as having a clip, but the site carries no entry for it"
                assert (out / "broadcast" / entry["file"]).exists(), f"{play['chance']}: its clip file was not published"
