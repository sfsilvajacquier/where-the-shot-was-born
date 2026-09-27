// Every name the pages use, with what it means and where it comes from. One entry per idea, written once and read from three places:
// the `i` beside a card (info.js), the references page (reference.js), and docs/glossary.md, which says the same in prose.
//
// `from` is the point of the whole file: a reader should never have to guess whether a number was handed to us or made here.
//   sc    SkillCorner's, as it arrives in the open data
//   lab   computed on this machine from those positions and labels
//   drawn an illustration: nothing is measured from it

export const SOURCES = {
  sc: { label: 'SkillCorner', hint: 'comes with the open data' },
  lab: { label: 'Computed here', hint: 'built from SkillCorner positions and labels' },
  drawn: { label: 'Drawn, not measured', hint: 'an illustration; no number is read off it' },
};

/** id → { term, from, what, more? }. `what` is the one line a hover shows; `more` is the paragraph the references page adds. */
export const TERMS = {
  // ─── what SkillCorner gives us ────────────────────────────────────────────
  tracking: { term: 'Tracking', from: 'sc',
    what: 'The position of all ten players and the ball, 25 times a second, for the tracked plays of ten Liga ACB games.',
    more: 'Everything on these pages is read off those positions and the labels beside them. No video is used, and none is in the repository.' },
  shot_quality: { term: 'Shot quality', from: 'sc',
    what: "SkillCorner's own chance of a shot going in, 0–100, from where it was taken and how it was contested.",
    more: 'Shown as a percentage. It is the reference every "worth" and every price on these pages is measured against, so it is never re-estimated here.' },
  matchups: { term: 'Who is guarding whom', from: 'sc',
    what: 'SkillCorner names a defender for each attacker, frame by frame; sometimes it names nobody.',
    more: 'Stretches shorter than 0.2 s are dropped: they are relays between two defenders, not a decision. When nobody is assigned to anybody the chance has ended, not five men left alone.' },
  labels: { term: 'The labels', from: 'sc',
    what: 'The events SkillCorner marks: ball screen and its coverage, hand-off, drive, isolation, post-up, close-out, pass, shot, turnover.',
    more: 'The chapters, the ticks on the strip and the Director’s cuts all key off these labels rather than off a rule invented here.' },
  seen: { term: 'Ghost', from: 'sc',
    what: 'A player drawn grey and undressed is off camera at that instant: SkillCorner extrapolates his position.',
    more: 'The file carries a `seen` flag per player per frame. Nothing is hidden when it is 0, but the picture says so.' },
  season: { term: 'Season figures', from: 'sc',
    what: 'The season totals SkillCorner publishes per player, shown on his roster profile beside what the tracked play gives.',
    more: 'They are not recomputed here; they sit next to the play figures so the two can be told apart.' },

  // ─── what is computed here ────────────────────────────────────────────────
  normal_spot: { term: 'Normal spot', from: 'lab',
    what: 'Where a defender usually stands: a weighted average of his man (0.62), the ball (0.15) and the hoop (0.23).',
    more: 'The shape follows Franks, Miller, Bornn and Goldsberry (2015); the three weights were refitted on these ten games. A test recovers known weights from generated positions.' },
  beyond: { term: 'Beyond his normal spot', from: 'lab',
    what: 'How many feet farther from his man a defender stands than the normal spot would put him. Negative is tighter.',
    more: 'This one number drives the bands, the tension strip and the Marks card. It is the only quantity on these pages that carries colour.' },
  price: { term: 'Price of the rotation', from: 'lab',
    what: 'Expected points a conceded shot would have lost had the defender been closer at the release, and nothing else changed.',
    more: 'Three kinds: a late close-out (placed where an on-time start at the league median of 10.4 ft/s would have put him), nobody on him, and help not recovered (a defender back at his normal spot). The quality-versus-distance slope is fitted per zone and frozen in league.json. It is a model on top of SkillCorner’s model, and an upper bound: the defender arrives and nothing else changes.' },
  strip: { term: 'Tension strip', from: 'lab',
    what: 'The whole possession as one row per attacker, coloured by how far his defender is beyond the normal spot.',
    more: "SkillCorner's labels sit on it as ticks. It is also the timeline: drag it to move in time." },
  chapters: { term: 'The four chapters', from: 'lab',
    what: 'A play read backwards from the shot: the action that opened it, the help, the race to close out, and the shot.',
    more: 'The origin is the last on-ball action SkillCorner labelled before the pass that fed the shooter; failing that the first off-ball screen; failing that the shot has no origin. The action runs from 1 s before the origin to 1.2 s after it, the help to the feed pass, the race to the release, the shot to the end.' },
  selection: { term: 'Selection against making', from: 'lab',
    what: 'Points scored beyond what the quality of the looks expected, per 100 field-goal attempts. Positive: they went in more than their quality said.',
    more: 'It separates the looks a defence gave up from what the opponent did with them. Fouled shots are excluded.' },
  glass: { term: 'Crash and box-out', from: 'lab',
    what: 'After a miss: a crasher gains 2 ft or more towards the hoop while the ball flies and ends within 14 ft of it; a box-out moves less than 2 ft within 10 ft of the hoop.',
    more: 'The 2 ft and 14 ft thresholds were chosen because they best predict who actually takes the rebound in these games.' },
  look: { term: 'The look', from: 'lab',
    what: 'What a player could see, from positions alone: a defender with his man and the ball more than 120° apart has lost one.',
    more: 'A closer arriving more than 60° off the direction the ball came from is out of the shooter’s view. Full rules in docs/the_look.md.' },
  moments: { term: 'Moments', from: 'lab',
    what: 'Shots conceded off a catch in set defence, 3 s or more into the chance, off a broken rotation.',
    more: 'Broken means nobody assigned to the shooter for 1 s or more, or his man 6 ft or more beyond his normal spot when the pass left.' },
  league: { term: 'The league figure', from: 'lab',
    what: 'The same measure over all ten games, so a defence is read against its league rather than on its own.',
    more: 'On a tile, the dot beside it is amber when this defence conceded more than the league, blue when less, grey within 5 %.' },
  transition: { term: 'Transition', from: 'lab',
    what: 'Points per transition possession conceded, by how many defenders were between the ball and their basket as it crossed into the front court.',
    more: '0–2 back is the broken end of it; the tile shows that end because it is the one a defence can do something about.' },
  bill: { term: 'The bill', from: 'lab',
    what: 'The two figures that summarise a defence: points conceded beyond the quality of the looks, and what the rotations cost.',
    more: 'Below them, the game quarter by quarter: what the looks were worth against what was scored, and the price of the rotations under each.' },
  who_paid: { term: 'Who paid', from: 'lab',
    what: 'The rotation ledger by the defender it names, with the shots and close-outs it came from.',
    more: 'A shot with nobody assigned is priced to nobody rather than to the nearest man; the footnote says how many.' },

  // ─── symbols on the page ──────────────────────────────────────────────────
  shot_marks: { term: 'The shot marks', from: 'lab',
    what: 'A green disc went in. A dark cross did not.',
    more: 'Green is SkillCorner’s own mark colour, used here to say "made" and nothing else. The cross carries a pale halo so it stays readable where shots pile up at the rim.' },
  worth: { term: 'Worth', from: 'sc',
    what: 'Expected points per shot from that zone, from SkillCorner’s shot quality.',
    more: 'It is what the looks were worth, not what was scored: compare it with the made column beside it.' },
  zones: { term: 'The six zones', from: 'lab',
    what: 'The rim, the paint, mid-range, corner threes, wing threes and top threes.',
    more: 'Cut from the shot position alone, so every conceded attempt lands in exactly one of them.' },
  tension: { term: 'Amber and blue', from: 'lab',
    what: 'The only colour that carries a number: amber is worse than the league or a costlier rotation, blue is better or tighter.',
    more: 'Everything else on the page is ink, glass or a club colour. If something is amber or blue, it is telling you a quantity.' },

  // ─── what is drawn ────────────────────────────────────────────────────────
  figures: { term: 'The figures', from: 'drawn',
    what: 'One modelled body (Quaternius, CC0) posed by rules from position, speed and events: the data carries no body pose.',
    more: 'Arms, legs and gaze are generated. They make a play readable as basketball; no measurement is taken from a limb.' },
  bounces: { term: 'Bounces and spin', from: 'drawn',
    what: 'The reconstructed ball stops a foot or two above the floor on a dribble; the picture pulls it down at each dribble label.',
    more: 'Backspin in the air and roll in the hand are drawn for the same reason. Nothing is measured from either.' },
  kits: { term: 'Kits, crests and the floor', from: 'drawn',
    what: 'Club colours from public knowledge, on a template floor: the data carries names only.',
    more: 'The crests are the clubs’ trademarks, shown to identify them; SkillCorner’s mark credits the data. The floor is a template, not any arena’s real court.' },
  cameras: { term: 'The Director', from: 'drawn',
    what: 'A camera that cuts with the play, choosing its seats from SkillCorner’s labels; any seat can be picked by hand.',
    more: 'Eye-level gaze is generated from where the ball and the hoop are, not tracked.' },
  tv_side: { term: 'TV side', from: 'drawn',
    what: 'A play opens on the sideline the real broadcast camera sat on, so the attack runs the way it ran on television.',
    more: 'Unchecking the box crosses to the other sideline. The crest painted at centre court turns with the seat, as an arena’s does.' },
  clip: { term: 'TV clip', from: 'drawn',
    what: 'Real footage beside the animation, for reference only, and only if a clip sits on this machine.',
    more: 'No clip is ever in the repository and no number on these pages is read from one.' },
};

/** The references page reads this order; the three groups are the question a reader actually has. */
export const GROUPS = [
  { from: 'sc', title: 'What SkillCorner gives us', ids: ['tracking', 'shot_quality', 'matchups', 'labels', 'worth', 'seen', 'season'] },
  { from: 'lab', title: 'What is computed here', ids: ['normal_spot', 'beyond', 'price', 'strip', 'chapters', 'selection', 'glass', 'look', 'moments', 'league', 'transition', 'bill', 'who_paid', 'zones', 'shot_marks', 'tension'] },
  { from: 'drawn', title: 'What is drawn, not measured', ids: ['figures', 'bounces', 'kits', 'cameras', 'tv_side', 'clip'] },
];
