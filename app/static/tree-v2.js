/**
 * Tree Navigation v2
 * Graph-based tree view with SVG rendering (fallback for when CDN is blocked)
 */

let cy = null;  // Cytoscape instance (if available)
let currentPersonId = null;
let currentGraph = null;

function escapeHtml(s) {
  return (s ?? "").toString()
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function fullName(data) {
  const g = (data.given || "").trim();
  const s = (data.surname || "").trim();
  const name = `${g} ${s}`.trim();
  return name || "(unnamed)";
}

function formatDates(data) {
  const birth = (data.birth_date || "").trim();
  const death = (data.death_date || "").trim();
  if (birth || death) {
    return `${birth || "?"} – ${death || "?"}`;
  }
  return "";
}

async function loadGraph(personId, depth = 2) {
  currentPersonId = personId;
  
  const res = await fetch(`/api/graph?rootPersonId=${personId}&depth=${depth}`);
  if (!res.ok) {
    throw new Error(`Failed to load graph: ${res.status}`);
  }
  
  const graphData = await res.json();
  renderGraph(graphData);
}

function renderGraph(graphData) {
  currentGraph = graphData;
  const container = document.getElementById('treeV2Container');
  container.innerHTML = ''; // Clear previous content
  
  // Check if Cytoscape is available
  if (typeof cytoscape === 'undefined') {
    // Fallback to simple SVG visualization
    renderSimpleSVG(graphData, container);
    return;
  }
  
  // Build Cytoscape elements
  const elements = [];
  
  // Add nodes
  for (const node of graphData.nodes) {
    if (node.type === "person") {
      elements.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: fullName(node.data),
          personData: node.data,
          nodeType: 'person',
          quality: node.data.quality,
        }
      });
    } else if (node.type === "family") {
      elements.push({
        group: 'nodes',
        data: {
          id: node.id,
          label: '⚭',
          familyData: node.data,
          nodeType: 'family',
        }
      });
    }
  }
  
  // Add edges
  for (const edge of graphData.edges) {
    elements.push({
      group: 'edges',
      data: {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        edgeType: edge.type,
      }
    });
  }
  
  // Initialize Cytoscape
  try {
    cy = cytoscape({
    container: container,
    elements: elements,
    style: [
      {
        selector: 'node[nodeType="person"]',
        style: {
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': function(ele) {
            const quality = ele.data('quality');
            if (quality === 'high') return '#4a90e2';
            if (quality === 'medium') return '#7ab6f5';
            return '#b3d9ff';
          },
          'color': '#fff',
          'text-outline-color': '#333',
          'text-outline-width': 1,
          'width': 120,
          'height': 60,
          'shape': 'roundrectangle',
          'font-size': 12,
          'font-weight': 'bold',
          'text-wrap': 'wrap',
          'text-max-width': 110,
        }
      },
      {
        selector: 'node[nodeType="family"]',
        style: {
          'label': 'data(label)',
          'text-valign': 'center',
          'text-halign': 'center',
          'background-color': '#e8e8e8',
          'color': '#333',
          'width': 30,
          'height': 30,
          'shape': 'diamond',
          'font-size': 16,
        }
      },
      {
        selector: 'edge',
        style: {
          'width': 2,
          'line-color': '#999',
          'target-arrow-color': '#999',
          'target-arrow-shape': 'triangle',
          'curve-style': 'bezier',
        }
      },
      {
        selector: 'edge[edgeType="spouse"]',
        style: {
          'line-style': 'solid',
          'target-arrow-shape': 'none',
        }
      },
      {
        selector: 'edge[edgeType="child"]',
        style: {
          'line-style': 'solid',
        }
      },
      {
        selector: 'node:selected',
        style: {
          'border-width': 3,
          'border-color': '#f39c12',
        }
      }
    ],
    layout: {
      name: 'elk',
      elk: {
        algorithm: 'layered',
        'elk.direction': 'DOWN',
        'elk.spacing.nodeNode': 50,
        'elk.layered.spacing.nodeNodeBetweenLayers': 80,
      },
      fit: true,
      padding: 30,
    },
    minZoom: 0.3,
    maxZoom: 3,
  });
  } catch (err) {
    console.warn("Cytoscape render failed, falling back to SVG", err);
    cy = null;
    renderSimpleSVG(graphData, container);
    return;
  }
  
  // Handle node clicks
  cy.on('tap', 'node[nodeType="person"]', function(evt) {
    const node = evt.target;
    const personData = node.data('personData');
    showPersonPanel(personData);
  });
  
  // Handle pan and zoom
  cy.userZoomingEnabled(true);
  cy.userPanningEnabled(true);
}

function renderSimpleSVG(graphData, container) {
  // Simple fallback SVG rendering
  const width = container.clientWidth || 800;
  const height = container.clientHeight || 600;
  
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('width', width);
  svg.setAttribute('height', height);
  svg.style.background = '#050810';
  
  // Group nodes by type
  const personNodes = graphData.nodes.filter(n => n.type === 'person');
  const familyNodes = graphData.nodes.filter(n => n.type === 'family');
  
  // Simple layout: arrange persons in columns by generation
  const nodePositions = new Map();
  const nodeSize = { person: { w: 120, h: 60 }, family: { w: 30, h: 30 } };
  
  // Layout persons in a grid
  const cols = Math.ceil(Math.sqrt(personNodes.length));
  const xSpacing = Math.min(150, (width - 40) / cols);
  const ySpacing = 100;
  
  personNodes.forEach((node, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    const x = 20 + col * xSpacing + xSpacing / 2;
    const y = 50 + row * ySpacing;
    nodePositions.set(node.id, { x, y, node });
  });
  
  // Prepare defs (markers) for arrowheads and the edges group
  const defs = document.createElementNS('http://www.w3.org/2000/svg', 'defs');
  const marker = document.createElementNS('http://www.w3.org/2000/svg', 'marker');
  marker.setAttribute('id', 'treeV2Arrow');
  marker.setAttribute('markerWidth', '6');
  marker.setAttribute('markerHeight', '6');
  marker.setAttribute('refX', '5');
  marker.setAttribute('refY', '3');
  marker.setAttribute('orient', 'auto');
  marker.setAttribute('markerUnits', 'strokeWidth');
  const markerPath = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  markerPath.setAttribute('d', 'M0,0 L6,3 L0,6 Z');
  markerPath.setAttribute('fill', '#8cc0ff');
  marker.appendChild(markerPath);
  defs.appendChild(marker);
  svg.appendChild(defs);

  const edgesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  const getPersonPos = (personId) => personId ? nodePositions.get(`person_${personId}`) : null;
  const drawLine = (fromPos, toPos, opts = {}) => {
    if (!fromPos || !toPos) return;
    const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
    line.setAttribute('x1', fromPos.x);
    line.setAttribute('y1', fromPos.y);
    line.setAttribute('x2', toPos.x);
    line.setAttribute('y2', toPos.y);
    line.setAttribute('stroke', opts.color || '#666');
    line.setAttribute('stroke-width', '2');
    line.setAttribute('stroke-linecap', 'round');
    if (opts.dash) {
      line.setAttribute('stroke-dasharray', '6 4');
    }
    if (opts.arrow) {
      line.setAttribute('marker-end', 'url(#treeV2Arrow)');
    }
    edgesGroup.appendChild(line);
  };

  familyNodes.forEach(family => {
    const husbandPos = getPersonPos(family.data.husband_id);
    const wifePos = getPersonPos(family.data.wife_id);
    if (husbandPos && wifePos) {
      drawLine(husbandPos, wifePos, { color: '#f1c40f', dash: true });
    }
    const children = family.data.children || [];
    for (const childId of children) {
      const childPos = getPersonPos(childId);
      if (husbandPos) {
        drawLine(husbandPos, childPos, { color: '#7ad0d7', arrow: true });
      }
      if (wifePos) {
        drawLine(wifePos, childPos, { color: '#7ad0d7', arrow: true });
      }
    }
  });

  svg.appendChild(edgesGroup);
  
  // Draw person nodes
  const nodesGroup = document.createElementNS('http://www.w3.org/2000/svg', 'g');
  personNodes.forEach(node => {
    const pos = nodePositions.get(node.id);
    if (!pos) return;
    
    const group = document.createElementNS('http://www.w3.org/2000/svg', 'g');
    group.setAttribute('cursor', 'pointer');
    group.onclick = () => showPersonPanel(node.data);
    
    // Draw rectangle
    const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
    rect.setAttribute('x', pos.x - nodeSize.person.w / 2);
    rect.setAttribute('y', pos.y - nodeSize.person.h / 2);
    rect.setAttribute('width', nodeSize.person.w);
    rect.setAttribute('height', nodeSize.person.h);
    rect.setAttribute('rx', '8');
    
    // Color based on quality
    let color = '#b3d9ff'; // low quality
    if (node.data.quality === 'high') color = '#4a90e2';
    else if (node.data.quality === 'medium') color = '#7ab6f5';
    
    rect.setAttribute('fill', color);
    rect.setAttribute('stroke', '#2c3e50');
    rect.setAttribute('stroke-width', '2');
    group.appendChild(rect);
    
    // Draw text
    const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
    text.setAttribute('x', pos.x);
    text.setAttribute('y', pos.y);
    text.setAttribute('text-anchor', 'middle');
    text.setAttribute('dominant-baseline', 'middle');
    text.setAttribute('fill', '#fff');
    text.setAttribute('font-size', '12');
    text.setAttribute('font-weight', 'bold');
    
    const name = fullName(node.data);
    const shortName = name.length > 18 ? name.substring(0, 16) + '...' : name;
    text.textContent = shortName;
    group.appendChild(text);
    
    nodesGroup.appendChild(group);
  });
  svg.appendChild(nodesGroup);
  
  // Add zoom and pan functionality
  let scale = 1;
  let translateX = 0;
  let translateY = 0;
  let isDragging = false;
  let startX, startY;
  
  svg.addEventListener('wheel', (e) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? 0.9 : 1.1;
    scale *= delta;
    scale = Math.max(0.3, Math.min(3, scale));
    nodesGroup.setAttribute('transform', `translate(${translateX}, ${translateY}) scale(${scale})`);
    edgesGroup.setAttribute('transform', `translate(${translateX}, ${translateY}) scale(${scale})`);
  });
  
  svg.addEventListener('mousedown', (e) => {
    if (e.target === svg || e.target.tagName === 'line') {
      isDragging = true;
      startX = e.clientX - translateX;
      startY = e.clientY - translateY;
      svg.style.cursor = 'grabbing';
    }
  });
  
  svg.addEventListener('mousemove', (e) => {
    if (isDragging) {
      translateX = e.clientX - startX;
      translateY = e.clientY - startY;
      nodesGroup.setAttribute('transform', `translate(${translateX}, ${translateY}) scale(${scale})`);
      edgesGroup.setAttribute('transform', `translate(${translateX}, ${translateY}) scale(${scale})`);
    }
  });
  
  svg.addEventListener('mouseup', () => {
    isDragging = false;
    svg.style.cursor = 'default';
  });
  
  svg.addEventListener('mouseleave', () => {
    isDragging = false;
    svg.style.cursor = 'default';
  });
  
  container.appendChild(svg);
}

function escapeCsv(value) {
  if (value == null) return '';
  const str = value.toString();
  if (str.includes('"') || str.includes(',') || str.includes('\n')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return str;
}

function exportTreeData() {
  if (!currentGraph) {
    alert('Load a tree before exporting.');
    return;
  }
  const peopleNodes = currentGraph.nodes.filter(node => node.type === 'person');
  if (!peopleNodes.length) {
    alert('No person data found in the current view.');
    return;
  }

  const header = ['Given', 'Surname', 'Sex', 'Birth Date', 'Birth Place', 'Death Date', 'Death Place', 'Quality', 'XREF'];
  const rows = [
    header.join(','),
    ...peopleNodes.map(node => {
      const data = node.data;
      return [
        escapeCsv(data.given),
        escapeCsv(data.surname),
        escapeCsv(data.sex),
        escapeCsv(data.birth_date),
        escapeCsv(data.birth_place),
        escapeCsv(data.death_date),
        escapeCsv(data.death_place),
        escapeCsv(data.quality),
        escapeCsv(data.xref),
      ].join(',');
    })
  ];

  const csvContent = rows.join('\r\n');
  const blob = new Blob([csvContent], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `family-tree-${currentPersonId || 'graph'}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function printTreeView() {
  const container = document.getElementById('treeV2Container');
  if (!container) return;
  const win = window.open('', '_blank');
  if (!win) return;
  const styles = `
    <style>
      body { margin: 0; background: #050810; color: #fff; font-family: ui-sans-serif, system-ui, sans-serif; }
      .tree-print { width: 100%; min-height: 100vh; padding: 20px; box-sizing: border-box; background: #050810; }
    </style>
  `;
  win.document.write(`<!doctype html><html><head><title>Family Tree</title>${styles}</head><body><div class="tree-print">${container.innerHTML}</div></body></html>`);
  win.document.close();
  win.focus();
  win.print();
}

function showPersonPanel(personData) {
  const panel = document.getElementById('treeV2Panel');
  panel.classList.remove('hidden');
  
  const name = fullName(personData);
  const dates = formatDates(personData);
  
  let html = `
    <div class="panelHeader">
      <h3>${escapeHtml(name)}</h3>
      <button id="closePanel" class="btn btnSecondary">×</button>
    </div>
    <div class="panelContent">
      <div class="formRow"><label>ID:</label><span>${personData.id}</span></div>
      ${personData.xref ? `<div class="formRow"><label>XREF:</label><span>${escapeHtml(personData.xref)}</span></div>` : ''}
      <div class="formRow"><label>Sex:</label><span>${escapeHtml(personData.sex || '—')}</span></div>
      ${dates ? `<div class="formRow"><label>Dates:</label><span>${escapeHtml(dates)}</span></div>` : ''}
      ${personData.birth_place ? `<div class="formRow"><label>Birth Place:</label><span>${escapeHtml(personData.birth_place)}</span></div>` : ''}
      ${personData.death_place ? `<div class="formRow"><label>Death Place:</label><span>${escapeHtml(personData.death_place)}</span></div>` : ''}
      <div class="formRow">
        <button id="viewDetails" class="btn" data-person-id="${personData.id}">View Full Details</button>
        <button id="reCenter" class="btn btnSecondary" data-person-id="${personData.id}">Re-center on This Person</button>
      </div>
    </div>
  `;
  
  panel.innerHTML = html;
  
  document.getElementById('closePanel').onclick = () => {
    panel.classList.add('hidden');
  };
  
  document.getElementById('viewDetails').onclick = () => {
    // Switch back to regular view and load details
    window.location.href = `/?personId=${personData.id}`;
  };
  
  document.getElementById('reCenter').onclick = async () => {
    const depth = parseInt(document.getElementById('depthSelect')?.value || 2);
    await loadGraph(personData.id, depth);
    panel.classList.add('hidden');
  };
}

// Initialize on page load if tree=v2 query param is present
// Export to global scope for other modules to use
window.TreeV2 = {
  loadGraph: loadGraph,
  exportTreeData: exportTreeData,
  printTreeView: printTreeView,
};
