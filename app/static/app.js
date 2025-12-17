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
  const items = p.media || [];
  if(items.length === 0){
    host.innerHTML = `<div class="muted">No media attached.</div>`;
    return;
  }
  for(const m of items){
    const div = document.createElement("div");
    div.className = "note";
    const link = `/api/media/${encodeURIComponent(m.file_name)}`;
    div.innerHTML = `
      <div><a href="${link}" target="_blank" rel="noreferrer">${escapeHtml(m.original_name || m.file_name)}</a></div>
      <div class="muted" style="font-size:11px;margin-top:6px;">${escapeHtml(m.mime_type||"")}${m.size_bytes ? " • "+m.size_bytes+" bytes" : ""}</div>
    `;
    host.appendChild(div);
  }
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
    await api(`/api/people/${id}/media`, { method:"POST", body: fd });
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
  try {
    const res = await api("/api/import/gedcom", { method:"POST", body: fd });
    alert(`Imported: ${res.imported.people} people, ${res.imported.families} families`);
    await refreshPeople(($("search").value||"").trim());
  } catch (err) {
    alert(`Import failed: ${err.message}`);
  }
}

function formatBytes(b) {
  if(b < 1024) return `${b} bytes`;
  if(b < 1024*1024) return `${(b/1024).toFixed(1)} KB`;
  return `${(b/(1024*1024)).toFixed(1)} MB`;
}

async function showDiagnostics(){
  const modal = $("diagnosticsModal");
  modal.style.display = "flex";
  const info = $("diagnosticsInfo");
  info.innerHTML = "Loading...";
  
  try {
    const diag = await api("/api/diagnostics");
    
    info.innerHTML = `
      <div><strong>App Version:</strong> ${escapeHtml(diag.app_version)}</div>
      <div><strong>Schema Version:</strong> ${escapeHtml(diag.schema_version)}</div>
      <div><strong>Database Path:</strong> ${escapeHtml(diag.db_path)}</div>
      <div><strong>Database Size:</strong> ${formatBytes(diag.db_size_bytes)}</div>
      <br/>
      <div><strong>Record Counts:</strong></div>
      <div style="margin-left: 20px;">
        <div>• People: ${escapeHtml(String(diag.counts.people))}</div>
        <div>• Families: ${escapeHtml(String(diag.counts.families))}</div>
        <div>• Media: ${escapeHtml(String(diag.counts.media))}</div>
        <div>• Unassigned Media: ${escapeHtml(String(diag.counts.unassigned_media))}</div>
      </div>
      <br/>
      <div><strong>Last Import:</strong> ${diag.last_import ? escapeHtml(diag.last_import) : "Never"}</div>
    `;
  } catch (err) {
    info.innerHTML = `<div style="color: red;">Failed to load diagnostics: ${escapeHtml(err.message)}</div>`;
  }
}

function closeDiagnostics() {
  $("diagnosticsModal").style.display = "none";
}

async function createBackup(){
  if(!confirm("Create a backup of the database and media files?")) return;
  
  try {
    const res = await api("/api/backup", { method:"POST", headers:{ "Content-Type":"application/json" }, body: "{}" });
    alert(`Backup created successfully!\n\nBackup: ${res.backup_name}\nDatabase: ${formatBytes(res.db_size_bytes)}\nMedia files: ${res.media_files}`);
  } catch (err) {
    alert(`Backup failed: ${err.message}`);
  }
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
  $("btnDiagnostics").onclick = showDiagnostics;
  $("btnBackup").onclick = createBackup;
  $("btnCloseDiagnostics").onclick = closeDiagnostics;
  
  // Close modal on backdrop click
  $("diagnosticsModal").onclick = (e) => {
    if (e.target.id === "diagnosticsModal") {
      closeDiagnostics();
    }
  };
  
  // Close modal on Escape key
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && $("diagnosticsModal").style.display === "flex") {
      closeDiagnostics();
    }
  });
}

(async function init(){
  wire();
  await refreshPeople();
  setButtons(false);
})();
