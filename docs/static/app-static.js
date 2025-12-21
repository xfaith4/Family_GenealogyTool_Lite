/**
 * Static version of app.js for GitHub Pages
 * 
 * This version uses the data-adapter.js to load JSON files
 * instead of making API calls to the Flask backend.
 */

let state = { people: [], selected: null };
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

function renderList(){
  const el = $("peopleList");
  el.innerHTML = "";
  if(state.people.length === 0){
    el.innerHTML = `<div class="muted">No people yet.</div>`;
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
  // Use data adapter instead of API call
  if (q) {
    state.people = await window.dataAdapter.searchPersons(q);
  } else {
    state.people = await window.dataAdapter.getPersons();
  }
  renderList();
}

function detailsForm(p){
  return `
  <div class="formRow"><label>Given</label><div class="readOnly">${escapeHtml(p.given||"—")}</div></div>
  <div class="formRow"><label>Surname</label><div class="readOnly">${escapeHtml(p.surname||"—")}</div></div>
  <div class="formRow"><label>Sex</label><div class="readOnly">${escapeHtml(p.sex||"—")}</div></div>
  <div class="formRow"><label>Birth Date</label><div class="readOnly">${escapeHtml(p.birth_date||"—")}</div></div>
  <div class="formRow"><label>Birth Place</label><div class="readOnly">${escapeHtml(p.birth_place||"—")}</div></div>
  <div class="formRow"><label>Death Date</label><div class="readOnly">${escapeHtml(p.death_date||"—")}</div></div>
  <div class="formRow"><label>Death Place</label><div class="readOnly">${escapeHtml(p.death_place||"—")}</div></div>

  <div class="sectionTitle">Notes</div>
  <div id="notes"></div>

  <div class="sectionTitle">Media</div>
  <div id="mediaList"></div>
  `;
}

async function renderNotes(p){
  const host = $("notes");
  host.innerHTML = "";
  const notes = await window.dataAdapter.getPersonNotes(p.id);
  
  if(notes.length === 0) {
    host.innerHTML = `<div class="muted">No notes.</div>`;
    return;
  }
  
  for(const n of notes){
    const div = document.createElement("div");
    div.className = "note";
    div.textContent = n.note_text;
    host.appendChild(div);
  }
}

async function renderMedia(p){
  const host = $("mediaList");
  host.innerHTML = "";
  const media = await window.dataAdapter.getPersonMedia(p.id);
  
  if(media.length === 0) {
    host.innerHTML = `<div class="muted">No media.</div>`;
    return;
  }
  
  for(const m of media){
    const div = document.createElement("div");
    div.className = "mediaItem";
    div.innerHTML = `
      <div class="mediaName">${escapeHtml(m.original_filename || "Unknown")}</div>
      <div class="mediaMeta">${escapeHtml(m.mime_type || "")} • ${m.size_bytes ? Math.round(m.size_bytes/1024) + " KB" : ""}</div>
    `;
    host.appendChild(div);
  }
}

async function renderMiniTree(p){
  const el = $("tree");
  el.innerHTML = "";
  
  // Get family relationships
  const families = await window.dataAdapter.getFamilies();
  const familyChildren = await window.dataAdapter.getFamilyChildren();
  const relationships = await window.dataAdapter.getRelationships();
  const allPersons = await window.dataAdapter.getPersons();
  
  const personMap = new Map(allPersons.map(person => [person.id, person]));
  
  // Find parents
  const parents = [];
  const parentRels = relationships.filter(r => r.child_person_id === p.id);
  parentRels.forEach(rel => {
    const parent = personMap.get(rel.parent_person_id);
    if (parent && !parents.find(pr => pr.id === parent.id)) {
      parents.push(parent);
    }
  });
  
  // Find families where person is a parent
  const parentFamilies = families.filter(
    f => f.husband_person_id === p.id || f.wife_person_id === p.id
  );
  
  // Find children from families
  const children = [];
  for (const family of parentFamilies) {
    const familyChildRels = familyChildren.filter(fc => fc.family_id === family.id);
    familyChildRels.forEach(fc => {
      const child = personMap.get(fc.child_person_id);
      if (child && !children.find(c => c.id === child.id)) {
        children.push(child);
      }
    });
  }
  
  // Also check direct parent relationships
  const childRels = relationships.filter(r => r.parent_person_id === p.id);
  childRels.forEach(rel => {
    const child = personMap.get(rel.child_person_id);
    if (child && !children.find(c => c.id === child.id)) {
      children.push(child);
    }
  });
  
  // Render tree
  if (parents.length > 0) {
    const div = document.createElement("div");
    div.className = "treeSection";
    div.innerHTML = `<div class="treeSectionTitle">Parents</div>`;
    parents.forEach(parent => {
      const item = document.createElement("div");
      item.className = "treeItem";
      item.innerHTML = `<div class="treeName">${escapeHtml(fullName(parent))}</div>`;
      item.onclick = () => loadDetails(parent.id);
      div.appendChild(item);
    });
    el.appendChild(div);
  }
  
  // Current person
  const selfDiv = document.createElement("div");
  selfDiv.className = "treeSection";
  selfDiv.innerHTML = `
    <div class="treeSectionTitle">Selected</div>
    <div class="treeItem current">
      <div class="treeName">${escapeHtml(fullName(p))}</div>
    </div>
  `;
  el.appendChild(selfDiv);
  
  if (children.length > 0) {
    const div = document.createElement("div");
    div.className = "treeSection";
    div.innerHTML = `<div class="treeSectionTitle">Children</div>`;
    children.forEach(child => {
      const item = document.createElement("div");
      item.className = "treeItem";
      item.innerHTML = `<div class="treeName">${escapeHtml(fullName(child))}</div>`;
      item.onclick = () => loadDetails(child.id);
      div.appendChild(item);
    });
    el.appendChild(div);
  }
  
  if (parents.length === 0 && children.length === 0) {
    el.innerHTML = `<div class="muted">No immediate family connections found.</div>`;
  }
}

async function loadDetails(id){
  const p = await window.dataAdapter.getPerson(id);
  if(!p) {
    alert("Person not found");
    return;
  }
  
  state.selected = p;
  $("details").innerHTML = detailsForm(p);
  
  // Load related data
  await renderNotes(p);
  await renderMedia(p);
  await renderMiniTree(p);
}

// Search handler
let searchTimeout;
$("search")?.addEventListener("input", (e) => {
  clearTimeout(searchTimeout);
  searchTimeout = setTimeout(() => {
    refreshPeople(e.target.value.trim());
  }, 300);
});

// Set active nav
window.setActiveNav = function() {
  const path = window.location.pathname;
  const links = document.querySelectorAll('.bottomNav a');
  links.forEach(link => {
    link.classList.remove('active');
    const route = link.getAttribute('data-route');
    if (
      (route === 'home' && (path === '/' || path === '/index.html')) ||
      (route === 'tree' && path.includes('tree')) ||
      (route === 'analytics' && path.includes('analytics'))
    ) {
      link.classList.add('active');
    }
  });
};

// Initialize on page load
(async function init() {
  try {
    await refreshPeople();
    console.log('✓ Loaded people data');
  } catch (error) {
    console.error('Error loading data:', error);
    $("peopleList").innerHTML = `<div class="muted error">Error loading data: ${error.message}</div>`;
  }
})();
