/* =====================================================================
   L'IA consomme combien ? — même prompt envoyé aux 3 Raspberry Pi,
   énergie consommée comparée à ChatGPT pour le même nombre de tokens.
   ===================================================================== */
(function () {
  'use strict';
  const CFG = JSON.parse(document.getElementById('en-config').textContent);
  const K = CFG.calculs;
  const $ = id => document.getElementById(id);
  const PIS = CFG.pis;
  // Couleurs des courbes, comme sur la maquette de la Fête de la science
  const couleurPi = nom => nom.startsWith('Sans refroidissement') ? '#1B2250'
    : nom.startsWith('Refroidissement passif') ? '#E5383B' : '#1B9CD9';

  /* ---------------- formats ---------------- */
  const sig = x => x.toLocaleString('fr-FR', { maximumSignificantDigits: 2 });
  const num = (x, d = 1) => x.toLocaleString('fr-FR', { maximumFractionDigits: d });
  const fmtWh = wh => wh < 1000 ? sig(wh) + ' Wh' : sig(wh / 1000) + ' kWh';
  const co2g = wh => wh / 1000 * K.co2_g_par_kwh;
  const fmtCo2 = g => g < 1 ? sig(g * 1000) + ' mg CO₂' : g < 1000 ? sig(g) + ' g CO₂' : sig(g / 1000) + ' kg CO₂';
  const fmtS = s => s < 60 ? num(s, s < 10 ? 1 : 0) + ' s' : Math.floor(s / 60) + ' min ' + String(Math.round(s % 60)).padStart(2, '0');
  const whPi = secondes => K.puissance_pi_w * secondes / 3600;
  const whGpt = tokens => tokens / 100 * K.gpt_wh_100_tokens;
  const parAn = K.prompts_par_jour * K.jours_par_an;

  document.querySelector('[data-v="puissance"]').textContent = num(K.puissance_pi_w) + ' W';
  document.querySelector('[data-v="gpt"]').textContent = num(K.gpt_wh_100_tokens, 3);
  document.querySelector('[data-v="co2"]').textContent = num(K.co2_g_par_kwh, 0);

  /* ---------------- écran 1 : choix ---------------- */
  const sel = { q: 0, model: Object.keys(CFG.modeles)[0], longueur: 'moyenne' };
  function seg(id, items, cle) {
    $(id).replaceChildren(...items.map(it => {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'opt'; b.dataset.v = it.value;
      b.innerHTML = '<span class="opt-l"></span><small class="opt-s"></small>';
      b.querySelector('.opt-l').textContent = it.label;
      b.querySelector('.opt-s').textContent = it.sub || '';
      b.onclick = () => { sel[cle] = it.value; marquer(); };
      return b;
    }));
  }
  function marquer() {
    for (const [id, cle] of [['questions', 'q'], ['models', 'model'], ['longueurs', 'longueur']])
      for (const b of $(id).children) b.classList.toggle('sel', b.dataset.v === String(sel[cle]));
  }
  seg('questions', CFG.questions.map((x, i) => ({ label: x.titre, sub: x.prompt, value: i })), 'q');
  seg('models', Object.entries(CFG.modeles).map(([n, m]) => ({ label: n, sub: m.desc, value: n })), 'model');
  seg('longueurs', Object.entries(CFG.longueurs).map(([k, l]) => ({ label: l.titre, value: k })), 'longueur');
  marquer();

  /* ---------------- températures en direct ---------------- */
  const chart = new Chart($('chart').getContext('2d'), {
    type: 'line',
    data: { labels: [], datasets: PIS.map(nom => ({
      label: nom, data: [], borderColor: couleurPi(nom), backgroundColor: couleurPi(nom) + '22',
      tension: .25, pointRadius: 0, borderWidth: 3,
    })) },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      plugins: { legend: { position: 'bottom', labels: { font: { size: 15 }, boxWidth: 18 } } },
      scales: {
        y: { title: { display: true, text: '°C', font: { size: 15 } }, ticks: { font: { size: 14 } }, suggestedMin: 35, suggestedMax: 70 },
        x: { ticks: { font: { size: 12 }, maxTicksLimit: 6 } },
      },
    },
  });
  $('pisLive').replaceChildren(...PIS.map(nom => {
    const d = document.createElement('div');
    d.className = 'pi-live'; d.style.setProperty('--pc', couleurPi(nom));
    d.innerHTML = '<span class="pi-live-n"></span><b class="pi-live-t">—</b><small class="pi-live-m"></small>';
    d.querySelector('.pi-live-n').textContent = nom;
    return d;
  }));
  let derniereMesure = {};
  const classeTemp = t => t == null ? '' : t >= 65 ? 'chaud' : t >= 50 ? 'tiede' : 'froid';

  async function lireMesures() {
    try {
      const r = await fetch(CFG.urlMesures, { cache: 'no-store' });
      const m = await r.json();
      derniereMesure = m.pis;
      chart.data.labels.push(m.heure);
      if (chart.data.labels.length > 60) chart.data.labels.shift();
      chart.data.datasets.forEach(ds => {
        const x = m.pis[ds.label];
        ds.data.push(x && x.ok ? x.temperature_c : null);
        if (ds.data.length > 60) ds.data.shift();
      });
      chart.update();
      [...$('pisLive').children].forEach((d, i) => {
        const x = m.pis[PIS[i]] || {};
        const t = x.ok ? x.temperature_c : null;
        const el = d.querySelector('.pi-live-t');
        el.textContent = t == null ? '—' : num(t) + ' °C'; el.className = 'pi-live-t ' + classeTemp(t);
        d.querySelector('.pi-live-m').textContent = x.ok
          ? 'CPU ' + num(x.cpu_load_percent || 0, 0) + ' % · ' + num((x.cpu_freq_mhz || 0) / 1000, 1) + ' GHz · RAM ' + num(x.ram_used_percent || 0, 0) + ' %'
          : 'pas de mesure';
      });
      majTempsCartes();
    } catch (e) { /* on réessaie au prochain tour */ }
  }
  lireMesures();
  setInterval(lireMesures, 2000);

  /* ---------------- écran 2 : réponses ---------------- */
  const cartes = {};
  $('pis').replaceChildren(...PIS.map(nom => {
    const c = document.createElement('article');
    c.className = 'pi'; c.style.setProperty('--pc', couleurPi(nom));
    c.innerHTML = `
      <header class="pi-h"><h3 class="pi-nom"></h3><span class="pi-t">—</span></header>
      <div class="pi-rep"></div>
      <div class="pi-stats">
        <div><span>Durée</span><b data-s="duree">—</b></div>
        <div><span>Tokens</span><b data-s="tokens">—</b></div>
        <div><span>Débit</span><b data-s="debit">—</b></div>
        <div><span>T° max</span><b data-s="tmax">—</b></div>
      </div>
      <div class="pi-energie">
        <div class="barre-l"><span class="barre-n">Raspberry Pi</span><span class="barre-v" data-e="pi">—</span></div>
        <div class="barre"><i class="barre-pi" data-b="pi"></i></div>
        <div class="barre-l"><span class="barre-n">ChatGPT <small>(mêmes tokens)</small></span><span class="barre-v" data-e="gpt">—</span></div>
        <div class="barre"><i class="barre-gpt" data-b="gpt"></i></div>
        <p class="ratio" data-e="ratio"></p>
        <p class="pi-an" data-e="an"></p>
      </div>`;
    c.querySelector('.pi-nom').textContent = nom;
    cartes[nom] = c;
    return c;
  }));

  function majTempsCartes() {
    for (const nom of PIS) {
      const x = derniereMesure[nom] || {};
      const t = x.ok ? x.temperature_c : null;
      const el = cartes[nom].querySelector('.pi-t');
      el.textContent = t == null ? '—' : num(t) + ' °C'; el.className = 'pi-t ' + classeTemp(t);
    }
  }

  let runId = null, etat = null;
  const reps = {};  // texte déjà affiché par Pi (évite de tout redessiner)

  function rendreRun() {
    const run = etat && etat.run;
    if (!run) return;
    const Q = CFG.questions[run.q];
    $('bQuestion').textContent = Q.prompt;
    $('bModel').textContent = run.model + ' · ' + CFG.modeles[run.model].desc;
    $('bLongueur').textContent = 'Réponse ' + CFG.longueurs[run.longueur].titre.toLowerCase();
    $('bStatut').textContent = etat.en_cours ? 'Génération en cours…' : etat.en_mesure ? 'Mesure de la température…' : 'Terminé';
    $('bStatut').className = 'statut' + (etat.en_cours ? ' actif' : '');

    const maintenant = Date.now() / 1000;
    let fini = true;
    for (const nom of PIS) {
      const p = run.pis[nom], c = cartes[nom];
      if (!p.fini) fini = false;
      // Réponse (markdown), redessinée seulement si elle a changé
      if (reps[nom] !== p.texte + p.fini) {
        reps[nom] = p.texte + p.fini;
        const box = c.querySelector('.pi-rep');
        const enBas = box.scrollHeight - box.scrollTop - box.clientHeight < 30;
        box.innerHTML = p.texte ? marked.parse(p.texte) + (p.fini ? '' : '<span class="caret">▋</span>')
                                : '<em class="attente">' + (p.fini ? '(aucune réponse)' : 'Le Pi réfléchit…') + '</em>';
        if (enBas) box.scrollTop = box.scrollHeight;
      }
      // Durée : mesurée à la fin, sinon temps écoulé depuis l'envoi
      const secondes = p.secondes != null ? p.secondes : Math.max(0, maintenant - run.debut);
      const s = (k, v) => { c.querySelector(`[data-s="${k}"]`).textContent = v; };
      s('duree', fmtS(secondes));
      s('tokens', p.tokens ? num(p.tokens, 0) : '—');
      s('debit', p.tokens && secondes > 0 ? num(p.tokens / secondes) + ' tok/s' : '—');
      s('tmax', p.temp_max != null ? num(p.temp_max) + ' °C' : '—');

      // Énergie : Pi (puissance × durée) et ChatGPT (même nombre de tokens)
      const ePi = whPi(secondes), eGpt = whGpt(p.tokens || 0);
      const e = (k, v) => { c.querySelector(`[data-e="${k}"]`).textContent = v; };
      e('pi', fmtWh(ePi) + ' · ' + fmtCo2(co2g(ePi)));
      e('gpt', p.tokens ? fmtWh(eGpt) + ' · ' + fmtCo2(co2g(eGpt)) : '—');
      const max = Math.max(ePi, eGpt) || 1;
      c.querySelector('[data-b="pi"]').style.width = (100 * ePi / max) + '%';
      c.querySelector('[data-b="gpt"]').style.width = (100 * eGpt / max) + '%';
      const ratio = c.querySelector('[data-e="ratio"]');
      if (p.fini && p.tokens && ePi > 0) {
        const r = eGpt / ePi;
        ratio.textContent = r >= 1 ? 'ChatGPT consomme ×' + num(r) + ' plus pour ces tokens'
                                   : 'Le Raspberry Pi consomme ×' + num(1 / r) + ' plus pour ces tokens';
        ratio.className = 'ratio ' + (r >= 1 ? 'gpt' : 'pi');
        e('an', 'Sur un an (' + K.prompts_par_jour + ' prompts/jour) : Pi ' + fmtWh(ePi * parAn) + ' · ChatGPT ' + fmtWh(eGpt * parAn));
      } else {
        ratio.textContent = ''; e('an', '');
      }
      c.classList.toggle('fini', p.fini);
    }
    $('annee').textContent = fini
      ? 'Ordres de grandeur : la puissance du Pi est supposée constante (' + num(K.puissance_pi_w) + ' W) ; l’entraînement des modèles et la fabrication du matériel ne sont pas comptés.'
      : '';
    $('send').disabled = !!etat.en_cours;
    $('send').querySelector('.send-l').textContent = etat.en_cours ? 'Génération en cours…' : 'Envoyer aux 3 Raspberry Pi';
  }

  async function lireEtat() {
    try {
      const r = await fetch(CFG.urlEtat, { cache: 'no-store' });
      traiter(await r.json());
    } catch (e) { /* on réessaie */ }
  }
  function traiter(e) {
    etat = e;
    if (e.run && e.run.id !== runId) {
      runId = e.run.id;
      for (const nom of PIS) { reps[nom] = null; cartes[nom].querySelector('.pi-rep').scrollTop = 0; }
    } else if (!e.run && runId !== null) {
      // Génération oubliée (retour à l'accueil) : retour à l'écran des paramètres
      runId = null; montrer(1);
      $('send').disabled = false;
    }
    rendreRun();
  }

  /* ---------------- navigation ---------------- */
  function montrer(n) {
    $('ecran1').hidden = n !== 1; $('ecran2').hidden = n !== 2;
    document.body.dataset.ecran = n;
    if (n === 1) setTimeout(() => chart.resize(), 0);
  }
  $('send').onclick = async () => {
    if (etat && etat.en_cours) return;
    $('send').disabled = true;
    try {
      const r = await fetch(CFG.urlLancer, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': CFG.csrf },
        body: JSON.stringify(sel),
      });
      traiter(await r.json());
      montrer(2);
    } catch (e) { $('send').disabled = false; }
  };
  $('nouveau').onclick = () => montrer(1);

  setInterval(lireEtat, 500);
  // À l'ouverture : écran 2 si une génération est déjà en cours, sinon écran 1
  lireEtat().then(() => montrer(etat && etat.en_cours ? 2 : 1));
})();
