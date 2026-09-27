# Glossary

The same definitions are in the viewer itself: an `i` beside a card opens the one line it needs, and `reference.html` (Home →
References, or `G`) lists every term on one page, grouped by whether the figure is SkillCorner's, computed here, or only drawn.
Both read `viewer/glossary.js`, so the page and this file are edited together and cannot drift apart silently.

The names the screens, the report and this documentation share. One name per idea, one unit per quantity: feet (ft), seconds (s),
points per possession (pts/poss), expected points per shot, percent (%). Never metres.

## The model

**Normal spot.** Where a defender usually stands, as a weighted average of three points: his man (0.62), the ball (0.15) and the
hoop (0.23). The weights follow Franks, Miller, Bornn and Goldsberry (2015) and were refitted on the ten ACB games
(`courtlab.equilibrium`). The refit recovers known weights in a test.

**Beyond his normal spot.** How many feet farther from his man a defender stands than the normal spot would put him. Negative means
tighter than normal, positive means pulled away. It is the number the bands, the strip and the Marks card show.

**Tension strip.** The whole possession as one row per attacker, coloured by how far his defender is beyond the normal spot,
with SkillCorner's labels (screens, passes, the shot) as ticks. It is also the timeline: drag it to move in time.

**Nobody assigned to him.** SkillCorner's `matchups` name no defender for that attacker at that instant. Rows shorter than 0.2 s are
dropped (they are relays, not decisions).

**Play over.** SkillCorner assigns nobody to anybody: the chance has ended, not five men left alone.

## The chapters

**Origin.** The last on-ball action SkillCorner labelled before the pass that fed the shooter (ball screen, hand-off, drive, isolation,
post-up); if none, the first off-ball screen; if none, the shot has no origin. One implementation, `chapters.origin()`, used by the
start screen, the chapters and the report.

**The action.** From 1 s before the origin to 1.2 s after it. Its number: how far the screener (the man who handed off, the cutter, or
the most pulled team-mate) stands beyond his normal spot at +1.2 s.

**The help.** From the end of the action to the pass that fed the shooter. Its number: the seconds the shooter had nobody assigned,
or, failing that, the most his defender was pulled beyond the normal spot.

**The race.** From the feed pass to the release. Its number: the closing defender's top speed, with its percentile among all labelled
close-outs; also when he started relative to the pass and his distance at the pass and at the release.

**The shot.** From the release to the end. Its number: SkillCorner's chance of scoring (`shotQuality`, 0–100), read as a percentage.

**Price of the rotation.** Expected points the shot would have lost had the defender's distance at the release been different, and
nothing else. Three kinds: *late close-out* (he starts running after the pass; he is placed where an on-time start at the league's
median close-out speed, 10.4 ft/s, would have put him), *nobody on him* and *help not recovered* (a defender at the normal spot).
The quality-versus-distance slope comes from a fit per zone, frozen in `league.json`. It is a model on top of SkillCorner's model, and an
upper bound: the defender arrives and nothing else changes.

## The report

**Transition.** Points per transition possession conceded, by how many defenders were between the ball and their basket when it
crossed into the front court.

**Shot selection vs shot making.** Points scored beyond what SkillCorner's shot quality expected, per 100 field-goal attempts.
Positive: the looks went in more than their quality said. Fouled shots excluded.

**Ball screens.** Points per possession after the last ball screen of a set possession, by coverage (`over/show`, `over/soft`,
`switch/switch`, …), with the outcome tree: what the handler did out of the screen (shot, pass, foul drawn, turnover).

**Close-outs.** Points the possession produced after a labelled close-out, by what the attacker did once the defender arrived.

**The rim.** Attempts from the restricted area: made, by whether a defender was within 4 ft at the release.

**The glass.** After a miss: who crashes, who boxes out, who watches. **Crash**: a team-mate of the shooter gains at least 2 ft
towards the hoop while the ball flies and ends within 14 ft of it (chosen because it best predicts who takes the rebound).
**Box-out**: a defender who moves less than 2 ft and is within 10 ft of the hoop.

**Rotations.** The ledger: every conceded shot with a counterfactual, its price, summed per team and game.

**Moments.** Shots conceded off a catch in set defence (3 s or more into the chance) off a broken rotation: nobody assigned to the
shooter for 1 s or more, or his man 6 ft or more beyond his normal spot when the pass left.

## The viewer

**Director.** The camera that cuts with the play, from SkillCorner's own labels. **TV side** is on by default: a play opens on the
sideline the real broadcast camera sat on, so the attack runs the way it ran on television (to the right for half the plays, to the
left for the other half). Unchecking it crosses to the other sideline. The crest painted at centre court turns with the seat, as an
arena's does, so it is upright from wherever the camera is; Home keeps its own drifting seat and never turns. **TV clip** shows the real footage beside the animation, for reference only. **Distances** and **Path of the ball** are layers.
**Pucks** are the players as discs; **Figures** are one modelled body (Quaternius, CC0) posed by rules from position, speed and events and dressed in cloth cut from its own skin: the data has no body pose, so a body is an illustration.
**Bounces.** The reconstructed ball bottoms out a foot or two above the floor on a dribble; at each dribble label the picture pulls it to the floor for a fifth of a second, as the bend into the ring: nothing is measured from it. In the air the ball carries backspin, in a hand it rolls with its travel; both are drawn, not tracked.
**Ghost.** A player drawn grey, translucent and undressed is off camera at that instant: SkillCorner extrapolates his position (`seen` = 0 in the file).
**Kits and crests.** The figures wear a tank top and shorts printed in their club's classic home colours (a hand-written table in `viewer/kits.js`, from public knowledge: the data carries names only; the print is a template with side panels, or stripes for the clubs that wear them); the pucks stay light for the attack and dark for the defence, with the club's colour in their ring, so that blue and amber remain the only colours that carry a number. The club's crest sits in the headers and on Home rows, with a monogram in its colours until it loads; the crests are the clubs' trademarks, shown to identify them, and SkillCorner's mark on Home and in the tab is theirs, shown to credit the data. The floor takes the home club's colour in the paint and its crest at centre court: a template, not any arena's real floor.
**The look.** What a player could see, from positions alone (docs/the_look.md): a defender at the pass with his man and the ball more than 120° apart has *lost one*; a closer arriving more than 60° off the direction the ball came from is *out of the shooter's view*. The eighth tile, and one line each in the race and the shot chapters.
**Roster.** Both teams of a match, one profile per player from SkillCorner's data alone: minutes, distance and top speed read off the positions on the tracked play (sampled five times a second; top speed is the 98th percentile of 0.2 s steps while on camera), his labels, whom he guarded, how far beyond his normal spot he stood, his close-outs, the shots conceded with him nearest, what his rotations cost, and the season counts SkillCorner publishes. Nothing biographical: the data has none.
**Players.** From Home: every player of the games on this machine, one point per player and game (a player who played twice has two points). The chart asks one of five questions (discipline and its price, shot making vs selection, who closes out and who pays, workload, creation), each with a reference line, or plots any pair; the focused player is a scouting card, every metric with a strip of the players shown and his mark, and a second player can be pinned to compare. Only feet beyond his normal spot carries colour.
**The bill.** The two figures that summarise a defence on the match page: points the opponent scored beyond what the quality of their looks expected, and what the rotations cost; beneath them the game by quarter, what the looks were worth against what was scored, and the rotations' price. **Who paid** is the ledger by the defender it names. **Where they shot from** is every field-goal attempt conceded on the half court, made filled, missed hollow, with six zones and what SkillCorner's quality expected in each.
**League dot.** On a match tile, a dot beside the league figure: amber when this defence conceded more than the league, blue when less, grey within 5 %; the price of a play is tinted the same way, the costlier the more amber.
**HUD** has three levels: Full, Minimal (time, one subtitle, a chapter scrubber on mouse move) and None; inside a level, the card and the strip fold on their chevrons (P, S).
**Marks · Story.** The card's two tabs: every attacker's feet beyond his normal spot, and the chapter the play is in.
