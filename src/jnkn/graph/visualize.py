# FILE: src/jnkn/graph/visualize.py
"""
Visualization Engine v3.3

A professional-grade Miller Columns interface for exploring dependency graphs.

Key Features:
- Bi-directional Traversal: Switch between Impact (Downstream) and Dependency (Upstream).
- Global Search: Fuzzy find artifacts and jump to them in the graph.
- Diff Context: Visual highlights for Added, Removed, and Modified nodes.
- Rich Inspector: Tabbed view for Details, Upstream, and Downstream dependencies.
- Neighborhood Mesh: Force-directed graph view for analyzing local complexity.
"""

import json
import webbrowser
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ..core.interfaces import IGraph

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jnkn Impact Browser</title>
    <script src="https://d3js.org/d3.v7.min.js"></script>
    <style>
        /* ============================================================
           DESIGN SYSTEM
           ============================================================ */
        :root {
            /* Core palette */
            --bg-base: #0a0a0a;
            --bg-elevated: #111111;
            --bg-surface: #171717;
            --bg-hover: #1f1f1f;
            --bg-active: #262626;
            
            /* Borders */
            --border-subtle: #262626;
            --border-default: #333333;
            --border-focus: #525252;
            
            /* Text */
            --text-primary: #fafafa;
            --text-secondary: #a1a1aa;
            --text-tertiary: #71717a;
            
            /* Semantic colors */
            --color-danger: #ef4444;
            --color-danger-bg: rgba(239, 68, 68, 0.1);
            --color-warning: #f59e0b;
            --color-warning-bg: rgba(245, 158, 11, 0.1);
            --color-success: #22c55e;
            --color-success-bg: rgba(34, 197, 94, 0.1);
            --color-info: #3b82f6;
            --color-info-bg: rgba(59, 130, 246, 0.1);
            
            /* Diff colors */
            --diff-added-bg: rgba(34, 197, 94, 0.15);
            --diff-added-border: #22c55e;
            --diff-removed-bg: rgba(239, 68, 68, 0.15);
            --diff-removed-border: #ef4444;
            --diff-mod-bg: rgba(245, 158, 11, 0.15);
            --diff-mod-border: #f59e0b;
            
            /* Accent */
            --accent: #3b82f6;
            --accent-hover: #2563eb;
            
            /* Domain colors */
            --domain-infra: #f59e0b;
            --domain-config: #22c55e;
            --domain-code: #3b82f6;
            --domain-data: #a855f7;
            
            /* Typography */
            --font-sans: -apple-system, BlinkMacSystemFont, "Segoe UI", "Inter", Roboto, sans-serif;
            --font-mono: "SF Mono", "Fira Code", monospace;
            
            /* Spacing */
            --radius-md: 6px;
        }

        * { box-sizing: border-box; }
        
        body {
            margin: 0;
            padding: 0;
            height: 100vh;
            background: var(--bg-base);
            color: var(--text-primary);
            font-family: var(--font-sans);
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }

        /* HEADER */
        .header {
            height: 56px;
            border-bottom: 1px solid var(--border-subtle);
            display: flex;
            align-items: center;
            padding: 0 16px;
            background: var(--bg-elevated);
            gap: 16px;
        }
        
        .brand {
            display: flex;
            align-items: center;
            gap: 10px;
            font-weight: 700;
            font-size: 16px;
        }
        
        .brand-logo {
            width: 24px;
            height: 24px;
            background: linear-gradient(135deg, var(--accent) 0%, #8b5cf6 100%);
            border-radius: 4px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }

        /* Mode Toggle */
        .mode-toggle {
            display: flex;
            background: var(--bg-surface);
            border-radius: 6px;
            padding: 2px;
            border: 1px solid var(--border-default);
        }
        
        .mode-btn {
            background: transparent;
            border: none;
            color: var(--text-secondary);
            padding: 4px 12px;
            font-size: 12px;
            font-weight: 500;
            cursor: pointer;
            border-radius: 4px;
            transition: all 0.2s;
        }
        
        .mode-btn.active {
            background: var(--bg-active);
            color: var(--text-primary);
            box-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }

        /* Search Bar */
        .search-container {
            flex: 1;
            max-width: 400px;
            position: relative;
        }
        
        .search-input {
            width: 100%;
            background: var(--bg-base);
            border: 1px solid var(--border-default);
            padding: 6px 12px 6px 32px;
            border-radius: 6px;
            color: var(--text-primary);
            font-size: 13px;
        }
        
        .search-input:focus {
            border-color: var(--accent);
            outline: none;
        }
        
        .search-icon {
            position: absolute;
            left: 10px;
            top: 50%;
            transform: translateY(-50%);
            color: var(--text-tertiary);
            font-size: 12px;
        }
        
        /* Search Results Dropdown */
        .search-results {
            position: absolute;
            top: 100%;
            left: 0;
            width: 100%;
            background: var(--bg-elevated);
            border: 1px solid var(--border-default);
            border-radius: 6px;
            margin-top: 4px;
            max-height: 300px;
            overflow-y: auto;
            display: none;
            z-index: 1000;
            box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
        }
        
        .search-item {
            padding: 8px 12px;
            cursor: pointer;
            font-size: 13px;
            border-bottom: 1px solid var(--border-subtle);
        }
        
        .search-item:hover { background: var(--bg-hover); }
        .search-item small { color: var(--text-tertiary); display: block; font-size: 11px; }

        /* MILLER COLUMNS */
        .main-container {
            flex: 1;
            display: flex;
            overflow: hidden;
        }
        
        .columns-wrapper {
            flex: 1;
            display: flex;
            overflow-x: auto;
            scroll-behavior: smooth;
        }
        
        .column {
            width: 320px;
            min-width: 320px;
            border-right: 1px solid var(--border-subtle);
            background: var(--bg-elevated);
            display: flex;
            flex-direction: column;
        }
        
        .column:nth-child(odd) { background: var(--bg-base); }
        
        .column-header {
            padding: 12px 16px;
            border-bottom: 1px solid var(--border-subtle);
            font-size: 11px;
            font-weight: 600;
            text-transform: uppercase;
            color: var(--text-tertiary);
            display: flex;
            justify-content: space-between;
        }
        
        .column-list {
            flex: 1;
            overflow-y: auto;
            padding: 8px;
        }

        /* ITEMS */
        .item {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            margin-bottom: 2px;
            border-radius: 6px;
            cursor: pointer;
            border: 1px solid transparent;
            font-size: 13px;
        }
        
        .item:hover { background: var(--bg-hover); }
        .item.active { background: var(--bg-active); border-color: var(--border-default); }
        
        /* Diff States */
        .item.diff-added { background: var(--diff-added-bg); border-left: 3px solid var(--diff-added-border); }
        .item.diff-removed { background: var(--diff-removed-bg); border-left: 3px solid var(--diff-removed-border); opacity: 0.7; }
        .item.diff-modified { background: var(--diff-mod-bg); border-left: 3px solid var(--diff-mod-border); }
        
        .item-icon { margin-right: 10px; font-size: 16px; }
        .item-content { flex: 1; min-width: 0; }
        .item-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-weight: 500; }
        .item-meta { font-size: 11px; color: var(--text-tertiary); margin-top: 2px; }
        
        .badge {
            font-size: 9px;
            padding: 2px 6px;
            border-radius: 4px;
            margin-left: 6px;
            text-transform: uppercase;
            font-weight: 600;
        }
        
        .badge.runtime { background: rgba(139, 92, 246, 0.2); color: #a78bfa; border: 1px solid rgba(139, 92, 246, 0.3); }
        .badge.static { background: rgba(113, 113, 122, 0.2); color: #a1a1aa; }
        .badge.low-conf { background: var(--color-warning-bg); color: var(--color-warning); }

        /* INSPECTOR */
        .inspector {
            width: 420px;
            min-width: 420px;
            background: var(--bg-elevated);
            border-left: 1px solid var(--border-subtle);
            display: none;
            flex-direction: column;
        }
        
        .inspector-header {
            padding: 20px;
            border-bottom: 1px solid var(--border-subtle);
        }
        
        .inspector-title { font-size: 18px; font-weight: 600; margin-bottom: 4px; word-break: break-all; }
        .inspector-subtitle { font-size: 12px; color: var(--text-tertiary); font-family: var(--font-mono); }
        
        .action-bar { display: flex; gap: 8px; margin-top: 16px; }
        .btn {
            flex: 1; padding: 8px; border-radius: 6px; border: 1px solid var(--border-default);
            background: var(--bg-surface); color: var(--text-secondary); cursor: pointer;
            font-size: 12px; font-weight: 500; display: flex; align-items: center; justify-content: center; gap: 6px;
        }
        .btn:hover { background: var(--bg-hover); color: var(--text-primary); }
        .btn-primary { background: var(--accent); color: white; border-color: var(--accent); }
        .btn-primary:hover { background: var(--accent-hover); }

        /* TABS */
        .tabs { display: flex; border-bottom: 1px solid var(--border-subtle); background: var(--bg-surface); }
        .tab {
            flex: 1; padding: 12px; text-align: center; font-size: 12px; font-weight: 600;
            color: var(--text-tertiary); cursor: pointer; border-bottom: 2px solid transparent;
        }
        .tab.active { color: var(--text-primary); border-bottom-color: var(--accent); }
        
        .tab-content { padding: 20px; flex: 1; overflow-y: auto; display: none; }
        .tab-content.active { display: block; }

        /* DETAILS LIST */
        .detail-row { display: flex; margin-bottom: 12px; font-size: 13px; }
        .detail-label { width: 100px; color: var(--text-tertiary); flex-shrink: 0; }
        .detail-value { flex: 1; color: var(--text-secondary); word-break: break-all; }
        
        /* Dependency List Item in Tabs */
        .dep-list-item {
            padding: 8px; border-radius: 4px; margin-bottom: 4px; background: var(--bg-surface);
            font-size: 12px; display: flex; justify-content: space-between; align-items: center;
            cursor: pointer;
        }
        .dep-list-item:hover { background: var(--bg-hover); }

        /* MODAL (Force Directed Graph) */
        .modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0, 0, 0, 0.8); z-index: 1000;
            display: none; align-items: center; justify-content: center;
        }
        .modal-content {
            width: 90vw; height: 90vh; background: var(--bg-base);
            border-radius: 8px; border: 1px solid var(--border-default);
            display: flex; flex-direction: column;
        }
        .modal-header {
            padding: 16px; border-bottom: 1px solid var(--border-subtle);
            display: flex; justify-content: space-between; align-items: center;
        }
        #mesh-container { flex: 1; overflow: hidden; background: #050505; }
        
        /* D3 Graph Styles */
        .node circle { stroke: #fff; stroke-width: 1.5px; cursor: pointer; }
        .link { stroke: #555; stroke-opacity: 0.6; }
        .node text { font-size: 10px; fill: #aaa; pointer-events: none; }
    </style>
</head>
<body>
    <header class="header">
        <div class="brand">
            <div class="brand-logo">J</div>
            <span>Jnkn Impact Browser</span>
        </div>
        
        <div class="mode-toggle">
            <button class="mode-btn active" onclick="setMode('downstream')">
                Impact (Downstream)
            </button>
            <button class="mode-btn" onclick="setMode('upstream')">
                Dependency (Upstream)
            </button>
        </div>
        
        <div class="search-container">
            <span class="search-icon">🔍</span>
            <input type="text" class="search-input" placeholder="Search resources, tables, files..." onkeyup="handleSearch(this.value)">
            <div class="search-results" id="searchResults"></div>
        </div>
    </header>
    
    <main class="main-container">
        <div class="columns-wrapper" id="columnsWrapper"></div>
        
        <aside class="inspector" id="inspector">
            <div class="inspector-header">
                <div class="inspector-title" id="insp-title">Select an item</div>
                <div class="inspector-subtitle" id="insp-id"></div>
                
                <div class="action-bar">
                    <button class="btn btn-primary" id="btn-editor" onclick="openEditor()">
                        <span>📝</span> Editor
                    </button>
                    <button class="btn" onclick="openMeshModal()">
                        <span>🕸️</span> Neighborhood
                    </button>
                </div>
            </div>
            
            <div class="tabs">
                <div class="tab active" onclick="switchTab('details')">Details</div>
                <div class="tab" id="tab-up-count" onclick="switchTab('upstream')">Upstream (0)</div>
                <div class="tab" id="tab-down-count" onclick="switchTab('downstream')">Downstream (0)</div>
            </div>
            
            <div id="view-details" class="tab-content active"></div>
            <div id="view-upstream" class="tab-content"></div>
            <div id="view-downstream" class="tab-content"></div>
        </aside>
    </main>

    <div class="modal-overlay" id="meshModal">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Neighborhood View</h3>
                <button class="btn" style="width: auto;" onclick="closeMeshModal()">Close</button>
            </div>
            <div id="mesh-container"></div>
        </div>
    </div>

    <script>
        // DATA
        const rawData = __GRAPH_DATA__;
        
        // STATE
        let state = {
            mode: 'downstream', // 'downstream' or 'upstream'
            nodeMap: {},
            outgoingEdges: {}, // Source -> [Edges]
            incomingEdges: {}, // Target -> [Edges]
            currentNode: null
        };

        // INITIALIZATION
        window.onload = function() {
            indexData(rawData);
            renderRootColumn();
        };

        function indexData(data) {
            data.nodes.forEach(n => state.nodeMap[n.id] = n);
            
            if (data.edges) {
                data.edges.forEach(e => {
                    if (!state.outgoingEdges[e.source_id]) state.outgoingEdges[e.source_id] = [];
                    state.outgoingEdges[e.source_id].push(e);
                    
                    if (!state.incomingEdges[e.target_id]) state.incomingEdges[e.target_id] = [];
                    state.incomingEdges[e.target_id].push(e);
                });
            }
        }

        // ============================================================
        // LOGIC & NAVIGATION
        // ============================================================
        window.setMode = function(mode) {
            state.mode = mode;
            document.querySelectorAll('.mode-btn').forEach(btn => {
                btn.classList.toggle('active', btn.innerText.toLowerCase().includes(mode));
            });
            
            // If we have a selection, try to re-render flow from root
            // But simpler is just reset to root to avoid confusion
            renderRootColumn();
        };

        // Search
        window.handleSearch = function(query) {
            const resultsDiv = document.getElementById('searchResults');
            if (query.length < 2) {
                resultsDiv.style.display = 'none';
                return;
            }
            
            const matches = rawData.nodes.filter(n => 
                n.name.toLowerCase().includes(query.toLowerCase()) || 
                n.id.toLowerCase().includes(query.toLowerCase())
            ).slice(0, 10);
            
            if (matches.length > 0) {
                resultsDiv.innerHTML = matches.map(n => `
                    <div class="search-item" onclick="jumpToNode('${n.id}')">
                        <div>${n.name}</div>
                        <small>${n.id}</small>
                    </div>
                `).join('');
                resultsDiv.style.display = 'block';
            } else {
                resultsDiv.style.display = 'none';
            }
        };

        window.jumpToNode = function(nodeId) {
            document.getElementById('searchResults').style.display = 'none';
            document.querySelector('.search-input').value = '';
            
            const node = state.nodeMap[nodeId];
            if (node) {
                // Reset flow and show this node
                renderRootColumn(); 
                
                // Simulate selection
                state.currentNode = node;
                updateInspector(node);
                
                // Try to expand the category in the root column that contains this node
                const groups = {
                    'Infrastructure': node.type.includes('infra') || node.id.startsWith('infra:'),
                    'Configuration': node.type.includes('env') || node.type.includes('config') || node.id.startsWith('env:'),
                    'Data': node.type.includes('data') || node.id.startsWith('data:'),
                };
                
                let category = 'Code'; // Default
                for(let k in groups) if(groups[k]) category = k;
                
                // Highlight the category if possible (requires finding DOM element)
                // For now, just showing the inspector is a huge win
            }
        };

        // ============================================================
        // MILLER COLUMNS LOGIC
        // ============================================================
        function renderRootColumn() {
            const wrapper = document.getElementById('columnsWrapper');
            wrapper.innerHTML = ''; // Clear all
            
            // Group by Domain
            const groups = { 'Infrastructure': [], 'Configuration': [], 'Code': [], 'Data': [] };
            
            rawData.nodes.forEach(n => {
                const t = (n.type || '').toLowerCase();
                const id = n.id.toLowerCase();
                if (t.includes('infra') || id.startsWith('infra:')) groups['Infrastructure'].push(n);
                else if (t.includes('env') || t.includes('config') || id.startsWith('env:')) groups['Configuration'].push(n);
                else if (t.includes('data') || id.startsWith('data:')) groups['Data'].push(n);
                else groups['Code'].push(n);
            });
            
            const col = createColumn('Domains', rawData.nodes.length);
            
            Object.keys(groups).forEach(key => {
                if (groups[key].length === 0) return;
                const item = document.createElement('div');
                item.className = 'item';
                item.innerHTML = `
                    <span class="item-icon">${getCategoryIcon(key)}</span>
                    <div class="item-content"><div class="item-title">${key}</div></div>
                    <div class="item-meta">${groups[key].length}</div>
                    <span style="margin-left:8px; color:#666;">›</span>
                `;
                
                // Root items are always at index 0
                item.onclick = () => {
                    highlightItem(item);
                    renderNodeList(groups[key], key, 0); 
                };
                col.querySelector('.column-list').appendChild(item);
            });
            wrapper.appendChild(col);
            
            // Hide inspector on reset
            document.getElementById('inspector').style.display = 'none';
        }

        function renderNodeList(nodes, title, parentColIndex) {
            // Remove columns that came after the parent of this new list
            removeColumnsAfter(parentColIndex);
            
            const col = createColumn(title, nodes.length);
            const myColIndex = parentColIndex + 1;
            
            nodes.sort((a, b) => a.name.localeCompare(b.name));
            
            nodes.forEach(node => {
                const item = createNodeItem(node);
                item.onclick = () => {
                    highlightItem(item);
                    state.currentNode = node;
                    updateInspector(node);
                    renderConnections(node, myColIndex);
                };
                col.querySelector('.column-list').appendChild(item);
            });
            
            document.getElementById('columnsWrapper').appendChild(col);
            col.scrollIntoView({behavior: 'smooth', inline: 'end'});
        }

        function renderConnections(node, parentColIndex) {
            removeColumnsAfter(parentColIndex);
            
            let connections = [];
            let title = "";
            
            if (state.mode === 'downstream') {
                // Outgoing: What does this node affect?
                const edges = state.outgoingEdges[node.id] || [];
                connections = edges.map(e => ({ node: state.nodeMap[e.target_id], edge: e }));
                title = `Impacts (${connections.length})`;
            } else {
                // Incoming: What does this node depend on?
                const edges = state.incomingEdges[node.id] || [];
                connections = edges.map(e => ({ node: state.nodeMap[e.source_id], edge: e }));
                title = `Depends On (${connections.length})`;
            }
            
            if (connections.length === 0) return;
            
            const col = createColumn(title, connections.length);
            const myColIndex = parentColIndex + 1;
            
            // Sort by confidence
            connections.sort((a, b) => (b.edge.confidence || 0) - (a.edge.confidence || 0));
            
            connections.forEach(({node, edge}) => {
                if (!node) return;
                const item = createNodeItem(node, edge);
                
                item.onclick = () => {
                    highlightItem(item);
                    state.currentNode = node;
                    updateInspector(node, edge);
                    renderConnections(node, myColIndex);
                };
                
                col.querySelector('.column-list').appendChild(item);
            });
            
            document.getElementById('columnsWrapper').appendChild(col);
            col.scrollIntoView({behavior: 'smooth', inline: 'end'});
        }

        // ============================================================
        // DOM HELPERS
        // ============================================================
        function createColumn(title, count) {
            const div = document.createElement('div');
            div.className = 'column';
            div.innerHTML = `
                <div class="column-header">
                    <span>${title}</span>
                    ${count !== undefined ? `<span style="opacity:0.6">${count}</span>` : ''}
                </div>
                <div class="column-list"></div>
            `;
            return div;
        }

        function createNodeItem(node, edge) {
            const div = document.createElement('div');
            
            // Diff Highlighting
            let classes = 'item';
            if (node.metadata?.change_type === 'added') classes += ' diff-added';
            if (node.metadata?.change_type === 'removed') classes += ' diff-removed';
            if (node.metadata?.change_type === 'modified') classes += ' diff-modified';
            
            div.className = classes;
            
            // Badges
            let badge = '';
            if (edge && edge.metadata?.source === 'openlineage') {
                badge = `<span class="badge runtime">Runtime</span>`;
            } else if (edge) {
                const conf = edge.confidence || 1.0;
                if (conf < 0.5) badge = `<span class="badge low-conf">Low Conf</span>`;
            }

            const icon = getNodeIcon(node.type);
            div.innerHTML = `
                <span class="item-icon">${icon}</span>
                <div class="item-content">
                    <div class="item-title">${node.name}</div>
                    <div class="item-meta">${node.type}</div>
                </div>
                ${badge}
                <span style="color:var(--text-tertiary)">›</span>
            `;
            return div;
        }

        function highlightItem(item) {
            const list = item.parentElement;
            Array.from(list.children).forEach(c => c.classList.remove('active'));
            item.classList.add('active');
        }

        function removeColumnsAfter(index) {
            const wrapper = document.getElementById('columnsWrapper');
            while (wrapper.children.length > index + 1) {
                wrapper.removeChild(wrapper.lastChild);
            }
        }

        // ============================================================
        // INSPECTOR LOGIC
        // ============================================================
        function updateInspector(node, contextEdge = null) {
            document.getElementById('inspector').style.display = 'flex';
            
            // Header
            document.getElementById('insp-title').textContent = node.name;
            document.getElementById('insp-id').textContent = node.id;
            
            // Editor Button
            const btnEditor = document.getElementById('btn-editor');
            if (node.path) {
                btnEditor.disabled = false;
                btnEditor.title = node.path;
            } else {
                btnEditor.disabled = true;
                btnEditor.title = "No file path available";
            }

            // Update Counts for Tabs
            const upEdges = state.incomingEdges[node.id] || [];
            const downEdges = state.outgoingEdges[node.id] || [];
            
            document.getElementById('tab-up-count').textContent = `Upstream (${upEdges.length})`;
            document.getElementById('tab-down-count').textContent = `Downstream (${downEdges.length})`;

            // Render Details Tab
            const detailsHtml = `
                <div class="detail-row">
                    <span class="detail-label">Type</span>
                    <span class="detail-value">${node.type}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">File</span>
                    <span class="detail-value">${node.path || '-'}</span>
                </div>
                <div class="detail-row">
                    <span class="detail-label">Line</span>
                    <span class="detail-value">${node.metadata?.line || '-'}</span>
                </div>
                ${contextEdge ? `
                <div style="margin-top: 20px; padding: 12px; background: var(--bg-surface); border-radius: 6px; border: 1px solid var(--border-default);">
                    <div style="font-size: 11px; font-weight: 600; color: var(--text-tertiary); margin-bottom: 8px;">CONNECTION STRENGTH</div>
                    <div style="display: flex; justify-content: space-between; margin-bottom: 4px; font-size: 13px;">
                        <span>Confidence</span>
                        <strong>${Math.round((contextEdge.confidence || 1) * 100)}%</strong>
                    </div>
                    <div style="height: 6px; background: var(--bg-active); border-radius: 3px; overflow: hidden;">
                        <div style="height: 100%; width: ${(contextEdge.confidence || 1) * 100}%; background: var(--accent);"></div>
                    </div>
                    <div style="margin-top: 8px; font-size: 11px; color: var(--text-tertiary);">
                        ${contextEdge.metadata?.explanation || 'Link detected via static analysis.'}
                    </div>
                </div>
                ` : ''}
                
                ${node.metadata?.change_type ? `
                <div style="margin-top: 20px; padding: 10px; background: var(--bg-active); border-radius: 6px;">
                    <strong>Change Detected</strong><br>
                    Status: <span style="text-transform:uppercase; font-size:11px;">${node.metadata.change_type}</span>
                </div>
                ` : ''}
            `;
            document.getElementById('view-details').innerHTML = detailsHtml;

            // Render Upstream List
            renderTabList('view-upstream', upEdges, 'source_id');
            // Render Downstream List
            renderTabList('view-downstream', downEdges, 'target_id');
            
            // Reset to details tab
            switchTab('details');
        }

        function renderTabList(elementId, edges, key) {
            const container = document.getElementById(elementId);
            if (edges.length === 0) {
                container.innerHTML = '<div style="color:var(--text-tertiary); text-align:center; padding:20px;">No dependencies</div>';
                return;
            }
            
            const html = edges.map(e => {
                const otherNode = state.nodeMap[e[key]];
                if (!otherNode) return '';
                return `
                    <div class="dep-list-item" onclick="jumpToNode('${otherNode.id}')">
                        <div>
                            <span style="margin-right: 6px;">${getNodeIcon(otherNode.type)}</span>
                            <strong>${otherNode.name}</strong>
                        </div>
                        <div style="font-size: 10px; color: var(--text-tertiary);">${e.type}</div>
                    </div>
                `;
            }).join('');
            container.innerHTML = html;
        }
        
        function switchTab(tabName) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
            
            // Handle specialized ID for count tabs
            let tabBtn;
            if (tabName === 'upstream') tabBtn = document.getElementById('tab-up-count');
            else if (tabName === 'downstream') tabBtn = document.getElementById('tab-down-count');
            else tabBtn = document.querySelector(`.tab:nth-child(1)`);
            
            if (tabBtn) tabBtn.classList.add('active');
            document.getElementById(`view-${tabName}`).classList.add('active');
        }

        function openEditor() {
            if (state.currentNode && state.currentNode.path) {
                const path = state.currentNode.path.startsWith('/') ? state.currentNode.path.substring(1) : state.currentNode.path;
                const line = state.currentNode.metadata?.line || 1;
                window.location.href = `vscode://file/${path}:${line}`;
            }
        }

        // ============================================================
        // MESH VISUALIZATION (Force Directed)
        // ============================================================
        function openMeshModal() {
            if (!state.currentNode) return;
            document.getElementById('meshModal').style.display = 'flex';
            renderMesh(state.currentNode);
        }

        function closeMeshModal() {
            document.getElementById('meshModal').style.display = 'none';
            document.getElementById('mesh-container').innerHTML = ''; // Clear D3
        }

        function renderMesh(centerNode) {
            const container = document.getElementById('mesh-container');
            const width = container.clientWidth;
            const height = container.clientHeight;
            
            // 1. Collect neighborhood (Depth 1)
            const nodes = new Set([centerNode]);
            const links = [];
            
            const up = state.incomingEdges[centerNode.id] || [];
            const down = state.outgoingEdges[centerNode.id] || [];
            
            [...up, ...down].forEach(e => {
                const src = state.nodeMap[e.source_id];
                const tgt = state.nodeMap[e.target_id];
                if(src && tgt) {
                    nodes.add(src);
                    nodes.add(tgt);
                    links.push({ source: src.id, target: tgt.id, type: e.type });
                }
            });

            const graphNodes = Array.from(nodes).map(n => ({ id: n.id, group: getGroup(n.type), name: n.name }));
            
            // 2. D3 Setup
            const svg = d3.select("#mesh-container").append("svg")
                .attr("width", width)
                .attr("height", height)
                .attr("viewBox", [0, 0, width, height]);

            const simulation = d3.forceSimulation(graphNodes)
                .force("link", d3.forceLink(links).id(d => d.id).distance(100))
                .force("charge", d3.forceManyBody().strength(-300))
                .force("center", d3.forceCenter(width / 2, height / 2));

            const link = svg.append("g")
                .attr("stroke", "#555")
                .selectAll("line")
                .data(links)
                .join("line");

            const node = svg.append("g")
                .selectAll("g")
                .data(graphNodes)
                .join("g")
                .call(drag(simulation));

            // Node Circles
            node.append("circle")
                .attr("r", d => d.id === centerNode.id ? 10 : 6)
                .attr("fill", d => getColor(d.group))
                .attr("stroke", d => d.id === centerNode.id ? "#fff" : "none");

            // Labels
            node.append("text")
                .text(d => d.name)
                .attr("x", 8)
                .attr("y", 3)
                .style("font-size", "10px")
                .style("fill", "#ccc");

            simulation.on("tick", () => {
                link
                    .attr("x1", d => d.source.x)
                    .attr("y1", d => d.source.y)
                    .attr("x2", d => d.target.x)
                    .attr("y2", d => d.target.y);

                node
                    .attr("transform", d => `translate(${d.x},${d.y})`);
            });
        }

        // D3 Helpers
        function drag(simulation) {
            function dragstarted(event) {
                if (!event.active) simulation.alphaTarget(0.3).restart();
                event.subject.fx = event.subject.x;
                event.subject.fy = event.subject.y;
            }
            function dragged(event) {
                event.subject.fx = event.x;
                event.subject.fy = event.y;
            }
            function dragended(event) {
                if (!event.active) simulation.alphaTarget(0);
                event.subject.fx = null;
                event.subject.fy = null;
            }
            return d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended);
        }

        function getColor(group) {
            const colors = { infra: '#f59e0b', config: '#22c55e', code: '#3b82f6', data: '#a855f7' };
            return colors[group] || '#777';
        }
        function getGroup(type) {
            if (type.includes('infra')) return 'infra';
            if (type.includes('env')) return 'config';
            if (type.includes('data')) return 'data';
            return 'code';
        }

        // ============================================================
        // UTILS
        // ============================================================
        function getCategoryIcon(cat) {
            const map = {'Infrastructure': '☁️', 'Configuration': '🔧', 'Code': '💻', 'Data': '📊'};
            return map[cat] || '📦';
        }
        
        function getNodeIcon(type) {
            if (type.includes('infra')) return '☁️';
            if (type.includes('env')) return '🔧';
            if (type.includes('data')) return '📊';
            return '📄';
        }
    </script>
</body>
</html>
"""


def _json_default(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code"""
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def generate_html(graph: IGraph) -> str:
    """
    Generate the HTML content for the graph visualization.
    """
    if hasattr(graph, "to_dict"):
        graph_data = graph.to_dict()
    else:
        graph_data = {
            "nodes": [n.model_dump() for n in graph.iter_nodes()],
            "edges": [e.model_dump() for e in graph.iter_edges()],
        }

    json_data = json.dumps(graph_data, default=_json_default)
    return HTML_TEMPLATE.replace("__GRAPH_DATA__", json_data)


def open_visualization(graph: IGraph, output_path: str = "graph.html") -> str:
    """
    Generate and open the visualization in the browser.
    """
    html_content = generate_html(graph)
    out_file = Path(output_path)
    out_file.write_text(html_content, encoding="utf-8")

    abs_path = out_file.resolve().as_uri()
    webbrowser.open(abs_path)

    return str(out_file)
