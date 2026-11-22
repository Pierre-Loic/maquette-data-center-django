/* =====================================================================
   La vie d'un prompt — fonctions communes aux deux écrans
   ===================================================================== */
window.VP = (function () {
  'use strict';
  const CFG = JSON.parse(document.getElementById('vp-config').textContent);
  // Couleur de chaque phase : Envoi, Arrivée, Chargement, Calcul, Affichage
  const COL = ['#1B9CD9', '#7C5CD6', '#EE8A0B', '#E5383B', '#2FAA4A'];

  /* Décalage entre l'horloge du serveur et celle du navigateur,
     pour que les deux écrans affichent la même chose au même moment. */
  let decalage = 0;
  const maintenant = () => Date.now() + decalage;

  async function getEtat() {
    const r = await fetch(CFG.urlEtat, { cache: 'no-store' });
    if (!r.ok) throw new Error('HTTP ' + r.status);
    const e = await r.json();
    decalage = e.serveur - Date.now();
    return e;
  }

  async function post(url, data) {
    const r = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrf },
      body: JSON.stringify(data),
    });
    const e = await r.json();
    if (e.serveur) decalage = e.serveur - Date.now();
    return { ok: r.ok, status: r.status, etat: e };
  }

  /* État des 5 phases ('idle' | 'active' | 'done' | 'skip') après les
     événements dont l'heure t est passée. */
  function phasesA(evenements, ecoule) {
    const st = ['idle', 'idle', 'idle', 'idle', 'idle'];
    let tokens = 0;
    for (const e of evenements) {
      if (e.t > ecoule) break;
      switch (e.type) {
        case 'sent': st[0] = 'active'; break;
        case 'received': st[0] = 'done'; st[1] = 'active'; break;
        case 'load_start': st[1] = 'done'; st[2] = 'active'; break;
        case 'loaded': st[2] = 'done'; break;
        case 'load_skipped': st[1] = 'done'; st[2] = 'skip'; break;
        case 'generation_start': st[3] = 'active'; break;
        case 'token': if (!tokens++) st[4] = 'active'; break;
        case 'generation_end': st[3] = 'done'; break;
        case 'done': st[4] = 'done'; break;
        case 'error': for (let i = 0; i < 5; i++) if (st[i] === 'active') st[i] = 'idle'; break;
      }
    }
    return st;
  }

  const secondes = ms => (ms / 1000).toFixed(1).replace('.', ',') + ' s';

  return { CFG, COL, maintenant, getEtat, post, phasesA, secondes };
})();
