FALLBACK_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>KM — Knowledge Manager</title>
<script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9/dist/htmx.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/cytoscape@3.30/dist/cytoscape.min.js"></script>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Sans:opsz,wght@9..40,300;9..40,400;9..40,500;9..40,600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg-deepest: #06070d;
    --bg-deep: #0b0d18;
    --bg-surface: #111422;
    --bg-card: #161a2c;
    --bg-hover: #1c2138;
    --text-primary: #e2e6f0;
    --text-secondary: #8890b0;
    --text-tertiary: #586080;
    --accent-amber: #e0a83a;
    --accent-gold: #c4922e;
    --accent-blue: #5b9bd5;
    --accent-green: #4cb882;
    --accent-red: #e0556a;
    --accent-teal: #3bb0a0;
    --border-subtle: rgba(255,255,255,0.05);
    --border-visible: rgba(255,255,255,0.10);
    --radius-sm: 4px;
    --radius-md: 8px;
    --radius-lg: 14px;
    --shadow-card: 0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.3);
    --shadow-elevated: 0 4px 16px rgba(0,0,0,0.5);
    --font-display: 'DM Serif Display', Georgia, 'Times New Roman', serif;
    --font-body: 'DM Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    --font-mono: 'JetBrains Mono', 'Cascadia Code', 'Consolas', monospace;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  html { font-size: 15px; }
  body {
    font-family: var(--font-body);
    background: var(--bg-deepest);
    color: var(--text-primary);
    min-height: 100vh;
    background-image:
      radial-gradient(ellipse at 20% 10%, rgba(224,168,58,0.03) 0%, transparent 60%),
      radial-gradient(ellipse at 80% 90%, rgba(91,155,213,0.04) 0%, transparent 60%),
      radial-gradient(circle at 50% 50%, rgba(255,255,255,0.008) 0%, transparent 100%);
  }

  /* ── Layout ── */
  .km-shell {
    display: grid;
    grid-template-columns: 280px 1fr;
    grid-template-rows: 56px 1fr;
    grid-template-areas:
      "topbar topbar"
      "sidebar main";
    height: 100vh;
    overflow: hidden;
  }

  /* ── Top Bar ── */
  .km-topbar {
    grid-area: topbar;
    display: flex;
    align-items: center;
    padding: 0 24px;
    border-bottom: 1px solid var(--border-subtle);
    background: var(--bg-deep);
    backdrop-filter: blur(12px);
    gap: 16px;
  }
  .km-logo {
    font-family: var(--font-display);
    font-size: 1.2rem;
    color: var(--accent-amber);
    letter-spacing: 0.02em;
    white-space: nowrap;
    line-height: 1;
  }
  .km-logo span { color: var(--text-tertiary); font-weight: 300; font-family: var(--font-body); font-size: 0.85rem; margin-left: 4px; }
  .km-topbar-search {
    flex: 1;
    max-width: 480px;
  }
  .km-topbar-search input {
    width: 100%;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 8px 16px;
    color: var(--text-primary);
    font-family: var(--font-body);
    font-size: 0.9rem;
    transition: all 0.2s ease;
    outline: none;
  }
  .km-topbar-search input::placeholder { color: var(--text-tertiary); }
  .km-topbar-search input:focus {
    border-color: var(--accent-amber);
    box-shadow: 0 0 0 3px rgba(224,168,58,0.1);
  }
  .km-topbar-nav { display: flex; gap: 8px; }
  .km-topbar-nav a {
    color: var(--text-secondary);
    text-decoration: none;
    font-size: 0.82rem;
    padding: 6px 14px;
    border-radius: var(--radius-sm);
    transition: all 0.15s ease;
    letter-spacing: 0.02em;
    cursor: pointer;
    border: 1px solid transparent;
  }
  .km-topbar-nav a:hover { color: var(--text-primary); background: var(--bg-hover); border-color: var(--border-visible); }
  .km-topbar-nav a.active { color: var(--accent-amber); border-color: rgba(224,168,58,0.2); background: rgba(224,168,58,0.06); }

  /* ── Sidebar ── */
  .km-sidebar {
    grid-area: sidebar;
    border-right: 1px solid var(--border-subtle);
    background: var(--bg-deep);
    overflow-y: auto;
    overflow-x: hidden;
    padding: 20px 0;
  }
  .km-sidebar::-webkit-scrollbar { width: 4px; }
  .km-sidebar::-webkit-scrollbar-thumb { background: var(--border-visible); border-radius: 2px; }

  .km-sidebar-header {
    padding: 0 20px 16px;
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    color: var(--text-tertiary);
    font-weight: 500;
  }

  /* ── Drop Zone ── */
  .km-dropzone {
    margin: 0 12px 16px;
    border: 2px dashed var(--border-visible);
    border-radius: var(--radius-md);
    padding: 16px 12px;
    text-align: center;
    cursor: pointer;
    transition: all 0.2s ease;
    background: var(--bg-surface);
  }
  .km-dropzone:hover, .km-dropzone.drag-over {
    border-color: var(--accent-amber);
    background: rgba(224,168,58,0.05);
  }
  .km-dropzone-icon {
    font-size: 1.5rem;
    margin-bottom: 4px;
  }
  .km-dropzone-text {
    font-size: 0.72rem;
    color: var(--text-tertiary);
    line-height: 1.4;
  }
  .km-dropzone-text strong { color: var(--accent-amber); }
  .km-toast {
    position: fixed;
    top: 20px; right: 20px;
    z-index: 9999;
    max-width: 360px;
    background: var(--bg-card);
    border: 1px solid var(--border-visible);
    border-radius: var(--radius-md);
    padding: 14px 18px;
    box-shadow: var(--shadow-elevated);
    animation: km-slide-in 0.25s ease;
    font-size: 0.85rem;
  }
  .km-toast.success { border-left: 3px solid var(--accent-green); }
  .km-toast.error { border-left: 3px solid var(--accent-red); }
  .km-toast-title { font-weight: 600; margin-bottom: 4px; }
  .km-toast-detail { font-size: 0.75rem; color: var(--text-secondary); }
  @keyframes km-slide-in {
    from { opacity: 0; transform: translateX(40px); }
    to { opacity: 1; transform: translateX(0); }
  }

  /* ── Tree ── */
  .km-tree { padding: 0 4px; }
  .km-tree-cat {
    margin-bottom: 12px;
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    overflow: hidden;
  }
  .km-tree-cat-header {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 14px;
    cursor: pointer;
    font-size: 0.85rem;
    font-weight: 600;
    color: var(--text-primary);
    transition: all 0.12s ease;
    user-select: none;
  }
  .km-tree-cat-header:hover { background: var(--bg-hover); }
  .km-tree-cat-icon {
    font-size: 1.1rem;
    width: 26px; height: 26px;
    display: flex;
    align-items: center;
    justify-content: center;
    background: var(--bg-surface);
    border-radius: var(--radius-sm);
    flex-shrink: 0;
  }
  .km-tree-cat-header .km-tree-count {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
    margin-left: auto;
    background: var(--bg-surface);
    padding: 1px 8px;
    border-radius: 9999px;
  }
  .km-tree-modules {
    border-top: 1px solid var(--border-subtle);
    padding: 4px 0;
  }
  .km-tree-modules[hidden] { display: none; }
  .km-tree-leaf {
    padding: 6px 12px 6px 38px;
    font-size: 0.8rem;
    color: var(--text-secondary);
    cursor: pointer;
    transition: all 0.1s ease;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    position: relative;
  }
  .km-tree-leaf::before {
    content: '';
    position: absolute;
    left: 20px; top: 50%;
    width: 5px; height: 5px;
    background: var(--border-visible);
    border-radius: 50%;
    transform: translateY(-50%);
    transition: all 0.15s ease;
  }
  .km-tree-leaf:hover { color: var(--text-primary); background: var(--bg-hover); }
  .km-tree-leaf:hover::before { background: var(--accent-amber); }
  .km-tree-leaf[data-active] { color: var(--accent-blue); background: rgba(91,155,213,0.08); }
  .km-tree-leaf[data-active]::before { background: var(--accent-blue); box-shadow: 0 0 4px rgba(91,155,213,0.4); }

  /* ── Main Content ── */
  .km-main {
    grid-area: main;
    overflow-y: auto;
    overflow-x: hidden;
    padding: 32px 40px;
  }
  .km-main::-webkit-scrollbar { width: 6px; }
  .km-main::-webkit-scrollbar-thumb { background: var(--border-visible); border-radius: 3px; }

  /* ── Dashboard Cards ── */
  .km-stats-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 32px;
  }
  .km-stat-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-lg);
    padding: 22px 20px;
    position: relative;
    overflow: hidden;
    transition: all 0.2s ease;
  }
  .km-stat-card:hover {
    border-color: var(--border-visible);
    transform: translateY(-1px);
    box-shadow: var(--shadow-elevated);
  }
  .km-stat-card .km-stat-label {
    font-size: 0.72rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-tertiary);
    margin-bottom: 8px;
    font-weight: 500;
  }
  .km-stat-card .km-stat-value {
    font-family: var(--font-display);
    font-size: 2.4rem;
    line-height: 1;
    color: var(--text-primary);
  }
  .km-stat-card .km-stat-value.accent { color: var(--accent-amber); }
  .km-stat-card::after {
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 60px; height: 60px;
    background: radial-gradient(circle at top right, rgba(255,255,255,0.02), transparent 70%);
  }

  /* ── Search Results ── */
  .km-search-header { margin-bottom: 24px; }
  .km-search-header h2 {
    font-family: var(--font-display);
    font-size: 1.6rem;
    font-weight: 400;
    margin-bottom: 4px;
  }
  .km-search-header .km-search-meta {
    font-size: 0.8rem;
    color: var(--text-tertiary);
  }
  .km-search-meta .km-pill {
    display: inline-block;
    padding: 2px 10px;
    background: rgba(91,155,213,0.1);
    border: 1px solid rgba(91,155,213,0.2);
    border-radius: 9999px;
    font-size: 0.72rem;
    color: var(--accent-blue);
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .km-result-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 18px 20px;
    margin-bottom: 10px;
    cursor: pointer;
    transition: all 0.15s ease;
    display: flex;
    gap: 14px;
    align-items: flex-start;
  }
  .km-result-card:hover {
    border-color: var(--border-visible);
    background: var(--bg-hover);
  }
  .km-result-index {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
    min-width: 20px;
    padding-top: 2px;
  }
  .km-result-body { flex: 1; min-width: 0; }
  .km-result-title {
    font-weight: 600;
    font-size: 0.95rem;
    margin-bottom: 4px;
    display: flex;
    gap: 8px;
    align-items: center;
  }
  .km-result-snippet {
    font-size: 0.82rem;
    color: var(--text-secondary);
    line-height: 1.5;
    overflow: hidden;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
  }
  .km-result-meta {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-tertiary);
    margin-top: 6px;
  }

  /* ── Badges ── */
  .km-badge {
    display: inline-block;
    padding: 1px 8px;
    border-radius: 9999px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  .km-badge-high { background: rgba(76,184,130,0.12); color: var(--accent-green); border: 1px solid rgba(76,184,130,0.2); }
  .km-badge-medium { background: rgba(224,168,58,0.1); color: var(--accent-amber); border: 1px solid rgba(224,168,58,0.2); }
  .km-badge-low { background: rgba(224,85,106,0.1); color: var(--accent-red); border: 1px solid rgba(224,85,106,0.2); }
  .km-badge-status {
    background: var(--bg-surface);
    color: var(--text-secondary);
    border: 1px solid var(--border-visible);
  }
  .km-badge-source {
    background: rgba(91,155,213,0.08);
    color: var(--accent-blue);
    border: 1px solid rgba(91,155,213,0.15);
    font-size: 0.62rem;
  }

  /* ── Tags ── */
  .km-tags { display: flex; flex-wrap: wrap; gap: 5px; margin: 10px 0; }
  .km-tag {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    padding: 2px 10px;
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-sm);
    color: var(--text-secondary);
    letter-spacing: 0.02em;
  }
  .km-related-tag {
    cursor: pointer;
    transition: all 0.12s ease;
    border-color: rgba(91,155,213,0.15);
    color: var(--accent-blue);
  }
  .km-related-tag:hover { background: rgba(91,155,213,0.08); border-color: rgba(91,155,213,0.3); }

  /* ── Module Detail ── */
  .km-module { max-width: 720px; }
  .km-module-breadcrumb {
    font-family: var(--font-mono);
    font-size: 0.7rem;
    color: var(--text-tertiary);
    margin-bottom: 12px;
    letter-spacing: 0.04em;
  }
  .km-module h1 {
    font-family: var(--font-display);
    font-size: 2rem;
    font-weight: 400;
    line-height: 1.25;
    margin-bottom: 8px;
    color: var(--text-primary);
  }
  .km-module-summary {
    font-size: 1.05rem;
    line-height: 1.6;
    color: var(--text-secondary);
    margin-bottom: 20px;
    font-style: italic;
    font-family: var(--font-display);
  }
  .km-section { margin: 24px 0; }
  .km-section h3 {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.14em;
    color: var(--text-tertiary);
    margin-bottom: 10px;
    font-weight: 600;
  }
  .km-section p {
    font-size: 0.92rem;
    line-height: 1.7;
    color: var(--text-secondary);
  }
  .km-section pre {
    background: var(--bg-surface);
    border: 1px solid var(--border-subtle);
    border-radius: var(--radius-md);
    padding: 16px;
    font-family: var(--font-mono);
    font-size: 0.78rem;
    line-height: 1.6;
    color: var(--text-primary);
    overflow-x: auto;
    white-space: pre-wrap;
  }
  .km-caveat {
    background: rgba(224,168,58,0.05);
    border: 1px solid rgba(224,168,58,0.15);
    border-left: 3px solid var(--accent-amber);
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    padding: 16px 20px;
    margin: 20px 0;
  }
  .km-caveat strong {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--accent-amber);
    display: block;
    margin-bottom: 6px;
  }
  .km-caveat p { font-size: 0.85rem; color: var(--text-secondary); line-height: 1.6; }

  /* ── Health ── */
  .km-health-header { margin-bottom: 24px; }
  .km-health-header h2 { font-family: var(--font-display); font-size: 1.6rem; font-weight: 400; margin-bottom: 6px; }
  .km-health-score {
    font-family: var(--font-display);
    font-size: 2.4rem;
    color: var(--accent-amber);
  }
  .km-health-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 10px; }
  .km-risk-card {
    background: var(--bg-card);
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--accent-red);
    border-radius: 0 var(--radius-md) var(--radius-md) 0;
    padding: 14px 18px;
    transition: all 0.15s ease;
  }
  .km-risk-card:hover { background: var(--bg-hover); }
  .km-risk-card .km-risk-title {
    font-weight: 600;
    font-size: 0.88rem;
    margin-bottom: 4px;
  }
  .km-risk-card .km-risk-meta {
    font-family: var(--font-mono);
    font-size: 0.68rem;
    color: var(--text-tertiary);
    margin-top: 6px;
  }
  .km-risk-card .km-risk-issues {
    display: flex;
    gap: 4px;
    margin-top: 4px;
  }
  .km-risk-issues span {
    font-size: 0.62rem;
    padding: 1px 8px;
    border-radius: 9999px;
    background: rgba(224,85,106,0.08);
    color: var(--accent-red);
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }

  /* ── Category breakdown ── */
  .km-category-list { display: flex; flex-direction: column; gap: 8px; margin-top: 16px; }
  .km-category-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 8px 0;
  }
  .km-category-name {
    font-size: 0.85rem;
    font-weight: 500;
    min-width: 100px;
    color: var(--text-secondary);
  }
  .km-category-bar-bg {
    flex: 1;
    height: 6px;
    background: var(--bg-surface);
    border-radius: 3px;
    overflow: hidden;
  }
  .km-category-bar-fill {
    height: 100%;
    border-radius: 3px;
    background: var(--accent-amber);
    opacity: 0.7;
    transition: width 0.6s ease;
  }
  .km-category-score {
    font-family: var(--font-mono);
    font-size: 0.75rem;
    color: var(--text-tertiary);
    min-width: 40px;
    text-align: right;
  }

  /* ── Recommendations ── */
  .km-recs-section { margin-bottom: 28px; }
  .km-recs-section h3 {
    font-family: var(--font-display);
    font-size: 1.1rem;
    font-weight: 400;
    margin-bottom: 12px;
    color: var(--text-primary);
  }
  .km-rec-item {
    padding: 10px 16px;
    border-left: 2px solid var(--border-visible);
    margin-bottom: 6px;
    font-size: 0.85rem;
    color: var(--text-secondary);
    background: var(--bg-card);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    transition: all 0.12s ease;
  }
  .km-rec-item:hover { border-left-color: var(--accent-amber); background: var(--bg-hover); }

  /* ── Loading ── */
  .km-loading {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 60px 0;
    color: var(--text-tertiary);
    font-size: 0.85rem;
  }
  .km-loading::after {
    content: '';
    display: inline-block;
    width: 8px; height: 8px;
    margin-left: 8px;
    background: var(--accent-amber);
    border-radius: 50%;
    animation: km-pulse 1.2s ease-in-out infinite;
  }
  @keyframes km-pulse {
    0%, 100% { opacity: 0.2; transform: scale(0.8); }
    50% { opacity: 1; transform: scale(1.2); }
  }

  /* ── Empty state ── */
  .km-empty {
    text-align: center;
    padding: 60px 20px;
    color: var(--text-tertiary);
  }
  .km-empty-icon {
    font-size: 3rem;
    margin-bottom: 12px;
    opacity: 0.3;
  }
  .km-empty p {
    font-family: var(--font-display);
    font-size: 1.1rem;
    color: var(--text-secondary);
  }

  /* ── Responsive ── */
  @media (max-width: 800px) {
    .km-shell {
      grid-template-columns: 1fr;
      grid-template-rows: 48px 1fr;
      grid-template-areas: "topbar" "main";
    }
    .km-sidebar { display: none; }
    .km-main { padding: 20px 16px; }
    .km-stats-grid { grid-template-columns: repeat(2, 1fr); }
    .km-topbar-nav a { padding: 4px 8px; font-size: 0.7rem; }
    .km-module h1 { font-size: 1.5rem; }
  }
</style>
</head>
<body>

<div class="km-shell">
  <header class="km-topbar">
    <div class="km-logo">KM<span>v0.5</span></div>
    <div class="km-topbar-search">
      <input type="search" id="global-search" placeholder="Search knowledge base..."
        name="query"
        hx-post="/api/search"
        hx-trigger="keyup changed delay:250ms"
        hx-target="#main-content"
        hx-swap="innerHTML"
        hx-vals="js:{query: document.getElementById('global-search').value, top_k: 10}">
    </div>
    <nav class="km-topbar-nav">
      <a href="#" hx-get="/api/stats" hx-target="#main-content" hx-swap="innerHTML" onclick="setActive(this)">Stats</a>
      <a href="#" hx-get="/api/health" hx-target="#main-content" hx-swap="innerHTML" onclick="setActive(this)">Health</a>
      <a href="#" hx-get="/api/recommendations" hx-target="#main-content" hx-swap="innerHTML" onclick="setActive(this)">Recs</a>
      <a href="#" onclick="setActive(this);renderGraph()">Graph</a>
    </nav>
  </header>

  <aside class="km-sidebar">
    <div class="km-dropzone" id="km-dropzone">
      <div class="km-dropzone-icon">📂</div>
      <div class="km-dropzone-text">Drop <strong>.md .txt .png</strong><br>to auto-extract</div>
    </div>
    <div class="km-sidebar-header">Knowledge Tree</div>
    <div id="sidebar-tree" class="km-tree">
      <div class="km-loading">Loading</div>
    </div>
  </aside>

  <main class="km-main" id="main-content">
    <div id="main-content">
      <div class="km-loading">Preparing dashboard</div>
    </div>
  </main>
</div>

<script>
  // ── Drop zone ──
  (function setupDropZone() {
    var dz = document.getElementById('km-dropzone');
    if (!dz) return;

    ['dragenter', 'dragover'].forEach(function(evt) {
      dz.addEventListener(evt, function(e) { e.preventDefault(); dz.classList.add('drag-over'); });
    });
    ['dragleave', 'drop'].forEach(function(evt) {
      dz.addEventListener(evt, function(e) { e.preventDefault(); dz.classList.remove('drag-over'); });
    });

    dz.addEventListener('drop', function(e) {
      var files = e.dataTransfer.files;
      for (var i = 0; i < files.length; i++) {
        uploadFile(files[i]);
      }
    });

    dz.addEventListener('click', function() {
      var input = document.createElement('input');
      input.type = 'file';
      input.accept = '.md,.txt,.png,.jpg,.jpeg,.gif,.webp';
      input.multiple = true;
      input.onchange = function() {
        for (var i = 0; i < input.files.length; i++) {
          uploadFile(input.files[i]);
        }
      };
      input.click();
    });
  })();

  function uploadFile(file) {
    var formData = new FormData();
    formData.append('file', file);
    formData.append('category', 'general');
    formData.append('mode', 'auto');

    showToast('info', 'Extracting...', 'Analyzing ' + file.name);

    var xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/upload');
    xhr.onload = function() {
      if (xhr.status === 200) {
        var data = JSON.parse(xhr.responseText);
        var mods = data.modules || [];
        var titles = mods.map(function(m) { return m.title; }).join(', ');
        showToast('success', 'Extracted ' + mods.length + ' module(s)',
          file.name + ' → ' + (titles || 'staging'));
        // Reload tree after 2s
        setTimeout(function() {
          var tx = new XMLHttpRequest();
          tx.open('GET', '/api/tree');
          tx.onload = function() {
            if (tx.status === 200) {
              document.getElementById('sidebar-tree').innerHTML = renderTree(JSON.parse(tx.responseText));
            }
          };
          tx.send();
        }, 2000);
      } else {
        showToast('error', 'Extraction failed', file.name + ': ' + xhr.status);
      }
    };
    xhr.onerror = function() {
      showToast('error', 'Upload failed', 'Could not reach server');
    };
    xhr.send(formData);
  }

  function showToast(type, title, detail) {
    var toast = document.createElement('div');
    toast.className = 'km-toast ' + type;
    toast.innerHTML = '<div class="km-toast-title">' + esc(title) + '</div>'
      + '<div class="km-toast-detail">' + esc(detail || '') + '</div>';
    document.body.appendChild(toast);
    setTimeout(function() { toast.style.opacity = '0'; toast.style.transition = 'opacity 0.3s'; }, 4000);
    setTimeout(function() { if (toast.parentNode) toast.parentNode.removeChild(toast); }, 4500);
  }

  var activeEl = null;

  function setActive(el) {
    if (activeEl) activeEl.classList.remove('active');
    el.classList.add('active');
    activeEl = el;
  }

  // Load tree on page start
  (function initTree() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/tree');
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var tree = JSON.parse(xhr.responseText);
          document.getElementById('sidebar-tree').innerHTML = renderTree(tree);
        } catch(e) { console.error('Tree render error:', e); }
      }
    };
    xhr.send();
  })();

  // Load dashboard on page start
  (function initDashboard() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/stats');
    xhr.onload = function() {
      if (xhr.status === 200) {
        try {
          var data = JSON.parse(xhr.responseText);
          document.getElementById('main-content').innerHTML = renderStats(data);
        } catch(e) { console.error('Dashboard render error:', e); }
      }
    };
    xhr.send();
  })();

  // Handle htmx responses for nav links and search
  document.body.addEventListener('htmx:afterSwap', function(evt) {
    if (evt.detail.target.id === 'main-content') {
      var ct = evt.detail.xhr.responseText.trim();
      if (ct.startsWith('{')) {
        try {
          var data = JSON.parse(ct);
          if (data.results) {
            document.getElementById('main-content').innerHTML = renderSearch(data);
          } else if (data.total_searches !== undefined) {
            document.getElementById('main-content').innerHTML = renderStats(data);
          } else if (data.overall_score !== undefined) {
            document.getElementById('main-content').innerHTML = renderHealth(data);
          } else if (data.archive_candidates !== undefined) {
            document.getElementById('main-content').innerHTML = renderRecommendations(data);
          } else if (data.title && data.content) {
            document.getElementById('main-content').innerHTML = renderModule(data);
          } else {
            document.getElementById('main-content').innerHTML = '<pre style="font-size:0.75rem;color:var(--text-tertiary)">' + JSON.stringify(data, null, 2) + '</pre>';
          }
        } catch(e) { console.error('Content render error:', e); }
      }
    }
  });

  var CAT_ICONS = {
    'general': '📦',
    'api': '🌐',
    'auth': '🔒',
    'database': '🗄',
    'deployment': '☁️',
    'architecture': '🏗',
    'backend': '⚙️',
    'frontend': '🎨',
    'devops': '🛠',
    'security': '🛡',
    'testing': '🧪',
    'decisions': '✏️',
    'operations': '📊',
    'default': '📄'
  };

  var CAT_LABELS = {
    'general': 'General',
    'api': 'API Design',
    'auth': 'Authentication',
    'database': 'Database',
    'deployment': 'Deployment',
    'architecture': 'Architecture',
    'backend': 'Backend',
    'frontend': 'Frontend',
    'devops': 'DevOps',
    'security': 'Security',
    'testing': 'Testing',
    'decisions': 'Decisions',
    'operations': 'Operations'
  };

  function catIcon(name) { return CAT_ICONS[name] || CAT_ICONS['default']; }
  function catLabel(name) { return CAT_LABELS[name] || name; }

  function renderTree(node) {
    var html = '';
    if (node.children) {
      node.children.forEach(function(cat) {
        var icon = catIcon(cat.title);
        var label = catLabel(cat.title);
        var count = cat.children ? cat.children.length : cat.module_count || 0;
        html += '<div class="km-tree-cat">';
        html += '<div class="km-tree-cat-header" onclick="toggleCat(this)">';
        html += '<span class="km-tree-cat-icon">' + icon + '</span>';
        html += '<span>' + esc(label) + '</span>';
        html += '<span class="km-tree-count">' + count + '</span>';
        html += '</div>';
        html += '<div class="km-tree-modules">';
        if (cat.children) {
          cat.children.forEach(function(mod) {
            html += '<div class="km-tree-leaf" data-path="' + esc(mod.path) + '" data-onclick-path="' + esc(mod.path) + '">'
              + esc(mod.title) + '</div>';
          });
        }
        html += '</div></div>';
      });
    }
    return html;
  }

  function toggleCat(header) {
    var modules = header.nextElementSibling;
    if (modules) modules.hidden = !modules.hidden;
  }

  // Delegated click handler for module navigation
  document.body.addEventListener('click', function(evt) {
    var el = evt.target.closest('[data-onclick-path]');
    if (el) {
      evt.stopPropagation();
      loadModule(el.getAttribute('data-onclick-path'));
      if (el.classList.contains('km-tree-leaf')) {
        document.querySelectorAll('.km-tree-leaf').forEach(function(l) { l.removeAttribute('data-active'); });
        el.setAttribute('data-active', '');
      }
    }
  });

  function renderSearch(data) {
    var html = '<div class="km-search-header">';
    html += '<h2>' + esc(data.query || 'Search') + '</h2>';
    html += '<span class="km-search-meta"><span class="km-pill">' + esc(data.intent || 'reference') + '</span> &middot; ' + (data.results ? data.results.length : 0) + ' results</span>';
    html += '</div>';
    if (!data.results || !data.results.length) {
      html += '<div class="km-empty"><div class="km-empty-icon">&#9906;</div><p>No results found</p></div>';
      return html;
    }
    data.results.forEach(function(r, i) {
      html += '<div class="km-result-card" data-onclick-path="' + esc(r.category) + '/' + esc(r.id) + '">';
      html += '<div class="km-result-index">' + (i + 1) + '</div>';
      html += '<div class="km-result-body">';
      html += '<div class="km-result-title">' + esc(r.title);
      html += '<span class="km-badge km-badge-' + r.confidence + '">' + r.confidence + '</span>';
      if (r.source === 'related') html += '<span class="km-badge km-badge-source">' + r.source + '</span>';
      html += '</div>';
      html += '<div class="km-result-snippet">' + esc(r.snippet || r.summary || '') + '</div>';
      html += '<div class="km-result-meta">' + esc(r.category) + '/' + esc(r.id) + '</div>';
      html += '</div></div>';
    });
    return html;
  }

  function renderStats(data) {
    var html = '<h2 style="font-family:var(--font-display);font-size:1.6rem;font-weight:400;margin-bottom:24px">Dashboard</h2>';
    html += '<div class="km-stats-grid">';
    html += '<div class="km-stat-card"><div class="km-stat-label">Searches (30d)</div><div class="km-stat-value accent">' + (data.total_searches || 0) + '</div></div>';
    html += '<div class="km-stat-card"><div class="km-stat-label">Module Loads</div><div class="km-stat-value">' + (data.total_loads || 0) + '</div></div>';
    html += '<div class="km-stat-card"><div class="km-stat-label">Conversion Rate</div><div class="km-stat-value">' + (data.conversion_rate || 0) + '<span style="font-size:1rem">%</span></div></div>';
    html += '<div class="km-stat-card"><div class="km-stat-label">Sessions</div><div class="km-stat-value">' + (data.total_sessions || 0) + '</div></div>';
    html += '</div>';

    if (data.top_modules && data.top_modules.length) {
      html += '<h3 style="font-family:var(--font-display);font-size:1.1rem;font-weight:400;margin:0 0 14px">Top Modules</h3>';
      data.top_modules.forEach(function(m) {
        html += '<div class="km-rec-item">' + esc(m.category) + '/' + esc(m.module_id) + ' &mdash; <strong>' + m.load_count + '</strong> loads</div>';
      });
    }

    if (data.daily_activity && data.daily_activity.length) {
      html += '<h3 style="font-family:var(--font-display);font-size:1.1rem;font-weight:400;margin:24px 0 14px">Recent Activity</h3>';
      data.daily_activity.slice(-7).forEach(function(d) {
        html += '<div class="km-rec-item">' + d.date + ' &mdash; ' + d.searches + ' searches, ' + d.loads + ' loads</div>';
      });
    }
    return html;
  }

  function renderHealth(data) {
    var scoreColor = data.overall_score >= 70 ? 'var(--accent-green)' : data.overall_score >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)';
    var html = '<div class="km-health-header">';
    html += '<h2>Health Report</h2>';
    html += '<div class="km-health-score" style="color:' + scoreColor + '">' + data.overall_score + '<span style="font-size:1rem">/100</span></div>';
    html += '<p style="color:var(--text-secondary);font-size:0.85rem;margin-top:4px">' + data.total_modules + ' modules across ' + data.total_categories + ' categories</p>';
    html += '</div>';

    if (data.category_breakdown) {
      html += '<h3 style="font-family:var(--font-display);font-size:1rem;font-weight:400;margin:20px 0 12px">Category Scores</h3>';
      html += '<div class="km-category-list">';
      var cats = data.category_breakdown;
      Object.keys(cats).sort().forEach(function(k) {
        var c = cats[k];
        html += '<div class="km-category-row">';
        html += '<span class="km-category-name">' + esc(k) + '</span>';
        html += '<div class="km-category-bar-bg"><div class="km-category-bar-fill" style="width:' + Math.max(c.avg_score, 2) + '%"></div></div>';
        html += '<span class="km-category-score">' + c.avg_score + '</span>';
        html += '</div>';
      });
      html += '</div>';
    }

    if (data.at_risk_modules && data.at_risk_modules.length) {
      html += '<h3 style="font-family:var(--font-display);font-size:1rem;font-weight:400;margin:24px 0 12px">At-Risk Modules (' + data.at_risk_modules.length + ')</h3>';
      html += '<div class="km-health-grid">';
      data.at_risk_modules.forEach(function(m) {
        html += '<div class="km-risk-card">';
        html += '<div class="km-risk-title">' + esc(m.title) + '</div>';
        html += '<div class="km-risk-meta">' + esc(m.category) + '/' + esc(m.module_id) + ' &middot; score ' + m.score.overall + '</div>';
        if (m.issues && m.issues.length) {
          html += '<div class="km-risk-issues">';
          m.issues.forEach(function(issue) { html += '<span>' + issue + '</span>'; });
          html += '</div>';
        }
        html += '</div>';
      });
      html += '</div>';
    }
    return html;
  }

  function renderRecommendations(data) {
    var html = '<h2 style="font-family:var(--font-display);font-size:1.6rem;font-weight:400;margin-bottom:24px">Recommendations</h2>';
    var sections = [
      {key: 'archive_candidates', title: 'Archive Candidates', icon: '&#9744;'},
      {key: 'enrichment_needed', title: 'Needs Enrichment', icon: '&#9998;'},
      {key: 'suggested_links', title: 'Suggested Links', icon: '&#8608;'},
      {key: 'review_reminders', title: 'Review Reminders', icon: '&#9200;'}
    ];
    sections.forEach(function(s) {
      var items = data[s.key] || [];
      if (items.length) {
        html += '<div class="km-recs-section">';
        html += '<h3>' + s.title + ' &middot; ' + items.length + '</h3>';
        items.slice(0, 10).forEach(function(r) {
          html += '<div class="km-rec-item">' + esc(r.module_id || r.title || '') + ' &mdash; <span style="color:var(--text-tertiary)">' + esc(r.reason || '') + '</span></div>';
        });
        html += '</div>';
      }
    });
    if (!sections.some(function(s) { return (data[s.key]||[]).length; })) {
      html += '<div class="km-empty"><p>No recommendations at this time</p></div>';
    }
    return html;
  }

  function renderModule(mod) {
    var html = '<div class="km-module">';
    html += '<div class="km-module-breadcrumb">' + esc(mod.category || '') + ' / ' + esc(mod.id || '') + '</div>';
    html += '<h1>' + esc(mod.title || '') + '</h1>';
    html += '<p class="km-module-summary">' + esc(mod.summary || '') + '</p>';

    html += '<div class="km-tags">';
    (mod.metadata && mod.metadata.tags || []).forEach(function(t) {
      html += '<span class="km-tag">' + esc(t) + '</span>';
    });
    if (mod.metadata) {
      html += '<span class="km-badge km-badge-' + (mod.metadata.confidence || 'medium') + '">' + (mod.metadata.confidence || 'medium') + '</span>';
      html += '<span class="km-badge km-badge-status">' + (mod.metadata.status || 'published') + '</span>';
    }
    html += '</div>';

    if (mod.content) {
      if (mod.content.overview) {
        html += '<div class="km-section"><h3>Overview</h3><p>' + esc(mod.content.overview) + '</p></div>';
      }
      if (mod.content.details) {
        html += '<div class="km-section"><h3>Details</h3><p>' + esc(mod.content.details) + '</p></div>';
      }
      if (mod.content.examples) {
        html += '<div class="km-section"><h3>Examples</h3><pre>' + esc(mod.content.examples) + '</pre></div>';
      }
      if (mod.content.caveats) {
        html += '<div class="km-caveat"><strong>Caution</strong><p>' + esc(mod.content.caveats) + '</p></div>';
      }
      if (mod.content.references) {
        html += '<div class="km-section"><h3>References</h3><p>' + esc(mod.content.references) + '</p></div>';
      }
    }

    if (mod.metadata && mod.metadata.related_modules && mod.metadata.related_modules.length) {
      html += '<div class="km-section"><h3>Related Modules</h3><div class="km-tags">';
      mod.metadata.related_modules.forEach(function(ref) {
        html += '<span class="km-tag km-related-tag" data-onclick-path="' + esc(ref) + '">' + esc(ref) + '</span>';
      });
      html += '</div></div>';
    }

    html += '</div>';
    return html;
  }

  function loadModule(path) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/modules/' + path);
    xhr.onload = function() {
      if (xhr.status === 200) {
        document.getElementById('main-content').innerHTML = renderModule(JSON.parse(xhr.responseText));
      } else {
        document.getElementById('main-content').innerHTML = '<div class="km-empty"><p>Module not found</p><div style="font-size:0.75rem;color:var(--text-tertiary)">' + esc(path) + '</div></div>';
      }
    };
    xhr.onerror = function() {
      document.getElementById('main-content').innerHTML = '<div class="km-empty"><p>Network error</p></div>';
    };
    xhr.send();
  }

  function esc(s) {
    if (typeof s !== 'string') return s;
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Knowledge Graph ──
  var cyInstance = null;

  function renderGraph() {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '/api/graph');
    xhr.onload = function() {
      if (xhr.status !== 200) return;
      var data = JSON.parse(xhr.responseText);
      var container = document.getElementById('main-content');
      container.innerHTML = '<div id="km-graph" style="width:100%;height:calc(100vh - 100px);border-radius:var(--radius-md);overflow:hidden;background:var(--bg-card);border:1px solid var(--border-subtle)"></div>';

      if (cyInstance) cyInstance.destroy();

      cyInstance = cytoscape({
        container: document.getElementById('km-graph'),
        elements: {
          nodes: (data.nodes || []).map(function(n) {
            return {
              data: { id: n.id, label: n.title || n.id, category: n.category || '', type: n.type || 'module' }
            };
          }),
          edges: (data.edges || []).map(function(e) {
            return { data: { source: e.source, target: e.target } };
          })
        },
        style: [
          { selector: 'node', style: {
            'label': 'data(label)',
            'text-valign': 'center',
            'text-halign': 'center',
            'font-size': '10px',
            'font-family': 'var(--font-body)',
            'color': '#e2e6f0',
            'background-color': '#4a90d9',
            'width': 'mapData(degree, 1, 10, 24, 48)',
            'height': 'mapData(degree, 1, 10, 24, 48)',
            'border-width': 2,
            'border-color': '#0b0d18',
            'text-wrap': 'wrap',
            'text-max-width': 100
          }},
          { selector: 'edge', style: {
            'width': 1,
            'line-color': 'rgba(255,255,255,0.08)',
            'curve-style': 'bezier',
            'target-arrow-color': 'rgba(255,255,255,0.15)',
            'target-arrow-shape': 'triangle'
          }},
          { selector: ':selected', style: {
            'border-color': '#e0a83a',
            'border-width': 3
          }}
        ],
        layout: { name: 'cose', animate: true, nodeRepulsion: 4000, idealEdgeLength: 80 },
        wheelSensitivity: 0.3
      });

      // Click to load module
      cyInstance.on('tap', 'node', function(evt) {
        var node = evt.target;
        var id = node.data('id');
        var cat = node.data('category');
        if (cat && id) loadModule(cat + '/' + id);
      });

      // Compute degree for sizing
      cyInstance.nodes().forEach(function(n) {
        n.data('degree', n.degree(true));
      });
    };
    xhr.send();
  }
</script>
</body>
</html>"""
