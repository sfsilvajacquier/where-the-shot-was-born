// The HUD in three levels, as a game does it. Full: the column and the strip (analyse). Minimal: the time pill, one subtitle
// with the chapter, and a chapter scrubber that shows on mouse move (watch). None: the scene; the controls show on mouse move.
// The camera chooses the level by default (cinematic cameras → Minimal); the user's own choice is kept until the camera changes.
// Nothing is remembered between visits: a play opens the way its camera wants it.

const LEVELS = ['full', 'minimal', 'none'];
const CINEMATIC = new Set(['auto', 'behind', 'eyes', 'rail']);
const AWAKE_MS = 2000;

export class Hud {
  constructor(stage, { onChange, onSeek }) {
    this.stage = stage; this.onChange = onChange; this.onSeek = onSeek;
    this.level = 'full'; this.forced = false; this.timer = null;
    this.sel = stage.querySelector('#hudsel'); this.sub = stage.querySelector('#subtitle'); this.scrub = stage.querySelector('#scrub');
    this.head = this.scrub.querySelector('.head'); this.segs = this.scrub.querySelector('.segs');
    for (const b of this.sel.querySelectorAll('button')) b.onclick = () => this.set(b.dataset.tab, true);
    stage.addEventListener('pointermove', () => this.wake());
    this.scrub.addEventListener('pointerdown', (e) => { this.scrubbing = true; this.scrub.setPointerCapture(e.pointerId); this.seek(e); });
    this.scrub.addEventListener('pointermove', (e) => { if (this.scrubbing) this.seek(e); });
    this.scrub.addEventListener('pointerup', () => { this.scrubbing = false; });
    this.n = 1; this.chapters = [];
  }

  static defaultFor(camera) { return CINEMATIC.has(camera) ? 'minimal' : 'full'; }

  /** The camera changed: unless the user forced a level, take the camera's default. */
  camera(id) { if (!this.forced) this.set(Hud.defaultFor(id), false); }

  set(level, byUser) {
    if (!LEVELS.includes(level)) level = 'full';
    this.level = level;
    if (byUser) this.forced = true;
    for (const l of LEVELS) this.stage.classList.toggle(`hud-${l}`, l === level);
    for (const b of this.sel.querySelectorAll('button')) b.setAttribute('aria-selected', String(b.dataset.tab === level));
    this.stage.classList.toggle('nopanel', level !== 'full');
    this.stage.querySelector('.strip').classList.toggle('folded', level !== 'full');
    this.wake();
    if (this.onChange) this.onChange(level);
  }

  cycle() { this.set(LEVELS[(LEVELS.indexOf(this.level) + 1) % LEVELS.length], true); }

  /** Something moved: the scrubber and the controls show for two seconds (always, when motion is off). */
  wake() {
    this.stage.classList.add('awake');
    clearTimeout(this.timer);
    if (!this.stage.classList.contains('nomotion')) this.timer = setTimeout(() => this.stage.classList.remove('awake'), AWAKE_MS);
  }

  /** The chapters as segments of the scrubber; call once the play is loaded. */
  chapterSegments(chapters, n) {
    this.chapters = chapters || []; this.n = n;
    this.segs.innerHTML = '';
    for (const c of this.chapters) {
      const s = document.createElement('span');
      s.className = 'chap'; s.title = c.title;
      s.style.left = `${(100 * c.i0) / n}%`; s.style.width = `${(100 * (c.i1 - c.i0 + 1)) / n}%`;
      this.segs.append(s);
    }
  }

  seek(e) {
    const r = this.scrub.getBoundingClientRect();
    const f = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    if (this.onSeek) this.onSeek(f * (this.n - 1));
  }

  /** Per frame: the playhead of the scrubber and the subtitle of the chapter. */
  update(t, chapter) {
    this.head.style.left = `${(100 * t) / Math.max(1, this.n - 1)}%`;
    for (const s of this.segs.children) s.classList.toggle('on', !!chapter && s.title === chapter.title);
    if (chapter !== this.shown) {
      this.shown = chapter;
      if (chapter) {
        const v = chapter.big.value, sign = chapter.big.unit === 'ft' && v != null && v > 0 ? '+' : '';
        const value = v == null ? '' : `${sign}${Number.isInteger(v) ? v : v.toFixed(1)}${chapter.big.unit === '%' ? ' %' : chapter.big.unit === 's' ? ' s' : ` ${chapter.big.unit}`}`;
        this.sub.innerHTML = `<span class="k">${chapter.title}</span><span class="v">${value}</span><span class="l">${chapter.big.label}</span>`;
        this.sub.hidden = false;
      } else this.sub.hidden = true;
    }
  }
}
