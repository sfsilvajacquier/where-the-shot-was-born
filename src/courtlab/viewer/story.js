// The Story tab: the chapter the play is in right now, with its one number, its sentence and the league figure it quotes.
// Chapters come from the possession file (courtlab.chapters); nothing is computed here, only chosen and worded.

const CI = (s) => (s && s.ci ? ` [${s.ci[0].toFixed(2)}–${s.ci[1].toFixed(2)}]` : '');
const F = (v, nd = 2) => (v == null ? '–' : (Math.round((Number(v) + Number.EPSILON) * 10 ** nd) / 10 ** nd).toFixed(nd));  // 1.095 → 1.10, not 1.09

/** One sentence of league context for a chapter, worded for the play at hand. */
export function leagueLine(key, stats, d, chapter) {
  const s = stats[key];
  if (!s) return '';
  const games = d.league && d.league.n_games ? `${d.league.n_games} games` : 'the league';
  if (key === 'pick_coverage') {
    const pick = [...d.actions].reverse().find((a) => a.type === 'pick' && a.i != null && a.i <= chapter.i1);
    const cov = pick ? `${pick.coverage}/${pick.screener_coverage}` : null;
    const row = s.rows.find((r) => r.coverage === cov) || s.rows[0];
    return `League · ball screens defended ${row.coverage}: a team-mate is pulled ${F(row.stretch_ft, 1)} ft beyond normal at +1.2 s; ${F(row.points_per_possession)} pts per possession${CI(row)} (n ${row.n}, ${games}).`;
  }
  if (key === 'unowned_shooter') {
    return `League · a shot off a catch with nobody assigned to the shooter for 1 s or more is worth ${F(s.value)} expected pts${CI(s)}, against ${F(s.baseline.value)} with his man in place (n ${s.n} / ${s.baseline.n}).`;
  }
  if (key === 'race') {
    return `League · a pass travels ${F(s.pass_speed.value, 0)} ft/s, a close-out runs ${F(s.closeout_top_speed.value, 1)}; starting 0.4 s late costs ${s.late_start_price.value >= 0 ? '+' : ''}${F(s.late_start_price.value)} expected pts${CI(s.late_start_price)} (n ${s.late_start_price.n}).`;
  }
  if (key === 'open_three_by_shooter') {
    const shooter = d.players.find((p) => p.id === (d.actions.find((a) => a.type === 'shot') || {}).player);
    const s3 = shooter && shooter.season_three, pct = s3 && s3.attempts >= 40 ? s3.made / s3.attempts : null;
    const [lo, hi] = s.thresholds, name = pct == null ? null : pct < lo ? 'bottom third' : pct < hi ? 'middle third' : 'top third';
    const rows = s.rows.map((r) => `${r.tercile.split(' ')[0]} ${F(r.scored)}`).join(' · ');
    return `League · an open three off a broken rotation scores, by the shooter's season accuracy: ${rows} pts per shot, while the model says ~${F(s.rows[1].quality_says, 1)} for all` + (name ? ` (this shooter: ${name}).` : '.');
  }
  if (key === 'one_more_pass') {
    const r = Object.fromEntries(s.rows.map((x) => [String(x.passes), x.value]));
    return `League · a shot after the action is worth ${F(r['0'])} expected pts with no pass, ${F(r['1'])} with one, ${F(r['2'])} with two (n ${s.n}).`;
  }
  if (key === 'shot_selection') {
    return `League · SkillCorner expects ${F(s.expected_per_shot)} pts per shot; a team's shot making in one game runs from ${F(s.percentiles['25'], 0)} to ${F(s.percentiles['75'], 0)} pts per 100 shots around that.`;
  }
  return '';
}

export class Story {
  constructor(el, data) {
    this.el = el; this.d = data;
    this.chapters = data.chapters || [];
    this.stats = (data.league && data.league.stats) || {};
    this.current = null;
    this.no = el.querySelector('#story-no'); this.big = el.querySelector('#story-big'); this.unit = el.querySelector('#story-unit');
    this.context = el.querySelector('#story-context'); this.league = el.querySelector('#story-league'); this.price = el.querySelector('#story-price'); this.look = el.querySelector('#story-look');
  }

  /** The chapter that contains frame t, or null. */
  at(t) {
    const i = Math.round(t);
    return this.chapters.find((c) => i >= c.i0 && i <= c.i1) || null;
  }

  /** Fill the tab for a chapter; returns true when the chapter changed. */
  render(c) {
    if (c === this.current) return false;
    this.current = c;
    if (!c) return true;
    const k = this.chapters.indexOf(c) + 1;
    this.no.textContent = `Chapter ${k} of ${this.chapters.length}`;
    const v = c.big.value;
    const sign = c.big.unit === 'ft' && v != null && v > 0 ? '+' : '';
    this.big.textContent = v == null ? '–' : `${sign}${Number.isInteger(v) ? v : v.toFixed(1)}${c.big.unit === '%' ? ' %' : ''}`;
    this.unit.textContent = (c.big.unit === '%' ? '' : `${c.big.unit} · `) + c.big.label;
    this.context.textContent = c.context;
    this.league.textContent = leagueLine(c.league_key, this.stats, this.d, c);
    if (c.price) { this.price.hidden = false; this.price.innerHTML = `Price of the rotation: <b>${c.price.value >= 0 ? '+' : ''}${c.price.value.toFixed(2)} pts</b> · ${c.price.kind} · ${c.price.note}.`; }
    else this.price.hidden = true;
    if (c.look) { this.look.hidden = false; this.look.textContent = c.look.text; } else this.look.hidden = true;  // what he could see, from positions (docs/the_look.md)
    this.el.classList.remove('fresh'); void this.el.offsetWidth; this.el.classList.add('fresh');  // a short fade on each new chapter
    return true;
  }
}
