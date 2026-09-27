// The `i` beside a heading, and the panel it opens. One definition lives in glossary.js and is read from here, so a hover and the
// references page can never drift apart.
//
// Hover opens it, moving away closes it, a click pins it open (so it can be read at leisure, and so a tap works), Escape or a click
// anywhere else closes it. It is never the only way to reach a definition: reference.html has all of them on one page.

import { TERMS, SOURCES } from './glossary.js';

/** The markup for one `i`. `ids` are glossary keys, in the order the panel should list them. */
export function infoMark(...ids) {
  const list = ids.flatMap((i) => String(i).split(',')).map((i) => i.trim()).filter((i) => TERMS[i]);
  if (!list.length) return '';
  return `<button class="inf" type="button" tabindex="-1" data-info="${list.join(',')}" aria-label="What ${TERMS[list[0]].term} means">i</button>`;
}

const panel = (ids) => ids.map((id) => {
  const t = TERMS[id], s = SOURCES[t.from];
  return `<div class="ientry"><p class="ihead"><span class="iterm">${t.term}</span><span class="ifrom ${t.from}">${s.label}</span></p><p class="iwhat">${t.what}</p></div>`;
}).join('');

/**
 * Wire every `i` under `root` (delegated, so cards re-rendered later keep working).
 * `root` must be the scaled stage: the panel is positioned inside it, in stage pixels.
 */
export function wireInfo(root) {
  if (root.__info) return root.__info;
  const pop = document.createElement('div');
  pop.className = 'infopop glass';
  pop.hidden = true;
  root.appendChild(pop);
  let pinned = null, over = null;

  const place = (btn) => {
    const b = btn.getBoundingClientRect(), r = root.getBoundingClientRect();
    const scale = (r.width / root.offsetWidth) || 1;  // the stage is drawn at 1920 and scaled to the window
    const cx = (b.left + b.width / 2 - r.left) / scale, top = (b.top - r.top) / scale, h = b.height / scale;
    pop.style.left = `${Math.round(Math.min(Math.max(cx - pop.offsetWidth / 2, 16), root.offsetWidth - pop.offsetWidth - 16))}px`;
    const below = top + h + 12;
    pop.style.top = `${Math.round(below + pop.offsetHeight > root.offsetHeight - 16 ? top - pop.offsetHeight - 12 : below)}px`;
  };
  const open = (btn) => {
    pop.innerHTML = panel(btn.dataset.info.split(','))
      + '<a class="iall" href="reference.html">All the references →</a>';
    pop.hidden = false;
    place(btn);
  };
  const close = () => { pop.hidden = true; pinned = null; over = null; };

  root.addEventListener('pointerover', (e) => {
    const btn = e.target.closest && e.target.closest('.inf');
    if (!btn || btn === over || pinned) return;
    over = btn; open(btn);
  });
  root.addEventListener('pointerout', (e) => {
    const btn = e.target.closest && e.target.closest('.inf');
    if (!btn || pinned) return;
    if (e.relatedTarget && (pop.contains(e.relatedTarget) || btn.contains(e.relatedTarget))) return;
    over = null; pop.hidden = true;
  });
  // the `i` sits inside a card that opens on click: the card must not hear this one
  root.addEventListener('pointerdown', (e) => { if (e.target.closest && e.target.closest('.inf')) e.stopPropagation(); }, true);
  root.addEventListener('click', (e) => {
    const btn = e.target.closest && e.target.closest('.inf');
    if (btn) { e.stopPropagation(); e.preventDefault(); if (pinned === btn) close(); else { pinned = btn; open(btn); } return; }
    if (!pop.contains(e.target)) close();
  }, true);
  pop.addEventListener('pointerleave', () => { if (!pinned) close(); });
  addEventListener('keydown', (e) => { if (e.key === 'Escape' && !pop.hidden) { close(); e.stopPropagation(); } }, true);
  root.__info = { close };
  return root.__info;
}
