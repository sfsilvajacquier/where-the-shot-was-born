// The references page: every term the viewer uses, on one page, grouped by where the figure came from. It reads from glossary.js,
// the same file the `i` panels read, so a hover and this page can never say different things. No data is loaded: it is a document.

import { place, dip, keys } from './ui.js';
import { TERMS, SOURCES, GROUPS } from './glossary.js';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);

function main() {
  $('stage').classList.add('booting');
  place($('stage'));
  if (params.get('motion') === '0' || matchMedia('(prefers-reduced-motion: reduce)').matches) $('stage').classList.add('nomotion');

  $('ref').innerHTML = GROUPS.map((g) => `<section class="ref-group" data-from="${g.from}">`
    + `<p class="section">${g.title}<span class="hint">${SOURCES[g.from].hint}</span></p>`
    + `<div class="ref-grid">${g.ids.map((id) => {
      const t = TERMS[id];
      return `<article class="ref-card glass" id="t-${id}" data-from="${t.from}"><h3>${t.term}<span class="ifrom ${t.from}">${SOURCES[t.from].label}</span></h3>`
        + `<p class="what">${t.what}</p>${t.more ? `<p class="more">${t.more}</p>` : ''}</article>`;
    }).join('')}</div></section>`).join('');

  // the filter: a term may sit in a group whose heading says "computed here" while the term itself is SkillCorner's (worth, say), so
  // the filter reads each card's own source rather than its group's
  const FILTERS = [['all', 'Everything'], ...Object.keys(SOURCES).map((k) => [k, SOURCES[k].label])];
  $('filters').innerHTML = FILTERS.map(([k, label]) => `<button data-tab="${k}" role="tab" aria-selected="${k === 'all'}">${label}</button>`).join('');
  const apply = (which) => {
    for (const b of $('filters').querySelectorAll('button')) b.setAttribute('aria-selected', String(b.dataset.tab === which));
    for (const c of $('ref').querySelectorAll('.ref-card')) c.classList.toggle('out', which !== 'all' && c.dataset.from !== which);
    for (const g of $('ref').querySelectorAll('.ref-group')) g.hidden = !g.querySelector('.ref-card:not(.out)');
    $('ref').scrollTop = 0;
  };
  for (const b of $('filters').querySelectorAll('button')) b.onclick = () => apply(b.dataset.tab);
  apply(['sc', 'lab', 'drawn'].includes(params.get('from')) ? params.get('from') : 'all');

  keys(document.querySelector('.keys'), [[['↑', '↓'], 'Scroll'], [['Esc'], 'Home']]);
  const home = () => dip(() => { location.href = './?start=1'; });
  $('back').onclick = home;
  addEventListener('keydown', (e) => { if (e.key === 'Escape') home(); });
  // a term linked to from an `i` panel or from a page: reference.html#t-price scrolls to it and marks it for a moment
  const wanted = location.hash && $('ref').querySelector(location.hash);
  if (wanted) wanted.scrollIntoView({ block: 'center' });

  requestAnimationFrame(() => { $('stage').classList.add('up'); $('stage').classList.remove('booting'); });
}

document.fonts.load('700 48px Inter').then(main, main);
