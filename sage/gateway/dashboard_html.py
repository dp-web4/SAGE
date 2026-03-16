"""
SAGE Dashboard HTML — single-file web interface served by the gateway.

Provides live stats (metabolic state, ATP, GPU, cycles) and a chat interface.
Connects via SSE to /stream for real-time updates.
Chat history is persisted server-side and loaded on page open.
"""

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SAGE Dashboard</title>
<link rel="icon" href="data:image/png;base64,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">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }

  :root {
    --bg: #0a0a0a;
    --surface: #111;
    --border: #222;
    --text: #c8c8c8;
    --text-dim: #666;
    --accent: #00ff41;
    --state-wake: #00ff41;
    --state-focus: #ffd700;
    --state-rest: #4488ff;
    --state-dream: #cc44ff;
    --state-crisis: #ff3333;
    --state-lightweight: #4488ff;
    --state-color: var(--state-wake);
  }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'JetBrains Mono', 'Fira Code', 'Courier New', monospace;
    font-size: 13px;
    line-height: 1.5;
    min-height: 100vh;
  }

  header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 8px 16px;
    border-bottom: 1px solid var(--border);
    background: var(--surface);
  }

  header h1 {
    font-size: 14px;
    font-weight: 600;
    color: var(--accent);
  }

  header .meta {
    display: flex;
    gap: 16px;
    align-items: center;
    font-size: 11px;
    color: var(--text-dim);
  }

  /* Notification bell + panel */
  .notif-bell {
    position: relative;
    cursor: pointer;
    font-size: 16px;
    user-select: none;
    padding: 2px 6px;
    border-radius: 4px;
    transition: background 0.2s;
  }
  .notif-bell:hover { background: rgba(255,255,255,0.08); }
  .notif-badge {
    position: absolute;
    top: -4px;
    right: -6px;
    background: #ff3333;
    color: #fff;
    font-size: 9px;
    font-weight: 700;
    min-width: 16px;
    height: 16px;
    line-height: 16px;
    text-align: center;
    border-radius: 8px;
    padding: 0 4px;
    display: none;
  }
  .notif-badge.visible { display: block; }

  .notif-panel {
    display: none;
    position: fixed;
    top: 37px;
    right: 16px;
    width: 380px;
    max-height: 420px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 8px 32px rgba(0,0,0,0.5);
    z-index: 1000;
    overflow: hidden;
    flex-direction: column;
  }
  .notif-panel.open { display: flex; }
  .notif-panel-header {
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--accent);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .notif-panel-body {
    overflow-y: auto;
    flex: 1;
    padding: 6px 0;
  }
  .notif-item {
    padding: 8px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.04);
    font-size: 12px;
    display: flex;
    gap: 8px;
    align-items: flex-start;
  }
  .notif-item:last-child { border-bottom: none; }
  .notif-item .notif-content { flex: 1; min-width: 0; }
  .notif-item .notif-source {
    font-size: 9px;
    color: var(--text-dim);
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }
  .notif-item .notif-snippet {
    margin-top: 2px;
    color: var(--text);
    word-break: break-word;
  }
  .notif-item .notif-time {
    font-size: 9px;
    color: var(--text-dim);
    white-space: nowrap;
  }
  .notif-ack-btn {
    background: none;
    border: 1px solid var(--border);
    color: var(--text-dim);
    font-size: 9px;
    padding: 2px 8px;
    border-radius: 4px;
    cursor: pointer;
    font-family: inherit;
    flex-shrink: 0;
    align-self: center;
  }
  .notif-ack-btn:hover { border-color: var(--accent); color: var(--accent); }
  .notif-empty {
    padding: 24px;
    text-align: center;
    color: var(--text-dim);
    font-size: 12px;
  }

  .connection-dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    background: #ff3333;
    display: inline-block;
    transition: background 0.3s;
  }
  .connection-dot.connected { background: var(--accent); }

  .grid {
    display: grid;
    grid-template-columns: 220px 1fr;
    height: calc(100vh - 37px);
  }

  /* Left Panel — Avatar + Identity + Stats */
  .sidebar {
    padding: 12px;
    border-right: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 8px;
    overflow-y: auto;
    background: var(--surface);
  }

  .avatar-wrap {
    position: relative;
    width: 120px;
    height: 120px;
    border-radius: 10px;
    overflow: hidden;
    flex-shrink: 0;
  }

  .avatar-wrap img {
    width: 100%;
    height: 100%;
    object-fit: cover;
    border-radius: 10px;
  }

  .avatar-wrap::after {
    content: '';
    position: absolute;
    inset: -3px;
    border-radius: 13px;
    border: 2px solid var(--state-color);
    box-shadow: 0 0 16px color-mix(in srgb, var(--state-color) 40%, transparent);
    animation: glow 2s ease-in-out infinite;
    pointer-events: none;
  }

  @keyframes glow {
    0%, 100% { opacity: 0.6; }
    50% { opacity: 1; }
  }

  .machine-name {
    font-size: 16px;
    font-weight: 700;
    color: white;
    text-transform: uppercase;
    letter-spacing: 2px;
  }

  .lct-id {
    font-size: 9px;
    color: var(--text-dim);
    word-break: break-all;
    text-align: center;
  }

  .metabolic-badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 1px;
    background: color-mix(in srgb, var(--state-color) 15%, transparent);
    color: var(--state-color);
    border: 1px solid var(--state-color);
  }

  .network-toggle {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 4px 10px;
    border-radius: 20px;
    font-size: 10px;
    cursor: pointer;
    border: 1px solid var(--border);
    background: var(--bg);
    color: var(--text-dim);
    transition: all 0.3s;
    user-select: none;
    font-family: inherit;
  }

  .network-toggle { border-color: #aa3333; color: #aa3333; }
  .network-toggle:hover { border-color: #ff4444; color: #ff4444; }
  .network-toggle.open { border-color: var(--accent); color: var(--accent); }

  .network-toggle .indicator {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #aa3333;
    transition: background 0.3s;
  }
  .network-toggle.open .indicator {
    background: var(--accent);
    box-shadow: 0 0 4px var(--accent);
  }

  /* Compact Stats */
  .stats-section {
    width: 100%;
    margin-top: 4px;
    display: flex;
    flex-direction: column;
    gap: 6px;
  }

  .stat-compact {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 6px 10px;
  }

  .stat-compact label {
    display: block;
    font-size: 9px;
    text-transform: uppercase;
    letter-spacing: 1px;
    color: var(--text-dim);
    margin-bottom: 2px;
  }

  .stat-compact .value {
    font-size: 14px;
    font-weight: 700;
    color: white;
  }

  .stat-compact .sub {
    font-size: 10px;
    color: var(--text-dim);
  }

  .stat-row {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }

  .bar-wrap {
    background: #1a1a1a;
    border-radius: 3px;
    height: 6px;
    overflow: hidden;
    margin-top: 3px;
  }

  .bar-fill {
    height: 100%;
    border-radius: 3px;
    transition: width 0.5s ease, background 0.5s ease;
  }

  .bar-fill.atp {
    background: linear-gradient(90deg, #ff3333, #ffd700, #00ff41);
    background-size: 300% 100%;
  }

  .bar-fill.gpu { background: #4488ff; }

  .trust-bars {
    display: flex;
    flex-direction: column;
    gap: 2px;
    margin-top: 3px;
  }

  .trust-row {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 10px;
  }

  .trust-row .name {
    width: 70px;
    color: var(--text-dim);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .trust-row .mini-bar {
    flex: 1;
    height: 4px;
    background: #1a1a1a;
    border-radius: 2px;
    overflow: hidden;
  }

  .trust-row .mini-fill {
    height: 100%;
    background: var(--accent);
    border-radius: 2px;
    transition: width 0.5s ease;
  }

  .trust-row .val {
    width: 28px;
    text-align: right;
    color: var(--text);
    font-size: 9px;
  }

  /* Chat Panel — takes most of the window */
  .chat-panel {
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
  }

  .chat-header {
    padding: 8px 16px;
    border-bottom: 1px solid var(--border);
    font-size: 11px;
    font-weight: 600;
    color: var(--accent);
    text-transform: uppercase;
    letter-spacing: 1px;
    background: var(--surface);
    flex-shrink: 0;
  }

  .chat-log {
    flex: 1;
    overflow-y: auto;
    padding: 12px 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
  }

  .chat-msg {
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    line-height: 1.5;
    max-width: 85%;
    word-wrap: break-word;
  }

  .chat-msg.user {
    background: #1a2a1a;
    border: 1px solid #2a4a2a;
    align-self: flex-end;
    color: #a0d0a0;
  }

  .chat-msg.sage {
    background: var(--surface);
    border: 1px solid var(--border);
    align-self: flex-start;
  }

  .chat-msg.error {
    background: #2a1a1a;
    border: 1px solid #4a2a2a;
    color: #ff6666;
  }

  .chat-msg.dream {
    background: #2a1a3a;
    border: 1px solid #4a2a5a;
    color: #cc88ff;
    font-style: italic;
  }

  .chat-msg .sender {
    font-weight: 700;
    font-size: 11px;
    margin-bottom: 2px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
  }

  .chat-msg.user .sender { color: var(--accent); }
  .chat-msg.sage .sender { color: var(--state-color); }

  .chat-msg .time {
    font-size: 9px;
    color: var(--text-dim);
    float: right;
    margin-left: 8px;
  }

  .tool-calls {
    margin-top: 6px;
    font-size: 11px;
    color: var(--text-dim);
    border-top: 1px dashed var(--border);
    padding-top: 4px;
  }
  .tool-calls summary {
    cursor: pointer;
    color: var(--accent);
    font-size: 10px;
  }
  .tool-calls ul {
    margin: 4px 0 0 12px;
    padding: 0;
    list-style: none;
  }
  .tool-calls li {
    margin-bottom: 4px;
    padding: 3px 6px;
    background: rgba(255,255,255,0.03);
    border-radius: 3px;
  }
  .tool-calls code {
    font-size: 10px;
    color: var(--text-dim);
  }

  .chat-form {
    display: flex;
    gap: 8px;
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    background: var(--surface);
    flex-shrink: 0;
  }

  .chat-form textarea {
    flex: 1;
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    color: var(--text);
    font-family: inherit;
    font-size: 13px;
    outline: none;
    resize: none;
    min-height: 36px;
    max-height: 120px;
    line-height: 1.4;
    overflow-y: auto;
  }

  .chat-form textarea:focus { border-color: var(--accent); }
  .chat-form textarea:disabled { opacity: 0.5; }

  .chat-form button {
    background: var(--accent);
    color: var(--bg);
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-family: inherit;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 1px;
  }

  .chat-form button:hover { opacity: 0.8; }
  .chat-form button:disabled { opacity: 0.4; cursor: not-allowed; }

  /* Responsive */
  @media (max-width: 700px) {
    .grid {
      grid-template-columns: 1fr;
      grid-template-rows: auto 1fr;
      height: auto;
    }
    .sidebar {
      flex-direction: row;
      flex-wrap: wrap;
      border-right: none;
      border-bottom: 1px solid var(--border);
      padding: 8px;
      justify-content: center;
    }
    .avatar-wrap { width: 60px; height: 60px; }
    .stats-section { flex-direction: row; flex-wrap: wrap; }
    .stat-compact { flex: 1; min-width: 100px; }
    .chat-panel { height: 70vh; }
  }
</style>
</head>
<body>
  <header>
    <h1>SAGE</h1>
    <div class="meta">
      <span id="version-display">v--</span>
      <span id="cycle-display">Cycle: --</span>
      <span id="uptime-display">Up: --</span>
      <span class="notif-bell" id="notif-bell" title="Notifications">&#128276;<span class="notif-badge" id="notif-badge">0</span></span>
      <span><span class="connection-dot" id="conn-dot"></span> <span id="conn-label">connecting</span></span>
    </div>
  </header>

  <div class="notif-panel" id="notif-panel">
    <div class="notif-panel-header">
      <span>Notifications</span>
      <span id="notif-panel-count"></span>
    </div>
    <div class="notif-panel-body" id="notif-panel-body">
      <div class="notif-empty">No notifications</div>
    </div>
  </div>

  <div class="grid">
    <!-- Left: Avatar + Identity + Compact Stats -->
    <section class="sidebar">
      <div class="avatar-wrap">
        <img src="/images/agentzero.png" alt="SAGE" id="sage-face" />
      </div>
      <div class="machine-name" id="machine-name">--</div>
      <div class="metabolic-badge" id="metabolic-badge">--</div>
      <div class="lct-id" id="lct-id">--</div>
      <button class="network-toggle" id="network-toggle" title="Allow others on the network to talk to SAGE">
        <span class="indicator"></span>
        <span id="network-label">Local Only</span>
      </button>

      <div class="stats-section">
        <div class="stat-row">
          <div class="stat-compact">
            <label>ATP</label>
            <div class="value" id="atp-value">--</div>
            <div class="bar-wrap"><div class="bar-fill atp" id="atp-bar" style="width:0%"></div></div>
          </div>
          <div class="stat-compact">
            <label>Cycles</label>
            <div class="value" id="cycle-value">0</div>
            <div class="sub" id="effects-sub">--</div>
          </div>
        </div>

        <div class="stat-row">
          <div class="stat-compact">
            <label>GPU</label>
            <div class="value" id="gpu-value">--</div>
            <div class="bar-wrap"><div class="bar-fill gpu" id="gpu-bar" style="width:0%"></div></div>
            <div class="sub" id="gpu-name">--</div>
          </div>
          <div class="stat-compact">
            <label>System</label>
            <div class="value" id="cpu-value">--%</div>
            <div class="sub" id="ram-sub">RAM: --</div>
          </div>
        </div>

        <div class="stat-compact">
          <label>SNARC</label>
          <div class="value" id="salience-value">0.000</div>
          <div class="sub" id="messages-sub">messages: --</div>
        </div>

        <div class="stat-compact">
          <label>Tools</label>
          <div class="value" id="tool-count">0</div>
          <div class="sub" id="tool-tier">tier: --</div>
          <div class="sub" id="tool-detail">ok: 0  denied: 0</div>
        </div>

        <div class="stat-compact">
          <label>LLM Pool</label>
          <div class="value" id="llm-pool-count">0</div>
          <div class="sub" id="llm-pool-active">active: --</div>
          <div class="trust-bars" id="llm-pool-bars">
            <div class="sub">waiting...</div>
          </div>
        </div>

        <div class="stat-compact">
          <label>Plugin Trust</label>
          <div class="trust-bars" id="trust-bars">
            <div class="sub">waiting...</div>
          </div>
        </div>

        <div class="stat-compact">
          <label>Sensor Trust</label>
          <div class="trust-bars" id="sensor-trust-bars">
            <div class="sub">waiting...</div>
          </div>
        </div>

        <div class="stat-compact">
          <label>Trust Posture</label>
          <div class="sub" id="posture-label">--</div>
          <div class="sub" id="posture-detail"></div>
        </div>
      </div>
    </section>

    <!-- Right: Chat (main area) -->
    <section class="chat-panel">
      <div class="chat-header">
        Talk to <span id="chat-sage-name">SAGE</span>
        <span style="opacity:0.5; margin:0 6px;">as</span>
        <input id="operator-name-input" type="text" value="dennis"
          spellcheck="false" autocomplete="off"
          style="background:transparent; border:none; border-bottom:1px solid var(--accent);
                 color:var(--accent); font-size:11px; font-weight:600; text-transform:uppercase;
                 letter-spacing:1px; width:80px; padding:0 2px; outline:none;"
        />
      </div>
      <div class="chat-log" id="chat-log"></div>
      <form class="chat-form" id="chat-form">
        <textarea id="chat-input" placeholder="Say something..." autocomplete="off" rows="1"></textarea>
        <button type="submit" id="chat-send">Send</button>
      </form>
    </section>
  </div>

<script>
// --- State color mapping ---
const STATE_COLORS = {
  wake: '#00ff41', focus: '#ffd700', rest: '#4488ff',
  dream: '#cc44ff', crisis: '#ff3333', lightweight: '#4488ff',
};

function setStateColor(state) {
  const color = STATE_COLORS[state] || STATE_COLORS.wake;
  document.documentElement.style.setProperty('--state-color', color);
}

// --- SSE Connection ---
let evtSource = null;
function connectSSE() {
  evtSource = new EventSource('/stream');

  evtSource.onopen = () => {
    document.getElementById('conn-dot').classList.add('connected');
    document.getElementById('conn-label').textContent = 'live';
  };

  evtSource.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      updateDashboard(data);
    } catch (e) { console.error('SSE parse error:', e); }
  };

  evtSource.onerror = () => {
    document.getElementById('conn-dot').classList.remove('connected');
    document.getElementById('conn-label').textContent = 'reconnecting';
    evtSource.close();
    setTimeout(connectSSE, 3000);
  };
}

// --- Dashboard update ---
function updateDashboard(d) {
  if (d.machine) {
    document.getElementById('machine-name').textContent = d.machine;
    document.getElementById('chat-sage-name').textContent = d.machine;
    sageName = d.machine;
  }
  if (d.operator_name && !operatorInput._initialized) {
    // Only set from SSE once on first update, and only if no localStorage override
    operatorInput._initialized = true;
    if (!localStorage.getItem('sage-operator-name')) {
      operatorName = d.operator_name;
      operatorInput.value = operatorName;
    }
  }
  if (d.lct_id) document.getElementById('lct-id').textContent = d.lct_id;
  if (d.code_version) document.getElementById('version-display').textContent = 'v' + d.code_version;

  const state = (d.metabolic_state || 'unknown').toLowerCase();
  document.getElementById('metabolic-badge').textContent = state.toUpperCase();
  setStateColor(state);

  if (d.atp_current !== undefined && d.atp_max) {
    const pct = Math.round((d.atp_current / d.atp_max) * 100);
    document.getElementById('atp-value').textContent =
      d.atp_current.toFixed(0) + ' / ' + d.atp_max;
    const bar = document.getElementById('atp-bar');
    bar.style.width = pct + '%';
    bar.style.backgroundPosition = (100 - pct) + '% 0';
  }

  if (d.cycle_count !== undefined) {
    document.getElementById('cycle-value').textContent = d.cycle_count.toLocaleString();
    document.getElementById('cycle-display').textContent = 'Cycle: ' + d.cycle_count.toLocaleString();
  }

  if (d.loop_stats) {
    const ls = d.loop_stats;
    document.getElementById('effects-sub').textContent =
      'fx: ' + (ls.effects_proposed || 0) + '/' + (ls.effects_approved || 0);
  }

  if (d.gpu) {
    const used = d.gpu.memory_allocated_mb;
    const total = d.gpu.memory_total_mb;
    const pct = Math.round((used / total) * 100);
    document.getElementById('gpu-value').textContent =
      (used / 1000).toFixed(1) + '/' + (total / 1000).toFixed(1) + 'G';
    document.getElementById('gpu-bar').style.width = pct + '%';
    document.getElementById('gpu-name').textContent = d.gpu.name || '';
  } else {
    document.getElementById('gpu-value').textContent = 'N/A';
    document.getElementById('gpu-name').textContent =
      d.mode === 'lightweight' ? 'Ollama' : 'no GPU';
  }

  if (d.cpu_percent !== undefined) {
    document.getElementById('cpu-value').textContent = d.cpu_percent.toFixed(0) + '%';
  }
  if (d.ram_used_mb !== undefined && d.ram_total_mb) {
    document.getElementById('ram-sub').textContent =
      'RAM: ' + (d.ram_used_mb / 1000).toFixed(1) + '/' + (d.ram_total_mb / 1000).toFixed(1) + 'G';
  }

  if (d.average_salience !== undefined) {
    document.getElementById('salience-value').textContent = d.average_salience.toFixed(3);
  }

  if (d.message_stats) {
    const ms = d.message_stats;
    document.getElementById('messages-sub').textContent =
      'in: ' + (ms.submitted || 0) + '  out: ' + (ms.resolved || 0);
  }

  if (d.plugin_trust && Object.keys(d.plugin_trust).length > 0) {
    const container = document.getElementById('trust-bars');
    container.innerHTML = '';
    const sorted = Object.entries(d.plugin_trust).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [name, val] of sorted) {
      const shortName = name.replace(/_impl$/, '').replace(/_plugin$/, '').replace(/_irp$/, '');
      const pct = Math.round(val * 100);
      container.innerHTML += '<div class="trust-row">' +
        '<span class="name" title="' + name + '">' + shortName + '</span>' +
        '<div class="mini-bar"><div class="mini-fill" style="width:' + pct + '%"></div></div>' +
        '<span class="val">' + val.toFixed(2) + '</span></div>';
    }
  }

  if (d.sensor_trust && Object.keys(d.sensor_trust).length > 0) {
    const container = document.getElementById('sensor-trust-bars');
    container.innerHTML = '';
    const sorted = Object.entries(d.sensor_trust).sort((a, b) => a[0].localeCompare(b[0]));
    for (const [name, val] of sorted) {
      const pct = Math.round(val * 100);
      const color = val >= 0.15 ? '#4ec9b0' : '#666';
      container.innerHTML += '<div class="trust-row">' +
        '<span class="name">' + name + '</span>' +
        '<div class="mini-bar"><div class="mini-fill" style="width:' + pct + '%;background:' + color + '"></div></div>' +
        '<span class="val">' + val.toFixed(2) + '</span></div>';
    }
  }

  if (d.trust_posture) {
    const p = d.trust_posture;
    document.getElementById('posture-label').textContent = p.label +
      ' (conf=' + p.confidence.toFixed(2) + ' asym=' + p.asymmetry.toFixed(2) + ' brd=' + p.breadth.toFixed(2) + ')';
    const restricted = p.effect_restrictions.length > 0 ? 'blocked: ' + p.effect_restrictions.join(', ') : 'no restrictions';
    document.getElementById('posture-detail').textContent =
      'dom: ' + p.dominant_modality + ' | ' + restricted;
  }

  if (d.uptime_seconds !== undefined) {
    const h = Math.floor(d.uptime_seconds / 3600);
    const m = Math.floor((d.uptime_seconds % 3600) / 60);
    const str = (h > 0 ? h + 'h ' : '') + m + 'm';
    document.getElementById('uptime-display').textContent = 'Up: ' + str;
  }

  if (d.chat_count !== undefined) {
    document.getElementById('messages-sub').textContent = 'chats: ' + d.chat_count;
  }

  if (d.tool_stats) {
    const ts = d.tool_stats;
    document.getElementById('tool-count').textContent = ts.total || 0;
    document.getElementById('tool-tier').textContent =
      'tier: ' + (ts.tier || '--') + ' (' + (ts.registered || 0) + ' tools)';
    document.getElementById('tool-detail').textContent =
      'ok: ' + (ts.success || 0) + '  denied: ' + (ts.denied || 0);
  }

  if (d.llm_pool) {
    const lp = d.llm_pool;
    document.getElementById('llm-pool-count').textContent = lp.count || 0;
    document.getElementById('llm-pool-active').textContent =
      'active: ' + (lp.active || '--');
    const barsEl = document.getElementById('llm-pool-bars');
    if (lp.entries && lp.entries.length > 0) {
      let html = '';
      lp.entries.forEach(e => {
        const pct = Math.round(e.trust * 100);
        const color = e.healthy ? (e.model_name === lp.active ? '#4ec9b0' : '#569cd6') : '#888';
        const label = e.model_name.split(':').pop() || e.model_name;
        html += '<div style="display:flex;align-items:center;gap:4px;margin:1px 0">' +
          '<span style="width:48px;font-size:10px;text-align:right;opacity:0.7">' + label + '</span>' +
          '<div style="flex:1;background:#333;border-radius:2px;height:8px">' +
          '<div style="width:' + pct + '%;background:' + color +
          ';border-radius:2px;height:100%"></div></div>' +
          '<span style="width:28px;font-size:10px">' + pct + '%</span></div>';
        });
      barsEl.innerHTML = html;
    }
  }

  if (d.network_open !== undefined) {
    networkOpen = d.network_open;
    updateNetworkToggle();
  }

  if (d.notification_count !== undefined) {
    updateNotifBadge(d.notification_count);
  }
}

// --- Chat ---
const chatForm = document.getElementById('chat-form');
const chatInput = document.getElementById('chat-input');
const chatSend = document.getElementById('chat-send');
const chatLog = document.getElementById('chat-log');

function escapeHtml(text) {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

function formatTime(ts) {
  if (!ts) return '';
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function appendChat(sender, text, cssClass, timestamp, toolCalls) {
  const div = document.createElement('div');
  div.className = 'chat-msg ' + (cssClass || 'sage');
  const timeStr = timestamp ? '<span class="time">' + formatTime(timestamp) + '</span>' : '';
  let html = '<div class="sender">' + timeStr + escapeHtml(sender) + '</div>' +
             '<div>' + escapeHtml(text) + '</div>';
  // Tool call details (collapsible)
  if (toolCalls && toolCalls.length > 0) {
    html += '<details class="tool-calls"><summary>Tools used (' + toolCalls.length + ')</summary><ul>';
    for (const tc of toolCalls) {
      const status = tc.success ? '&check;' : '&cross;';
      const result = tc.success ? (tc.result || '').substring(0, 200) : (tc.error || 'failed');
      html += '<li><b>' + status + ' ' + escapeHtml(tc.name || '') + '</b>';
      if (tc.arguments) html += ' <code>' + escapeHtml(JSON.stringify(tc.arguments)) + '</code>';
      html += '<br><small>' + escapeHtml(result) + '</small></li>';
    }
    html += '</ul></details>';
  }
  div.innerHTML = html;
  chatLog.appendChild(div);
  chatLog.scrollTop = chatLog.scrollHeight;
}

// Load chat history on startup
async function loadChatHistory() {
  try {
    const resp = await fetch('/chat-history');
    if (!resp.ok) return;
    const messages = await resp.json();
    for (const msg of messages) {
      appendChat(msg.sender, msg.text, msg.css_class, msg.timestamp);
    }
    if (messages.length === 0) {
      appendChat(sageName, 'Dashboard connected. Type a message to begin.', 'sage');
    }
  } catch (e) {
    appendChat('SAGE', 'Dashboard connected. Type a message to begin.', 'sage');
  }
}

let currentConversationId = null;
// Identity names — sageName from SSE, operatorName from localStorage or SSE default
let sageName = 'SAGE';
let operatorName = localStorage.getItem('sage-operator-name') || 'dennis';

// Operator name input — persist on change
const operatorInput = document.getElementById('operator-name-input');
operatorInput.value = operatorName;
operatorInput.addEventListener('change', () => {
  const val = operatorInput.value.trim();
  if (val) {
    operatorName = val;
    localStorage.setItem('sage-operator-name', val);
  }
});
operatorInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); operatorInput.blur(); }
});

async function sendChat() {
  const message = chatInput.value.trim();
  if (!message) return;

  appendChat(operatorName, message, 'user');
  chatInput.value = '';
  chatInput.disabled = true;
  chatSend.disabled = true;
  chatSend.textContent = '...';

  try {
    const payload = {
      sender: operatorName,
      message: message,
      max_wait_seconds: 90,
    };
    if (currentConversationId) {
      payload.conversation_id = currentConversationId;
    }
    const resp = await fetch('/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const text = await resp.text();
    let result;
    try { result = JSON.parse(text); } catch (pe) {
      appendChat('System', 'Bad response: ' + text.substring(0, 200), 'error');
      return;
    }

    if (result.conversation_id) {
      currentConversationId = result.conversation_id;
    }

    if (resp.status === 202) {
      appendChat(sageName, '(dreaming... message queued)', 'dream');
    } else if (result.error) {
      appendChat(sageName, 'Error: ' + result.error, 'error');
    } else {
      appendChat(sageName, result.response || result.text || JSON.stringify(result), 'sage');
    }
  } catch (err) {
    appendChat('System', 'Connection error: ' + err.message, 'error');
  } finally {
    chatInput.disabled = false;
    chatSend.disabled = false;
    chatSend.textContent = 'Send';
    chatInput.style.height = 'auto';
    chatInput.focus();
  }
}

chatForm.addEventListener('submit', (e) => {
  e.preventDefault();
  sendChat();
});

chatInput.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendChat();
  }
});
chatSend.addEventListener('click', (e) => {
  e.preventDefault();
  sendChat();
});
chatInput.addEventListener('input', () => {
  chatInput.style.height = 'auto';
  chatInput.style.height = Math.min(chatInput.scrollHeight, 120) + 'px';
});

// --- Network Access Toggle ---
const networkToggle = document.getElementById('network-toggle');
let networkOpen = false;

networkToggle.addEventListener('click', async () => {
  try {
    const resp = await fetch('/network-access', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ open: !networkOpen }),
    });
    const result = await resp.json();
    networkOpen = result.network_open;
    updateNetworkToggle();
  } catch (err) {
    console.error('Network toggle failed:', err);
  }
});

function updateNetworkToggle() {
  const toggle = document.getElementById('network-toggle');
  const label = document.getElementById('network-label');
  if (networkOpen) {
    toggle.classList.add('open');
    label.textContent = 'Network Open';
  } else {
    toggle.classList.remove('open');
    label.textContent = 'Local Only';
  }
}

// --- Notifications ---
let prevNotifCount = 0;
const notifBell = document.getElementById('notif-bell');
const notifBadge = document.getElementById('notif-badge');
const notifPanel = document.getElementById('notif-panel');

notifBell.addEventListener('click', (e) => {
  e.stopPropagation();
  const isOpen = notifPanel.classList.toggle('open');
  if (isOpen) fetchNotifications();
});

document.addEventListener('click', (e) => {
  if (!notifPanel.contains(e.target) && e.target !== notifBell) {
    notifPanel.classList.remove('open');
  }
});

function updateNotifBadge(count) {
  notifBadge.textContent = count;
  if (count > 0) {
    notifBadge.classList.add('visible');
  } else {
    notifBadge.classList.remove('visible');
  }
  // Chime when count increases
  if (count > prevNotifCount && prevNotifCount >= 0) {
    playNotifChime();
  }
  prevNotifCount = count;
}

function playNotifChime() {
  try {
    const ctx = new (window.AudioContext || window.webkitAudioContext)();
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.connect(gain);
    gain.connect(ctx.destination);
    osc.frequency.setValueAtTime(880, ctx.currentTime);
    osc.frequency.setValueAtTime(1100, ctx.currentTime + 0.08);
    gain.gain.setValueAtTime(0.08, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.3);
    osc.start(ctx.currentTime);
    osc.stop(ctx.currentTime + 0.3);
  } catch (e) { /* no audio context */ }
}

async function fetchNotifications() {
  try {
    const resp = await fetch('/notifications');
    if (!resp.ok) return;
    const items = await resp.json();
    renderNotifications(items);
  } catch (e) { console.error('Notification fetch error:', e); }
}

function renderNotifications(items) {
  const body = document.getElementById('notif-panel-body');
  const countEl = document.getElementById('notif-panel-count');
  if (!items || items.length === 0) {
    body.innerHTML = '<div class="notif-empty">No unread notifications</div>';
    countEl.textContent = '';
    return;
  }
  countEl.textContent = items.length;
  let html = '';
  for (const n of items) {
    const t = n.timestamp ? new Date(n.timestamp * 1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) : '';
    html += '<div class="notif-item" data-id="' + (n.id || '') + '">' +
      '<div class="notif-content">' +
        '<div class="notif-source">' + escapeHtml(n.source || '') + ' / ' + escapeHtml(n.source_detail || '') + '</div>' +
        '<div class="notif-snippet">' + escapeHtml(n.text_snippet || '') + '</div>' +
        '<div class="notif-time">' + t + '</div>' +
      '</div>' +
      '<button class="notif-ack-btn" data-notif-id="' + (n.id || '') + '">ack</button>' +
    '</div>';
  }
  body.innerHTML = html;
}

async function ackNotification(id, btn) {
  try {
    await fetch('/notifications/acknowledge', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ id: id }),
    });
    const item = btn.closest('.notif-item');
    if (item) item.remove();
    // Update badge
    const remaining = document.querySelectorAll('.notif-item').length;
    updateNotifBadge(remaining);
    if (remaining === 0) {
      document.getElementById('notif-panel-body').innerHTML =
        '<div class="notif-empty">No unread notifications</div>';
      document.getElementById('notif-panel-count').textContent = '';
    }
  } catch (e) { console.error('Ack error:', e); }
}

// --- Notification ack via delegation (avoids inline onclick quote issues) ---
document.addEventListener('click', function(e) {
  const btn = e.target.closest('.notif-ack-btn');
  if (btn) {
    const id = btn.getAttribute('data-notif-id');
    ackNotification(id, btn);
  }
});

// --- Init ---
loadChatHistory();
connectSSE();
</script>
</body>
</html>"""
