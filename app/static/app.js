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
    div.innerHTML = `
      <div class="name">${escapeHtml(fullName(p))}</div>
      <div class="meta">ID ${p.id}${p.xref ? " • " + escapeHtml(p.xref) : ""}${p.sex ? " • " + escapeHtml(p.sex) : ""}</div>
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
  const t = await api(`/api/tree/${id}`);
  const card = (p) => `
    <div class="treeCard">
      <strong>${escapeHtml(fullName(p))}</strong>
      <div class="muted" style="font-size:12px;">ID ${p.id}</div>
    </div>`;
  const section = (title, list) => `
    <div class="sectionTitle">${escapeHtml(title)}</div>
    ${list.length ? list.map(card).join("") : `<div class="muted">None</div>`}`;

  host.innerHTML = `
    ${card(t.root)}
    ${section("Parents", t.parents || [])}
    ${section("Children", t.children || [])}
  `;
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
}

(async function init(){
  wire();
  await refreshPeople();
  setButtons(false);
})();
