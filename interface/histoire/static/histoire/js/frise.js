/* =====================================================================
   LA FRISE DE L'IA — code du jeu (version stand SEPEM)
   Pas besoin de modifier ce fichier pour changer les textes ou les cartes :
   voir frise_contenu.js. Les scores sont enregistrés dans la base Django.
   ===================================================================== */
document.addEventListener('DOMContentLoaded', () => {
'use strict';

const API = JSON.parse(document.getElementById('frise-config').textContent);

const fill = (s, v) => {
  const all = Object.assign({ n: N, minutes: MIN, penalite: PEN / 1000, themes: ORDER.length }, v);
  for (const x of Object.keys(all)) s = s.split('{' + x + '}').join(all[x]);
  return s;
};
const tx = (k, v) => TEXTES[k] == null ? '[' + k + ']' : fill(TEXTES[k], v);
const TH = {};
for (const k of Object.keys(THEMES)) TH[k] = { name: THEMES[k].nom, desc: THEMES[k].description, bg: THEMES[k].couleurFond, ink: THEMES[k].couleurTexte };
const CARDS = CARTES.map(c => ({ th: c.theme, year: String(c.annee), y: Number(c.annee), where: c.lieu || '', title: c.titre, body: c.texte }));
const ORDER = Object.keys(THEMES);
const N = REGLAGES.nbCartes, TOTAL = REGLAGES.dureeSecondes * 1000, PEN = REGLAGES.penaliteSecondes * 1000, COUNT = REGLAGES.decompte;
const MIN = Math.round(REGLAGES.dureeSecondes / 60);
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function h(tag, props, ...kids) {
  const e = document.createElement(tag);
  if (props) for (const k of Object.keys(props)) {
    const v = props[k];
    if (v == null || v === false) continue;
    if (k === 'class') e.className = v;
    else if (k === 'text') e.textContent = v;
    else if (k === 'style') e.style.cssText = v;
    else if (k.slice(0, 2) === 'on') e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v === true ? '' : String(v));
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c);
  return e;
}
const shuffle = a => { for (let i = a.length - 1; i > 0; i--) { const j = Math.floor(Math.random() * (i + 1)); [a[i], a[j]] = [a[j], a[i]]; } return a; };
const fmt = ms => { const s = Math.max(0, Math.ceil(ms / 1000)); return Math.floor(s / 60) + ':' + String(s % 60).padStart(2, '0'); };
const fmtDur = ms => { const s = Math.round(ms / 1000); return tx('formatDuree', { m: Math.floor(s / 60), s: String(s % 60).padStart(2, '0') }); };
const announce = t => { const l = $('#live'); l.textContent = ''; setTimeout(() => { l.textContent = t; }, 40); };
const themeStyle = t => '--fbg:' + t.bg + ';--fink:' + t.ink;

/* recto : thématique + titre */
function rectoEl(id, root, extra) {
  const c = CARDS[id], t = TH[c.th];
  return h(root || 'span', { class: 'card' + (extra ? ' ' + extra : ''), style: themeStyle(t) },
    h('span', { class: 'c-top' }, h('span', { class: 'tag', text: t.name })),
    h('span', { class: 'c-title', text: c.title }));
}
/* verso : date (si trouvée) + lieu + texte */
function versoEl(id, full) {
  const c = CARDS[id], t = TH[c.th];
  return h('article', { class: 'verso', style: themeStyle(t) },
    h('div', { class: 'v-band' },
      h('div', { class: 'v-row' }, h('span', { text: t.name })),
      full ? h('div', { class: 'v-row2' }, h('span', { class: 'v-year', text: c.year }), h('span', { class: 'v-where', text: c.where }))
           : h('div', { class: 'v-row2' }, h('span', { class: 'v-year', 'aria-label': tx('versoDateAria'), text: tx('versoDateInconnue') }))),
    h('h3', { class: 'v-title', id: 'vs-title', text: c.title }),
    h('p', { class: 'v-body', text: c.body }));
}
function openVerso(id, full) {
  $('#vs-body').replaceChildren(versoEl(id, full));
  const d = $('#verso'); if (!d.open) d.showModal();
  $('#vs-close').focus();
}

/* ---- classement (base de données Django) ---- */
let RANKS = API.classements || {};
async function refreshRanks() {
  try {
    const r = await fetch(API.urlClassement, { cache: 'no-store' });
    if (r.ok) RANKS = (await r.json()).classements;
  } catch (e) { /* hors ligne : on garde le dernier classement connu */ }
}
async function postScore(entry) {
  const r = await fetch(API.urlScore, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-CSRFToken': API.csrf },
    body: JSON.stringify(entry),
  });
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}

/* ---- tirage : N cartes, années toutes différentes ---- */
function draw(th) {
  const pool = shuffle(CARDS.map((c, i) => i).filter(i => CARDS[i].th === th));
  const used = new Set(), out = [];
  for (const i of pool) { if (!used.has(CARDS[i].y)) { used.add(CARDS[i].y); out.push(i); if (out.length === N) break; } }
  return out;
}

/* ---- navigation ---- */
let G = null, rankTheme = ORDER[0], lastEntry = null;
function show(p) {
  for (const id of ['p2', 'p3', 'p4']) $('#' + id).hidden = id !== p;
  document.body.dataset.ecran = p;
  window.scrollTo(0, 0);
}
const playing = () => !!(G && G.running && !G.over);
function stopTimer() { if (G && G.timer) { clearInterval(G.timer); G.timer = null; } G && (G.running = false); }
function renderThemes() {
  $('#themes').replaceChildren(...ORDER.map(k => {
    const t = TH[k], best = (RANKS[k] || [])[0];
    return h('button', { type: 'button', class: 'theme', 'data-th': k, onclick: () => start(k) },
      h('span', { class: 'theme-card', style: themeStyle(t) },
        h('span', { class: 'theme-name', text: t.name }),
        h('span', { class: 'theme-desc', text: t.desc }),
        h('span', { class: 'theme-meta' + (best ? '' : ' none'),
          text: best ? tx('selectionRecord', { temps: fmtDur(best.ms), nom: best.pseudo }) : tx('selectionSansRecord') })));
  }));
}
function goSelect() {
  stopTimer(); $('#cd').hidden = true; G = null;
  renderThemes();
  show('p2');
  refreshRanks().then(() => { if (!$('#p2').hidden) renderThemes(); });
}

/* ---- partie ---- */
function start(th) {
  rankTheme = th; lastEntry = null;
  const ids = draw(th);
  G = { th, ids, slots: ids.slice().sort((a, b) => CARDS[a].y - CARDS[b].y), hand: shuffle(ids.slice()), placed: Array(N).fill(null),
        sel: null, errors: 0, ok: 0, t0: 0, timer: null, running: false, over: false, flash: -1, nope: -1 };
  $('#h-theme').textContent = TH[th].name;
  $('#h-theme').style.cssText = themeStyle(TH[th]);
  $('#h-time').textContent = fmt(TOTAL); $('#h-time').classList.remove('low');
  $('#hand').replaceChildren(); $('#frise').replaceChildren();
  show('p3');
  $('#p3').hidden = true;
  const cd = $('#cd'), n = $('#cd-n'); cd.hidden = false;
  n.textContent = String(COUNT); announce(String(COUNT));
  const me = G;
  setTimeout(() => { if (G === me) renderBoard(); }, 60);   // le plateau est préparé pendant le décompte
  let k = COUNT;
  const next = () => {
    if (G !== me || me.running) return;
    k--;
    if (k > 0) { n.textContent = String(k); n.style.animation = 'none'; void n.offsetWidth; n.style.animation = ''; announce(String(k)); setTimeout(next, 1000); }
    else { cd.hidden = true; begin(); }
  };
  setTimeout(next, 1000);
}
function begin() {
  $('#p3').hidden = false;
  G.running = true; G.t0 = Date.now();
  updateHud();
  G.timer = setInterval(tick, 100);
  announce(tx('annonceDepart', { minutes: MIN }));
}
const elapsed = () => Date.now() - G.t0;
const total = () => elapsed() + PEN * G.errors;
function tick() {
  if (!G || !G.running) return;
  const left = TOTAL - total();
  if (left <= 0) return finish(false);
  updateHud(left);
  const s = Math.ceil(left / 1000);
  if ([180, 120, 60, 30, 10].includes(s) && G.lastSay !== s) { G.lastSay = s; announce(tx('annonceReste', { temps: fmt(left) })); }
}
function updateHud(left) {
  if (left == null) left = TOTAL - total();
  const t = $('#h-time'); t.firstChild.nodeValue = fmt(left); t.classList.toggle('low', left <= 30000);
  $('#h-bar').style.width = (100 * Math.max(0, left) / TOTAL) + '%';
  $('#h-bar').classList.toggle('low', left <= 30000);
  $('#h-err').textContent = G.errors; $('#h-ok').textContent = G.ok + '/' + N;
}
function renderBoard() {
  const armed = G.sel != null;
  $('#hand').replaceChildren(...G.hand.map(id => {
    const b = h('button', { type: 'button', class: 'hcard' + (G.nope === id ? ' nope' : ''), draggable: 'true', 'data-id': id,
      'aria-pressed': G.sel === id ? 'true' : 'false', 'aria-label': tx('ariaCarte', { titre: CARDS[id].title, theme: TH[CARDS[id].th].name }),
      onclick: () => { G.sel = G.sel === id ? null : id; renderBoard(); },
      ondragstart: e => { G.sel = id; e.dataTransfer.setData('text/plain', String(id)); e.dataTransfer.effectAllowed = 'move'; setTimeout(() => b.classList.add('dragging'), 0); $('#frise').classList.add('armed'); },
      ondragend: () => { b.classList.remove('dragging'); $('#frise').classList.toggle('armed', G && G.sel != null && G.hand.includes(G.sel)); } }, rectoEl(id));
    return h('div', { class: 'hwrap' }, b,
      h('button', { type: 'button', class: 'vbtn', 'aria-label': tx('ariaLireVerso', { titre: CARDS[id].title }), onclick: () => openVerso(id, false) }, tx('jeuLireVerso')));
  }));
  $('#g-hint').textContent = G.hand.length ? tx(armed ? 'jeuAideSelection' : 'jeuAide') : tx('jeuAideFin');
  $('#g-hint').classList.toggle('armed', armed);
  $('#frise').className = 'grid6 frise-slots' + (armed ? ' armed' : '');
  $('#frise').replaceChildren(...G.slots.map((sid, i) => {
    const y = CARDS[sid].y, pl = G.placed[i];
    return h('div', { class: 'slot-wrap' + (pl != null ? ' placed' : '') },
      h('div', { class: 's-date', text: String(y) }),
      pl != null ? h('button', { type: 'button', class: 'plwrap', 'aria-label': tx('ariaLireVerso', { titre: CARDS[pl].title }), onclick: () => openVerso(pl, true) }, rectoEl(pl, 'span'), h('span', { class: 'badge', 'aria-hidden': 'true', text: '✓' }))
        : h('button', { type: 'button', class: 'dropzone' + (G.flash === i ? ' flash' : ''), 'aria-label': tx('ariaDeposer', { annee: y }),
            onclick: () => { if (G.sel == null) { announce(tx('annonceChoisir')); return; } attempt(G.sel, i); },
            ondragover: e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; },
            ondragenter: e => e.currentTarget.classList.add('over'),
            ondragleave: e => e.currentTarget.classList.remove('over'),
            ondrop: e => { e.preventDefault(); const id = parseInt(e.dataTransfer.getData('text/plain'), 10); if (!isNaN(id)) attempt(id, i); } },
          tx('jeuDeposer')));
  }));
}
function attempt(id, i) {
  if (!playing() || G.placed[i] != null || !G.hand.includes(id)) return;
  G.sel = null;
  if (CARDS[id].y === CARDS[G.slots[i]].y) {
    G.placed[i] = id; G.hand = G.hand.filter(x => x !== id); G.ok++;
    announce(tx('annonceBonne', { annee: CARDS[id].year }));
    renderBoard(); updateHud();
    if (G.ok === N) finish(true);
  } else {
    G.errors++; G.flash = i; G.nope = id;
    announce(tx('annonceMauvaise', { n: PEN / 1000 }));
    const t = $('#h-time'); t.classList.remove('pulse'); void t.offsetWidth; t.classList.add('pulse');
    t.append(h('span', { class: 'pen', 'aria-hidden': 'true', text: tx('jeuPenaliteFlash', { n: PEN / 1000 }) }));
    setTimeout(() => { $$('.pen', t).forEach(x => x.remove()); }, 1200);
    renderBoard(); updateHud();
    if (TOTAL - total() <= 0) return finish(false);
    setTimeout(() => { if (G && !G.over) { G.flash = -1; G.nope = -1; renderBoard(); } }, 600);
  }
}

/* ---- résultats ---- */
function finish(win) {
  if (!G || G.over) return;
  const ms = Math.min(total(), win ? total() : TOTAL);
  stopTimer(); G.over = true; G.win = win; G.ms = Math.round(ms);
  show('p4');
  $('#p4').classList.toggle('lost', !win);
  $('#p4-title').textContent = tx(win ? 'resTitreVictoire' : 'resTitreDefaite');
  if (win) {
    $('#r-time').textContent = fmtDur(G.ms);
    $('#r-sub').textContent = G.errors ? tx('resDetailErreurs', { n: G.errors, pen: G.errors * PEN / 1000 }) : tx('resDetailSansErreur');
  } else {
    $('#r-time').textContent = tx('resScoreDefaite', { ok: G.ok, n: N });
    $('#r-sub').textContent = tx('resDetailDefaite');
  }
  $('#save').hidden = !win; $('#saved').hidden = true;
  $('#pseudo').value = '';
  $('#save button').disabled = false;
  renderSolution();
  renderRank();
  if (win) setTimeout(() => $('#pseudo').focus(), 50);
  announce(win ? tx('annonceVictoire', { temps: fmtDur(G.ms) }) : tx('resTitreDefaite'));
}
/* La bonne frise : cartes de la partie dans l'ordre, cliquables pour lire le verso */
function renderSolution() {
  $('#solution').replaceChildren(...G.slots.map((id, i) => {
    const c = CARDS[id], t = TH[c.th], ok = G.placed[i] != null;
    return h('button', { type: 'button', class: 'tile-btn', onclick: () => openVerso(id, true), 'aria-label': tx('ariaLireVerso', { titre: c.title }) },
      h('span', { class: 'tile' + (ok ? '' : ' bad'), style: themeStyle(t) },
        h('span', { class: 't-year', text: c.year }),
        h('span', { class: 't-title', text: c.title })));
  }));
}
function renderRank() {
  $('#rank-chips').replaceChildren(...ORDER.map(k => h('button', { type: 'button', class: 'chip', style: themeStyle(TH[k]),
    'aria-pressed': k === rankTheme ? 'true' : 'false', text: TH[k].name, onclick: () => { rankTheme = k; renderRank(); } })));
  const rows = RANKS[rankTheme] || [];
  $('#rank').replaceChildren(...(rows.length ? rows.map((e, i) => h('li', { class: e.id === lastEntry ? 'me' : '' },
    h('span', { class: 'rk-n', text: (i + 1) + '.' }),
    h('span', { class: 'rk-name', text: e.pseudo }),
    h('span', { class: 'rk-t', text: fmtDur(e.ms) }), h('span', { class: 'rk-e', text: tx('classementErreurs', { n: e.erreurs }) })))
    : [h('li', { class: 'rank-empty', text: tx('classementVide') })]));
}

/* ---- textes des écrans ---- */
$$('[data-t]').forEach(e => { e.textContent = tx(e.dataset.t); });
$$('[data-t-aria]').forEach(e => { e.setAttribute('aria-label', tx(e.dataset.tAria)); });
$('#rules').replaceChildren(...TEXTES.accueilRegles.map(r => h('li', { text: fill(r) })));
$('#h-ok').textContent = '0/' + N;

/* ---- branchements ---- */
$('#quit').addEventListener('click', goSelect);
$('#replay').addEventListener('click', () => start(G.th));
$('#other').addEventListener('click', goSelect);
$('#vs-close').addEventListener('click', () => $('#verso').close());
$('#verso').addEventListener('click', e => { if (e.target === $('#verso')) $('#verso').close(); });
$('#save').addEventListener('submit', async e => {
  e.preventDefault();
  if (!G || !G.win || lastEntry) return;
  const btn = $('#save button'); btn.disabled = true;
  const pseudo = $('#pseudo').value.trim().slice(0, 20) || tx('pseudoDefaut');
  const s = $('#saved');
  try {
    const res = await postScore({ theme: G.th, ms: G.ms, erreurs: G.errors, pseudo });
    RANKS = res.classements; lastEntry = res.score.id; rankTheme = G.th;
    $('#save').hidden = true;
    s.classList.remove('ko');
    s.textContent = res.rang === 1 ? tx('resEnregistrePremier', { nom: res.score.pseudo })
                                   : tx('resEnregistre', { nom: res.score.pseudo, rang: res.rang, total: res.total });
    renderRank();
  } catch (err) {
    btn.disabled = false;
    s.classList.add('ko'); s.textContent = tx('resErreurEnregistrement');
  }
  s.hidden = false;
});
goSelect();
});
