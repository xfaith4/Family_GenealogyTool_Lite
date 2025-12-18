/*
  Analytics dashboard (no build step).
  - Uses Chart.js from CDN
  - Pulls from /api/analytics/* endpoints
*/

const $ = (id) => document.getElementById(id);

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

let charts = {
  decades: null,
  surnames: null,
  places: null,
  children: null,
};

function destroyChart(key){
  if(charts[key]){
    charts[key].destroy();
    charts[key] = null;
  }
}

function buildBarChart(canvasId, labels, datasets){
  const ctx = $(canvasId).getContext('2d');
  return new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets,
    },
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
      }
    }
  });
}

function renderTable(hostId, columns, rows){
  const host = $(hostId);
  if(!rows || rows.length === 0){
    host.innerHTML = `<div class="muted" style="padding:8px;">No data.</div>`;
    return;
  }

  const thead = `<tr>${columns.map(c => `<th>${c.title}</th>`).join('')}</tr>`;
  const tbody = rows.map(r => {
    return `<tr>${columns.map(c => `<td>${c.render(r)}</td>`).join('')}</tr>`;
  }).join('');

  host.innerHTML = `
    <table>
      <thead>${thead}</thead>
      <tbody>${tbody}</tbody>
    </table>
  `;
}

async function refresh(){
  // Overview (counts + coverage + top lists + children dist)
  const ov = await api('/api/analytics/overview');

  // KPIs
  const kpiRow = $('kpiRow');
  kpiRow.innerHTML = '';
  kpiRow.appendChild(kpiCard('People', fmtNum(ov.counts.people), 'records'));
  kpiRow.appendChild(kpiCard('Families', fmtNum(ov.counts.families), 'records'));
  kpiRow.appendChild(kpiCard('Media Assets', fmtNum(ov.counts.media_assets), 'files'));
  kpiRow.appendChild(kpiCard('Notes', fmtNum(ov.counts.notes), 'rows'));
  kpiRow.appendChild(kpiCard('Birth year known', `${ov.coverage.birth_year_pct}%`, 'coverage'));
  kpiRow.appendChild(kpiCard('Birth place known', `${ov.coverage.birth_place_pct}%`, 'coverage'));

  // Decade time-series
  const ts = await api('/api/analytics/timeseries');
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
  charts.decades = buildBarChart('chartDecades', decades, [
    { label: 'Births', data: births },
    { label: 'Deaths', data: deaths },
    { label: 'Marriages', data: marriages },
  ]);

  // Top surnames
  destroyChart('surnames');
  charts.surnames = buildBarChart(
    'chartSurnames',
    (ov.top_surnames || []).map(x => x.surname),
    [{ label: 'People', data: (ov.top_surnames || []).map(x => x.count) }]
  );

  // Top birth places
  destroyChart('places');
  charts.places = buildBarChart(
    'chartPlaces',
    (ov.top_birth_places || []).map(x => x.place),
    [{ label: 'People', data: (ov.top_birth_places || []).map(x => x.count) }]
  );

  // Children per family distribution
  const dist = (ov.children_per_family && ov.children_per_family.distribution) ? ov.children_per_family.distribution : [];
  destroyChart('children');
  charts.children = buildBarChart(
    'chartChildren',
    dist.map(x => String(x.children)),
    [{ label: 'Families', data: dist.map(x => x.families) }]
  );

  // Migration pairs + duplicates
  const migLimit = parseInt($('migrationLimit').value || '20');
  const dupLimit = parseInt($('dupeLimit').value || '50');

  const migrations = await api(`/api/analytics/migration-pairs?limit=${migLimit}`);
  renderTable('migrationTable', [
    { title: 'From', render: (r) => `<span class="mono">${r.from}</span>` },
    { title: 'To', render: (r) => `<span class="mono">${r.to}</span>` },
    { title: 'Count', render: (r) => fmtNum(r.count) },
  ], migrations);

  const dupes = await api(`/api/analytics/duplicates?limit=${dupLimit}`);
  renderTable('dupeTable', [
    { title: 'Name', render: (r) => `${r.given} ${r.surname}` },
    { title: 'Birth year', render: (r) => String(r.birth_year) },
    { title: 'Count', render: (r) => fmtNum(r.count) },
    { title: 'IDs', render: (r) => `<span class="mono">${(r.ids || []).join(', ')}</span>` },
  ], dupes);
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
}

(async function init(){
  wire();
  try {
    await refresh();
  } catch (e) {
    alert(e.message || String(e));
  }
})();
