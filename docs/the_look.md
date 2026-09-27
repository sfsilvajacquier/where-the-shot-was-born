# The look: what a player could see, from positions alone

The basketball data has no body pose and no gaze. What it has is where everybody stood, 25 times a second, and SkillCorner's labels
for the pass, the catch and the close-out. From those, one question can be asked honestly on both sides of the ball: **could he see
what mattered?** Two rules, stated before any number was computed, and the predictions they were tested against.

## The rules

**A defender off the ball watches two things: his man and the ball.** At the instant a pass leaves for the man he is assigned to,
the angle at the defender between the direction to his man and the direction to the ball says whether both fit in one field of view.
A human field of view is about 120° wide with the head still. **Both in view: angle ≤ 120°. Lost one: angle > 120°.** He may have
turned his head; the data cannot know. The claim is only that a 130° split is harder to watch than a 60° one.

**A player catching a pass looks at the ball.** At the catch, the direction he faces is the direction the ball came from (the passer's
position when it left). The defender closing out on him arrives from some bearing relative to that direction. **Closer in view:
bearing ≤ 60° (half of the same 120° field). Closer out of view: bearing > 60°.**

Both are computed on the tracking positions, normalised as everything else here (the attack runs to −x). Nothing is read from video.

## The predictions (written 2026-09-26, before running)

Defence, on catches that fed a shot in set defence, the receiver's assigned defender at the pass:

- **D1.** When he had lost one of the two (angle > 120°), the closest defender is farther from the shooter at the release: median
  distance at least 1 ft larger than when he saw both.
- **D2.** The shot is worth more: SkillCorner's expected points per shot at least 0.05 higher when he had lost one.

Attack, on catches followed by a labelled close-out:

- **A1.** When the closer comes from out of view (bearing > 60°) the shooter releases later: median release time longer.
- **A2.** The closer ends nearer: median distance at the release smaller when he came from out of view.
- **A3.** The attacker shoots more often, and drives or passes less often, when the closer is out of view (he does not see him coming).

What counts as holding: the sign, and the size stated where a size is stated. What did not hold goes to
[what_did_not_hold.md](what_did_not_hold.md) as well, in the same words.

## The results (ten public games, `league.json["stats"]["look"]`)

Defence, 694 catches in set defence that fed a shot. The receiver's defender had lost one of the two on 15.9 % of them.

- **D1 did not hold.** The closest defender's distance at the release is the same either way: 3.9 ft median when he had lost one,
  3.9 ft when he saw both. Losing sight of the ball or the man at the pass does not show up as a later arrival.
- **D2 held.** The shot is worth 1.06 expected points when he had lost one against 0.99 when he saw both: +0.08 [+0.04, +0.12] by
  the game bootstrap. Scored points go the same way, 1.09 against 0.96 per shot. So the price of a lost look is not paid in feet at
  the release; it is paid in the kind of shot the catch produces (where, and how set the shooter is), which SkillCorner's quality
  already reads.

Attack, 562 catches followed by a labelled close-out. The closer came from outside the shooter's view on 18.9 % of them.

- **A1 did not hold.** The median release time is 0.8 s either way.
- **A2 held (sign; no size was stated).** The closer ends nearer when he came from out of view: 5.7 ft against 6.1 ft at the release.
- **A3 held the other way round.** The attacker shoots *less* often when the closer is out of view (41 % against 49 %), and drives or
  passes slightly more. A reading that fits the numbers, offered as a reading and not a result: a defender arriving from behind or
  from the side is one the shooter did not expect, and the catch turns into a decision rather than a shot.

Two of five predictions held as stated, one held in sign, two did not hold. All five are kept here as written, and the two that
failed are listed in [what_did_not_hold.md](what_did_not_hold.md). What the viewer shows: the eighth tile of the match page (the share
of catches where the defender had lost one of the two, against the league), one line in the race chapter of a play (the angle at the
pass) and one in the shot chapter (the closer's bearing at the catch). Positions only, as the labels say.
