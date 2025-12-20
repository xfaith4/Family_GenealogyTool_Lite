let state = { people: [], selected: null, dirty: false };
const $ = (id) => document.getElementById(id);

function escapeHtml(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
}
function fullName(p){
  const g = (p.given || "").trim();
  const s = (p.surname || "").trim();
  const name = `${g} ${s}`.trim();
  return name || "(unnamed)";
}
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

function renderList(){
  const el = $("peopleList");
  el.innerHTML = "";
  if(state.people.length === 0){
    el.innerHTML = `<div class="muted">No people yet. Import a GEDCOM or create a person.</div>`;
    return;
  }
  for(const p of state.people){
    const div = document.createElement("div");
    div.className = "item";
    // Build metadata string with birth/death info, minimize ID display
    let meta = [];
    if(p.birth_date) meta.push(`b. ${escapeHtml(p.birth_date)}`);
    if(p.death_date) meta.push(`d. ${escapeHtml(p.death_date)}`);
    if(p.sex) meta.push(escapeHtml(p.sex));
    // Only show ID if no other metadata
    if(meta.length === 0) {
      meta.push(`ID ${p.id}`);
    }
    div.innerHTML = `
      <div class="name">${escapeHtml(fullName(p))}</div>
      <div class="meta">${meta.join(" • ")}</div>
    `;
    div.onclick = () => loadDetails(p.id);
    el.appendChild(div);
  }
}

async function refreshPeople(q=""){
  const url = q ? `/api/people?q=${encodeURIComponent(q)}` : "/api/people";
  state.people = await api(url);
  renderList();
}

function markDirty(d){
  state.dirty = d;
  $("btnSave").disabled = !state.selected || !d;
}

function setButtons(enabled){
  $("btnSave").disabled = !enabled;
  $("btnDelete").disabled = !enabled;
}

function detailsForm(p){
  return `
  <div class="formRow"><label>Given</label><input id="f_given" value="${escapeHtml(p.given||"")}" /></div>
  <div class="formRow"><label>Surname</label><input id="f_surname" value="${escapeHtml(p.surname||"")}" /></div>
  <div class="formRow"><label>Sex</label><input id="f_sex" value="${escapeHtml(p.sex||"")}" /></div>
  <div class="formRow"><label>Birth Date</label><input id="f_birth_date" value="${escapeHtml(p.birth_date||"")}" /></div>
  <div class="formRow"><label>Birth Place</label><input id="f_birth_place" value="${escapeHtml(p.birth_place||"")}" /></div>
  <div class="formRow"><label>Death Date</label><input id="f_death_date" value="${escapeHtml(p.death_date||"")}" /></div>
  <div class="formRow"><label>Death Place</label><input id="f_death_place" value="${escapeHtml(p.death_place||"")}" /></div>

  <div class="sectionTitle">Notes</div>
  <div class="row">
    <input id="noteText" class="input" placeholder="Add a note..." />
    <button id="btnAddNote" class="btn btnSecondary">Add</button>
  </div>
  <div id="notes"></div>

  <div class="sectionTitle">Media</div>
  <div class="row">
    <input id="mediaFile" type="file" />
    <button id="btnUpload" class="btn btnSecondary">Upload</button>
  </div>
  <div id="mediaList"></div>
  `;
}

function renderNotes(p){
  const host = $("notes");
  host.innerHTML = "";
  const notes = p.notes || [];
  if(notes.length === 0){
    host.innerHTML = `<div class="muted">No notes.</div>`;
    return;
  }
  for(const n of notes){
    const div = document.createElement("div");
    div.className = "note";
    div.innerHTML = `<div>${escapeHtml(n.text)}</div><div class="muted" style="font-size:11px;margin-top:6px;">${escapeHtml(n.created_at)}</div>`;
    host.appendChild(div);
  }
}

function renderMedia(p){
  const host = $("mediaList");
  host.innerHTML = "";
  
  // Fetch media v2 if available
  if(p.id){
    fetchAndRenderMediaV2(p.id, host);
  }
}

async function fetchAndRenderMediaV2(personId, host){
  try {
    const items = await api(`/api/people/${personId}/media/v2`);
    
    if(items.length === 0){
      host.innerHTML = `<div class="muted">No media attached.</div>`;
      return;
    }
    
    for(const m of items){
      const div = document.createElement("div");
      div.className = "mediaItem";
      
      const link = `/api/media/${encodeURIComponent(m.path)}`;
      const thumbUrl = m.thumbnail_path 
        ? `/api/media/thumbnail/${encodeURIComponent(m.thumbnail_path)}`
        : link;
      
      const isImage = m.mime_type && m.mime_type.startsWith('image/');
      
      div.innerHTML = `
        <div class="mediaPreview">
          ${isImage && m.thumbnail_path 
            ? `<img src="${thumbUrl}" alt="${escapeHtml(m.original_filename)}" class="thumbnail" />` 
            : `<div class="noThumb">📄</div>`}
        </div>
        <div class="mediaInfo">
          <div><a href="${link}" target="_blank" rel="noreferrer">${escapeHtml(m.original_filename || m.path)}</a></div>
          <div class="muted" style="font-size:11px;margin-top:6px;">${escapeHtml(m.mime_type||"")}${m.size_bytes ? " • "+formatBytes(m.size_bytes) : ""}</div>
          <button class="btnSmall btnDanger" data-link-id="${m.link_id}">Detach</button>
        </div>
      `;
      
      // Add detach handler
      const detachBtn = div.querySelector('[data-link-id]');
      detachBtn.onclick = async () => {
        if(!confirm('Detach this media?')) return;
        await api(`/api/media/link/${m.link_id}`, { method: 'DELETE' });
        await loadDetails(personId);
      };
      
      host.appendChild(div);
    }
  } catch(err) {
    host.innerHTML = `<div class="muted">Error loading media.</div>`;
    console.error('Failed to load media:', err);
  }
}

function formatBytes(bytes){
  if(bytes < 1024) return bytes + ' B';
  if(bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/(1024*1024)).toFixed(1) + ' MB';
}

async function renderTree(id){
  const host = $("tree");
  host.classList.remove("muted");
  host.innerHTML = `<div class="muted" style="text-align:center;padding:30px;">Loading tree…</div>`;

  let treeData;
  try {
    treeData = await api(`/api/tree/${id}`);
  } catch (err) {
    host.innerHTML = `<div class="muted" style="text-align:center;padding:30px;">Failed to load tree.</div>`;
    console.error("Failed to load mini tree", err);
    return;
  }

  host.innerHTML = '';
  if(!treeData?.root){
    host.innerHTML = `<div class="muted" style="text-align:center;padding:30px;">No tree data available.</div>`;
    return;
  }

  const svgWidth = Math.max(360, host.clientWidth || 360);
  const svgHeight = 260;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', svgWidth);
  svg.setAttribute('height', svgHeight);
  svg.setAttribute('viewBox', `0 0 ${svgWidth} ${svgHeight}`);

  const parentNodes = (treeData.parents || []).slice(0, 4);
  const childNodes = (treeData.children || []).slice(0, 6);
  const positions = new Map();

  const parentY = 40;
  const rootY = svgHeight / 2 - 10;
  const childY = svgHeight - 60;

  const drawNode = (person, x, y, opts = {}) => {
    const width = 120;
    const height = 40;
    positions.set(person.id, { x, y: y + height / 2 });

    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('cursor', 'pointer');
    group.setAttribute('data-person-id', person.id);
    group.addEventListener('click', () => loadDetails(person.id));

    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', x - width / 2);
    rect.setAttribute('y', y);
    rect.setAttribute('width', width);
    rect.setAttribute('height', height);
    rect.setAttribute('rx', '10');
    rect.setAttribute('fill', opts.fill || '#0c1621');
    rect.setAttribute('stroke', opts.stroke || 'var(--line)');
    rect.setAttribute('stroke-width', opts.strokeWidth || '1.8');
    group.appendChild(rect);

    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', x);
    text.setAttribute('y', y + height / 2 - 2);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('fill', '#fff');
    text.setAttribute('font-size', '12');
    text.setAttribute('font-weight', '600');
    text.textContent = fullName(person);
    group.appendChild(text);

    const meta = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    meta.setAttribute('x', x);
    meta.setAttribute('y', y + height / 2 + 14);
    meta.setAttribute('text-anchor', 'middle');
    meta.setAttribute('dominant-baseline', 'hanging');
    meta.setAttribute('fill', 'var(--muted)');
    meta.setAttribute('font-size', '10');
    meta.textContent = `ID ${person.id}`;
    group.appendChild(meta);

    svg.appendChild(group);
  };

  const drawLine = (from, to, opts = {}) => {
    if(!from || !to) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', from.x);
    line.setAttribute('y1', from.y);
    line.setAttribute('x2', to.x);
    line.setAttribute('y2', to.y);
    line.setAttribute('stroke', opts.color || '#7f8c9a');
    line.setAttribute('stroke-width', opts.width || '2');
    line.setAttribute('stroke-linecap', 'round');
    svg.appendChild(line);
  };

  const parentSpacing = parentNodes.length ? svgWidth / (parentNodes.length + 1) : 0;
  parentNodes.forEach((parent, index) => {
    const x = parentSpacing * (index + 1);
    drawNode(parent, x, parentY, { fill: '#16354c' });
  });

  const rootX = svgWidth / 2;
  drawNode(treeData.root, rootX, rootY, { fill: '#1b6edc', stroke: '#fff', strokeWidth: '2' });

  const childSpacing = childNodes.length ? svgWidth / (childNodes.length + 1) : 0;
  childNodes.forEach((child, index) => {
    const x = childSpacing * (index + 1);
    drawNode(child, x, childY, { fill: '#1b1f29' });
  });

  parentNodes.forEach(parent => {
    drawLine(positions.get(parent.id), positions.get(treeData.root.id));
  });
  childNodes.forEach(child => {
    drawLine(positions.get(treeData.root.id), positions.get(child.id));
  });

  const legend = document.createElement('div');
  legend.style.fontSize = '12px';
  legend.style.marginTop = '8px';
  legend.style.color = 'var(--muted)';
  legend.innerHTML = 'Click a box to load that person’s profile.';

  host.innerHTML = '';
  host.appendChild(svg);
  host.appendChild(legend);
}

async function loadDetails(id){
  const p = await api(`/api/people/${id}`);
  state.selected = p;
  state.dirty = false;

  $("details").classList.remove("muted");
  $("details").innerHTML = detailsForm(p);

  const fields = ["given","surname","sex","birth_date","birth_place","death_date","death_place"];
  for(const f of fields){
    const el = $(`f_${f}`);
    el.addEventListener("input", () => markDirty(true));
  }

  $("btnAddNote").onclick = async () => {
    const txt = ($("noteText").value || "").trim();
    if(!txt) return;
    await api(`/api/people/${id}/notes`, { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ text: txt }) });
    await loadDetails(id);
  };

  $("btnUpload").onclick = async () => {
    const input = $("mediaFile");
    if(!input.files || input.files.length === 0) return;
    const f = input.files[0];
    const fd = new FormData();
    fd.append("file", f);
    fd.append("person_id", id);
    await api(`/api/media/upload`, { method:"POST", body: fd });
    await loadDetails(id);
  };

  $("btnSave").onclick = saveSelected;
  $("btnDelete").onclick = deleteSelected;

  $("btnSave").disabled = true;
  $("btnDelete").disabled = false;

  renderNotes(p);
  renderMedia(p);
  await renderTree(id);
}

async function saveSelected(){
  if(!state.selected) return;
  const id = state.selected.id;
  const payload = {
    given: $("f_given").value,
    surname: $("f_surname").value,
    sex: $("f_sex").value,
    birth_date: $("f_birth_date").value,
    birth_place: $("f_birth_place").value,
    death_date: $("f_death_date").value,
    death_place: $("f_death_place").value,
  };
  await api(`/api/people/${id}`, { method:"PUT", headers:{ "Content-Type":"application/json" }, body: JSON.stringify(payload) });
  markDirty(false);
  await refreshPeople(($("search").value||"").trim());
  await loadDetails(id);
}

async function deleteSelected(){
  if(!state.selected) return;
  const id = state.selected.id;
  if(!confirm("Delete this person?")) return;
  await api(`/api/people/${id}`, { method:"DELETE" });
  state.selected = null;
  $("details").innerHTML = `<div class="muted">Select a person…</div>`;
  $("tree").innerHTML = `<div class="muted">Select a person…</div>`;
  setButtons(false);
  await refreshPeople(($("search").value||"").trim());
}

async function newPerson(){
  const p = await api("/api/people", { method:"POST", headers:{ "Content-Type":"application/json" }, body: JSON.stringify({ given:"Temp", surname:"Person" }) });
  await refreshPeople(($("search").value||"").trim());
  await loadDetails(p.id);
}

async function importGedcom(file){
  const fd = new FormData();
  fd.append("file", file);
  const res = await api("/api/import/gedcom", { method:"POST", body: fd });
  alert(`Imported: ${res.imported.people} people, ${res.imported.families} families`);
  await refreshPeople(($("search").value||"").trim());
}

async function importRmtree(file){
  const fd = new FormData();
  fd.append("file", file);
  const res = await api("/api/import/rmtree", { method:"POST", body: fd });
  const summary = res.imported || {};
  alert(`Imported: ${summary.people || 0} people, ${summary.media_assets || 0} media assets, ${summary.media_links || 0} media links, ${summary.relationships || 0} relationships`);
  await refreshPeople(($("search").value||"").trim());
}

function wire(){
  $("search").addEventListener("input", async () => {
    await refreshPeople(($("search").value || "").trim());
  });
  $("btnNewPerson").onclick = newPerson;
  $("gedcomFile").addEventListener("change", async (ev) => {
    const f = ev.target.files && ev.target.files[0];
    if(!f) return;
    await importGedcom(f);
    ev.target.value = "";
  });
  $("rmtreeFile").addEventListener("change", async (ev) => {
    const f = ev.target.files && ev.target.files[0];
    if(!f) return;
    await importRmtree(f);
    ev.target.value = "";
  });
}

(async function init(){
  wire();
  await refreshPeople();
  setButtons(false);

  // Support deep-linking from Tree v2 and other pages
  // Example: /?personId=123
  const params = new URLSearchParams(window.location.search);
  const personId = params.get('personId');
  if(personId){
    const pid = parseInt(personId, 10);
    if(!Number.isNaN(pid)){
      try {
        await loadDetails(pid);
      } catch (e) {
        console.warn('Failed to load personId from URL:', e);
      }
    }
  }
})();
