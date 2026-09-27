# What did not hold

Ideas that were tested on the ten games and did not survive, or survived only as description. They are listed so nobody has to test
them twice, and so the figures that did survive are read next to the ones that did not. Intervals resample whole games (600 draws,
fixed seed); a finding is kept only if its interval excludes zero and it survives moving our own thresholds.

## Died

**The screen as a collision.** The on-ball defender loses no speed at the instant SkillCorner labels the screen, whether the screener is
still or moving. A ball screen shows up as geometry (who is pulled where 1.2 s later), not as contact.

**Fatigue.** Close-out top speed and reaction delay are flat by quarter and by minutes played.

**Deceleration and change of direction as what beats a defender.** Neither top speed (−0.42 ft/s [−1.29, +0.43]), nor braking, nor a
change of direction, nor the reaction delay separates the drives that beat their man from the ones that were contained. What does:
the beaten defender stood **1.3 ft closer** [−1.96, −0.84] when the drive started, and 1.95 ft closer half a second earlier. It holds
inside every drive type.

**Ball height and speed.** The ball is reconstructed (`isDetected` = 0 always; gravity fits at 28 ft/s²). Dribble height, pass speed
from the ball and shot arc were dropped; the pass speed quoted is measured passer to receiver.

**Three or more still defenders while the ball flies = more offensive rebounds conceded.** It read +10 points [+2, +19] in a first
pass; split by distance to the hoop it vanishes (+0.07 [−0.01, +0.16] on 562 misses). A still defender under the rim is boxing out
(he takes 18 % of rebounds), a still defender far away is watching (7 %). It stays as a description, not a figure.

**Changes of assignment per possession** as a signal of defensive quality: no relation to points conceded once the relays under 0.2 s
are removed.

**Second-chance points by how many crashed.** 0.67 / 1.24 / 0.67 / 0.64 points with n from 9 to 58: too noisy to quote.

**A defender who lost sight arrives later** (docs/the_look.md, D1). When the shooter's defender had his man and the ball more than 120°
apart at the pass, the closest defender is at 3.9 ft at the release, the same as when he saw both. The look costs expected points
(+0.08 [+0.04, +0.12]) without costing feet at the release.

**The unseen closer buys the shooter time** (docs/the_look.md, A1 and A3). A closer arriving from outside the shooter's view neither
lengthens the release (0.8 s either way) nor makes the shot more likely: the attacker shoots less often (41 % against 49 %). Written
as the opposite before running; kept as written.

## Survived only in part

**"Coming in motion" helps a drive.** +2.2 ft/s [+0.43, +3.65] overall, but only in drives after a ball screen (9.9 vs 7.7 ft/s); in
every other drive type, nothing. It is a property of the screen, not a rule.

**Pass and move.** The passer travels 7.6 ft in the two seconds after his pass; 15 % stay still. Descriptive; no relation to the
shot's quality that survives.

**The dribble as a metronome.** 1.4 dribbles per second; the last two of a drive shorten to 0.60 s in 68 % of drives. It does not
separate beaten from contained defenders: rhythm, not warning.

**Unowned shooter under a second, or in a possession under 3 s.** Worth 0.98–0.99 expected points, nothing beyond a shot with the
defender in place: that is the relay, not the fault. The figure quoted needs the shooter unowned for 1 s or more (1.10 [1.00, 1.18],
n = 182, against 0.93 [0.90, 0.96] with his defender in place).

**The shooter's season accuracy.** On a three off a broken rotation SkillCorner's quality says 1.08–1.11 points for every tercile of
shooter; the bottom third scored 0.71 [0.41, 0.97], the middle 1.18 [0.95, 1.37], the top 1.02 [0.86, 1.18]. The bottom third is the
only clear gap, so the report quotes it as a caveat on the quality, never as a per-player figure.

## Not attempted, by design

A shot-anticipation model, player-role clustering, a play-type classifier à la Synergy, an expected-possession-value model, a body-pose
or physics layer for the mannequins, and a generative "what if" simulator. Each needs more than ten games, or data the release does not
have (no pose), or would add a model where SkillCorner's own is enough. The mannequins, the eye-level gaze rule and the ball's bend into
the ring are illustrations and are labelled as such on screen.
