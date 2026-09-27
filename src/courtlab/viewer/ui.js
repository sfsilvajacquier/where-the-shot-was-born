// The pieces every screen shares: one focused row at all times, a detail card that waits a beat, the key legend, the segmented
// control, the quarter-second dip between states, the mini tension strip and club short names. Home, the marks card and the
// match report are built from these and nothing else for those jobs (docs/contracts.md §7).

import { css } from './palette.js';

/** A club's short name: the last word, unless that is a generic ("Bilbao Basket" → Bilbao, "Valencia BC" → Valencia), keeping "Gran Canaria" and "Real Madrid" whole. */
export const short = (name) => {
  const w = (name || '').split(' ').filter(Boolean);
  if (!w.length) return '';
  if (['Basket', 'BC', 'CB', 'Baloncesto', 'Basketball'].includes(w[w.length - 1]) && w.length > 1) w.pop();
  return w.length > 1 && ['Gran', 'Real', 'San'].includes(w[w.length - 2]) ? w.slice(-2).join(' ') : w[w.length - 1];
};

/** The stage scaled to the window, before anything has loaded: the failure state is laid out like everything else. */
export function place(stage, W = 1920, H = 1080) {
  const fit = () => { stage.style.transform = `scale(${Math.min(innerWidth / W, innerHeight / H)}) translate(-50%, -50%)`; };
  addEventListener('resize', fit); fit();
}

/** Nothing loaded: the page shows one message and nothing else; `why` says what to do, as HTML. */
export function fail(stage, why) {
  stage.classList.add('failed'); stage.classList.remove('booting');
  const el = stage.querySelector('#error');
  el.hidden = false; el.innerHTML = why;
}

/** The dip: darken, do the switch in the dark, come back. A newer dip simply takes over an older one. */
let dipToken = 0;
export function dip(during) {
  const mine = ++dipToken, el = document.getElementById('dip'), still = document.getElementById('stage').classList.contains('nomotion');
  el.classList.add('on');
  setTimeout(() => { if (mine !== dipToken) return; during(); setTimeout(() => { if (mine === dipToken) el.classList.remove('on'); }, still ? 0 : 40); }, still ? 0 : 230);
}

/** The miniature of the tension strip: one row per attacker, the real colours, a light tick at the release. */
export function miniStrip(cv, thumb, release) {
  const c = cv.getContext('2d'), rows = thumb || [], w = cv.width, h = cv.height, rh = h / Math.max(rows.length, 1);
  c.fillStyle = 'rgba(255,255,255,0.06)'; c.fillRect(0, 0, w, h);
  rows.forEach((row, i) => {
    const cw = w / row.length;
    row.forEach((v, k) => { if (v != null) { c.fillStyle = css(v, v < 0 ? 0.6 : 1); c.fillRect(k * cw, i * rh + 1, cw + 0.5, rh - 2); } });
  });
  if (release != null) { c.fillStyle = 'rgba(255,255,255,0.85)'; c.fillRect(Math.round(release * w) - 1, 0, 2, h); }
}

/** One focused row at all times: the mouse moves the focus and never clears it; ↑↓ move it, ↵ opens. Rows never take the browser's focus. */
export class FocusList {
  constructor(root, rows, { render, onFocus, onOpen, visible = 7, className = 'play' }) {
    this.root = root; this.list = rows; this.onFocus = onFocus; this.onOpen = onOpen;
    this.focus = 0; this.opening = false;
    this.rows = rows.map((r, k) => {
      const b = document.createElement('button');
      b.className = className; b.setAttribute('role', 'option'); b.tabIndex = -1; b.style.setProperty('--i', k);
      render(b, r, k);
      b.onmouseenter = () => this.setFocus(k);
      b.onfocus = () => this.setFocus(k);
      b.onclick = () => this.open(k);
      root.append(b);
      return b;
    });
    root.classList.toggle('fits', this.rows.length <= visible);
  }

  setFocus(k, silent = false) {
    if (!this.rows.length) return;
    this.focus = (k + this.rows.length) % this.rows.length;
    this.rows.forEach((b, i) => b.setAttribute('aria-selected', String(i === this.focus)));
    this.rows[this.focus].scrollIntoView({ block: 'nearest', behavior: silent ? 'instant' : 'smooth' });
    if (this.onFocus) this.onFocus(this.list[this.focus], this.focus, silent);
  }

  focusWhere(pred, silent = true) { this.setFocus(Math.max(0, this.list.findIndex(pred)), silent); }

  open(k = this.focus) {
    if (this.opening || !this.rows.length) return;  // a key and a click can both fire for one press
    this.opening = true; setTimeout(() => { this.opening = false; }, 600);
    if (this.onOpen) this.onOpen(this.list[k], k);
  }

  /** Returns true when the key was handled. */
  key(e) {
    if (e.key === 'ArrowDown' || e.key === 'ArrowRight') { e.preventDefault(); this.setFocus(this.focus + 1); return true; }
    if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') { e.preventDefault(); this.setFocus(this.focus - 1); return true; }
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this.open(); return true; }
    return false;
  }
}

/** The detail card of the focused row: shows after a beat, so moving fast through a list does not flicker. */
export class Detail {
  constructor(el, delay = 120) { this.el = el; this.delay = delay; this.timer = null; }
  show(fill, silent = false) {  // fill(el) writes the content and returns false to hide the card
    clearTimeout(this.timer);
    const go = () => { const ok = fill(this.el); this.el.hidden = ok === false; };
    if (silent) go(); else this.timer = setTimeout(go, this.delay);
  }
}

/** The key legend: [[['↵'], 'Open'], [['↑', '↓'], 'Choose']]. */
export function keys(el, items) {
  el.innerHTML = items.map(([ks, label]) => `<span>${ks.map((k) => `<kbd>${k}</kbd>`).join('')} ${label}</span>`).join('');
}

/** The segmented control: buttons with data-tab; `set` marks one, `enable` wakes or sleeps one, `onChange` fires on a click. */
export class Tabs {
  constructor(el, { onChange, attr = 'aria-selected' }) {
    this.el = el; this.attr = attr; this.buttons = [...el.querySelectorAll('button')];
    for (const b of this.buttons) b.onclick = () => { if (!b.disabled) { this.set(b.dataset.tab); if (onChange) onChange(b.dataset.tab); } };
  }
  get value() { return (this.buttons.find((b) => b.getAttribute(this.attr) === 'true') || {}).dataset?.tab; }
  set(name) { for (const b of this.buttons) b.setAttribute(this.attr, String(b.dataset.tab === name)); }
  enable(name, on) { const b = this.buttons.find((x) => x.dataset.tab === name); if (b) b.disabled = !on; }
}
