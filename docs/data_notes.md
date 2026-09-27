# Data notes

What we learned about SkillCorner's basketball open data (Liga ACB 2025-2026, ten games) while building this. Everything marked
*verified* comes from `scripts/probe_data.py` or a test in `tests/`. Read `KNOWN_ISSUES.md` in the dataset first; this page only adds
to it.

## The frame is a mirror

The documentation says the raw tracking frame is the TV camera's: x left to right on the picture, y bottom to top. A broadcast frame of
the Zaragoza three (game 191313, Q1 7:49) says otherwise: **y grows towards the camera**. The raw frame is left-handed, a mirror image of
the real court. Distances, angles and areas do not care; anything that says *left* or *right* does. The viewer maps data `(x, y)` to
three.js `(x, 0, +y)`, which turns the mirror into a rotation, and the possession file records which sideline the broadcast sat on
(`tv_sideline_y`). Rule for lateral analyses: compute in the data's frame, flip the sign when naming the side.

## Events are normalised, tracking is not

Events put the attacked hoop at negative x for both teams; tracking stays in camera coordinates. For the team attacking towards +x the
event `location` equals `(−x, −y)` of the tracking (a central symmetry, not a mirror in x). *Verified* on 1,459 shots: 670 match as they
are, 713 reflected, none half way. Which hoop the home team attacks in the first period varies by game (−x in seven, +x in three), so it
is read from `possessions.leftHoop`, never assumed. Teams swap after the second period; overtime keeps the fourth's.

## Clocks

SkillCorner's game and shot clocks run about **0.6 s behind the arena display** (checked against the broadcast at three instants of the
Zaragoza three). They are derived, not measured. The hand and the rim set the time here, not the clocks.

## The ball is reconstructed

`isDetected` is 0 for the ball in every frame of every game: its position and height are modelled. A gravity fit over made threes
gives 28.1 ft/s² (32.2 is the truth). The viewer draws the ball and, on made shots, bends its last feet into the ring for the picture
only. No number is ever derived from the ball's height or speed; the pass speed is measured between the passer and the receiver.

## Possession, chance, and what counts

A possession can hold several chances: an offensive rebound keeps the possession and opens a new chance. Almost every "per possession"
figure in basketball is really per chance; here `points per possession` means per chance, as SkillCorner's `ptsScored` does.
`shots` includes missed shots with a foul (the FIBA box score does not count them as attempts); every figure here excludes fouled
shots. `passes.toReceiverId` is the intercepting defender, not the receiver. `chance_players.shotLoc` and `rimLoc` give every player's
spot at the shot and when the ball reaches the rim, which is what the glass analysis reads.

## Matchups

`matchups` says who defends whom at every instant, which no ordinary play-by-play has. 16 % of the rows last under 0.2 s; they are relays
between two assignments, not decisions, and are dropped (`MIN_MATCHUP = 5` frames). Only 1.8 % of shots off a catch have nobody assigned
to the shooter *and* a possession under 3 s old: the rest of the unowned catches are rotations that broke, not early offence.

## Coverage

76–83 % of player positions are seen on camera; the rest are extrapolated with a stated expected error (`predError`, a 90 % radius:
0.9 ft when seen, 4.9 ft when not). Positions are smoothed with a nine-frame gaussian window weighing each sample by 1/σ² with
σ = predError / 2.146. Between 26 and 55 % of frames per game are dead time (no players, no ball; the clocks keep running); the
possession file stops at the first hole after the chance. Transition figures carry the share of defenders on camera at the
front-court frame (84.5 %) because that is where extrapolation is worst.

## Aggregates

The season aggregates cover 293 of 327 games and only the offence (shots, drives, picks). Picks in the aggregates are `direct = true`
only, about 52 % of the events. Traded players have one row per team plus a `total` row: sum the team rows, skip `total`. Nine players
have two ids (`player_id_aliases.csv`); the shooter's season accuracy uses the canonical id and needs 40 attempts to be quoted.

## Shot quality behaves like a probability

By quintile of `shotQuality`, the mean says 22 / 34 / 39 / 47 / 75 and the shots went in 21 / 29 / 35 / 52 / 72 % of the time. By
contest level: open 55 % (closest defender 6.0 ft), plus 37 % (2.8 ft), blocked 0 %. It is filled for 98 % of shots. It is the anchor of
every expected-points figure here; the rotation price only moves it along its own distance slope.

## Final scores

The score from `shots` plus `free_throws` matches the official result in all ten games. The report's score is the last chance's start
score plus its points.
