FALLBACK_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Knowledge Manager</title>
  <script src="https://cdn.jsdelivr.net/npm/htmx.org@1.9/dist/htmx.min.js"></script>
  <script src="https://cdn.jsdelivr.net/npm/alpinejs@3.x/dist/cdn.min.js" defer></script>
  <link href="https://cdn.jsdelivr.net/npm/water.css@2/out/water.min.css" rel="stylesheet">
  <style>
    .km-layout { display: flex; gap: 1rem; min-height: 80vh; }
    .km-sidebar { width: 260px; flex-shrink: 0; border-right: 1px solid #e5e7eb; padding-right: 1rem; overflow-y: auto; }
    .km-main { flex: 1; min-width: 0; }
    .km-module-card { border: 1px solid #e5e7eb; border-radius: 6px; padding: 0.75rem; margin-bottom: 0.5rem; cursor: pointer; }
    .km-module-card:hover { background: #f9fafb; }
    .km-badge { display: inline-block; padding: 2px 8px; border-radius: 9999px; font-size: 0.75rem; margin-right: 4px; }
    .km-badge-high { background: #dcfce7; color: #166534; }
    .km-badge-medium { background: #fef9c3; color: #854d0e; }
    .km-badge-low { background: #fee2e2; color: #991b1b; }
    .km-caveat { background: #fef3c7; border-left: 3px solid #f59e0b; padding: 0.5rem 1rem; margin: 1rem 0; }
    .km-section { margin: 1rem 0; }
    .km-tags { margin: 0.5rem 0; }
    .km-tag { display: inline-block; background: #e5e7eb; padding: 1px 8px; border-radius: 4px; font-size: 0.8rem; margin-right: 4px; }
    .km-search { width: 100%; padding: 0.5rem; margin-bottom: 1rem; border: 1px solid #d1d5db; border-radius: 4px; }
    .km-tree-item { padding: 0.25rem 0; cursor: pointer; }
    .km-tree-item:hover { color: #3b82f6; }
    .km-related { margin-top: 1rem; }
    .km-stats-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 1rem; margin: 1rem 0; }
    .km-stat-card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 1rem; text-align: center; }
    .km-stat-value { font-size: 2rem; font-weight: bold; }
    .km-risk-item { padding: 0.5rem; border-left: 3px solid #ef4444; margin: 0.5rem 0; background: #fef2f2; }
    .km-module-detail h1 { margin-bottom: 0.25rem; }
    .km-module-detail .km-summary { color: #6b7280; font-size: 1.1rem; margin-bottom: 1rem; }
    @media (max-width: 768px) {
      .km-layout { flex-direction: column; }
      .km-sidebar { width: 100%; border-right: none; border-bottom: 1px solid #e5e7eb; padding-bottom: 1rem; }
    }
  </style>
</head>
<body>
  <header>
    <h1>Knowledge Manager</h1>
    <nav>
      <a href="#" hx-get="/api/stats" hx-target="#main-content" hx-swap="innerHTML">Stats</a> |
      <a href="#" hx-get="/api/health" hx-target="#main-content" hx-swap="innerHTML">Health</a> |
      <a href="#" hx-get="/api/recommendations" hx-target="#main-content" hx-swap="innerHTML">Recommendations</a>
    </nav>
  </header>

  <div class="km-layout">
    <aside class="km-sidebar">
      <input type="search" class="km-search" placeholder="Search modules..."
        name="query"
        hx-post="/api/search"
        hx-trigger="keyup changed delay:300ms"
        hx-target="#main-content"
        hx-swap="innerHTML"
        hx-vals="js:{query: document.querySelector('.km-search').value, top_k: 10}" />

      <div id="sidebar-tree"
        hx-get="/api/tree"
        hx-trigger="load"
        hx-swap="innerHTML">
        <p>Loading...</p>
      </div>
    </aside>

    <main class="km-main" id="main-content">
      <div id="dashboard"
        hx-get="/api/stats"
        hx-trigger="load"
        hx-swap="innerHTML">
        <p>Loading knowledge base...</p>
      </div>
    </main>
  </div>

  <script>
    // Render tree from /api/tree JSON response
    document.body.addEventListener('htmx:afterSwap', function(evt) {
      if (evt.detail.target.id === 'sidebar-tree') {
        try {
          var tree = JSON.parse(evt.detail.xhr.responseText);
          var html = renderTree(tree);
          document.getElementById('sidebar-tree').innerHTML = html;
        } catch(e) {}
      }
      if (evt.detail.target.id === 'main-content') {
        var ct = evt.detail.xhr.responseText.trim();
        if (ct.startsWith('{')) {
          try {
            var data = JSON.parse(ct);
            // Check if it's a search result or stats
            if (data.results) {
              document.getElementById('main-content').innerHTML = renderSearchResults(data);
            } else if (data.total_searches !== undefined) {
              document.getElementById('main-content').innerHTML = renderStats(data);
            } else if (data.overall_score !== undefined) {
              document.getElementById('main-content').innerHTML = renderHealth(data);
            } else if (data.archive_candidates !== undefined) {
              document.getElementById('main-content').innerHTML = renderRecommendations(data);
            } else if (data.title && data.content) {
              document.getElementById('main-content').innerHTML = renderModule(data);
            } else {
              document.getElementById('main-content').innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            }
          } catch(e) {}
        }
      }
    });

    function renderTree(node) {
      var html = '<div class="km-tree">';
      if (node.children) {
        node.children.forEach(function(child) {
          html += '<details open><summary class="km-tree-item"><strong>' + esc(child.title) + '</strong>';
          if (child.module_count) html += ' <small>(' + child.module_count + ')</small>';
          html += '</summary>';
          if (child.children) {
            child.children.forEach(function(mod) {
              html += '<div class="km-tree-item" style="padding-left:1rem" onclick="loadModule(\'' + esc(mod.path) + '\')">'
                + esc(mod.title) + '</div>';
            });
          }
          html += '</details>';
        });
      }
      html += '</div>';
      return html;
    }

    function renderSearchResults(data) {
      var html = '<h2>Search: ' + esc(data.query) + '</h2>';
      html += '<p><small>Intent: ' + esc(data.intent) + '</small></p>';
      if (!data.results.length) return html + '<p>No results found.</p>';
      data.results.forEach(function(r) {
        html += '<div class="km-module-card" onclick="loadModule(\'' + esc(r.category) + '/' + esc(r.id) + '\')">';
        html += '<strong>' + esc(r.title) + '</strong> ';
        html += '<span class="km-badge km-badge-' + r.confidence + '">' + r.confidence + '</span>';
        if (r.source === 'related') html += '<span class="km-badge">related</span>';
        html += '<br><small>' + esc(r.snippet || r.summary) + '</small>';
        html += '<br><small>' + esc(r.category) + '/' + esc(r.id) + '</small>';
        html += '</div>';
      });
      return html;
    }

    function renderStats(data) {
      var html = '<h2>KB Stats</h2>';
      html += '<div class="km-stats-grid">';
      html += '<div class="km-stat-card"><div class="km-stat-value">' + data.total_searches + '</div><small>Searches</small></div>';
      html += '<div class="km-stat-card"><div class="km-stat-value">' + data.total_loads + '</div><small>Loads</small></div>';
      html += '<div class="km-stat-card"><div class="km-stat-value">' + data.conversion_rate + '%</div><small>Conversion</small></div>';
      html += '<div class="km-stat-card"><div class="km-stat-value">' + data.total_sessions + '</div><small>Sessions</small></div>';
      html += '</div>';
      if (data.top_modules && data.top_modules.length) {
        html += '<h3>Top Modules</h3><ul>';
        data.top_modules.forEach(function(m) {
          html += '<li>' + esc(m.category) + '/' + esc(m.module_id) + ' — ' + m.load_count + ' loads</li>';
        });
        html += '</ul>';
      }
      return html;
    }

    function renderHealth(data) {
      var html = '<h2>Health Report</h2>';
      html += '<p>Overall Score: <strong>' + data.overall_score + '/100</strong> | '
        + data.total_modules + ' modules | ' + data.total_categories + ' categories</p>';
      if (data.at_risk_modules && data.at_risk_modules.length) {
        html += '<h3>At-Risk Modules (' + data.at_risk_modules.length + ')</h3>';
        data.at_risk_modules.forEach(function(m) {
          html += '<div class="km-risk-item"><strong>' + esc(m.category) + '/' + esc(m.module_id) + '</strong>'
            + ' — ' + esc(m.title) + '<br><small>Score: ' + m.score.overall + ' | Issues: ' + (m.issues||[]).join(', ') + '</small></div>';
        });
      }
      return html;
    }

    function renderRecommendations(data) {
      var html = '<h2>Recommendations</h2>';
      var sections = [
        {key: 'archive_candidates', title: 'Archive Candidates', icon: ''},
        {key: 'enrichment_needed', title: 'Needs Enrichment', icon: ''},
        {key: 'suggested_links', title: 'Suggested Links', icon: ''},
        {key: 'review_reminders', title: 'Review Reminders', icon: ''}
      ];
      sections.forEach(function(s) {
        var items = data[s.key] || [];
        if (items.length) {
          html += '<h3>' + s.title + ' (' + items.length + ')</h3><ul>';
          items.slice(0, 10).forEach(function(r) {
            html += '<li>' + esc(r.module_id || r.title) + ' — ' + esc(r.reason) + ' (' + r.score.toFixed(2) + ')</li>';
          });
          html += '</ul>';
        }
      });
      return html;
    }

    function renderModule(module) {
      var html = '<div class="km-module-detail">';
      html += '<p><small>' + esc(module.category) + '/' + esc(module.id) + '</small></p>';
      html += '<h1>' + esc(module.title) + '</h1>';
      html += '<p class="km-summary">' + esc(module.summary) + '</p>';
      html += '<div class="km-tags">';
      (module.metadata.tags || []).forEach(function(t) { html += '<span class="km-tag">' + esc(t) + '</span>'; });
      html += '<span class="km-badge km-badge-' + module.metadata.confidence + '">' + module.metadata.confidence + '</span>';
      html += '<span class="km-badge">' + module.metadata.status + '</span>';
      html += '</div>';
      if (module.content) {
        html += '<div class="km-section"><h3>Overview</h3><p>' + esc(module.content.overview || '') + '</p></div>';
        html += '<div class="km-section"><h3>Details</h3><p>' + esc(module.content.details || '') + '</p></div>';
        if (module.content.examples) html += '<div class="km-section"><h3>Examples</h3><pre>' + esc(module.content.examples) + '</pre></div>';
        if (module.content.caveats) html += '<div class="km-caveat"><strong>Caution</strong><br>' + esc(module.content.caveats) + '</div>';
        if (module.content.references) html += '<div class="km-section"><h3>References</h3><p>' + esc(module.content.references) + '</p></div>';
      }
      if (module.metadata.related_modules && module.metadata.related_modules.length) {
        html += '<div class="km-related"><h3>Related Modules</h3>';
        module.metadata.related_modules.forEach(function(ref) {
          html += '<span class="km-tag" style="cursor:pointer" onclick="loadModule(\'' + esc(ref) + '\')">' + esc(ref) + '</span> ';
        });
        html += '</div>';
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
          document.getElementById('main-content').innerHTML = '<p style="color:red">Module not found: ' + esc(path) + '</p>';
        }
      };
      xhr.onerror = function() {
        document.getElementById('main-content').innerHTML = '<p style="color:red">Network error loading module</p>';
      };
      xhr.send();
    }

    function esc(s) {
      if (typeof s !== 'string') return s;
      return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
  </script>
</body>
</html>"""
