// ── State ──────────────────────────────────────────────────────────────────
const state = { files: {}, results: null, activeTab: 0 };
const API = '';   // same origin

// ── DOM helpers ────────────────────────────────────────────────────────────
const $ = (s, p = document) => p.querySelector(s);
const $$ = (s, p = document) => [...p.querySelectorAll(s)];

// ── Drop zones ─────────────────────────────────────────────────────────────
$$('.dz').forEach(dz => {
  const key = dz.dataset.key;
  const inp = dz.querySelector('input[type=file]');

  dz.addEventListener('dragover', e => { e.preventDefault(); dz.classList.add('dragover'); });
  dz.addEventListener('dragleave', () => dz.classList.remove('dragover'));
  dz.addEventListener('drop', e => {
    e.preventDefault(); dz.classList.remove('dragover');
    const f = e.dataTransfer.files[0];
    if (f) setFile(key, f);
  });
  dz.addEventListener('click', e => { if (!e.target.classList.contains('lbl')) inp.click(); });

  if (inp) inp.addEventListener('change', () => { if (inp.files[0]) setFile(key, inp.files[0]); });
});

function setFile(key, file) {
  state.files[key] = file;
  const ch = $(`#ch-${key}`);
  const dz = $(`#dz-${key}`);
  if (ch) {
    ch.classList.remove('hidden');
    ch.querySelector('.fname').textContent = file.name;
  }
  if (dz) dz.querySelector('.dz > svg, .dz > p, .hint') && null;
  const card = $(`#dz-${key}`)?.closest('.card');
  if (card) card.classList.add('has-file');
}

function clearFile(key) {
  delete state.files[key];
  const ch = $(`#ch-${key}`);
  const inp = $(`#f-${key}`);
  if (ch) ch.classList.add('hidden');
  if (inp) inp.value = '';
  const card = $(`#dz-${key}`)?.closest('.card');
  if (card) card.classList.remove('has-file');
}

$$('.clr').forEach(btn => btn.addEventListener('click', () => clearFile(btn.dataset.k)));

// ── Pipeline animation ─────────────────────────────────────────────────────
const pipelineSteps = $$('.ps');
let pipeAnim = null;
function animatePipeline() {
  let i = 0;
  pipelineSteps.forEach(p => p.classList.remove('active','done','running'));
  pipeAnim = setInterval(() => {
    if (i > 0) { pipelineSteps[i-1].classList.remove('running'); pipelineSteps[i-1].classList.add('done'); }
    if (i < pipelineSteps.length) { pipelineSteps[i].classList.add('running'); i++; }
    else { clearInterval(pipeAnim); }
  }, 300);
}
function resetPipeline() {
  if (pipeAnim) clearInterval(pipeAnim);
  pipelineSteps.forEach((p,i) => { p.classList.remove('running','done'); if(i===pipelineSteps.length-1) p.classList.add('active'); });
}

// ── Processing steps animation ─────────────────────────────────────────────
const procStepIds = ['ps-parse','ps-map','ps-extract','ps-canon','ps-norm','ps-validate','ps-match','ps-trust','ps-resolve','ps-golden'];
let procAnim = null;
function startProcAnim() {
  let i = 0;
  procStepIds.forEach(id => { const el=$(`#${id}`); if(el){el.classList.remove('done','running');} });
  procAnim = setInterval(() => {
    if (i > 0) { const prev = $(`#${procStepIds[i-1]}`); if(prev){prev.classList.remove('running');prev.classList.add('done');} }
    if (i < procStepIds.length) { const cur = $(`#${procStepIds[i]}`); if(cur){cur.classList.add('running');} i++; }
    else clearInterval(procAnim);
  }, 350);
}
function stopProcAnim() { if(procAnim) clearInterval(procAnim); }

// ── Show/hide sections ─────────────────────────────────────────────────────
function showSection(id) { $(`#${id}`).classList.remove('hidden'); }
function hideSection(id) { $(`#${id}`).classList.add('hidden'); }

// ── Sample data loader ─────────────────────────────────────────────────────
$('#sampleBtn').addEventListener('click', async () => {
  try {
    const r = await fetch(`${API}/api/sample`);
    const samples = await r.json();
    // Load files as Blob objects
    for (const [fname, content] of Object.entries(samples)) {
      let key = null;
      if (fname.endsWith('.csv')) key = 'csv';
      else if (fname === 'ats.json') key = 'ats_json';
      else if (fname === 'resume.txt') key = 'resume';
      else if (fname === 'notes.txt') key = 'notes';
      if (key) {
        const blob = new Blob([content], { type: 'text/plain' });
        const file = new File([blob], fname, { type: blob.type });
        setFile(key, file);
      }
    }
    showToast('Sample data loaded! Click Run Pipeline to process.', 'success');
  } catch (e) {
    showToast('Could not load sample data. Is the API running?', 'error');
  }
});

// ── Form submit ────────────────────────────────────────────────────────────
$('#form').addEventListener('submit', async e => {
  e.preventDefault();
  hideSection('errSection');
  hideSection('results');

  const fd = new FormData();
  let count = 0;
  for (const [key, file] of Object.entries(state.files)) {
    if (file) { fd.append(key, file); count++; }
  }
  const gh = $('#f-github').value.trim();
  if (gh) { fd.append('github', gh); count++; }

  if (count === 0) { showToast('Please provide at least one data source.', 'error'); return; }

  // UI: loading state
  $('#btnTxt').classList.add('hidden');
  $('#btnLoad').classList.remove('hidden');
  $('#runBtn').disabled = true;
  showSection('procSection');
  animatePipeline();
  startProcAnim();

  try {
    const res = await fetch(`${API}/api/transform`, { method: 'POST', body: fd });
    const data = await res.json();

    stopProcAnim();
    // mark all done
    procStepIds.forEach(id => { const el=$(`#${id}`); if(el){el.classList.remove('running');el.classList.add('done');} });
    pipelineSteps.forEach(p => { p.classList.remove('running'); p.classList.add('done'); });

    await sleep(400);
    hideSection('procSection');

    if (!data.success) {
      $('#errMsg').textContent = data.error || 'Unknown error';
      if (data.trace) { $('#errTrace').textContent = data.trace; $('#errDetails').removeAttribute('open'); }
      else { $('#errDetails').style.display = 'none'; }
      showSection('errSection');
    } else {
      state.results = data;
      renderResults(data);
      showSection('results');
      setTimeout(() => $('#results').scrollIntoView({ behavior: 'smooth' }), 100);
    }
  } catch(err) {
    stopProcAnim();
    hideSection('procSection');
    $('#errMsg').textContent = err.message;
    showSection('errSection');
  } finally {
    $('#btnTxt').classList.remove('hidden');
    $('#btnLoad').classList.add('hidden');
    $('#runBtn').disabled = false;
  }
});

$('#errDismiss').addEventListener('click', () => hideSection('errSection'));

// ── Render results ─────────────────────────────────────────────────────────
function renderResults(data) {
  const { candidates, count } = data;
  $('#resMeta').textContent = `${count} candidate${count!==1?'s':''} processed · ${new Date().toLocaleTimeString()}`;

  // Tabs
  const tabsEl = $('#tabs');
  const cviewEl = $('#cview');
  tabsEl.innerHTML = '';
  cviewEl.innerHTML = '';

  candidates.forEach((c, i) => {
    const tab = document.createElement('button');
    tab.className = 'tab' + (i === 0 ? ' active' : '');
    tab.textContent = c.full_name || `Candidate ${i+1}`;
    tab.dataset.i = i;
    tab.addEventListener('click', () => {
      $$('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      state.activeTab = i;
      renderCandidate(c, cviewEl);
    });
    tabsEl.appendChild(tab);
  });

  if (candidates.length > 0) renderCandidate(candidates[0], cviewEl);
}

function renderCandidate(c, container) {
  const conf = c.overall_confidence || 0;
  const confPct = Math.round(conf * 100);
  const initials = (c.full_name || '?').split(' ').map(w=>w[0]).join('').slice(0,2).toUpperCase();

  const exp0 = c.experience && c.experience[0];
  const title = exp0 ? `${exp0.title || ''}${exp0.company ? ' @ ' + exp0.company : ''}` : '';

  const links = c.links || {};
  const linksHtml = buildLinks(links, c.emails, c.phones);

  const skillsHtml = buildSkills(c.skills || []);
  const expHtml = buildExperience(c.experience || []);
  const eduHtml = buildEducation(c.education || []);
  const infoHtml = buildInfo(c);
  const provHtml = buildProvenance(c.provenance || []);

  const conflictDashboardHtml = buildConflictDashboard(c.provenance || []);
  const rawCompareHtml = buildRawCompare(c);

  container.innerHTML = `
<div class="cand-card">
  <div class="cand-header">
    <div style="display:flex;align-items:center;gap:16px">
      <div class="cand-avatar">${initials}</div>
      <div class="cand-identity">
        <div class="cand-name">${esc(c.full_name || 'Unknown')}</div>
        ${title ? `<div class="cand-title">${esc(title)}</div>` : ''}
        <div class="cand-id">ID: ${c.candidate_id || '—'}</div>
      </div>
    </div>
    <div class="conf-badge">
      <div class="conf-label">Overall Confidence</div>
      ${confRing(conf, confPct)}
    </div>
  </div>

  <!-- Subtabs Navigation -->
  <div class="subtabs-nav">
    <button class="subtab-btn active" data-target="sub-profile-${c.candidate_id}">👤 Golden Profile</button>
    <button class="subtab-btn" data-target="sub-conflicts-${c.candidate_id}">⚡ Conflict Dashboard</button>
    <button class="subtab-btn" data-target="sub-compare-${c.candidate_id}">⚖️ Raw vs Golden</button>
  </div>

  <!-- Tab 1: Profile View -->
  <div id="sub-profile-${c.candidate_id}" class="subtab-content">
    ${infoHtml}
    <hr class="section-divider"/>

    ${linksHtml}

    ${c.skills && c.skills.length ? `
      <div style="margin-bottom:8px"><span style="font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:600">Skills</span></div>
      <div class="skills-wrap">${skillsHtml}</div>
      <hr class="section-divider"/>
    ` : ''}

    ${c.experience && c.experience.length ? `
      <div style="margin-bottom:12px"><span style="font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:600">Experience</span></div>
      <div class="exp-list">${expHtml}</div>
      <hr class="section-divider"/>
    ` : ''}

    ${c.education && c.education.length ? `
      <div style="margin-bottom:12px"><span style="font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:600">Education</span></div>
      <div class="exp-list">${eduHtml}</div>
      <hr class="section-divider"/>
    ` : ''}

    <div class="prov-section">
      <button class="prov-toggle" id="provToggle">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        Show Provenance Trail (${(c.provenance||[]).length} entries)
      </button>
      <div id="provTable" class="hidden">
        <div class="prov-table-wrap">${provHtml}</div>
      </div>
    </div>
  </div>

  <!-- Tab 2: Conflict Resolution Dashboard -->
  <div id="sub-conflicts-${c.candidate_id}" class="subtab-content hidden">
    ${conflictDashboardHtml}
  </div>

  <!-- Tab 3: Raw vs Golden Comparison -->
  <div id="sub-compare-${c.candidate_id}" class="subtab-content hidden">
    ${rawCompareHtml}
  </div>
</div>`;

  // Attach Subtab click events
  const tabs = $$('.subtab-btn', container);
  const contents = $$('.subtab-content', container);
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      tabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const target = tab.dataset.target;
      contents.forEach(content => {
        if (content.id === target) {
          content.classList.remove('hidden');
        } else {
          content.classList.add('hidden');
        }
      });
    });
  });

  $('#provToggle').addEventListener('click', () => {
    const t = $('#provTable');
    const open = !t.classList.contains('hidden');
    t.classList.toggle('hidden');
    $('#provToggle').querySelector('svg').style.transform = open ? '' : 'rotate(180deg)';
  });
}

function confRing(conf, pct) {
  const r = 30, cx = 36, cy = 36, circ = 2 * Math.PI * r;
  const fill = circ * conf;
  const color = conf >= 0.8 ? '#22c55e' : conf >= 0.6 ? '#f59e0b' : '#ef4444';
  return `<div class="conf-ring">
    <svg width="72" height="72" viewBox="0 0 72 72">
      <circle cx="${cx}" cy="${cy}" r="${r}" stroke="var(--border)" stroke-width="5" fill="none"/>
      <circle cx="${cx}" cy="${cy}" r="${r}" stroke="${color}" stroke-width="5" fill="none"
        stroke-dasharray="${fill} ${circ - fill}" stroke-linecap="round"/>
    </svg>
    <div class="conf-ring-txt">
      <span class="conf-val">${pct}</span>
      <span class="conf-pct">%</span>
    </div>
  </div>`;
}

function buildInfo(c) {
  const emails = (c.emails || []).join(', ') || '—';
  const phones = (c.phones || []).join(', ') || '—';
  const loc = c.location ? [c.location.city, c.location.region, c.location.country].filter(Boolean).join(', ') || '—' : '—';
  const yoe = c.years_experience != null ? `${c.years_experience} years` : '—';
  const headline = c.headline || '—';

  return `<div class="info-grid">
    <div class="info-block">
      <div class="info-lbl"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"/><polyline points="22,6 12,13 2,6"/></svg> Email</div>
      <div class="info-val mono">${esc(emails)}</div>
    </div>
    <div class="info-block">
      <div class="info-lbl"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 16.92v3a2 2 0 01-2.18 2 19.79 19.79 0 01-8.63-3.07A19.5 19.5 0 014.27 9.81 19.79 19.79 0 011.21 1.18 2 2 0 013.22 1h3a2 2 0 012 1.72c.127.96.361 1.903.7 2.81a2 2 0 01-.45 2.11L7.09 8.43a16 16 0 006.29 6.29l1.59-1.59a2 2 0 012.11-.45c.907.339 1.85.573 2.81.7A2 2 0 0122 16.92z"/></svg> Phone</div>
      <div class="info-val mono">${esc(phones)}</div>
    </div>
    <div class="info-block">
      <div class="info-lbl"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="10" r="3"/><path d="M12 21.7C17.3 17 20 13 20 10a8 8 0 10-16 0c0 3 2.7 6.9 8 11.7z"/></svg> Location</div>
      <div class="info-val">${esc(loc)}</div>
    </div>
    <div class="info-block">
      <div class="info-lbl"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"/><path d="M16 21V5a2 2 0 00-2-2h-4a2 2 0 00-2 2v16"/></svg> Experience</div>
      <div class="info-val">${esc(yoe)}</div>
    </div>
    <div class="info-block" style="grid-column:span 2">
      <div class="info-lbl"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg> Headline</div>
      <div class="info-val">${esc(headline)}</div>
    </div>
  </div>`;
}

function buildLinks(links, emails, phones) {
  const items = [];
  if (links.linkedin) items.push({ href: links.linkedin, icon: '🔗', label: 'LinkedIn' });
  if (links.github) items.push({ href: links.github.startsWith('http') ? links.github : `https://github.com/${links.github}`, icon: '⌥', label: 'GitHub' });
  if (links.portfolio) items.push({ href: links.portfolio, icon: '🌐', label: 'Portfolio' });
  (links.other || []).forEach((u,i) => items.push({ href: u, icon: '🔗', label: `Link ${i+1}` }));
  (emails || []).forEach(em => items.push({ href: `mailto:${em}`, icon: '✉', label: em }));

  if (!items.length) return '';
  return `<div style="margin-bottom:8px"><span style="font-size:.8rem;color:var(--text3);text-transform:uppercase;letter-spacing:.05em;font-weight:600">Links & Contact</span></div>
<div class="links-wrap">
  ${items.map(it => `<a href="${esc(it.href)}" target="_blank" rel="noopener" class="link-chip">${it.icon} ${esc(it.label)}</a>`).join('')}
</div><hr class="section-divider"/>`;
}

function buildSkills(skills) {
  return skills.map(s => {
    const conf = s.confidence || 0;
    const cls = conf >= 0.7 ? 'high' : conf >= 0.5 ? 'mid' : 'low';
    const pct = Math.round(conf * 100);
    return `<div class="skill-chip">
      <span class="skill-name">${esc(s.name)}</span>
      <span class="skill-conf ${cls}">${pct}%</span>
      <span class="skill-src">${(s.sources||[]).join(', ')}</span>
    </div>`;
  }).join('');
}

function buildExperience(exp) {
  return exp.map(e => `
    <div class="exp-item">
      <div class="exp-dot"></div>
      <div>
        <div class="exp-company">${esc(e.company || '—')}</div>
        <div class="exp-title">${esc(e.title || '—')}${e.start ? ' · ' + e.start : ''}${e.end ? ' – ' + e.end : ''}</div>
        ${e.summary ? `<div style="font-size:.78rem;color:var(--text3);margin-top:4px">${esc(e.summary)}</div>` : ''}
      </div>
    </div>`).join('');
}

function buildEducation(edu) {
  if (!edu || !edu.length) return '';
  return edu.map(e => `
    <div class="exp-item">
      <div class="exp-dot" style="background:#06b6d4"></div>
      <div>
        <div class="exp-company">${esc(e.institution || '—')}</div>
        <div class="exp-title">${esc(e.degree || '—')}${e.field ? ' in ' + e.field : ''}${e.end_year ? ' · Class of ' + e.end_year : ''}</div>
        ${e.cgpa ? `<div style="font-size:.78rem;color:var(--text3);margin-top:4px">CGPA/GPA: ${esc(e.cgpa)}</div>` : ''}
      </div>
    </div>`).join('');
}

function buildConflictDashboard(provenance) {
  const byField = {};
  const scalarFields = ["full_name", "current_company", "title", "years_experience", "headline"];
  provenance.forEach(p => {
    if (!scalarFields.includes(p.field)) return;
    if (!p.competing_values || !p.competing_values.length) return;
    byField[p.field] = p;
  });

  const fields = Object.keys(byField);
  if (!fields.length) {
    return `<p style="color:var(--text3);font-size:.85rem;padding:20px;text-align:center">No conflicts detected. All sources provided agreeing values for candidate fields.</p>`;
  }

  const cardsHtml = fields.map(field => {
    const p = byField[field];
    const compValHtml = p.competing_values.map(cv => {
      const cls = cv.selected ? 'high' : 'low';
      const statusBadge = cv.selected ? '<span class="status-pill selected">✓ Won</span>' : '<span class="status-pill rejected">✕ Rejected</span>';
      
      const r = cv.reliability || 0;
      const cp = cv.conflict_penalty || 0;
      const ab = cv.agreement_boost || 0;
      const mathStr = `${r.toFixed(2)} (reliability) × (1 - ${cp.toFixed(2)}) (conflict) × ${ab.toFixed(2)} (agreement)`;

      return `
      <div class="competing-value-row ${cv.selected ? 'is-winner' : ''}">
        <div class="cv-left">
          <div class="cv-val mono">${esc(cv.value)}</div>
          <div class="cv-src">Source: <strong>${esc((cv.sources || []).join(', '))}</strong></div>
        </div>
        <div class="cv-right">
          <div class="cv-math-tooltip" title="${esc(mathStr)}">
            <span class="prov-trust ${cls}">${Math.round(cv.trust * 100)}%</span>
            <span class="tooltip-info-icon">ℹ️</span>
          </div>
          ${statusBadge}
        </div>
      </div>`;
    }).join('');

    const formulaExplanation = p.reasons.find(r => r.startsWith("Trust =")) || "";

    return `
    <div class="conflict-field-card" style="margin-bottom:16px">
      <div class="conflict-field-hdr">
        <h4>${esc(field.replace('_', ' ').toUpperCase())}</h4>
        <span class="info-pill">${p.competing_values.length} variant${p.competing_values.length > 1 ? 's' : ''} found</span>
      </div>
      <div class="competing-values-list">
        ${compValHtml}
      </div>
      <div class="resolution-explanation">
        <strong>Resolution Rule:</strong> Selected winner using <code>${esc(p.reasons.find(r => r.includes("Resolution strategy"))?.split(":")[1]?.trim() || "best")}</code> resolution strategy.<br/>
        ${formulaExplanation ? `<small style="color:var(--text3)">Formula calculation: <code>${esc(formulaExplanation.replace("Trust = ", ""))}</code></small>` : ''}
      </div>
    </div>`;
  }).join('');

  return `<div class="conflict-dashboard-grid">${cardsHtml}</div>`;
}

function buildRawCompare(c) {
  const sourceClaims = {};
  const fields = ["full_name", "email", "phone", "current_company", "title", "years_experience"];
  
  c.provenance.forEach(p => {
    if (!fields.includes(p.field)) return;
    
    if (p.competing_values && p.competing_values.length) {
      p.competing_values.forEach(cv => {
        (cv.sources || []).forEach(src => {
          if (!sourceClaims[src]) sourceClaims[src] = {};
          sourceClaims[src][p.field] = cv.value;
        });
      });
    } else {
      const src = p.source;
      if (src) {
        if (!sourceClaims[src]) sourceClaims[src] = {};
        sourceClaims[src][p.field] = p.value;
      }
    }
  });

  const sources = Object.keys(sourceClaims);
  if (!sources.length) {
    return `<p style="color:var(--text3);font-size:.85rem;padding:20px;text-align:center">No raw comparisons available.</p>`;
  }

  const headers = ['Field', ...sources.map(s => s.toUpperCase()), 'Resolved Golden'];
  const rows = fields.map(field => {
    const fieldLabel = field.replace('_', ' ').toUpperCase();
    
    let resolvedVal = '—';
    if (field === 'full_name') resolvedVal = c.full_name || '—';
    else if (field === 'email') resolvedVal = (c.emails || []).join(', ') || '—';
    else if (field === 'phone') resolvedVal = (c.phones || []).join(', ') || '—';
    else if (field === 'current_company') resolvedVal = c.experience?.[0]?.company || '—';
    else if (field === 'title') resolvedVal = c.experience?.[0]?.title || '—';
    else if (field === 'years_experience') resolvedVal = c.years_experience != null ? c.years_experience : '—';
    
    const sourceCols = sources.map(src => {
      const val = sourceClaims[src][field] || '—';
      return `<td class="mono" style="font-size:.78rem">${esc(val)}</td>`;
    }).join('');

    return `
    <tr>
      <td style="font-weight:600;color:var(--text2)">${esc(fieldLabel)}</td>
      ${sourceCols}
      <td style="font-weight:700;color:#c4b5fd" class="mono">${esc(resolvedVal)}</td>
    </tr>`;
  });

  return `
  <div class="raw-compare-wrap">
    <div style="margin-bottom:12px"><p style="font-size:.82rem;color:var(--text3)">Side-by-side comparison of field values extracted from each source vs. the resolved Golden Record.</p></div>
    <div class="prov-table-wrap">
      <table class="prov-table compare-table">
        <thead>
          <tr>
            ${headers.map(h => `<th>${esc(h)}</th>`).join('')}
          </tr>
        </thead>
        <tbody>
          ${rows.join('')}
        </tbody>
      </table>
    </div>
  </div>`;
}

function buildProvenance(prov) {
  if (!prov.length) return '<p style="color:var(--text3);font-size:.85rem">No provenance data.</p>';
  const rows = prov.map(p => {
    const t = p.trust || 0;
    const cls = t >= 0.7 ? 'high' : t >= 0.5 ? 'mid' : 'low';
    const reasons = (p.reasons || []).map(r => `<div class="prov-reason">• ${esc(r)}</div>`).join('');
    const trace = p.normalization_trace ? `<div class="trace-badge">${esc(p.normalization_trace)}</div>` : '—';
    return `<tr>
      <td><span class="info-pill">${esc(p.field)}</span></td>
      <td style="max-width:180px;word-break:break-all">${esc(String(p.value ?? '—'))}</td>
      <td style="color:var(--text3);font-size:.72rem">${esc(p.source||'')}</td>
      <td><span class="prov-trust ${cls}">${Math.round(t*100)}%</span></td>
      <td>${trace}</td>
      <td><div class="prov-reasons">${reasons}</div></td>
    </tr>`;
  }).join('');
  return `<table class="prov-table">
    <thead><tr><th>Field</th><th>Value</th><th>Source(s)</th><th>Trust</th><th>Normalization Trace</th><th>Reasons</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// ── Download / Raw JSON ────────────────────────────────────────────────────
$('#dlBtn').addEventListener('click', () => {
  if (!state.results) return;
  const blob = new Blob([JSON.stringify(state.results.candidates, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = `trustprofile_output_${Date.now()}.json`;
  a.click();
});

$('#rawBtn').addEventListener('click', () => {
  if (!state.results) return;
  $('#mjson').textContent = JSON.stringify(state.results.candidates, null, 2);
  $('#modal').classList.remove('hidden');
});
$('#mclose').addEventListener('click', () => $('#modal').classList.add('hidden'));
$('#mback').addEventListener('click', () => $('#modal').classList.add('hidden'));
$('#copyBtn').addEventListener('click', () => {
  navigator.clipboard.writeText($('#mjson').textContent).then(() => showToast('Copied!', 'success'));
});

// ── Toast ──────────────────────────────────────────────────────────────────
function showToast(msg, type = 'info') {
  let t = $('#toast');
  if (!t) {
    t = document.createElement('div');
    t.id = 'toast';
    t.style.cssText = 'position:fixed;bottom:28px;left:50%;transform:translateX(-50%) translateY(20px);background:var(--bg2);border:1px solid var(--border2);color:var(--text);padding:12px 24px;border-radius:10px;font-size:.88rem;z-index:1000;opacity:0;transition:all .3s;backdrop-filter:blur(12px);box-shadow:0 8px 32px rgba(0,0,0,.5);max-width:400px;text-align:center';
    document.body.appendChild(t);
  }
  t.textContent = msg;
  t.style.borderColor = type === 'success' ? 'rgba(34,197,94,.4)' : type === 'error' ? 'rgba(239,68,68,.4)' : 'var(--border2)';
  t.style.opacity = '1';
  t.style.transform = 'translateX(-50%) translateY(0)';
  clearTimeout(t._timer);
  t._timer = setTimeout(() => { t.style.opacity='0'; t.style.transform='translateX(-50%) translateY(20px)'; }, 3200);
}

// ── Utilities ──────────────────────────────────────────────────────────────
function esc(s) {
  return String(s ?? '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}
function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

// ── Init ───────────────────────────────────────────────────────────────────
resetPipeline();
console.log('%cTrustProfile loaded 🚀', 'color:#7c3aed;font-weight:700;font-size:1.1rem');
