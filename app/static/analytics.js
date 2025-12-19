/*
  Analytics dashboard (no build step).
  - Uses Chart.js from CDN
  - Pulls from /api/analytics/* endpoints
  - Adds drilldown drawer + chart maximize overlay
*/

const $ = (id) => document.getElementById(id);
let analyticsState = { overview: null, timeseries: null, migrations: [], duplicates: [] };
let chartData = { decades: null, surnames: null, places: null, children: null, migration: null, duplicates: null };
let charts = { decades: null, surnames: null, places: null, children: null };

const drilldownCache = new Map();
const drilldownState = { payload: null, page: 1, pageSize: 20, total: 0, items: [] };
const overlayState = { chartKey: null, scrollY: 0 };

async function api(url, opts){
  const res = await fetch(url, opts);
  const txt = await res.text();
  let body = null;
  try { body = txt ? JSON.parse(txt) : null; } catch { body = txt; }
  if(!res.ok){
    const msg = (body && body.error) ? body.error : `HTTP ${res.status}`;
    throw new Error(msg);
  }
  return body;
}

function fmtNum(n){
  try { return (n ?? 0).toLocaleString(); } catch { return String(n ?? 0); }
}

function kpiCard(title, value, sub){
  const div = document.createElement('div');
  div.className = 'kpiCard';
  div.innerHTML = `
    <div class="kpiTitle">${title}</div>
    <div class="kpiValue">${value}</div>
    <div class="kpiSub">${sub || ''}</div>
  `;
  return div;
}

function copyToClipboard(text){
  if(!navigator?.clipboard){ return Promise.reject(new Error('Clipboard unavailable')); }
  return navigator.clipboard.writeText(text);
}

function destroyChart(key){
  if(charts[key]){
    charts[key].destroy();
    charts[key] = null;
  }
}

function buildBarChart(canvasId, labels, datasets, chartKey){
  const ctx = $(canvasId).getContext('2d');
  return new Chart(ctx, {
    type: 'bar',
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#cbd5e1' } },
        tooltip: { enabled: true },
      },
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.15)' } },
        y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.15)' } },
      },
      onClick: (evt, elements) => {
        if(!elements || elements.length === 0) return;
        const el = elements[0];
        const label = labels[el.index];
        const datasetLabel = datasets[el.datasetIndex]?.label;
        const payload = buildDrilldownPayload(chartKey, { label, datasetLabel, index: el.index });
        if(payload){ openDrilldown(payload); }
      }
    }
  });
}

function renderTable(hostId, columns, rows, opts = {}){
  const host = $(hostId);
  if(!rows || rows.length === 0){
    host.innerHTML = `<div class="muted" style="padding:8px;">No data.</div>`;
    return;
  }

  const thead = `<tr>${columns.map(c => `<th>${c.title}</th>`).join('')}</tr>`;
  const tbody = rows.map((r, idx) => {
    const clickable = typeof opts.onRowClick === 'function';
    return `<tr ${clickable ? `role="button" tabindex="0" data-row-index="${idx}"` : ''}>${columns.map(c => `<td>${c.render(r)}</td>`).join('')}</tr>`;
  }).join('');

  host.innerHTML = `
    <table>
      <thead>${thead}</thead>
      <tbody>${tbody}</tbody>
    </table>
  `;

  if(typeof opts.onRowClick === 'function'){
    host.querySelectorAll('tbody tr').forEach((rowEl) => {
      const idx = parseInt(rowEl.getAttribute('data-row-index'), 10);
      rowEl.addEventListener('click', () => opts.onRowClick(rows[idx]));
      rowEl.addEventListener('keydown', (e) => {
        if(e.key === 'Enter' || e.key === ' '){
          e.preventDefault();
          opts.onRowClick(rows[idx]);
        }
      });
      rowEl.classList.add('tableRowInteractive');
    });
  }
}

function personSummary(p){
  const name = [p.given, p.surname].filter(Boolean).join(' ').trim() || '(unnamed)';
  const birthYear = p.birth_year || (p.birth_date || '').slice(0,4);
  const deathYear = p.death_year || (p.death_date || '').slice(0,4);
  const years = (birthYear || deathYear) ? `${birthYear || '?'} – ${deathYear || '?'}` : 'Years unknown';
  const places = [p.birth_place, p.death_place].filter(Boolean).join(' • ');
  return { name, years, places };
}

function renderDrilldown(items, total){
  const host = $('drilldownContent');
  if(!items || items.length === 0){
    host.innerHTML = `<div class="muted">No people found for this selection.</div>`;
    $('drilldownPage').innerText = '';
    $('drilldownPrev').disabled = true;
    $('drilldownNext').disabled = true;
    return;
  }
  host.innerHTML = '';
  items.forEach((p) => {
    const { name, years, places } = personSummary(p);
    const div = document.createElement('div');
    div.className = 'drillItem';
    div.innerHTML = `
      <div class="drillPrimary">${name}</div>
      <div class="drillMeta">${years}</div>
      <div class="drillMeta">${places || ''}</div>
      <div class="drillActions">
        <a class="btn btnSecondary" href="/?personId=${encodeURIComponent(p.id)}">Open person</a>
      </div>
    `;
    host.appendChild(div);
  });
  const totalPages = Math.max(1, Math.ceil(total / drilldownState.pageSize));
  $('drilldownPage').innerText = `Page ${drilldownState.page} of ${totalPages} • ${total} people`;
  $('drilldownPrev').disabled = drilldownState.page <= 1;
  $('drilldownNext').disabled = drilldownState.page >= totalPages;
}

function setDrawerTitle(title, sub){
  $('drilldownTitle').innerText = title || 'People';
  $('drilldownSub').innerText = sub || '';
}

function buildDrilldownPayload(chartKey, ctx){
  if(!ctx) return null;
  if(chartKey === 'surnames'){
    return { chartId: chartKey, title: 'Top surnames', type: 'surname', label: `Surname: ${ctx.label}`, filters: { surname: ctx.label } };
  }
  if(chartKey === 'places'){
    return { chartId: chartKey, title: 'Top birth places', type: 'birth_place', label: `Birth place: ${ctx.label}`, filters: { place: ctx.label } };
  }
  if(chartKey === 'children'){
    const num = parseInt(ctx.label, 10);
    return { chartId: chartKey, title: 'Children per family', type: 'children_count', label: `Families with ${ctx.label} children`, filters: { children: isNaN(num) ? null : num } };
  }
  if(chartKey === 'decades'){
    const decade = parseInt(String(ctx.label).replace(/\D/g,''), 10);
    const kind = (ctx.datasetLabel || '').toLowerCase();
    if(kind.includes('birth')){
      return { chartId: chartKey, title: 'Births by decade', type: 'birth_decade', label: `Births in ${ctx.label}`, filters: { decade } };
    }
    if(kind.includes('death')){
      return { chartId: chartKey, title: 'Deaths by decade', type: 'death_decade', label: `Deaths in ${ctx.label}`, filters: { decade } };
    }
    if(kind.includes('marriage')){
      return { chartId: chartKey, title: 'Marriages by decade', type: 'marriage_decade', label: `Marriages in ${ctx.label}`, filters: { decade } };
    }
  }
  return null;
}

async function openDrilldown(payload){
  if(!payload) return;
  drilldownState.payload = payload;
  drilldownState.page = payload.page || 1;
  setDrawerTitle(payload.title || 'People', payload.label || '');
  document.body.classList.add('drawer-open');
  $('drilldownDrawer').classList.remove('hidden');
  $('btnCloseDrawer').focus({ preventScroll: true });
  await loadDrilldownPage();
}

async function loadDrilldownPage(){
  const payload = drilldownState.payload;
  if(!payload) return;
  const key = JSON.stringify({ ...payload, page: drilldownState.page, pageSize: drilldownState.pageSize });
  let res = drilldownCache.get(key);
  if(!res){
    res = await api('/api/analytics/drilldown', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...payload, page: drilldownState.page, pageSize: drilldownState.pageSize })
    });
    drilldownCache.set(key, res);
  }
  drilldownState.total = res.total || 0;
  drilldownState.items = res.items || [];
  renderDrilldown(drilldownState.items, drilldownState.total);
}

function changeDrilldownPage(delta){
  const next = drilldownState.page + delta;
  if(next < 1) return;
  const totalPages = Math.max(1, Math.ceil((drilldownState.total || 0) / drilldownState.pageSize));
  if(next > totalPages) return;
  drilldownState.page = next;
  loadDrilldownPage();
}

function copyCurrentIds(){
  const ids = (drilldownState.items || []).map((p) => p.id).filter(Boolean);
  if(ids.length === 0) return;
  copyToClipboard(ids.join(', ')).catch((err)=>{
    console.warn('Failed to copy IDs', err);
    alert('Copy failed. Please try selecting manually.');
  });
}

function closeDrilldown(){
  drilldownState.payload = null;
  $('drilldownDrawer').classList.add('hidden');
  document.body.classList.remove('drawer-open');
}

function openOverlay(chartKey){
  if(!chartKey) return;
  overlayState.chartKey = chartKey;
  overlayState.scrollY = window.scrollY;
  document.body.classList.add('overlay-open');
  $('chartOverlay').classList.remove('hidden');
  $('btnCloseOverlay').focus({ preventScroll: true });
  renderOverlay(chartKey);
  const url = new URL(window.location.href);
  url.searchParams.set('focus', chartKey);
  history.replaceState({}, '', url.toString());
}

function closeOverlay(){
  overlayState.chartKey = null;
  $('chartOverlay').classList.add('hidden');
  document.body.classList.remove('overlay-open');
  window.scrollTo(0, overlayState.scrollY || 0);
  const url = new URL(window.location.href);
  url.searchParams.delete('focus');
  history.replaceState({}, '', url.toString());
}

function renderOverlay(chartKey){
  const host = $('overlayBody');
  host.innerHTML = '';
  const meta = chartData[chartKey];
  const titleEl = $('overlayTitle');
  const titleMap = {
    decades: 'Births / Deaths / Marriages by decade',
    surnames: 'Top surnames',
    places: 'Top birth places',
    children: 'Children per family',
    migration: 'Migration pairs',
    duplicates: 'Duplicate candidates',
  };
  titleEl.innerText = titleMap[chartKey] || 'Chart';

  if(!meta){
    host.innerHTML = `<div class="muted">No data loaded yet.</div>`;
    return;
  }

  if(meta.type === 'table'){
    const container = document.createElement('div');
    container.className = 'overlayTable';
    container.innerHTML = `<table><thead><tr><th>Item</th><th>Count</th></tr></thead><tbody>${
      (meta.rows || []).map((r) => {
        if(chartKey === 'migration'){
          return `<tr><td>${r.from} → ${r.to}</td><td>${fmtNum(r.count)}</td></tr>`;
        }
        return `<tr><td>${r.given} ${r.surname} (${r.birth_year})</td><td>${fmtNum(r.count)}</td></tr>`;
      }).join('')
    }</tbody></table>`;
    host.appendChild(container);
    return;
  }

  const canvas = document.createElement('canvas');
  canvas.height = 360;
  host.appendChild(canvas);
  const ctx = canvas.getContext('2d');
  new Chart(ctx, {
    type: 'bar',
    data: { labels: meta.labels, datasets: meta.datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#cbd5e1' } } },
      scales: {
        x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.15)' } },
        y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.15)' } },
      },
    },
  });
}

async function refresh(){
  const ov = await api('/api/analytics/overview');
  const ts = await api('/api/analytics/timeseries');
  analyticsState.overview = ov;
  analyticsState.timeseries = ts;

  const kpiRow = $('kpiRow');
  kpiRow.innerHTML = '';
  kpiRow.appendChild(kpiCard('People', fmtNum(ov.counts.people), 'records'));
  kpiRow.appendChild(kpiCard('Families', fmtNum(ov.counts.families), 'records'));
  kpiRow.appendChild(kpiCard('Media Assets', fmtNum(ov.counts.media_assets), 'files'));
  kpiRow.appendChild(kpiCard('Notes', fmtNum(ov.counts.notes), 'rows'));
  kpiRow.appendChild(kpiCard('Birth year known', `${ov.coverage.birth_year_pct}%`, 'coverage'));
  kpiRow.appendChild(kpiCard('Birth place known', `${ov.coverage.birth_place_pct}%`, 'coverage'));

  const decadeSet = new Set([
    ...ts.births_by_decade.map(x => x.decade),
    ...ts.deaths_by_decade.map(x => x.decade),
    ...ts.marriages_by_decade.map(x => x.decade),
  ]);
  const decades = Array.from(decadeSet).sort((a,b) => a-b).map(d => `${d}s`);
  const birthsMap = new Map(ts.births_by_decade.map(x => [x.decade, x.count]));
  const deathsMap = new Map(ts.deaths_by_decade.map(x => [x.decade, x.count]));
  const marrMap  = new Map(ts.marriages_by_decade.map(x => [x.decade, x.count]));
  const decadeVals = Array.from(decadeSet).sort((a,b)=>a-b);
  const births = decadeVals.map(d => birthsMap.get(d) || 0);
  const deaths = decadeVals.map(d => deathsMap.get(d) || 0);
  const marriages = decadeVals.map(d => marrMap.get(d) || 0);

  destroyChart('decades');
  const decadeDatasets = [
    { label: 'Births', data: births },
    { label: 'Deaths', data: deaths },
    { label: 'Marriages', data: marriages },
  ];
  charts.decades = buildBarChart('chartDecades', decades, decadeDatasets, 'decades');
  chartData.decades = { labels: decades, datasets: decadeDatasets };

  destroyChart('surnames');
  const surnameLabels = (ov.top_surnames || []).map(x => x.surname);
  const surnameData = [{ label: 'People', data: (ov.top_surnames || []).map(x => x.count) }];
  charts.surnames = buildBarChart('chartSurnames', surnameLabels, surnameData, 'surnames');
  chartData.surnames = { labels: surnameLabels, datasets: surnameData };

  destroyChart('places');
  const placeLabels = (ov.top_birth_places || []).map(x => x.place);
  const placeData = [{ label: 'People', data: (ov.top_birth_places || []).map(x => x.count) }];
  charts.places = buildBarChart('chartPlaces', placeLabels, placeData, 'places');
  chartData.places = { labels: placeLabels, datasets: placeData };

  const dist = (ov.children_per_family && ov.children_per_family.distribution) ? ov.children_per_family.distribution : [];
  destroyChart('children');
  const childrenLabels = dist.map(x => String(x.children));
  const childrenData = [{ label: 'Families', data: dist.map(x => x.families) }];
  charts.children = buildBarChart('chartChildren', childrenLabels, childrenData, 'children');
  chartData.children = { labels: childrenLabels, datasets: childrenData };

  const migLimit = parseInt($('migrationLimit').value || '20');
  const dupLimit = parseInt($('dupeLimit').value || '50');

  const migrations = await api(`/api/analytics/migration-pairs?limit=${migLimit}`);
  analyticsState.migrations = migrations;
  renderTable('migrationTable', [
    { title: 'From', render: (r) => `<span class="mono">${r.from}</span>` },
    { title: 'To', render: (r) => `<span class="mono">${r.to}</span>` },
    { title: 'Count', render: (r) => fmtNum(r.count) },
  ], migrations, {
    onRowClick: (row) => openDrilldown({
      chartId: 'migration',
      title: 'Migration pairs',
      type: 'migration_pair',
      label: `Birth: ${row.from} → Death: ${row.to}`,
      filters: { from: row.from, to: row.to },
    }),
  });
  chartData.migration = { type: 'table', rows: migrations };

  const dupes = await api(`/api/analytics/duplicates?limit=${dupLimit}`);
  analyticsState.duplicates = dupes;
  renderTable('dupeTable', [
    { title: 'Name', render: (r) => `${r.given} ${r.surname}` },
    { title: 'Birth year', render: (r) => String(r.birth_year) },
    { title: 'Count', render: (r) => fmtNum(r.count) },
    { title: 'IDs', render: (r) => `<span class="mono">${(r.ids || []).join(', ')}</span>` },
  ], dupes, {
    onRowClick: (row) => openDrilldown({
      chartId: 'duplicates',
      title: 'Duplicate candidates',
      type: 'duplicate_cluster',
      label: `${row.given} ${row.surname} (${row.birth_year})`,
      filters: { ids: row.ids },
    }),
  });
  chartData.duplicates = { type: 'table', rows: dupes };
}

function wire(){
  $('btnRefresh').addEventListener('click', async () => {
    try { await refresh(); } catch (e) { alert(e.message || String(e)); }
  });

  $('migrationLimit').addEventListener('change', async () => {
    try { await refresh(); } catch (e) { alert(e.message || String(e)); }
  });

  $('dupeLimit').addEventListener('change', async () => {
    try { await refresh(); } catch (e) { alert(e.message || String(e)); }
  });

  $('btnCloseDrawer').addEventListener('click', closeDrilldown);
  $('drilldownPrev').addEventListener('click', () => changeDrilldownPage(-1));
  $('drilldownNext').addEventListener('click', () => changeDrilldownPage(1));
  $('drilldownCopy').addEventListener('click', copyCurrentIds);
  $('btnCloseOverlay').addEventListener('click', closeOverlay);

  document.addEventListener('keydown', (e) => {
    if(e.key === 'Escape'){
      if(overlayState.chartKey){ closeOverlay(); }
      if(drilldownState.payload){ closeDrilldown(); }
    }
  });

  document.querySelectorAll('[data-chart-title]').forEach((el) => {
    const chartKey = el.getAttribute('data-chart-title');
    el.classList.add('chartTitleClickable');
    const handler = () => openOverlay(chartKey);
    el.addEventListener('click', handler);
    el.addEventListener('keydown', (e) => {
      if(e.key === 'Enter' || e.key === ' '){
        e.preventDefault();
        handler();
      }
    });
  });
}

(async function init(){
  wire();
  try {
    await refresh();
  } catch (e) {
    alert(e.message || String(e));
  }
})(); 
