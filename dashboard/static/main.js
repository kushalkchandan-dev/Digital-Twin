/* ══════════════════════════════════════════════════════════════════════════
   Self-Healing Network Dashboard — Frontend Logic
   Handles: SocketIO, Chart.js charts, D3 topology, UI updates
══════════════════════════════════════════════════════════════════════════ */

'use strict';

// ────────────────────────────────────────────────────────────────────────────
// Constants
// ────────────────────────────────────────────────────────────────────────────
const MAX_DATA_POINTS = 60;
const CLASS_COLORS = {
  Normal:      '#00f5c4',
  Congestion:  '#ffd166',
  LinkFailure: '#ff4f6a',
  NodeDown:    '#b06aff',
};
const NODE_COLORS = {
  core:   '#4f9dff',
  edge:   '#00f5c4',
  access: '#ffd166',
};

// ────────────────────────────────────────────────────────────────────────────
// State
// ────────────────────────────────────────────────────────────────────────────
const state = {
  labels: [],
  latency: [],
  throughput: [],
  cpu: [],
  pktloss: [],
  faultCount: 0,
  healCount: 0,
  nodes: {},
  topology: { nodes: [], links: [] },
  aiPredictions: {},
};

// ────────────────────────────────────────────────────────────────────────────
// Chart.js Setup
// ────────────────────────────────────────────────────────────────────────────
const chartDefaults = {
  responsive: true,
  maintainAspectRatio: false,
  animation: { duration: 200 },
  interaction: { intersect: false },
  plugins: {
    legend: { display: false },
    tooltip: {
      backgroundColor: 'rgba(8,12,20,0.92)',
      titleColor: '#00f5c4',
      bodyColor: '#6a7fa8',
      borderColor: 'rgba(0,245,196,0.2)',
      borderWidth: 1,
    }
  },
  scales: {
    x: {
      grid: { color: 'rgba(255,255,255,0.04)', display: true },
      ticks: { color: '#6a7fa8', font: { family: 'JetBrains Mono', size: 9 }, maxTicksLimit: 8 },
    },
    y: {
      grid: { color: 'rgba(255,255,255,0.04)' },
      ticks: { color: '#6a7fa8', font: { family: 'JetBrains Mono', size: 9 } },
    }
  }
};

function makeDataset(color, label) {
  return {
    label,
    data: [],
    borderColor: color,
    backgroundColor: color + '18',
    fill: true,
    tension: 0.4,
    borderWidth: 2,
    pointRadius: 0,
    pointHoverRadius: 4,
  };
}

const charts = {
  latency:    new Chart(document.getElementById('chart-latency'),    { type: 'line', data: { labels: [], datasets: [makeDataset('#00f5c4', 'Latency ms')] },    options: { ...chartDefaults, scales: { ...chartDefaults.scales, y: { ...chartDefaults.scales.y, title: { display: true, text: 'ms', color: '#6a7fa8' } } } } }),
  throughput: new Chart(document.getElementById('chart-throughput'), { type: 'line', data: { labels: [], datasets: [makeDataset('#4f9dff', 'Throughput Mbps')] }, options: { ...chartDefaults } }),
  cpu:        new Chart(document.getElementById('chart-cpu'),        { type: 'line', data: { labels: [], datasets: [makeDataset('#ffd166', 'CPU %')] },           options: { ...chartDefaults, scales: { ...chartDefaults.scales, y: { ...chartDefaults.scales.y, min: 0, max: 100 } } } }),
  pktloss:    new Chart(document.getElementById('chart-pktloss'),    { type: 'line', data: { labels: [], datasets: [makeDataset('#ff4f6a', 'Pkt Loss %')] },      options: { ...chartDefaults } }),
};

function pushData(key, value) {
  const ts = new Date().toLocaleTimeString('en', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  state.labels.push(ts);
  state[key].push(value);
  if (state.labels.length > MAX_DATA_POINTS) {
    state.labels.shift();
    state[key].shift();
  }
}

function updateChart(name, key) {
  const ch = charts[name];
  ch.data.labels = [...state.labels];
  ch.data.datasets[0].data = [...state[key]];
  ch.update('none');
}

// ────────────────────────────────────────────────────────────────────────────
// Tab Switching
// ────────────────────────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.chart-tab').forEach(t => t.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById(btn.dataset.tab).classList.add('active');
    // Resize charts after tab switch
    setTimeout(() => Object.values(charts).forEach(c => c.resize()), 50);
  });
});

// ────────────────────────────────────────────────────────────────────────────
// D3 Network Topology
// ────────────────────────────────────────────────────────────────────────────
const topoContainer = document.getElementById('topology-svg-container');
const topoW = topoContainer.clientWidth || 500;
const topoH = 320;

const svg = d3.select('#topology-svg-container')
  .append('svg')
  .attr('viewBox', `0 0 ${topoW} ${topoH}`)
  .attr('preserveAspectRatio', 'xMidYMid meet');

// Arrow marker for directed links
svg.append('defs').append('marker')
  .attr('id', 'arrow')
  .attr('viewBox', '0 -4 8 8')
  .attr('refX', 20).attr('refY', 0)
  .attr('markerWidth', 5).attr('markerHeight', 5)
  .attr('orient', 'auto')
  .append('path')
  .attr('d', 'M0,-4L8,0L0,4')
  .attr('fill', 'rgba(0,245,196,0.4)');

const simulation = d3.forceSimulation()
  .force('link', d3.forceLink().id(d => d.id).distance(80).strength(0.6))
  .force('charge', d3.forceManyBody().strength(-220))
  .force('center', d3.forceCenter(topoW / 2, topoH / 2))
  .force('collision', d3.forceCollide(30));

let linkSel = svg.append('g').attr('class', 'links').selectAll('line');
let nodeSel = svg.append('g').attr('class', 'nodes').selectAll('g');

function initTopology(topoData) {
  const nodes = topoData.nodes.map(n => ({ ...n }));
  const nodeMap = new Map(nodes.map(n => [n.id, n]));

  // Deduplicate links (keep one direction for display)
  const seen = new Set();
  const links = [];
  for (const l of topoData.links) {
    const key = [Math.min(l.source, l.target), Math.max(l.source, l.target)].join('-');
    if (!seen.has(key)) { seen.add(key); links.push({ ...l }); }
  }

  // Links
  linkSel = svg.select('.links').selectAll('line').data(links, d => `${d.source}-${d.target}`);
  linkSel.exit().remove();
  const linkEnter = linkSel.enter().append('line')
    .attr('class', 'topo-link')
    .attr('marker-end', 'url(#arrow)');
  linkSel = linkEnter.merge(linkSel);

  // Nodes
  nodeSel = svg.select('.nodes').selectAll('g').data(nodes, d => d.id);
  nodeSel.exit().remove();
  const nodeEnter = nodeSel.enter().append('g')
    .attr('class', d => `topo-node ${d.status === 'down' ? 'down' : ''}`)
    .call(d3.drag()
      .on('start', (event, d) => { if (!event.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
      .on('end', (event, d) => { if (!event.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  nodeEnter.append('circle')
    .attr('r', d => d.type === 'core' ? 18 : d.type === 'edge' ? 14 : 10)
    .attr('fill', d => NODE_COLORS[d.type] + '33')
    .attr('stroke', d => NODE_COLORS[d.type]);

  nodeEnter.append('text')
    .attr('dy', d => d.type === 'core' ? 30 : d.type === 'edge' ? 25 : 20)
    .text(d => d.label.split('-')[0] + '\n' + d.label.split('-')[1]);

  nodeSel = nodeEnter.merge(nodeSel);

  simulation.nodes(nodes).on('tick', () => {
    linkSel
      .attr('x1', d => typeof d.source === 'object' ? d.source.x : nodeMap.get(d.source)?.x)
      .attr('y1', d => typeof d.source === 'object' ? d.source.y : nodeMap.get(d.source)?.y)
      .attr('x2', d => typeof d.target === 'object' ? d.target.x : nodeMap.get(d.target)?.x)
      .attr('y2', d => typeof d.target === 'object' ? d.target.y : nodeMap.get(d.target)?.y);
    nodeSel.attr('transform', d => `translate(${d.x},${d.y})`);
  });

  simulation.force('link').links(links);
  simulation.alpha(0.8).restart();
}

function updateTopologyColors(topoData) {
  if (!topoData) return;

  // Update link colors
  svg.select('.links').selectAll('line').each(function(d) {
    const src = typeof d.source === 'object' ? d.source.id : d.source;
    const tgt = typeof d.target === 'object' ? d.target.id : d.target;
    const link = topoData.links.find(l =>
      (l.source === src && l.target === tgt) || (l.source === tgt && l.target === src)
    );
    if (link) {
      const el = d3.select(this);
      if (link.status === 'down') el.attr('class', 'topo-link failed');
      else if (link.utilization > 0.75) el.attr('class', 'topo-link congested');
      else el.attr('class', 'topo-link');
    }
  });

  // Update node colors
  svg.select('.nodes').selectAll('g').each(function(d) {
    const node = topoData.nodes.find(n => n.id === d.id);
    if (!node) return;
    const el = d3.select(this);
    el.classed('down', node.status === 'down');
    const cpuColor = node.cpu > 80 ? '#ff4f6a' : node.cpu > 60 ? '#ffd166' : NODE_COLORS[node.type];
    el.select('circle')
      .attr('fill', cpuColor + '33')
      .attr('stroke', node.status === 'down' ? '#ff4f6a' : cpuColor);
  });
}

// ────────────────────────────────────────────────────────────────────────────
// KPI Cards
// ────────────────────────────────────────────────────────────────────────────
function updateKPIs(kpis) {
  setKPI('kv-availability', kpis.network_availability_pct + '%', kpis.network_availability_pct < 90 ? 'alert' : 'good');
  setKPI('kv-latency',      kpis.avg_latency_ms + ' ms',         kpis.avg_latency_ms > 50       ? 'warn'  : 'good');
  setKPI('kv-throughput',   kpis.total_throughput_mbps + '',     'good');
  setKPI('kv-cpu',          kpis.avg_cpu_usage + '%',            kpis.avg_cpu_usage > 75        ? 'warn'  : 'good');
  setKPI('kv-faults',       kpis.total_faults_detected + '',     kpis.total_faults_detected > 0  ? 'alert' : 'good');
  setKPI('kv-healed',       kpis.total_healed + '',              'good');
  setKPI('kv-energy',       kpis.total_energy_watts + ' W',      'good');
  setKPI('kv-pktloss',      kpis.avg_packet_loss_pct + '%',      kpis.avg_packet_loss_pct > 5   ? 'warn'  : 'good');
}

function setKPI(id, value, state) {
  const el = document.getElementById(id);
  if (el) {
    el.textContent = value;
    const card = el.closest('.kpi-card');
    if (card) {
      card.classList.remove('kpi-alert', 'kpi-warn', 'kpi-good');
      card.classList.add('kpi-' + state);
    }
  }
}

// ────────────────────────────────────────────────────────────────────────────
// Node Table
// ────────────────────────────────────────────────────────────────────────────
function updateNodeTable(nodes, aiPredictions) {
  const tbody = document.getElementById('node-table-body');
  if (!nodes || Object.keys(nodes).length === 0) return;

  const rows = Object.entries(nodes).map(([idStr, n]) => {
    const pred = aiPredictions[idStr] || { class: 'Normal', confidence: 1.0 };
    const statusClass = n.status === 'up' ? 'status-up' : 'status-down';
    const cls = pred.class || 'Normal';
    const conf = ((pred.confidence || 0) * 100).toFixed(0) + '%';
    const confColor = pred.is_fault ? 'color:var(--accent-red)' : '';

    return `<tr>
      <td>${n.label}</td>
      <td>${n.type}</td>
      <td class="${statusClass}">${n.status.toUpperCase()}</td>
      <td>${n.status === 'up' ? n.cpu_usage + '%' : '—'}</td>
      <td>${n.status === 'up' ? n.memory_usage + '%' : '—'}</td>
      <td>${n.status === 'up' ? n.throughput + ' Mbps' : '—'}</td>
      <td>${n.status === 'up' ? n.packet_loss + '%' : '—'}</td>
      <td><span class="class-badge class-${cls}">${cls}</span></td>
      <td style="${confColor}">${conf}</td>
    </tr>`;
  }).join('');

  tbody.innerHTML = rows;
}

// ────────────────────────────────────────────────────────────────────────────
// Heatmap
// ────────────────────────────────────────────────────────────────────────────
function updateHeatmap(nodes) {
  const container = document.getElementById('heatmap-container');
  if (!nodes || Object.keys(nodes).length === 0) return;

  const cells = Object.entries(nodes).map(([, n]) => {
    if (n.status === 'down') {
      return `<div class="heatmap-cell" style="background:rgba(255,79,106,0.15);border:1px solid rgba(255,79,106,0.3)">
        <div class="hm-label">${n.label}</div>
        <div class="hm-value" style="color:#ff4f6a">DOWN</div>
      </div>`;
    }
    const cpu = n.cpu_usage || 0;
    const hue = 120 - (cpu / 100) * 120;   // green → red
    const bg  = `hsla(${hue},70%,50%,0.15)`;
    const bdr = `hsla(${hue},70%,50%,0.35)`;
    const txt = `hsla(${hue},90%,65%,1)`;
    return `<div class="heatmap-cell" style="background:${bg};border:1px solid ${bdr}">
      <div class="hm-label" style="color:${txt}">${n.label}</div>
      <div class="hm-value" style="color:${txt}">${cpu}%</div>
    </div>`;
  }).join('');

  container.innerHTML = cells;
}

// ────────────────────────────────────────────────────────────────────────────
// Feed: Fault & Healing Logs
// ────────────────────────────────────────────────────────────────────────────
let faultCount = 0;
let healCount  = 0;

function addFaultItem(fault) {
  faultCount++;
  document.getElementById('fault-count-badge').textContent = faultCount;
  const feed = document.getElementById('fault-feed');

  // Remove empty placeholder
  const empty = feed.querySelector('.feed-empty');
  if (empty) empty.remove();

  const item = document.createElement('div');
  item.className = `feed-item sev-${fault.severity || 'critical'}`;
  item.innerHTML = `
    <div class="feed-item-header">
      <span class="feed-item-type">${(fault.type || '').replace(/_/g, ' ')}</span>
      <span class="feed-item-time">${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="feed-item-target">${fault.target || ''}</div>
    <div class="feed-item-desc">${fault.detail || fault.description || ''}</div>
  `;
  feed.prepend(item);

  // Toast
  showToast('fault', `⚠ ${(fault.type || '').replace(/_/g, ' ')}`, fault.target);
}

function addHealItem(action) {
  healCount++;
  document.getElementById('heal-count-badge').textContent = healCount;
  const feed = document.getElementById('heal-feed');

  const empty = feed.querySelector('.feed-empty');
  if (empty) empty.remove();

  const item = document.createElement('div');
  item.className = 'feed-item sev-heal';
  item.innerHTML = `
    <div class="feed-item-header">
      <span class="feed-item-type">${(action.action || action.type || '').replace(/_/g, ' ')}</span>
      <span class="feed-item-time">${new Date().toLocaleTimeString()}</span>
    </div>
    <div class="feed-item-target">${action.fault_target || action.target || ''}</div>
    <div class="feed-item-desc">${action.detail || action.description || ''}</div>
  `;
  feed.prepend(item);

  // Toast
  showToast('heal', `✅ ${(action.action || '').replace(/_/g, ' ')}`, action.fault_target || '');
}

// ────────────────────────────────────────────────────────────────────────────
// Toast Notifications
// ────────────────────────────────────────────────────────────────────────────
function showToast(type, title, body) {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<div class="toast-title">${title}</div><div class="toast-body">${body}</div>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// ────────────────────────────────────────────────────────────────────────────
// Socket.IO
// ────────────────────────────────────────────────────────────────────────────
const socket = io();
let topoInitialized = false;

socket.on('connect', () => {
  const pill = document.getElementById('status-pill');
  const dot  = pill.querySelector('.status-dot');
  document.getElementById('status-text').textContent = 'Live';
  dot.classList.add('live');
});

socket.on('disconnect', () => {
  document.getElementById('status-text').textContent = 'Disconnected';
  document.querySelector('.status-dot').classList.remove('live');
});

socket.on('system_info', (data) => {
  const badge = document.getElementById('model-badge');
  badge.textContent = data.model_ready ? '🤖 AI Model: Ready' : '⏳ AI Model: Training needed';
  showToast('info', '🔗 Connected', `Network: ${data.nodes} nodes, ${data.links} links`);
});

socket.on('network_state', (data) => {
  // Update tick
  document.getElementById('tick-val').textContent = data.tick || 0;

  // KPIs
  if (data.kpis) updateKPIs(data.kpis);

  // Charts
  if (data.kpis) {
    pushData('latency',    data.kpis.avg_latency_ms);
    pushData('throughput', data.kpis.total_throughput_mbps);
    pushData('cpu',        data.kpis.avg_cpu_usage);
    pushData('pktloss',    data.kpis.avg_packet_loss_pct);
    updateChart('latency',    'latency');
    updateChart('throughput', 'throughput');
    updateChart('cpu',        'cpu');
    updateChart('pktloss',    'pktloss');
  }

  // Topology
  if (data.topology) {
    if (!topoInitialized && data.topology.nodes.length > 0) {
      initTopology(data.topology);
      topoInitialized = true;
    } else {
      updateTopologyColors(data.topology);
    }
  }

  // Node table & heatmap
  if (data.nodes) {
    updateNodeTable(data.nodes, data.ai_predictions || {});
    updateHeatmap(data.nodes);
  }
});

socket.on('fault_detected', (data) => {
  if (data.fault) addFaultItem(data.fault);
});

socket.on('healing_action', (data) => {
  addHealItem(data);
});
