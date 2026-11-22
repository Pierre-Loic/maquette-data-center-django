/* =====================================================================
   La vie d'un prompt — écran du bas (commande)
   ===================================================================== */
(function () {
  'use strict';
  const { CFG, COL, maintenant, getEtat, post, phasesA, secondes } = window.VP;
  const $ = id => document.getElementById(id);

  const sel = { q: 0, pi: Number(Object.keys(CFG.pis)[0]), model: Object.keys(CFG.modeles)[0] };
  let etat = null, envoiEnCours = false;

  /* ---- boutons de choix ---- */
  function seg(id, items, cle) {
    const c = $(id);
    c.replaceChildren(...items.map(it => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'opt'; b.dataset.v = it.value;
      b.innerHTML = '<span class="opt-l"></span><small class="opt-s"></small>';
      b.querySelector('.opt-l').textContent = it.label;
      b.onclick = () => { sel[cle] = it.value; marquer(); envoyerSelection(); };
      return b;
    }));
  }
  function marquer() {
    for (const [id, cle] of [['questions', 'q'], ['pis', 'pi'], ['models', 'model']])
      for (const b of $(id).children) b.classList.toggle('sel', b.dataset.v === String(sel[cle]));
  }
  seg('questions', CFG.questions.map((p, i) => ({ label: p.q, value: i })), 'q');
  seg('pis', Object.keys(CFG.pis).map(n => ({ label: 'Pi ' + n, value: Number(n) })), 'pi');
  seg('models', Object.keys(CFG.modeles).map(n => ({ label: n, value: n })), 'model');
  for (const b of $('models').children) b.querySelector('.opt-s').textContent = CFG.modeles[b.dataset.v].desc;
  marquer();

  /* Sous chaque Pi : le modèle actuellement chargé dans sa RAM */
  function majCharges() {
    if (!etat) return;
    for (const b of $('pis').children) {
      const m = etat.charges[b.dataset.v];
      b.querySelector('.opt-s').textContent = m ? m + ' en mémoire' : 'mémoire vide';
    }
  }

  /* Sur la page combinée, le schéma est prévenu tout de suite (sans attendre son rafraîchissement) */
  const diffuser = e => window.dispatchEvent(new CustomEvent('vp:etat', { detail: e }));
  function envoyerSelection() { post(CFG.urlSelection, sel).then(r => { if (r.ok) diffuser(r.etat); }).catch(() => {}); }
  const avecSuivi = !!$('suivi');

  /* ---- étapes (écran de commande seul) ---- */
  if (avecSuivi) $('steps').replaceChildren(...CFG.phases.map((n, i) => {
    const li = document.createElement('li');
    li.className = 'step'; li.style.setProperty('--sc', COL[i]);
    li.innerHTML = '<i>' + (i + 1) + '</i><span></span>';
    li.querySelector('span').textContent = n;
    return li;
  }));

  /* ---- envoi ---- */
  $('send').onclick = async () => {
    if (envoiEnCours || (etat && etat.en_cours)) return;
    envoiEnCours = true; $('send').disabled = true;
    try {
      const r = await post(CFG.urlLancer, sel);
      etat = r.etat; diffuser(etat);
    } catch (e) { /* le rafraîchissement suivant resynchronisera */ }
    envoiEnCours = false;
    rendre();
  };

  function rendre() {
    const run = etat && etat.run;
    const enCours = !!(etat && etat.en_cours);
    document.body.classList.toggle('vp-en-cours', enCours);
    $('send').disabled = enCours || envoiEnCours;
    majCharges();
    if (!avecSuivi) {
      // Page combinée : le schéma au-dessus montre l'avancement
      document.querySelector('#send .send-l').textContent = enCours ? 'En cours…' : 'Envoyer';
      return;
    }
    // Le suivi reste affiché pendant la génération et 20 s après
    const ecoule = run ? maintenant() - run.debut : Infinity;
    const visible = run && (run.duree === null || ecoule < run.duree + 20000);
    $('suivi').hidden = !visible;
    $('send').hidden = !!enCours;
    if (!visible) return;
    const st = phasesA(run.evenements, ecoule);
    [...$('steps').children].forEach((li, i) => { li.className = 'step ' + st[i]; });
    if (enCours) {
      $('suivi-titre').textContent = 'Regardez l’écran du haut';
      $('suivi-temps').textContent = secondes(ecoule);
    } else {
      const err = run.evenements.find(e => e.type === 'error');
      $('suivi-titre').textContent = err ? err.message : 'Réponse affichée en haut';
      $('suivi-temps').textContent = err ? '' : 'en ' + secondes(run.duree);
    }
  }

  async function boucle() {
    try { etat = await getEtat(); } catch (e) { /* serveur indisponible : on réessaie */ }
    rendre();
  }
  boucle();
  setInterval(boucle, 500);
  envoyerSelection();
})();
