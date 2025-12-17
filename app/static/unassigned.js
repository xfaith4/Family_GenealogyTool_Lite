const $ = (id) => document.getElementById(id);

function escapeHtml(s){
  return (s ?? "").toString()
    .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
    .replaceAll('"',"&quot;").replaceAll("'","&#039;");
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

function formatBytes(bytes){
  if(bytes < 1024) return bytes + ' B';
  if(bytes < 1024*1024) return (bytes/1024).toFixed(1) + ' KB';
  return (bytes/(1024*1024)).toFixed(1) + ' MB';
}

async function loadUnassigned(){
  const media = await api('/api/media/unassigned');
  const analytics = await api('/api/analytics/orphaned-media');
  
  $('stats').textContent = `${analytics.orphaned_count} unassigned asset${analytics.orphaned_count === 1 ? '' : 's'}`;
  
  const grid = $('mediaGrid');
  grid.innerHTML = '';
  
  if(media.length === 0){
    grid.innerHTML = '<div class="muted" style="text-align:center;padding:40px;">No unassigned media. Upload some files!</div>';
    return;
  }
  
  const container = document.createElement('div');
  container.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(250px,1fr));gap:16px;';
  
  for(const m of media){
    const card = document.createElement('div');
    card.className = 'mediaCard';
    card.style.cssText = 'border:1px solid var(--line);border-radius:12px;padding:12px;background:rgba(0,0,0,0.12);';
    
    const isImage = m.mime_type && m.mime_type.startsWith('image/');
    const thumbUrl = m.thumbnail_path 
      ? `/api/media/thumbnail/${encodeURIComponent(m.thumbnail_path)}`
      : `/api/media/${encodeURIComponent(m.path)}`;
    
    card.innerHTML = `
      <div style="width:100%;height:150px;background:rgba(0,0,0,0.2);border-radius:8px;overflow:hidden;display:flex;align-items:center;justify-content:center;margin-bottom:10px;">
        ${isImage && m.thumbnail_path 
          ? `<img src="${thumbUrl}" alt="${escapeHtml(m.original_filename)}" style="max-width:100%;max-height:100%;object-fit:contain;" />` 
          : `<div style="font-size:48px;opacity:0.5;">📄</div>`}
      </div>
      <div style="font-size:13px;margin-bottom:4px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="${escapeHtml(m.original_filename)}">
        ${escapeHtml(m.original_filename)}
      </div>
      <div class="muted" style="font-size:11px;margin-bottom:10px;">
        ${escapeHtml(m.mime_type || 'unknown')} • ${formatBytes(m.size_bytes)}
      </div>
      <div style="display:flex;gap:8px;">
        <button class="btnSmall" style="flex:1;background:var(--btn);color:white;" data-asset-id="${m.id}">Attach to Person</button>
      </div>
    `;
    
    const attachBtn = card.querySelector('[data-asset-id]');
    attachBtn.onclick = () => attachToPerson(m.id, m.original_filename);
    
    container.appendChild(card);
  }
  
  grid.appendChild(container);
}

async function attachToPerson(assetId, filename){
  const personName = prompt(`Enter person ID or search name to attach "${filename}":`);
  if(!personName) return;
  
  let personId;
  
  // If it's a number, use it as person ID
  if(/^\d+$/.test(personName)){
    personId = parseInt(personName);
  } else {
    // Search for person by name
    const people = await api(`/api/people?q=${encodeURIComponent(personName)}`);
    if(people.length === 0){
      alert('No person found with that name.');
      return;
    }
    if(people.length > 1){
      alert(`Multiple people found. Please use person ID instead. Options:\n${people.map(p => `ID ${p.id}: ${p.given} ${p.surname}`).join('\n')}`);
      return;
    }
    personId = people[0].id;
  }
  
  try {
    await api('/api/media/link', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_id: assetId, person_id: personId })
    });
    alert('Media attached successfully!');
    await loadUnassigned();
  } catch(err){
    alert(`Error: ${err.message}`);
  }
}

async function uploadFiles(){
  const input = $('uploadFile');
  if(!input.files || input.files.length === 0) return;
  
  let uploaded = 0;
  for(const file of input.files){
    const fd = new FormData();
    fd.append('file', file);
    try {
      await api('/api/media/upload', { method: 'POST', body: fd });
      uploaded++;
    } catch(err){
      console.error(`Failed to upload ${file.name}:`, err);
    }
  }
  
  input.value = '';
  alert(`Uploaded ${uploaded} file(s)`);
  await loadUnassigned();
}

function wire(){
  $('uploadFile').addEventListener('change', uploadFiles);
}

(async function init(){
  wire();
  await loadUnassigned();
})();
