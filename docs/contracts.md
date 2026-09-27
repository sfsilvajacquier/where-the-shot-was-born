# Contracts

What every file the package writes looks like, what every name means, and which pieces of the viewer are shared. Code follows this
document, not the other way round. Nothing here is hand-edited data: every file below is generated on your machine from SkillCorner's
open data by a `courtlab` command, and none of them is committed to this repository.

## 1. One rule for "where the shot came from"

The **origin** of a shot is the last on-ball action SkillCorner labelled before the pass that fed the shooter (pick, hand-off, drive,
isolation, post-up), or, when the shooter ran an on-ball action himself after the catch, the last such action before the shot; if there is
none, the first off-ball screen before the feed; if there is none, the shot has no origin. `chapters.origin()` is the only implementation;
the start screen's story line, the chapters and the match report all call it.

## 2. `courtlab.possession/2` — one possession, for the viewer

Written by `courtlab export` into `outputs/possessions/<chance>.json`. Feet, origin at the centre of the court, attacked hoop at
negative x; arrays hold one value per frame at 25 fps; `i` fields index those arrays; missing values are `null`. The window starts a second
before the ball crossed into the front court, or earlier when the shot came fast or the feed was thrown from the back court (at least 8 s
before the shot and 2 s before that pass), never earlier than a second before the chance began; it ends 2 s after the chance or at the first
hole in the tracking.
Version 2 is version 1 plus two keys. No key of version 1 is renamed or removed. The viewer tolerates any missing key.

| Key | Content |
|---|---|
| `schema` | `"courtlab.possession/2"` |
| `source` | `dataset`, `game_id`, `chance_id`, `generated_by`, `role` (`play`: exported on its own merit, Home lists it; `moment`: exported by a match report, which opens it) |
| `game` | `date`, `competition`, `home`, `away`, `attack`, `defence`, `period`, `score_before` `[home, away]`, `points`, `outcome`, `how_it_started`, `transition` |
| `court` | FIBA geometry in feet (`length`, `width`, `hoop`, `three_radius`, `three_corner_y`, `paint`, `free_throw_radius`, `no_charge_radius`, `backboard_x`, `rim_height`) |
| `tv_sideline_y`, `tv_attack` | which sideline the broadcast camera sat on after normalisation (`+1`/`−1`), and whether the attack ran `left` or `right` on TV |
| `model` | `normal_spot` weights (`man`, `ball`, `hoop`), `reference`, `smoothing` |
| `fps` | 25 |
| `frames` | `idx` (tracking frame numbers), `game_clock`, `shot_clock` (seconds; `null` when SkillCorner has none) |
| `players[]` | `id`, `name`, `jersey`, `side` (`attack`/`defence`), `season_three` (`{made, attempts}` or `null`), `xy` per frame, `seen` (1 on camera, 0 extrapolated), `err` (SkillCorner's expected error, ft) |
| `ball` | `xyz` per frame (z is SkillCorner's reconstructed height: drawn, never measured), `seen` |
| `holder` | player id on the ball per frame, 0 while it travels |
| `guard` | attacker id → assigned defender id per frame (SkillCorner's matchups, rows under 0.2 s dropped), 0 when nobody; over the lead-in before the chance began, the first assignment is carried back |
| `ghost` | defender id → his normal spot per frame |
| `gap`, `extra` | attacker id → feet to his defender, and how much farther than the normal spot would put him |
| `actions[]` | SkillCorner's labels inside the chance, in order; each has `type` and `i` (see §2.1) |
| **`chapters[]`** *(v2)* | the possession in up to four chapters (see §2.2) |
| **`league`** *(v2)* | the league figures the chapters quote, copied from `league.json` at export time (see §3) |

### 2.1 Actions

`pick` (handler, screener, handler_def, screener_def, coverage, screener_coverage, xy, direct) · `handoff` (setter, receiver, coverage, xy) ·
`screen` (cutter, screener, coverage, xy) · `drive` (player, i_end, beat) · `isolation` · `post` · `closeout` (player, defender, i_touch, i_end, feet `[start, touch, end]`) ·
`pass` (from, to, i_end, complete, led_to_shot) · `dribble` (player) · `shot` (player, i_end, three, made, fouled, quality 0–100, contest, closest_def, closest_def_ft, kind, region (SkillCorner's zone), release_s, feet_to_hoop, xy, from_paint, assisted) ·
`rebound` · `turnover` · `foul`.

### 2.2 Chapters

Contiguous windows in frame indices, in this order; a chapter exists only if its events do.

| # | `id` | Window | `big` (the one number) | League line (`league` key) |
|---|---|---|---|---|
| 1 | `action` | 1 s before the origin → 1.2 s after it | the screener's (hand-off: the setter's; drive/iso/post: the most pulled team-mate's) feet beyond normal at +1.2 s, and where he started; with nobody assigned to him, his nearest defender's distance | `pick_coverage` (a screen) or `one_more_pass` (anything else) |
| 2 | `help` | end of 1 → the feed pass leaves | seconds the shooter had nobody assigned (a stretch that starts in this window, or later before the shot, is counted to its end, so it matches the strip), or his defender's peak feet beyond normal | `unowned_shooter` |
| 3 | `race` | feed pass leaves (or the end of 1, when the shooter ran the action himself after the catch) → the release | when the closing defender started (s after the pass), his distance at the pass and at the release, top speed and its percentile; without a labelled close-out, the pass's speed, or, when the shooter then kept the ball 2 s or more, his seconds on the ball; after his own action, his seconds on the ball from it to the shot | `race` (`one_more_pass` after his own action) |
| 4 | `shot` | the release → end | SkillCorner's chance of scoring, the shooter's season threes, the rotation price (`price` {value, kind, note}, from `quality_fit` in the league file; the same three kinds as the ledger, read from the file's smoothed positions, so it can differ from the report's ledger by a few hundredths where a close-out's start sits on the threshold) | `open_three_by_shooter` (a three) or `shot_selection` |

Each chapter: `id`, `title`, `i0`, `i1`, `big` `{value, unit, label}`, `context` (one sentence, ≤ 110 characters), `league_key`.
If a play has no origin, chapter 1 is absent and chapter 2 runs from the start of the file (the stretch in which the shooter got free) when that is a second or more; if no feed pass, chapters 2–3 are absent. The viewer shows the chapters it finds.

## 3. `league.json` — the league figures, computed, never typed

Written by `courtlab league` into `outputs/league.json` from the games in `data_dir()`, with a fixed random seed (600 game-cluster
bootstrap draws). Copied into every possession at export. A test asserts the values on the ten public games.

```json
{ "schema": "courtlab.league/1", "generated": "2026-09-25", "games": [114086, ...], "n_games": 10,
  "stats": {
    "unowned_shooter":      { "label": "Shot off a catch with nobody assigned to the shooter for 1 s or more",
                              "value": 1.10, "ci": [1.01, 1.18], "n": 182, "unit": "expected points per shot",
                              "baseline": { "label": "defender in place", "value": 0.93, "ci": [0.90, 0.96], "n": 352 },
                              "source": "courtlab.league.unowned_shooter · scripts/analysis_09_coach.py" },
    ...
  } }
```

Every stat has `label`, `unit`, `n`, `source` and either a `value` (with `ci` where n ≥ 30, `baseline` where a comparison is the point) or `rows`; a composite stat (`race`) carries its parts as named sub-figures plus one headline `value`.
Stats: `unowned_shooter`, `pick_coverage` (per coverage: stretch at +1.2 s, points per possession and the outcome tree `outcomes[]` — what the handler did
out of the screen: shot / pass / foul / turnover, with points per possession; the same tree over all coverages sits beside the rows), `one_more_pass` (0/1/2 passes),
`race` (pass speed, close-out speed, late-start price), `open_three_by_shooter` (bottom/middle/top third), `crash` (2+ crashing vs 0/1; `share_two_plus`, `offensive_rebound`),
`transition` (headline points per possession, rows by defenders back, and `seconds_to_set`: median seconds after the crossing until all five defenders are in the half they defend), `shot_selection` (expected vs actual per team-game distribution),
`closeouts` (possession points after one, rows by what the attacker did; median start and end distance), `rim` (made with a defender within 4 ft vs nobody),
`rotations` (the ledger: points per team-game, rows per kind — late close-out / nobody on him / help not recovered; `broken_share` of set-defence catches),
`quality_fit` (the betas the rotation price uses). The file only grows: a key is never renamed or removed.
Intervals come from one random stream in a fixed order, so adding a figure can move the third decimal of the bounds after it; the values never move.

## 4. `report.json` — one match, for the report page

Written by `courtlab report <game>` into `outputs/reports/<game>.json`; the possessions of its moments are exported alongside.

```
schema "courtlab.report/1" · source {dataset, game_id, generated_by, league {schema, generated, n_games}} · game {home, away, score [home, away], date, competition}
teams[]  (one per side, as the DEFENDING team): team, side (home/away), opponent
  tiles[] in this order: transition, shot_selection, ball_screens, closeouts, rim, glass, rotations, look
     each: id, title, big {value, unit}, league (the league figure on big's scale, or null), line (one comparison sentence with the league figure), n, detail[] (≤ 5 rows of label/value, both strings)
  story      what a coach asks first: quarters[] {period, shots, expected, scored, price, catches, broken} (conceded field goals: what the looks were worth and
             what was scored, the ledger's price, set catches and how many came off a broken rotation); zones[] {id, title, n, made, expected_per_shot} over six
             zones (rim, paint, mid-range, corner threes, wing threes, top threes, from SkillCorner's `region`); shots[] {x, y, made, three, quality, zone, period,
             shooter} (every conceded attempt with its location, events frame, attacked hoop at −x); who[] {name, price, shots, closeouts, conceded} (the ledger
             by the defender it names, most expensive first, six at most); unpriced_to_nobody (shots priced with no defender named)
  moments[]  conceded shots off a catch in set defence (3 s or more into the chance) off a broken rotation (nobody assigned for 1 s or more, or his man
             6 ft or more beyond his normal spot when the pass left), most expensive first, `--moments` per team (default 6)
     each: chance, i (the feed pass frame in that possession's file), clock "Q1 7:49", shooter, shot {three, made, quality}, origin (sentence, from
           `chapters.came_from`), rotation (sentence), closeout (sentence or null, the race chapter's), price {value, kind, note} (the ledger's),
           thumb (5 × 64 of `extra`, as the start screen)
```

| Tile | `big` | `n` |
|---|---|---|
| `transition` | points per transition possession conceded (rows: by defenders back; seconds until all five were back; who was not back, as counts) | transition possessions with five defenders tracked at the front-court frame |
| `shot_selection` | points the opponent scored beyond what SkillCorner's quality of their looks expected, per 100 shots | field-goal attempts conceded (fouled shots excluded) |
| `ball_screens` | points per possession after the last ball screen of a set possession | set possessions with a ball screen |
| `closeouts` | points per possession after a labelled close-out | close-outs with a labelled reaction of the attacker |
| `rim` | % made at the rim with a defender within 4 ft | rim attempts conceded (no foul) |
| `glass` | % of the opponent's rebounded misses they got back | opponent misses that were rebounded |
| `rotations` | expected points the rotations cost (the ledger's sum) | conceded shots with a counterfactual |

The match page reads the tiles in a coach's order (the bill and the quarters; how the set broke; inside and where they shot from), not the file's.
Per-game numbers are **counts and means**; only the league figures carry intervals. Nothing per player beyond counts. Every tile's rows come
from `league.Rows`, the same collector that makes `league.json`, filtered to the game and the defending team: a tile and the league line under it
share one definition by construction. `courtlab report` also writes the possession file of every moment into `outputs/possessions/`, so the
viewer can open it at the feed's frame (`?chance=…&i=…`).

## 4b. `roster.json` — one match's players, for the roster page

`courtlab roster <game>` (and `courtlab report`, which writes it too) → `outputs/rosters/<game>.json`, schema `courtlab.roster/1`.
`source` names the dataset, the game, the season aggregates used and the league file; `game` as in the report; `teams[]`: `team`, `side`,
`players[]` sorted by seconds on the tracked play, each with `id`, `name`, `surname`, `jersey`, `season` (SkillCorner's counts, summed over a
traded player's teams: games, fg, three, cns_three, contested as [made, attempts], points, picks {n, points, turnovers}, drives {n, blowby,
points, assists}; null when not published), `game` (seconds, distance_ft, top_speed from the positions sampled every 5 frames inside usable
chances; shots {n, made, three, three_made, quality, points}; assists, turnovers, passes, drives, blowby, picks_handler, screens, rebounds
[off, def], fouls from the labels), `defence` (guarded[] {who, seconds} from the matchups; extra {mean, within_3, n} from the same normal-spot
model as the play's bands; closeouts {n, start, end, pts, actions}; conceded {n, made, distance, quality} with him the closest defender;
price {value, n, kinds} from the ledger; each null when he has none) and `plays[]` (the exported possessions he appears in: chance, role,
side, period, clock, story). No field comes from outside SkillCorner's data.

## 5. Names (the glossary the screens and the README share)

Marks · Story (the card's tabs) · Beyond his normal spot · Normal spot · Tension strip · Play over · Nobody assigned to him ·
Price of the rotation · Late close-out · Help not recovered · Shot selection vs shot making · Transition · Close-outs · The rim · The glass ·
Crash · Box-out · Director · TV side · TV clip · Distances · Path of the ball · The look · Roster.
Units: feet (ft), seconds (s), points per possession (pts/poss), expected points per shot, percent (%). Never metres in basketball.

## 6. URL parameters of the viewer

`chance` · `i` (frame) · `play=1` · `cam` (`auto|broadcast|baseline|top|rail|behind|eyes|free`) · `eyes` (player id) · `view` (`pucks|figures`) ·
`layers` (comma list of `distances,path`) · roster page: `game`, `team`, `player` (id) · `tv` (`1` the TV's sideline, `0` the other; unset: the default seat, which is the TV's for half the plays) · `bc=1` · `hud` (`full|minimal|none`) · `start=1` · `motion=0`.
`fold=1` and `panel=0` keep working and map onto `hud`. Without `chance` (or with `start=1`), Home: the list of the games on this machine.
The match page, `report.html`: `game` (default: the latest with a report) · `team` (`home|away`, the defending side; defaults to the side that defended the focused play) ·
`focus` (`play:<chance>`, `moment:<k>` or `tile:<id>`) · `motion=0`. A play's ‹ and Esc go back to its match page with `focus=play:<chance>`; the match page's ‹ and Esc go to Home. In a play, `P` folds the card and `S` the strip (their chevrons do the same); a HUD level resets both.
Served alongside: `/games/index.json` (one row per game with something exported: game, home, away, date, competition, score, rotations {home, away}, moments, roster (true when its roster file exists; a server older than the page sends no such key, and the roster page says so), and `plays[]`, the
possession rows below), `/reports/<game>.json`, `/rosters/<game>.json`, `/court.json` (the geometry block the empty court is built from). A possession row carries `chance`, `game_id`, `date`, `attack`,
`defence`, `home`, `away`, `period`, `clock`, `shooter`, `outcome`, `story`, `thumb`, `release`, `chapters[]` (id, title, value, unit) for the chips, `clip` (a broadcast clip exists for it) and `moment` (its role is `moment`: a report exported it; the match page lists it among the plays of the side that defended it).

**The players index.** `/players/index.json` (and `players/index.json` in the static site): `schema` (`courtlab.players/2`; the page refuses an older one and says to restart the server), `source`, `games`, `rows[]`, one row per player and game from the
rosters on this machine (id, name, surname, jersey, team, opponent, game, date, side, minutes, distance_ft, top_speed, shots, made, three, three_made,
quality, points, assists, turnovers, closeouts, extra, within_3, conceded, conceded_made, price, season_three [made, attempts], season_cns_three, season_games;
derived: ft_per_min, price_per_conceded (three or more conceded), co_end and co_pts (three or more close-outs), conc_dist). The players page
(`players.html`: `view` discipline|making|closeouts|workload|creation|custom, `x`/`y` metric ids for custom, `team`, `min` 10|20, `focus=<player>:<game>`,
`pin=<player>:<game>`) plots it with a reference (the diagonal where both axes share a unit, the means of the players shown otherwise), shows the focused
player as a scouting card (a strip per metric with every player shown and his mark) and opens the roster on Enter.

**The static site.** `courtlab site` writes `outputs/site/`: the viewer's files plus every JSON the server would answer (`games/index.json`, `court.json`,
`possessions/`, `reports/`, `rosters/`, `players/index.json`, and `broadcast/sync.json`), so any static host serves it unchanged; every path the pages use is relative.
`--clips` also copies the broadcast clips of `broadcast/` and keeps their entries in `sync.json`; without it the clips stay behind AND every `clip` in the games index
is cleared, so no page tags a play `TV clip` whose viewer would have none to show (`tests/test_contracts.py` checks both modes).
It is generated, never committed to this repository; `scripts/console.py --site outputs/site` checks it served as a plain folder.

## 7. Shared viewer components (`viewer/ui.js`)

`place(stage)` scales the stage to the window before anything loads and `fail(stage, why)` leaves one message on it (`#stage.failed`): every page fails the same way, laid out, naming the cause (a server older than the page, a game not on this machine, an unwritten report or roster, no server).

`FocusList(root, rows, {render, onFocus, onOpen, visible, className})` one focused row at all times, mouse moves it, ↑↓ ↵ (`className` names the row's class: `play` on Home, `card` and `item` on the match page) · `Detail(el)` shows with a 120 ms delay ·
`keys(el, [...])` the key legend · `Tabs(el, {onChange})` the segmented control · `dip(during)` the quarter-second cut · `short(name)` club short names.
Home, the Marks/Story/Shot card and the report page use these and nothing else for those jobs. The world behind every screen is one setup, `viewer/scene.js` (`makeScene(canvas, court)`: renderer, hall, lights, court); a play adds its actors, the report shows the court empty.
