"""Finding, fetching and reading SkillCorner's basketball open data. The data is never part of this repository."""

from __future__ import annotations

import csv
import gzip
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

REPO = "https://github.com/SkillCorner/opendata-basketball.git"
LAB = Path(__file__).resolve().parents[2]
FRAME = re.compile(r'"frameIdx":\s*(\d+)')


def data_dir() -> Path:
    """COURTLAB_DATA, else ./data/opendata-basketball (where `courtlab fetch` puts it), else a clone sitting next to the lab."""
    for root in (os.environ.get("COURTLAB_DATA"), LAB / "data" / "opendata-basketball", LAB.parent / "opendata-basketball"):
        if root and (Path(root) / "data" / "matches.json").exists():
            return Path(root) / "data"
    raise SystemExit("SkillCorner's basketball open data was not found. Run `courtlab fetch` (needs git and git-lfs, about 400 MB).")


def fetch() -> Path:
    """Clone the public dataset, tracking included (Git LFS), into ./data/opendata-basketball."""
    target = LAB / "data" / "opendata-basketball"
    if not (target / ".git").exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--depth", "1", REPO, str(target)], check=True)
    subprocess.run(["git", "lfs", "pull"], cwd=target, check=True)
    return target / "data"


def game_ids() -> list[int]:
    return [g["id"] for g in json.load(open(data_dir() / "matches.json"))]


def season_shooting() -> dict[int, dict]:
    """Season three-point record per player, from the shots aggregates; duplicate ids merged, traded players' "total" rows skipped."""
    root = data_dir()
    alias = {int(r["player_id"]): int(r["canonical_player_id"]) for r in csv.DictReader(open(root / "player_id_aliases.csv"))}
    out: dict[int, dict] = {}
    for r in csv.DictReader(open(root / "aggregates" / "acb_shotsaggregates_20252026.csv")):
        if r["team_name"] == "total":
            continue
        pid = alias.get(int(r["player_id"]), int(r["player_id"]))
        rec = out.setdefault(pid, {"three_made": 0.0, "three_att": 0.0, "games": 0})
        rec["three_made"] += float(r["three_mades"] or 0)
        rec["three_att"] += float(r["three_attempts"] or 0)
        rec["games"] += int(float(r["games_played"] or 0))
    for pid, canon in alias.items():
        if canon in out:
            out[pid] = out[canon]
    return out


def season_aggregates() -> dict[int, dict]:
    """Per player, the season counts SkillCorner publishes (shots, ball screens as the handler, drives), summed over a traded player's
    teams; percentages are recomputed from the counts, never read. Every number here is SkillCorner's."""
    root = data_dir()
    alias = {int(r["player_id"]): int(r["canonical_player_id"]) for r in csv.DictReader(open(root / "player_id_aliases.csv"))}
    keep = {"shots": ("games_played", "attempts", "mades", "three_attempts", "three_mades", "total_points", "cns_three_attempts", "cns_three_mades", "contested_attempts", "contested_mades", "uncontested_attempts", "uncontested_mades"),
            "picks": ("handler_total_picks", "handler_points", "handler_score", "handler_assist", "handler_turnover"),
            "drives": ("total_drives", "blowby_count", "points", "assists", "successful_drives")}
    out: dict[int, dict] = {}
    for table, cols in keep.items():
        for r in csv.DictReader(open(root / "aggregates" / f"acb_{table}aggregates_20252026.csv")):
            if r["team_name"] == "total":
                continue
            pid = alias.get(int(r["player_id"]), int(r["player_id"]))
            rec = out.setdefault(pid, {}).setdefault(table, {})
            for c in cols:
                rec[c] = rec.get(c, 0) + int(float(r[c] or 0))
    for pid, canon in alias.items():
        if canon in out:
            out[pid] = out[canon]
    return out


@dataclass
class Game:
    id: int
    meta: dict = field(repr=False)
    events: dict = field(repr=False)

    @classmethod
    def load(cls, game_id: int) -> "Game":
        folder = data_dir() / "matches" / str(game_id)
        return cls(game_id, json.load(open(folder / f"{game_id}_game_data.json")), json.load(open(folder / f"{game_id}_dynamic_events.json")))

    @cached_property
    def players(self) -> dict[int, dict]:
        return {p["playerId"]: {**p, "side": side, "teamId": self.meta[side]["teamId"]} for side in ("homeTeam", "awayTeam") for p in self.meta[side]["players"]}

    @cached_property
    def chances(self) -> dict[str, dict]:
        return {c["id"]: c for c in self.events["chances"]}

    @cached_property
    def possessions(self) -> dict[str, dict]:
        return {p["id"]: p for p in self.events["possessions"]}

    def team_name(self, team_id: int) -> str:
        return next(self.meta[s]["teamName"] for s in ("homeTeam", "awayTeam") if self.meta[s]["teamId"] == team_id)

    def sign(self, chance: dict) -> int:
        """+1 when tracking already has the attacked hoop at negative x, -1 when it has to be reflected through the centre.

        Events are normalised to the offence, tracking is in camera coordinates. SkillCorner says which hoop each possession attacks."""
        return 1 if self.possessions[chance["possessionId"]]["leftHoop"] else -1

    def frames_at(self, wanted: set[int]) -> dict[int, dict]:
        """The live tracking frames with these numbers, in one pass over the file."""
        out, last = {}, max(wanted, default=-1)
        with gzip.open(data_dir() / "matches" / str(self.id) / f"{self.id}_tracking_data.jsonl.gz", "rt") as fh:
            for line in fh:
                i = int(FRAME.search(line).group(1))
                if i > last:
                    break
                if i in wanted and '"homePlayers": []' not in line:
                    f = json.loads(line)
                    if f["ball"]:
                        out[i] = f
        return out

    def frames(self, start: int, end: int) -> list[dict]:
        """Live tracking frames with start <= frameIdx <= end. Dead-time frames (no players, no ball) are skipped."""
        out = []
        with gzip.open(data_dir() / "matches" / str(self.id) / f"{self.id}_tracking_data.jsonl.gz", "rt") as fh:
            for line in fh:
                i = int(FRAME.search(line).group(1))
                if i > end:
                    break
                if i >= start and '"homePlayers": []' not in line:
                    f = json.loads(line)
                    if f["ball"]:
                        out.append(f)
        return out
