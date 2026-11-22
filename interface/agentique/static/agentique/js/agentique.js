/* =====================================================================
   L'IA qui agit — schéma animé de la boucle d'un agent IA
   Le serveur déroule la mission (événements datés) ; la page les rejoue.
   ===================================================================== */
(function () {
  'use strict';
  const CFG = JSON.parse(document.getElementById('ag-config').textContent);
  const $ = id => document.getElementById(id);
  const PHASES = Object.keys(CFG.phases);
  const COL = { comprendre: '#1B9CD9', planifier: '#7C5CD6', agir: '#EE8A0B', observer: '#2FAA4A', repondre: '#E5383B' };
  const OUTILS = Object.keys(CFG.outils);
  const TOP_OUTIL = { capteurs: 80, doc: 190, gmao: 300, message: 410 };

  /* ---------------- horloge commune avec le serveur ---------------- */
  let decalage = 0;
  const maintenant = () => Date.now() + decalage;
  async function appel(url, data) {
    const r = await fetch(url, data === undefined ? { cache: 'no-store' } : {
      method: 'POST', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrf },
      body: JSON.stringify(data),
    });
    const e = await r.json();
    if (e.serveur) decalage = e.serveur - Date.now();
    return e;
  }

  /* ---------------- flèches ---------------- */
  const svg = $('arrows'), defs = $('defs'), NS = 'http://www.w3.org/2000/svg';
  function marker(id, color) {
    const m = document.createElementNS(NS, 'marker');
    for (const [k, v] of Object.entries({ id, viewBox: '0 0 10 10', refX: 9, refY: 5, markerUnits: 'userSpaceOnUse', markerWidth: 22, markerHeight: 22, orient: 'auto' })) m.setAttribute(k, v);
    const p = document.createElementNS(NS, 'path'); p.setAttribute('d', 'M0 0L10 5L0 10z'); p.setAttribute('fill', color);
    m.appendChild(p); defs.appendChild(m);
  }
  marker('mk-idle', '#C3CBDD');
  for (const [ph, c] of Object.entries(COL)) marker('mk-' + ph, c);
  const FLECHES = { in: 'M284 120H336', out: 'M336 160H284' };
  for (const o of OUTILS) {
    const y = TOP_OUTIL[o];
    FLECHES['call-' + o] = `M784 ${y + 35}H851`;
    FLECHES['res-' + o] = `M851 ${y + 68}H784`;
  }
  const PHASE_FLECHE = k => k === 'in' ? 'comprendre' : k === 'out' ? 'repondre' : k.startsWith('call') ? 'agir' : 'observer';
  const paths = {};
  for (const [k, d] of Object.entries(FLECHES)) {
    const p = document.createElementNS(NS, 'path'); p.setAttribute('d', d); svg.appendChild(p); paths[k] = p;
  }
  function fleche(k, etat) {
    const p = paths[k], ph = PHASE_FLECHE(k);
    p.setAttribute('class', 'line ' + etat);
    if (etat === 'idle') { p.style.stroke = ''; p.setAttribute('marker-end', 'url(#mk-idle)'); }
    else { p.style.stroke = COL[ph]; p.style.color = COL[ph]; p.setAttribute('marker-end', 'url(#mk-' + ph + ')'); }
  }
  let flecheActive = null;
  function activerFleche(k) {
    if (flecheActive && flecheActive !== k) fleche(flecheActive, 'done');
    flecheActive = k;
    if (k) fleche(k, 'active');
  }

  /* ---------------- étapes de la boucle ---------------- */
  $('steps').replaceChildren(...PHASES.map((ph, i) => {
    const li = document.createElement('li');
    li.className = 'step'; li.style.setProperty('--sc', COL[ph]); li.dataset.ph = ph;
    li.innerHTML = '<i>' + (i + 1) + '</i><span></span>';
    li.querySelector('span').textContent = CFG.phases[ph];
    return li;
  }));
  const boucle = document.createElement('li');
  boucle.className = 'step boucle'; boucle.innerHTML = '<span>↺ la boucle recommence tant que la mission n’est pas finie</span>';
  $('steps').appendChild(boucle);

  /* ---------------- mise à l'échelle du schéma ---------------- */
  const stage = $('stage'), wrap = $('wrap');
  function fit() {
    const s = Math.min(wrap.clientWidth / 1200, wrap.clientHeight / 560);
    stage.style.transform = 'translate(' + Math.max(0, (wrap.clientWidth - 1200 * s) / 2) + 'px,0) scale(' + s + ')';
  }
  if (window.ResizeObserver) new ResizeObserver(fit).observe(wrap); else window.addEventListener('resize', fit);

  /* ---------------- info-bulles ---------------- */
  const tip = $('tip'); let curEl = null;
  const esc = s => String(s).replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
  document.addEventListener('mousemove', e => {
    const el = e.target.closest && e.target.closest('#stage [data-key]');
    const d = el && CFG.infos[el.dataset.key];
    if (!d) { tip.classList.remove('show'); if (curEl) curEl.classList.remove('hov'); curEl = null; return; }
    if (curEl !== el) {
      if (curEl) curEl.classList.remove('hov');
      curEl = el; el.classList.add('hov');
      tip.innerHTML = '<b>' + esc(d.t) + '</b><p>' + esc(d.w) + '</p>' + (d.r ? '<p class="r">' + esc(d.r) + '</p>' : '');
    }
    tip.classList.add('show');
    const w = tip.offsetWidth, h = tip.offsetHeight;
    let l = e.clientX + 18, t = e.clientY + 18;
    if (l + w > innerWidth - 8) l = e.clientX - w - 18; if (t + h > innerHeight - 8) t = e.clientY - h - 18;
    tip.style.left = Math.max(8, l) + 'px'; tip.style.top = Math.max(8, t) + 'px';
  });

  /* ---------------- rejeu des événements ---------------- */
  let run = null, runId = null, planifies = 0, timers = [], courant = null, enAttente = false;
  let nbOutils = 0, actions = [];
  const after = (ms, f) => timers.push(setTimeout(f, ms));

  function phaseActive(ph) {
    courant = ph;
    const vus = new Set((run ? run.evenements : []).filter(e => e.t <= maintenant() - run.debut).map(e => e.phase));
    for (const li of $('steps').children) {
      if (!li.dataset.ph) continue;
      li.classList.toggle('active', li.dataset.ph === ph);
      li.classList.toggle('done', li.dataset.ph !== ph && vus.has(li.dataset.ph));
    }
    $('agent').classList.toggle('on', ['comprendre', 'planifier', 'observer'].includes(ph));
    $('agent').style.setProperty('--cur', COL[ph] || COL.planifier);
    $('mEtape').textContent = ph ? CFG.phases[ph] : (run ? 'Terminé' : 'En attente');
  }

  let ecriture = null;
  function ecrire(el, texte) {   // effet « en train d'écrire » (annule le précédent)
    clearInterval(ecriture);
    el.textContent = '';
    let i = 0;
    const pas = Math.max(1, Math.round(texte.length / 40));
    ecriture = setInterval(() => { i += pas; el.textContent = texte.slice(0, i); if (i >= texte.length) clearInterval(ecriture); }, 25);
  }

  function outilActif(o, etat) {
    for (const k of OUTILS) $('o-' + k).classList.remove('on');
    if (!o) return;
    const b = $('o-' + o);
    b.classList.add('on');
    b.style.setProperty('--cur', COL[etat]);
  }

  function majActions() {
    if (!actions.length) { $('mActions').textContent = '—'; return; }
    const n = k => actions.filter(a => a === k).length;
    const parts = [];
    if (n('ok')) parts.push(n('ok') + ' validée' + (n('ok') > 1 ? 's' : ''));
    if (n('ko')) parts.push(n('ko') + ' refusée' + (n('ko') > 1 ? 's' : ''));
    if (n('auto')) parts.push(n('auto') + ' sans contrôle');
    $('mActions').textContent = parts.join(' · ');
  }

  function handle(e) {
    switch (e.type) {
      case 'sent':
        $('mission').textContent = e.text; $('mission').classList.add('lit');
        activerFleche('in'); break;
      case 'think':
        ecrire($('penseeTxt'), e.text); $('pensee').classList.remove('flash'); void $('pensee').offsetWidth; $('pensee').classList.add('flash');
        outilActif(null); activerFleche(null); break;
      case 'plan':
        $('planList').replaceChildren(...e.items.map(t => { const li = document.createElement('li'); li.textContent = t; return li; }));
        break;
      case 'plan_step': {
        const li = $('planList').children[e.index];
        if (li) li.className = e.etat;
        break;
      }
      case 'tool_call': {
        nbOutils++; $('mOutils').textContent = nbOutils;
        const b = $('o-' + e.outil);
        b.querySelector('.outil-call').textContent = e.text;
        b.querySelector('.outil-res').textContent = '…';
        outilActif(e.outil, 'agir'); b.classList.add('used'); activerFleche('call-' + e.outil); break;
      }
      case 'tool_result': {
        const b = $('o-' + e.outil);
        b.querySelector('.outil-res').textContent = e.text;
        outilActif(e.outil, 'observer'); activerFleche('res-' + e.outil);
        const li = document.createElement('li'); li.textContent = e.note;
        const mem = $('memList'); mem.appendChild(li);
        mem.scrollTop = mem.scrollHeight; mem.classList.toggle('deborde', mem.scrollHeight > mem.clientHeight + 2);
        break;
      }
      case 'validation':
        enAttente = true;
        $('garde').classList.add('show'); $('garde').classList.remove('auto');
        $('garde').querySelector('span').textContent = 'Validation humaine requise';
        outilActif(e.outil, 'agir'); activerFleche(null); break;
      case 'decision':
        enAttente = false; actions.push(e.ok ? 'ok' : 'ko'); majActions();
        $('garde').classList.remove('show'); break;
      case 'auto':
        actions.push('auto'); majActions();
        $('garde').querySelector('span').textContent = 'Action lancée sans contrôle humain';
        $('garde').classList.add('show', 'auto');
        after(1800, () => $('garde').classList.remove('show', 'auto')); break;
      case 'answer_start':
        $('answer').textContent = ''; outilActif(null); activerFleche('out'); break;
      case 'token':
        $('answer').append(e.text); $('answer').scrollTop = $('answer').scrollHeight; break;
      case 'done':
        activerFleche(null); fleche('out', 'done'); outilActif(null);
        $('agent').classList.remove('on'); break;
    }
    if (e.type === 'done') { courant = null; phaseActive(null); for (const li of $('steps').children) if (li.dataset.ph) li.classList.add('done'); }
    else if (e.phase) phaseActive(e.phase);
  }

  function reset() {
    timers.forEach(t => clearTimeout(t)); timers = []; clearInterval(ecriture);
    planifies = 0; nbOutils = 0; actions = []; enAttente = false; courant = null;
    $('mOutils').textContent = '—'; majActions();
    $('mission').textContent = 'Choisissez une mission en bas de l’écran'; $('mission').classList.remove('lit');
    $('mEtape').textContent = 'En attente'; $('mTemps').textContent = '—';
    $('agent').classList.remove('on');
    $('answer').textContent = ''; $('penseeTxt').textContent = '…';
    $('planList').replaceChildren(); $('memList').replaceChildren(); $('memList').classList.remove('deborde');
    $('garde').classList.remove('show', 'auto');
    for (const o of OUTILS) {
      const b = $('o-' + o); b.classList.remove('on', 'used');
      b.querySelector('.outil-call').textContent = '';
      b.querySelector('.outil-res').textContent = CFG.outils[o].desc;
    }
    for (const k of Object.keys(paths)) fleche(k, 'idle');
    flecheActive = null;
    for (const li of $('steps').children) li.classList.remove('active', 'done');
  }

  function planifier(r) {
    run = r;
    const ecoule = maintenant() - r.debut;
    for (let i = planifies; i < r.evenements.length; i++) {
      const e = r.evenements[i];
      if (e.t <= ecoule) handle(e); else after(e.t - ecoule, () => handle(e));
    }
    planifies = r.evenements.length;
  }

  /* ---------------- barre de paramètres ---------------- */
  const sel = { mission: CFG.missions[0].cle, autonomie: 'valider' };
  function seg(id, items, cle) {
    $(id).replaceChildren(...items.map(it => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'opt' + (it.cls ? ' ' + it.cls : ''); b.dataset.v = it.value;
      b.innerHTML = '<span class="opt-l"></span><small></small>';
      b.querySelector('.opt-l').textContent = it.label; b.querySelector('small').textContent = it.sub || '';
      b.onclick = () => { sel[cle] = it.value; marquer(); };
      return b;
    }));
  }
  function marquer() {
    for (const [id, cle] of [['missions', 'mission'], ['autonomies', 'autonomie']])
      for (const b of $(id).children) b.classList.toggle('sel', b.dataset.v === sel[cle]);
  }
  seg('missions', CFG.missions.map(m => ({ label: m.titre, value: m.cle })), 'mission');
  seg('autonomies', Object.entries(CFG.autonomies).map(([k, a]) => ({ label: a.titre, sub: a.desc, value: k, cls: 'au-' + k })), 'autonomie');
  marquer();

  let etat = null, envoi = false;
  function rendreBarre() {
    // Le panneau de validation n'apparaît que lorsque l'animation atteint la demande
    const enCours = !!(etat && etat.en_cours), att = etat && etat.attente && enAttente ? etat.attente : null;
    const rejeu = !!(etat && etat.attente) && !enAttente;  // animation pas encore arrivée à la demande
    document.body.classList.toggle('ag-en-cours', enCours || rejeu || !!att);
    $('send').hidden = !!att; $('valid').hidden = !att;
    $('send').disabled = enCours || rejeu || envoi;
    $('send').querySelector('.send-l').textContent = enCours || rejeu ? 'L’agent travaille…' : 'Lancer l’agent';
    if (att) $('validAction').textContent = att.action;
    const ecoule = run ? (run.duree != null && !enCours && !att ? run.duree : Math.max(0, maintenant() - run.debut)) : null;
    $('mTemps').textContent = ecoule == null ? '—' : (ecoule / 1000).toFixed(1).replace('.', ',') + ' s';
  }

  function traiter(e) {
    etat = e;
    if (e.run) {
      if (e.run.id !== runId) { runId = e.run.id; reset(); }
      planifier(e.run);
    } else if (runId !== null) {
      // Mission oubliée (retour à l'accueil) : schéma remis à l'état initial
      runId = null; run = null; reset();
    }
    rendreBarre();
  }

  $('send').onclick = async () => {
    if (envoi || (etat && etat.en_cours)) return;
    envoi = true; rendreBarre();
    try { traiter(await appel(CFG.urlLancer, sel)); } catch (err) { /* resynchronisé au prochain tour */ }
    envoi = false; rendreBarre();
  };
  async function decider(ok) {
    if (!run) return;
    $('btnOk').disabled = $('btnKo').disabled = true;
    try { traiter(await appel(CFG.urlDecider, { run: run.id, ok })); } catch (err) { /* idem */ }
    $('btnOk').disabled = $('btnKo').disabled = false;
  }
  $('btnOk').onclick = () => decider(true);
  $('btnKo').onclick = () => decider(false);

  async function sonder() { try { traiter(await appel(CFG.urlEtat)); } catch (err) { /* on réessaie */ } }
  reset(); fit(); sonder();
  setInterval(sonder, 300);
  setInterval(rendreBarre, 200);
})();
