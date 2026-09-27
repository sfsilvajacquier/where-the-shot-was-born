"""One scoring chance as everything a viewer needs: smoothed positions, who guards whom, each defender's normal spot,
the tension on every attacker, and the actions SkillCorner labels. Written as a small JSON file, generated locally."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from courtlab import chapters, court, equilibrium, league
from courtlab.data import Game, season_shooting

SCHEMA = "courtlab.possession/2"
FPS = 25
KERNEL = np.exp(-0.5 * (np.arange(-4, 5) / 2.0) ** 2)  # nine frames (0.36 s), most of the weight inside +-2 frames
P90_TO_SIGMA = 2.146  # predError is a 90 % radius; for an isotropic 2-D gaussian that is 2.146 sigma
MIN_MATCHUP = 5  # frames. 16 % of SkillCorner's matchup rows last under 0.2 s and nine in ten of those sit on a chance's last frame: a reset, not a marking


def _r(value, digits: int = 1):
    """Round what is there; SkillCorner leaves some measurements empty."""
    return None if value is None else round(value, digits)


def smooth(values: np.ndarray, err: np.ndarray | None = None) -> np.ndarray:
    """Centred weighted average. Each sample also weighs by how well it was measured (1 / sigma^2), so an extrapolated
    position between two detected ones gives way to them. NaNs are skipped; edges renormalise."""
    v = np.atleast_2d(values.T).T.astype(float)
    ok = ~np.isnan(v).any(1)
    w = ok / np.maximum((err if err is not None else np.ones(len(v))) / P90_TO_SIGMA, 0.3) ** 2
    num = np.stack([np.convolve(np.nan_to_num(v[:, k]) * w, KERNEL, mode="same") for k in range(v.shape[1])], 1)
    den = np.convolve(w, KERNEL, mode="same")[:, None]
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den > 0, num / den, np.nan)
    return out.reshape(values.shape)


@dataclass
class Possession:
    game: Game
    chance: dict
    idx: np.ndarray                      # tracking frame numbers, contiguous
    game_clock: np.ndarray
    shot_clock: np.ndarray
    xy: dict[int, np.ndarray]            # player -> (n, 2), feet, attacked hoop at negative x, smoothed
    seen: dict[int, np.ndarray]          # player -> (n,) bool: on camera, not extrapolated
    err: dict[int, np.ndarray]           # player -> (n,) SkillCorner's expected error, feet
    ball: np.ndarray                     # (n, 3)
    ball_seen: np.ndarray
    guard: dict[int, np.ndarray]         # attacker -> (n,) id of his assigned defender, 0 when nobody is
    holder: np.ndarray                   # (n,) id of the player on the ball, 0 while it travels
    ghost: dict[int, np.ndarray] = field(default_factory=dict)   # defender -> (n, 2) his normal spot
    gap: dict[int, np.ndarray] = field(default_factory=dict)     # attacker -> (n,) feet to his defender
    extra: dict[int, np.ndarray] = field(default_factory=dict)   # attacker -> (n,) feet beyond the normal spot

    @classmethod
    def build(cls, game: Game, chance_id: str, lead_s: float = 1.0, tail_s: float = 2.0, before_shot_s: float = 8.0) -> "Possession":
        """The window: from `lead_s` before the ball crossed into the front court, or earlier when the shot came fast or the pass that
        fed the shooter was thrown from the back court (at least `before_shot_s` before the shot and 2 s before that pass), never
        earlier than a second before the chance began; to `tail_s` after the chance, stopping at the first hole in the tracking."""
        c = game.chances[chance_id]
        sg = game.sign(c)
        first = (c["frontcourtFrame"] or c["startFrame"]) - int(lead_s * FPS)
        shots = [s for s in game.events["shots"] if s["chanceId"] == chance_id]
        if shots:
            shot = shots[-1]
            first = min(first, shot["startFrame"] - int(before_shot_s * FPS))
            feeds = [p for p in game.events["passes"] if p["chanceId"] == chance_id and p["complete"] and p["receiverId"] == shot["shooterId"] and p["startFrame"] <= shot["startFrame"]]
            if feeds:
                first = min(first, max(feeds, key=lambda p: p["startFrame"])["startFrame"] - 2 * FPS)
        raw = game.frames(max(first, c["startFrame"] - FPS), c["endFrame"] + int(tail_s * FPS))
        # the tracking has holes wherever the broadcast cut away and after a basket: keep the one live stretch that holds the shot
        # (or the end of the chance), so a play is never a fragment with its shot clamped to the last frame
        anchor = shots[-1]["startFrame"] if shots else c["endFrame"]
        segments, start = [], 0
        for k in range(1, len(raw) + 1):
            if k == len(raw) or raw[k]["frameIdx"] != raw[k - 1]["frameIdx"] + 1:
                segments.append(raw[start:k]); start = k
        raw = next((seg for seg in segments if seg[0]["frameIdx"] <= anchor <= seg[-1]["frameIdx"]),
                   next((seg for seg in reversed(segments) if seg[0]["frameIdx"] <= anchor), segments[0] if segments else raw))
        n = len(raw)
        idx = np.array([f["frameIdx"] for f in raw])
        ids = list(c["offPlayerIds"]) + list(c["defPlayerIds"])
        pos = {p: np.full((n, 2), np.nan) for p in ids}
        seen = {p: np.zeros(n, bool) for p in ids}
        err = {p: np.full(n, np.nan) for p in ids}
        ball, ball_seen, ball_err = np.full((n, 3), np.nan), np.zeros(n, bool), np.full(n, np.nan)
        for k, f in enumerate(raw):
            for p in f["homePlayers"] + f["awayPlayers"]:
                if p["playerId"] in pos:
                    pos[p["playerId"]][k] = (p["xyz"][0] * sg, p["xyz"][1] * sg)
                    seen[p["playerId"]][k], err[p["playerId"]][k] = bool(p["isDetected"]), p["predError"]
            b = f["ball"]
            ball[k], ball_seen[k], ball_err[k] = (b["xyz"][0] * sg, b["xyz"][1] * sg, b["xyz"][2]), bool(b["isDetected"]), b["predError"]
        xy = {p: smooth(pos[p], err[p]) for p in ids}
        ball = np.c_[smooth(ball[:, :2], ball_err), smooth(ball[:, 2])]

        at = {int(i): k for k, i in enumerate(idx)}
        guard = {p: np.zeros(n, int) for p in c["offPlayerIds"]}
        for m in game.events["matchups"]:
            if m["chanceId"] == chance_id and m["offPlayerId"] in guard and m["endFrame"] - m["startFrame"] >= MIN_MATCHUP:
                a, b = at.get(max(m["startFrame"], int(idx[0])), None), at.get(min(m["endFrame"], int(idx[-1])), None)
                if a is not None and b is not None and b >= a:
                    guard[m["offPlayerId"]][a:b + 1] = m["defPlayerId"]
        lead = sum(1 for i in idx if i < c["startFrame"])  # frames before the chance began, which have no matchup of their own
        for p, g in guard.items():  # carry the first assignment back over that lead-in only; inside the chance, nobody means nobody
            known = np.flatnonzero(g)
            if len(known) and known[0] > 0:
                g[:min(known[0], lead)] = g[known[0]]
        holder = np.zeros(n, int)
        for t in game.events["touches"]:
            if t["chanceId"] == chance_id:
                a, b = max(t["startFrame"], int(idx[0])), min(t["endFrame"], int(idx[-1]))
                if b >= a:
                    holder[at[a]:at[b] + 1] = t["playerId"]

        self = cls(game, c, idx, np.array([f["gameClock"] for f in raw]), np.array([f["shotClock"] if f["shotClock"] is not None else np.nan for f in raw]),
                   xy, seen, err, ball, ball_seen, guard, holder)
        self.ghost = {d: np.full((n, 2), np.nan) for d in c["defPlayerIds"]}
        for o in c["offPlayerIds"]:
            self.gap[o], self.extra[o] = np.full(n, np.nan), np.full(n, np.nan)
            for d in np.unique(guard[o][guard[o] > 0]):
                m = guard[o] == d
                if d in xy:
                    self.ghost[int(d)][m] = equilibrium.spot(xy[o][m], ball[m, :2])
                    self.gap[o][m], self.extra[o][m] = equilibrium.extra(xy[o][m], ball[m, :2], xy[int(d)][m])
        return self

    # ------------------------------------------------------------------ what happened, in frame positions of this window
    def actions(self) -> list[dict]:
        ev, cid, at = self.game.events, self.chance["id"], {int(i): k for k, i in enumerate(self.idx)}
        where = lambda frame: None if frame is None else at.get(int(min(max(frame, self.idx[0]), self.idx[-1])))  # noqa: E731  (some passes have no end frame)
        mine = lambda table: [e for e in ev[table] if e["chanceId"] == cid]  # noqa: E731
        out = []
        for e in mine("picks"):
            out.append({"type": "pick", "i": where(e["frame"]), "handler": e["ballhandlerId"], "screener": e["screenerId"],
                        "handler_def": e["ballhandlerDefId"], "screener_def": e["screenerDefId"], "coverage": e["bhrDefType"],
                        "screener_coverage": e["scrDefType"], "xy": e["location"], "direct": e["direct"]})
        for e in mine("handoffs"):
            out.append({"type": "handoff", "i": where(e["frame"]), "setter": e["setterId"], "receiver": e["receiverId"],
                        "coverage": e["receiverDefType"], "xy": e["location"]})
        for e in mine("off_ball_screens"):
            out.append({"type": "screen", "i": where(e["frame"]), "cutter": e["cutterId"], "screener": e["screenerId"],
                        "coverage": e["cutterDefType"], "xy": e["location"]})
        for e in mine("drives"):
            out.append({"type": "drive", "i": where(e["startFrame"]), "i_end": where(e["endFrame"]), "player": e["ballhandlerId"],
                        "beat_his_man": bool(e["blowby"]), "how_it_ended": e["endType"], "from": e["location"], "to": e["endLoc"]})
        for table in ("isolations", "posts"):
            for e in mine(table):
                out.append({"type": table[:-1], "i": where(e["startFrame"]), "i_end": where(e["endFrame"]), "player": e["ballhandlerId"]})
        for e in mine("closeouts"):
            out.append({"type": "closeout", "i": where(e["startFrame"]), "i_touch": where(e["touchFrame"]), "i_end": where(e["endFrame"]),
                        "player": e["ballhandlerId"], "defender": e["ballhandlerDefId"],
                        "feet": [_r(e["startDistance"]), _r(e["touchDistance"]), _r(e["endDistance"])]})
        for e in mine("passes"):
            out.append({"type": "pass", "i": where(e["startFrame"]), "i_end": where(e["endFrame"]), "from": e["passerId"], "to": e["receiverId"],
                        "complete": e["complete"], "led_to_shot": e["ledToShot"]})
        for e in mine("dribbles"):
            out.append({"type": "dribble", "i": where(e["frame"]), "player": e["ballhandlerId"]})
        for e in mine("shots"):
            out.append({"type": "shot", "i": where(e["startFrame"]), "i_end": where(e["endFrame"]), "player": e["shooterId"], "three": e["three"],
                        "made": bool(e["outcome"]), "fouled": e["fouled"], "quality": _r(e["shotQuality"]),
                        "contest": e["contestLevel"], "closest_def": e["closestDefId"],
                        "closest_def_ft": _r(e["closestDefDist"]),
                        "kind": e["complexShotType"], "region": e["region"], "release_s": e["releaseTime"], "feet_to_hoop": _r(e["distance"]),
                        "xy": e["location"], "from_paint": e["createdFromPaint"], "assisted": e["assisted"]})
        for e in mine("rebounds"):
            out.append({"type": "rebound", "i": where(e["frame"]), "player": e["rebounderId"], "defensive": e["defensive"]})
        for e in mine("turnovers"):
            out.append({"type": "turnover", "i": where(e["frame"]), "player": e["turnedOverId"], "stolen_by": e["stealerId"]})
        for e in mine("fouls"):
            out.append({"type": "foul", "i": where(e["frame"]), "by": e["foulerId"], "on": e["fouledId"], "shooting": e["shooting"]})
        return sorted((a for a in out if a["i"] is not None), key=lambda a: a["i"])

    def to_dict(self, role: str = "play") -> dict:
        """`role`: "play" when exported on its own merit (Home lists it), "moment" when a match report exported it as one of its moments."""
        g, c = self.game, self.chance
        num = lambda a, nd=2: [None if np.isnan(v) else round(float(v), nd) for v in a]  # noqa: E731
        pts = lambda a, nd=2: [None if np.isnan(r).any() else [round(float(v), nd) for v in r] for r in a]  # noqa: E731
        shooting = season_shooting()
        players = []
        for p in list(c["offPlayerIds"]) + list(c["defPlayerIds"]):
            who, rec = g.players[p], shooting.get(p)
            players.append({"id": p, "name": f"{who['firstName']} {who['lastName']}".strip(), "jersey": who["jersey"],
                            "side": "attack" if p in c["offPlayerIds"] else "defence",
                            "season_three": None if not rec or rec["three_att"] < 1 else {"made": int(rec["three_made"]), "attempts": int(rec["three_att"])},
                            "xy": pts(self.xy[p]), "seen": [int(v) for v in self.seen[p]], "err": num(self.err[p], 1)})
        d = {
            "schema": SCHEMA,
            "source": {"dataset": "SkillCorner Open Data, basketball (github.com/SkillCorner/opendata-basketball, MIT)",
                       "game_id": g.id, "chance_id": c["id"], "generated_by": "courtlab export (nothing in this file is hand-edited)", "role": role},
            "game": {"date": g.meta["date"][:10], "competition": f"{g.meta['competitionName']} {g.meta['seasonName']}",
                     "home": g.meta["homeTeam"]["teamName"], "away": g.meta["awayTeam"]["teamName"],
                     "attack": g.team_name(c["offTeamId"]), "defence": g.team_name(c["defTeamId"]), "period": c["period"],
                     "score_before": [c["homeStartScore"], c["awayStartScore"]], "points": c["ptsScored"], "outcome": c["outcome"],
                     "how_it_started": c["startType"], "transition": c["transition"]},
            "court": court.as_dict(),
            # SkillCorner's raw frame: x runs left→right on the broadcast picture, and y grows TOWARDS the camera (the documentation says
            # bottom→top; a broadcast frame of the Zaragoza three says otherwise), so the frame is a mirror of the court and the camera sits at raw y > 0.
            # After normalising the attack to −x, that sideline is at +y when the team attacked the left hoop and at −y when it attacked the right one.
            "tv_sideline_y": 1 if g.sign(c) == 1 else -1,
            "tv_attack": "left" if g.sign(c) == 1 else "right",
            "model": {"normal_spot": equilibrium.WEIGHTS, "reference": "Franks, Miller, Bornn, Goldsberry (2015); weights refitted on the ten ACB games",
                      "smoothing": "9-frame gaussian window, samples weighted by 1/sigma^2 with sigma = predError / 2.146"},
            "fps": FPS,
            "frames": {"idx": [int(i) for i in self.idx], "game_clock": num(self.game_clock, 2), "shot_clock": num(self.shot_clock, 2)},
            "players": players,
            "ball": {"xyz": pts(self.ball), "seen": [int(v) for v in self.ball_seen]},
            "holder": [int(v) for v in self.holder],
            "guard": {str(o): [int(v) for v in d] for o, d in self.guard.items()},
            "ghost": {str(d): pts(v) for d, v in self.ghost.items()},
            "gap": {str(o): num(v) for o, v in self.gap.items()},
            "extra": {str(o): num(v) for o, v in self.extra.items()},
            "actions": self.actions(),
        }
        # version 2: the league figures the chapters quote (computed by `courtlab league`; built now if missing) and the chapters themselves
        lg = league.load() or league.load(league.write())
        d["league"] = {"schema": lg["schema"], "generated": lg["generated"], "games": lg["games"], "n_games": lg["n_games"], "stats": lg["stats"]}
        d["chapters"] = chapters.build(d, lg)
        return d

    def write(self, folder: Path, role: str = "play") -> Path:
        """A file already exported as a play keeps that role when a report exports the same chance as a moment."""
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{self.chance['id']}.json"
        if path.exists() and role == "moment":
            try:
                role = json.loads(path.read_text())["source"].get("role", "play")
            except (ValueError, KeyError):
                pass
        path.write_text(json.dumps(self.to_dict(role), separators=(",", ":"), ensure_ascii=False))
        return path
