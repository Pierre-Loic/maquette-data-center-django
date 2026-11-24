/* =====================================================================
   La vie d'un prompt — écran du haut (observation)
   Rejoue les événements de la génération lancée depuis l'écran du bas.
   ===================================================================== */
(function () {
  'use strict';
  const { CFG, COL, maintenant, getEtat, phasesA, secondes } = window.VP;
  const PHN = CFG.phases, INFO = CFG.infos, MODELS = CFG.modeles, RAMBASE = CFG.ramBase;
  // Chaque flèche s'anime pendant une ou plusieurs étapes (s) :
  // lecture du prompt et génération utilisent toutes deux le chemin RAM → CPU
  const ARROWS = [
    { s: [0], d: 'M338 128H562' }, { s: [0], d: 'M608 128H654' },
    { s: [1], d: 'M858 118H964' },
    { s: [2], d: 'M858 440H964' },
    { s: [3, 4], d: 'M1065 376V234' },
    { s: [4], d: 'M964 162H858' }, { s: [4], d: 'M654 152H608' }, { s: [4], d: 'M562 152H338' },
  ];
  const NODES = { screen: [0, 4], net: [0, 4], entry: [1, 4], rack: [1, 2, 3, 4], flash: [2], ram: [2, 3, 4], cpu: [3, 4] };
  const NARR = CFG.narration;
  const IDLE = '#C3CBDD';

  const $ = id => document.getElementById(id);
  const stage = $('stage'), wrap = $('wrap'), svg = $('arrows'), defs = $('defs'), NS = 'http://www.w3.org/2000/svg';
  let st = ['idle', 'idle', 'idle', 'idle', 'idle'], timers = [], running = false;
  let run = null, runId = null, selection = null, charges = {};
  let tokTimes = [], genStarted = false, enErreur = false, lecture = null, statsFin = null;
  // mesures affichées (simulées ; remplaçables par de vraies mesures avec promptTrace.setMetrics)
  const M = { cpuT: 43, cpuF: 1.5, cpuU: 3, ramU: RAMBASE, ramT: RAMBASE };
  let live = false;

  /* ---- flèches ---- */
  function marker(id, color) {
    const m = document.createElementNS(NS, 'marker');
    for (const [k, v] of Object.entries({ id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerUnits: 'userSpaceOnUse', markerWidth: 24, markerHeight: 24, orient: 'auto' })) m.setAttribute(k, v);
    const p = document.createElementNS(NS, 'path'); p.setAttribute('d', 'M0 0L10 5L0 10z'); p.setAttribute('fill', color);
    m.appendChild(p); defs.appendChild(m);
  }
  marker('mk-idle', IDLE); COL.forEach((c, i) => marker('mk' + i, c));
  const paths = ARROWS.map(a => {
    const p = document.createElementNS(NS, 'path'); p.setAttribute('d', a.d); svg.appendChild(p);
    const h = document.createElementNS(NS, 'path'); h.setAttribute('d', a.d); h.setAttribute('class', 'hit'); h.setAttribute('data-key', 'p' + Math.max(...a.s)); svg.appendChild(h);
    return p;
  });

  /* ---- étapes ---- */
  const stepBtns = PHN.map((n, i) => {
    const b = document.createElement('li'); b.className = 'step'; b.style.setProperty('--sc', COL[i]); b.setAttribute('data-key', 'p' + i);
    b.innerHTML = '<i>' + (i + 1) + '</i><span></span>'; b.querySelector('span').textContent = n;
    $('steps').appendChild(b); return b;
  });

  /* Le schéma (1200 × 560) est mis à l'échelle pour occuper la place disponible */
  function fit() {
    const s = Math.min(wrap.clientWidth / 1200, wrap.clientHeight / 560);
    stage.style.transform = 'translate(' + Math.max(0, (wrap.clientWidth - 1200 * s) / 2) + 'px,0) scale(' + s + ')';
  }
  // Recalcul dès que la zone change de taille (fenêtre, barre de paramètres remplie après coup…)
  if (window.ResizeObserver) new ResizeObserver(fit).observe(wrap); else window.addEventListener('resize', fit);

  /* ---- info-bulles ---- */
  const tip = $('tip'); let curEl = null;
  function tipHTML(k) {
    const d = INFO[k]; if (!d) return '';
    const e = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
    return '<b>' + e(d.t) + '</b><p>' + e(d.w) + '</p><p><em>Maquette :</em> ' + e(d.m) + '</p><p><em>En vrai :</em> ' + e(d.r) + '</p>' + (d.l ? '<div class="lim">⚠ ' + e(d.l) + '</div>' : '');
  }
  function place(x, y) {
    const w = tip.offsetWidth, h = tip.offsetHeight, vw = window.innerWidth, vh = window.innerHeight;
    let l = x + 18, t = y + 18; if (l + w > vw - 8) l = x - w - 18; if (t + h > vh - 8) t = y - h - 18;
    tip.style.left = Math.max(8, l) + 'px'; tip.style.top = Math.max(8, t) + 'px';
  }
  function showTip(el, x, y) {
    const k = el.getAttribute('data-key'); if (!INFO[k]) return;
    if (curEl !== el) {
      if (curEl) curEl.classList.remove('hov');
      curEl = el; tip.innerHTML = tipHTML(k);
      const ph = /^p(\d)$/.exec(k); tip.style.setProperty('--tc', ph ? COL[+ph[1]] : '#5a6080');
      if (['chip', 'step', 'box', 'block'].some(c => el.classList.contains(c))) el.classList.add('hov');
    }
    tip.classList.add('show'); place(x, y);
  }
  function hideTip() { tip.classList.remove('show'); if (curEl) { curEl.classList.remove('hov'); curEl = null; } }
  document.addEventListener('mousemove', e => {
    const el = e.target.closest && e.target.closest('[data-key]');
    if (el) showTip(el, e.clientX, e.clientY); else hideTip();
  });
  document.addEventListener('mouseleave', hideTip);

  function clearTimers() { timers.forEach(clearTimeout); timers = []; }
  function after(ms, f) { timers.push(setTimeout(f, ms)); }

  function refresh() {
    paths.forEach((p, k) => {
      const ss = ARROWS[k].s;
      const actif = ss.filter(i => st[i] === 'active').pop(), fait = ss.filter(i => st[i] === 'done').pop();
      const s = actif != null ? actif : fait != null ? fait : ss[0];
      const v = actif != null ? 'active' : fait != null ? 'done' : st[ss[0]] === 'skip' ? 'skip' : 'idle';
      p.setAttribute('class', 'line ' + v);
      if (v === 'active' || v === 'done') { p.style.stroke = COL[s]; p.style.color = COL[s]; p.setAttribute('marker-end', 'url(#mk' + s + ')'); }
      else { p.style.stroke = ''; p.style.color = ''; p.setAttribute('marker-end', 'url(#mk-idle)'); }
    });
    Object.keys(NODES).forEach(k => {
      let c = -1; NODES[k].forEach(p => { if (st[p] === 'active') c = Math.max(c, p); });
      const el = $(k); el.classList.toggle('on', c >= 0); if (c >= 0) el.style.setProperty('--cur', COL[c]);
    });
    stepBtns.forEach((b, i) => { b.classList.remove('active', 'done', 'skip'); if (st[i] !== 'idle') b.classList.add(st[i]); });
    $('b3').classList.toggle('show', st[2] === 'active');
    $('b5').classList.toggle('show', st[3] === 'active');   // lecture : tout d'un coup
    $('b4').classList.toggle('show', st[4] === 'active');   // génération : le goulot
    $('strip').classList.toggle('lecture', st[3] === 'active');
    const act = st.lastIndexOf('active');
    $('narration').style.setProperty('--nc', act >= 0 ? COL[act] : '#5a6080');
    document.body.classList.toggle('vp-en-cours', running);
  }

  const toks = $('toks'), answer = $('answer'), chips = document.querySelectorAll('.chip');
  function addTok(cls, txt) { const e = document.createElement('span'); e.className = 'tok ' + cls; e.textContent = txt.trim() || txt; toks.appendChild(e); return e; }
  function addAns(txt) {
    const e = document.createElement('span'); e.className = 'new'; e.textContent = txt; answer.appendChild(e);
    setTimeout(() => { e.className = ''; }, 60);
    answer.scrollTop = answer.scrollHeight;  // une longue réponse défile vers le bas
    answer.classList.toggle('deborde', answer.scrollHeight > answer.clientHeight);
  }

  /* ---- bandeau « Ce qui se passe » ---- */
  const NARR_ATTENTE = 'Choisissez une question, un Raspberry Pi et un modèle, puis envoyez.';
  const fill = (t, v) => t.replace(/\{(\w+)\}/g, (m, k) => v[k] != null ? v[k] : m);
  const duree = ms => ms < 1000 ? (ms / 1000).toFixed(2).replace('.', ',') + ' s' : secondes(ms);
  function narrer(texte) {
    const p = $('narrTxt');
    if (p.textContent === texte) return;
    p.textContent = texte; p.classList.remove('nouveau'); void p.offsetWidth; p.classList.add('nouveau');
  }
  /* Bilan final : lire (en parallèle) va bien plus vite qu'écrire (token par token) */
  function bilan() {
    const S = statsFin || {};
    if (S.total_ms != null) {   // réponse reçue d'un bloc : pas de détail
      $('mGen').textContent = '≈ ' + S.gen_tokens + ' tokens · ' + duree(S.total_ms);
      narrer(fill(NARR.fin_sans_detail, { duree: duree(S.total_ms) }));
      return;
    }
    const nL = S.prompt_tokens || (lecture && lecture.n), msL = S.prompt_ms || (lecture && lecture.ms);
    const cache = S.prompt_cached || 0;   // tokens déjà calculés lors d'une requête précédente
    const n = tokTimes.length;
    const nE = S.gen_tokens || n;
    const msE = S.gen_ms || (n > 1 ? tokTimes[n - 1] - tokTimes[0] : null);
    if (nL && msL) $('mLecture').textContent = nL + ' tokens · ' + duree(msL) + (cache ? ' (' + cache + ' en cache)' : '');
    if (nE && msE) $('mGen').textContent = nE + ' tokens · ' + duree(msE);
    if (nL && cache > nL / 2 && nE && msE) {
      // l'essentiel du prompt était en cache : une vitesse de lecture serait trompeuse
      const nLus = nL - cache;
      const relus = nLus > 1 ? 'seuls ' + nLus + ' tokens sur ' + nL + ' ont été relus' : 'un seul token sur ' + nL + ' a été relu';
      narrer(fill(NARR.fin_cache, { relus, v_ecriture: fmt(nE / (msE / 1000), 1) }));
    } else if (nL && msL && nE && msE) {
      const vL = nL / (msL / 1000), vE = nE / (msE / 1000);
      narrer(fill(NARR.fin, { v_lecture: Math.round(vL), v_ecriture: fmt(vE, 1), ratio: Math.max(1, Math.round(vL / vE)) }));
    }
  }

  /* ---- réception d'un événement de la génération ---- */
  function handle(e) {
    switch (e.type) {
      case 'sent':
        running = true; narrer(NARR.envoi);
        chips.forEach((c, k) => after(300 + k * 450, () => c.classList.add('lit'))); break;
      case 'tokenized':
        narrer(NARR.decoupage);
        e.tokens.forEach((t, k) => after(k * 300, () => { if (!genStarted) addTok('in', t); }));
        // le pré-prompt est lu lui aussi : il compte dans les tokens du prompt
        if (e.n_prompt) after(e.tokens.length * 300, () => {
          if (!genStarted) addTok('in pre', 'pré-prompt +' + Math.max(0, e.n_prompt - e.tokens.length - (e.n_cache || 0)));
        });
        // certains modèles ajoutent leur propre pré-prompt, invisible pour l'utilisateur
        if (e.n_cache) after(e.tokens.length * 300 + 900, () => {
          if (genStarted) return;
          addTok('in cache', 'pré-prompt caché ' + e.fournisseur + ' +' + e.n_cache);
          narrer(fill(NARR.preprompt_cache, { fournisseur: e.fournisseur, n: e.n_cache }));
        });
        break;
      case 'load_start':
        M.ramT = RAMBASE; $('ramSub').textContent = 'chargement…';
        narrer(fill(NARR.chargement, { modele: run.model })); break;
      case 'load_progress': M.ramT = RAMBASE + MODELS[run.model].ram * e.pct / 100; break;
      case 'loaded':
        M.ramT = RAMBASE + MODELS[run.model].ram; $('ramSub').textContent = run.model;
        if (e.duree_ms != null) narrer(fill(NARR.charge, { duree: duree(e.duree_ms) })); break;
      case 'load_skipped':
        M.ramT = RAMBASE + MODELS[run.model].ram; $('ramSub').textContent = run.model;
        narrer(fill(NARR.deja_charge, { modele: run.model })); break;
      case 'prefill_start':
        narrer(fill(NARR.lecture, { n: e.n_prompt }));
        $('mLecture').textContent = '≈ ' + e.n_prompt + ' tokens…'; break;
      case 'prefill_end':
        lecture = { n: e.n_prompt, ms: e.duree_ms };
        $('mLecture').textContent = '≈ ' + e.n_prompt + ' tokens' + (e.duree_ms != null ? ' · ' + duree(e.duree_ms) : '');
        break;
      case 'generation_start':
        genStarted = true; toks.innerHTML = '';
        narrer(lecture && lecture.ms != null ? fill(NARR.generation, { duree: duree(lecture.ms) }) : NARR.generation_sans_duree);
        break;
      case 'token': {
        tokTimes.push(e.tr != null ? e.tr : e.t);  // heure réelle d'arrivée (mode réel)
        const el = addTok('out', e.text);
        after(450, () => { el.className = 'tok go'; after(180, () => { el.remove(); addAns(e.text); }); });
        break;
      }
      case 'generation_end': statsFin = e.stats || null; bilan(); break;
      case 'done': running = false; break;
      case 'error': {
        running = false; enErreur = true; toks.innerHTML = '';
        narrer('⚠ ' + e.message);
        const m = document.createElement('span'); m.className = 'erreur'; m.textContent = '⚠ ' + e.message;
        answer.appendChild(m);
        break;
      }
    }
    st = phasesA(run.evenements, e.t);
    refresh();
  }

  function reset() {
    clearTimers(); st = ['idle', 'idle', 'idle', 'idle', 'idle']; running = false; tokTimes = []; genStarted = false; enErreur = false; lecture = null; statsFin = null;
    chips.forEach(c => c.classList.remove('lit'));
    toks.innerHTML = ''; answer.innerHTML = '';
    $('mElapsed').textContent = '—'; $('mLecture').textContent = '—'; $('mGen').textContent = '—';
    narrer(NARR_ATTENTE);
  }

  /* Nouvelle génération */
  let planifies = 0;
  function demarrer(r) {
    reset(); run = r; planifies = 0;
    $('cpuTitle').textContent = 'CPU · Pi ' + r.pi;
    $('flashSub').textContent = r.model;
    $('promptTxt').textContent = '« ' + CFG.questions[r.q].q + ' »';
    $('ramSub').textContent = 'vide';
    refresh();
  }
  /* Planifie les événements pas encore traités : ceux déjà passés sont appliqués
     tout de suite. En mode réel, de nouveaux événements arrivent à chaque
     interrogation du serveur, au fil de la réponse du Pi. */
  function planifier(r) {
    run = r;
    const ecoule = maintenant() - r.debut;
    for (let i = planifies; i < r.evenements.length; i++) {
      const e = r.evenements[i];
      if (e.t <= ecoule) handle(e);
      else after(e.t - ecoule, () => handle(e));
    }
    planifies = r.evenements.length;
  }

  /* Aperçu du Pi et du modèle choisis sur l'écran du bas (hors génération) */
  function apercu() {
    if (running || !selection) return;
    if (run && run.duree === null) return;  // génération réelle pas encore terminée
    $('cpuTitle').textContent = 'CPU · Pi ' + selection.pi;
    $('flashSub').textContent = selection.model;
    const l = charges[selection.pi];
    $('ramSub').textContent = l || 'vide';
    M.ramT = RAMBASE + (l ? MODELS[l].ram : 0);
  }

  /* ---- mesures du Pi : simulées en mode démo, lues sur le vrai Pi en mode réel ---- */
  const tgt = { u: 3, f: 1.5, t: 43 };
  const fmt = (n, d) => n.toFixed(d).replace('.', ',');
  const val = (v, txt) => (v == null || isNaN(v)) ? '—' : txt(v);
  function renderM() {
    const tcol = M.cpuT >= 70 ? 'var(--c4)' : M.cpuT >= 60 ? 'var(--c3)' : '';
    $('cpuT').textContent = val(M.cpuT, v => Math.round(v) + ' °C'); $('cpuT').style.color = tcol;
    $('cpuF').textContent = val(M.cpuF, v => fmt(v, 1) + ' GHz');
    $('cpuU').textContent = val(M.cpuU, v => Math.round(v) + ' %'); $('cpubar').style.width = (M.cpuU || 0) + '%';
    $('ramU').textContent = val(M.ramU, v => Math.round(v) + ' %'); $('ramfill').style.width = (M.ramU || 0) + '%';
  }
  if (CFG.mode === 'reel') {
    live = true;
    M.cpuT = M.cpuF = M.cpuU = M.ramU = null;
    const lireMesures = async () => {
      const pi = run && run.duree === null ? run.pi : (selection ? selection.pi : (run ? run.pi : 1));
      try {
        const r = await fetch(CFG.urlMetriques + '?pi=' + pi, { cache: 'no-store' });
        const m = await r.json();
        if (!m.ok) { M.cpuT = M.cpuF = M.cpuU = M.ramU = null; }
        else {
          M.cpuT = m.temperature_c; M.cpuU = m.cpu_load_percent; M.ramU = m.ram_used_percent;
          M.cpuF = m.cpu_freq_mhz == null ? null : m.cpu_freq_mhz / 1000;
        }
      } catch (err) { M.cpuT = M.cpuF = M.cpuU = M.ramU = null; }
      renderM();
    };
    lireMesures();
    setInterval(lireMesures, 1000);
  }
  setInterval(() => {
    if (!live) {
      const pi = running && run ? run.pi : (selection ? selection.pi : 1);
      const base = CFG.pis[pi] || 43;
      if (st[3] === 'active' || st[4] === 'active') { tgt.u = 96 + Math.random() * 4; tgt.f = 2.4; tgt.t = 72; }
      else if (st[2] === 'active') { tgt.u = 22 + Math.random() * 6; tgt.f = 1.8; tgt.t = 55; }
      else if (running) { tgt.u = 8; tgt.f = 1.5; tgt.t = 50; }
      else { tgt.u = 3; tgt.f = 1.5; tgt.t = base; }
      M.cpuU += (tgt.u - M.cpuU) * .35;
      M.cpuF += (tgt.f - M.cpuF) * .25;
      M.cpuT += (tgt.t - M.cpuT) * (tgt.t > M.cpuT ? .03 : .012);
      M.ramU += (M.ramT - M.ramU) * .4;
    }
    renderM();
    if (!run) return;
    $('mElapsed').textContent = secondes(running || run.duree === null ? Math.max(0, maintenant() - run.debut) : run.duree);
    if (statsFin) return;  // valeurs finales exactes déjà affichées par bilan()
    const n = tokTimes.length;
    if (n > 1) $('mGen').textContent = n + ' tokens · ' + fmt((n - 1) / ((tokTimes[n - 1] - tokTimes[0]) / 1000), 1) + ' tokens/s';
    else if (n === 1) $('mGen').textContent = '1 token';
  }, 200);

  window.promptTrace = {
    setMetrics(m) {
      live = true;
      if (m.cpuTemp != null) M.cpuT = m.cpuTemp; if (m.cpuFreqGHz != null) M.cpuF = m.cpuFreqGHz;
      if (m.cpuUtil != null) M.cpuU = m.cpuUtil; if (m.ramUtil != null) M.ramU = m.ramUtil;
      renderM();
    },
  };

  /* ---- synchronisation avec le serveur ---- */
  function traiter(e) {
    selection = e.selection; charges = e.charges;
    if (e.run) {
      if (e.run.id !== runId) { runId = e.run.id; demarrer(e.run); }
      planifier(e.run);
    } else if (runId !== null) {
      // Génération oubliée (retour à l'accueil) : schéma remis à l'état initial
      runId = null; run = null; reset();
      $('promptTxt').textContent = ''; $('ramSub').textContent = 'vide';
      refresh();
    }
    apercu();
  }
  async function boucle() {
    try { traiter(await getEtat()); } catch (err) { /* serveur indisponible : on réessaie */ }
  }
  // Page combinée : l'écran de commande de la même page prévient directement
  window.addEventListener('vp:etat', ev => traiter(ev.detail));

  fit(); refresh(); renderM();
  boucle();
  setInterval(boucle, 300);
})();
