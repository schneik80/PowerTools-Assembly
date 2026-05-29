(function () {
    'use strict';

    var ptInit = window.__ptInit || {
        docName: '',
        theme: 'dark',
        openDocs: [],
        recentDocs: [],
        showChildren: false
    };

    function applyTheme(theme) {
        document.body.classList.remove('dark', 'light');
        document.body.classList.add(theme === 'light' ? 'light' : 'dark');
    }

    function setDocName(name) {
        var el = document.getElementById('docName');
        if (el) el.textContent = name || '';
    }

    function send(action, payload) {
        try {
            adsk.fusionSendData(action, JSON.stringify(payload || {}));
        } catch (e) {
            console.log('[New Assembly] not in Fusion palette:', action, payload);
        }
    }

    function escapeHtml(text) {
        var d = document.createElement('div');
        d.textContent = text == null ? '' : String(text);
        return d.innerHTML;
    }

    function setTabCount(id, n) {
        var el = document.getElementById(id);
        if (el) el.textContent = n > 0 ? ' (' + n + ')' : '';
    }

    function renderGallery(rootId, emptyId, docs) {
        // Update the corresponding tab count badge alongside the gallery so
        // the user sees how many items each tab holds without switching.
        if (rootId === 'openGallery') setTabCount('openCount', (docs || []).length);
        if (rootId === 'recentGallery') setTabCount('recentCount', (docs || []).length);

        var root = document.getElementById(rootId);
        if (!root) return;
        // Wipe and rebuild.
        root.innerHTML = '';
        if (!docs || docs.length === 0) {
            var empty = document.createElement('div');
            empty.className = 'empty';
            empty.id = emptyId;
            empty.textContent = (emptyId === 'openEmpty')
                ? 'No other open documents.'
                : 'No recent documents yet.';
            root.appendChild(empty);
            return;
        }
        docs.forEach(function (doc) {
            var card = document.createElement('div');
            card.className = 'doc-card';
            card.title = 'Insert ' + (doc.name || '');

            var thumbHtml;
            if (doc.thumbUrl) {
                thumbHtml = '<div class="doc-thumb">' +
                    '<img src="' + escapeHtml(doc.thumbUrl) + '" alt="" ' +
                    'onerror="this.parentNode.classList.add(\'broken\');this.remove();" />' +
                    '</div>';
            } else {
                thumbHtml = '<div class="doc-thumb broken"></div>';
            }

            card.innerHTML =
                thumbHtml +
                '<span class="badge ' + escapeHtml(doc.intent || 'part') + '">' +
                escapeHtml(doc.intent || 'part') +
                '</span>' +
                '<div class="doc-card-name">' + escapeHtml(doc.name || '') + '</div>';
            card.addEventListener('click', function () {
                send('insertDoc', {
                    dataFileId: doc.dataFileId,
                    name: doc.name,
                    intent: doc.intent
                });
            });
            root.appendChild(card);
        });
    }

    function updateIntentLabel() {
        var sel = document.getElementById('newCompIntent');
        var lbl = document.getElementById('intentLabel');
        if (sel && lbl) lbl.textContent = sel.value;
    }

    // --- Initial paint from ptInit ---
    applyTheme(ptInit.theme);
    setDocName(ptInit.docName);
    renderGallery('openGallery', 'openEmpty', ptInit.openDocs);
    renderGallery('recentGallery', 'recentEmpty', ptInit.recentDocs);
    updateIntentLabel();

    // "Show referenced children" toggles whether reference-loaded sub-assemblies
    // / parts of open assemblies appear in the Open tab. Off by default → only
    // top-level docs. Filtering is backend-side (an instant in-memory check),
    // so a change just re-requests the open-docs list.
    var showChildren = document.getElementById('openShowChildren');
    if (showChildren) {
        showChildren.checked = !!ptInit.showChildren;
        showChildren.addEventListener('change', function () {
            send('setShowChildren', { showChildren: showChildren.checked });
        });
    }

    // --- Wire actions ---
    document.getElementById('btnCreateComp').addEventListener('click', function () {
        var name = document.getElementById('newCompName').value.trim();
        var intent = document.getElementById('newCompIntent').value;
        if (!name) {
            document.getElementById('newCompName').focus();
            return;
        }
        send('createComponent', { name: name, intent: intent });
        document.getElementById('newCompName').value = '';
        document.getElementById('newCompName').focus();
    });

    document.getElementById('newCompName').addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
            e.preventDefault();
            document.getElementById('btnCreateComp').click();
        }
    });

    document.getElementById('newCompIntent').addEventListener('change', updateIntentLabel);

    document.getElementById('btnAssemblyBuilder').addEventListener('click', function () {
        send('launchAssemblyBuilder', {});
    });
    document.getElementById('btnGlobalParameters').addEventListener('click', function () {
        send('launchGlobalParameters', {});
    });
    document.getElementById('btnRefresh').addEventListener('click', function () {
        send('refresh', {});
    });

    // --- Tab switching (Open / Recent) ---
    function activateTab(which) {
        var tabs = document.querySelectorAll('.tab');
        for (var i = 0; i < tabs.length; i++) {
            var t = tabs[i];
            var active = t.dataset.tab === which;
            t.classList.toggle('active', active);
            t.setAttribute('aria-selected', active ? 'true' : 'false');
        }
        var panes = document.querySelectorAll('.tab-pane');
        for (var j = 0; j < panes.length; j++) {
            panes[j].classList.toggle('active', panes[j].dataset.tab === which);
        }
        // Reset scroll so a switch always starts at the top, regardless of
        // where the previous tab was scrolled to.
        var container = document.querySelector('.tab-panes');
        if (container) container.scrollTop = 0;
    }

    document.querySelectorAll('.tab').forEach(function (t) {
        t.addEventListener('click', function () { activateTab(t.dataset.tab); });
    });

    // --- Fusion → page bridge ---
    window.fusionJavaScriptHandler = {
        handle: function (action, data) {
            try {
                if (action === 'setDocumentName') {
                    setDocName(data);
                } else if (action === 'setTheme') {
                    applyTheme(data);
                } else if (action === 'setOpenDocs') {
                    var open = [];
                    try { open = JSON.parse(data) || []; } catch (e) { open = []; }
                    renderGallery('openGallery', 'openEmpty', open);
                } else if (action === 'setRecentDocs') {
                    var recent = [];
                    try { recent = JSON.parse(data) || []; } catch (e) { recent = []; }
                    renderGallery('recentGallery', 'recentEmpty', recent);
                }
            } catch (e) {
                console.log('[New Assembly] handler error:', e);
            }
            return 'OK';
        }
    };
})();
