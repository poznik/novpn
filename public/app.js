(function () {
    'use strict';

    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const addServiceBtn = document.getElementById('addServiceBtn');
    const serviceModal = document.getElementById('serviceModal');
    const serviceModalClose = document.getElementById('serviceModalClose');
    const serviceGrid = document.getElementById('serviceGrid');
    const dropOverlay = document.getElementById('dropOverlay');
    const editor = document.getElementById('editor');
    const highlight = document.getElementById('highlight');
    const jsonView = document.getElementById('jsonView');
    const checkBtn = document.getElementById('checkBtn');
    const downloadBtn = document.getElementById('downloadBtn');
    const statusEl = document.getElementById('status');

    const IPV4 = /^(25[0-5]|2[0-4]\d|[01]?\d\d?)(\.(25[0-5]|2[0-4]\d|[01]?\d\d?)){3}$/;
    const CIDR = /^(25[0-5]|2[0-4]\d|[01]?\d\d?)(\.(25[0-5]|2[0-4]\d|[01]?\d\d?)){3}\/([0-9]|[12]\d|3[0-2])$/;
    const DOMAIN = /^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))+$/;

    let badLines = new Set();
    let goodLines = new Set();
    let goodTimer = null;

    function setStatus(msg, kind) {
        statusEl.textContent = msg || '';
        statusEl.className = 'status' + (kind ? ' ' + kind : '');
    }

    function isNetwork(s) { return CIDR.test(s) || IPV4.test(s); }
    function isDomain(s) { return DOMAIN.test(s); }
    function isIp(s) { return IPV4.test(s); }

    const COMMENT_PREFIX = 'CMNT_';
    const COMMENT_SUFFIX = '.com';
    const COMMENT_IP = '127.0.0.1';

    function isCommentEntry(item) {
        if (!item) return false;
        const h = item.hostname || '';
        return item.ip === COMMENT_IP
            && h.startsWith(COMMENT_PREFIX)
            && h.endsWith(COMMENT_SUFFIX)
            && h.length > COMMENT_PREFIX.length + COMMENT_SUFFIX.length;
    }

    function entryToCommentLine(item) {
        const h = item.hostname;
        const body = h.slice(COMMENT_PREFIX.length, h.length - COMMENT_SUFFIX.length);
        return '# ' + body.replace(/_/g, ' ');
    }

    function jsonToLines(data) {
        if (!Array.isArray(data)) throw new Error('Ожидался массив объектов');
        return data.map(function (item) {
            if (isCommentEntry(item)) return entryToCommentLine(item);
            const host = (item && item.hostname) || '';
            const ip = (item && item.ip) || '';
            if (ip) return host + ' ' + ip;
            return host;
        }).filter(function (line) {
            return line.trim().length > 0;
        }).join('\n');
    }

    function linesToJson(text) {
        const lines = text.split(/\r?\n/);
        const result = [];
        const bad = new Set();
        let rewritten = false;
        for (let i = 0; i < lines.length; i++) {
            const raw = lines[i].trim();
            if (!raw) continue;
            if (raw.startsWith('#')) {
                continue;
            }
            const parts = raw.split(/\s+/);
            if (parts.length === 1) {
                let token = parts[0];
                if (isIp(token)) {
                    token = token + '/32';
                    lines[i] = token;
                    rewritten = true;
                }
                if (isNetwork(token)) {
                    result.push({ hostname: token, ip: '', __line: i });
                } else if (isDomain(token)) {
                    result.push({ hostname: token, ip: '', __line: i, __needsResolve: true });
                } else {
                    bad.add(i);
                }
            } else if (parts.length === 2) {
                const host = parts[0];
                const ip = parts[1];
                if (isDomain(host) && isIp(ip)) {
                    result.push({ hostname: host, ip: ip, __line: i });
                } else {
                    bad.add(i);
                }
            } else {
                bad.add(i);
            }
        }
        return { items: result, bad: bad, text: rewritten ? lines.join('\n') : null };
    }

    async function resolveDoH(domain) {
        const providers = [
            'https://cloudflare-dns.com/dns-query?name=' + encodeURIComponent(domain) + '&type=A',
            'https://dns.google/resolve?name=' + encodeURIComponent(domain) + '&type=A'
        ];
        for (const url of providers) {
            try {
                const res = await fetch(url, { headers: { 'Accept': 'application/dns-json' } });
                if (!res.ok) continue;
                const data = await res.json();
                if (data && Array.isArray(data.Answer)) {
                    const a = data.Answer.find(function (r) { return r.type === 1; });
                    if (a && a.data) return a.data;
                }
            } catch (e) { /* try next */ }
        }
        return null;
    }

    function escapeHtml(s) {
        return s.replace(/[&<>"']/g, function (c) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
        });
    }

    function renderHighlight() {
        const text = editor.value;
        const lines = text.split('\n');
        const html = lines.map(function (line, i) {
            const content = line.length ? escapeHtml(line) : '&nbsp;';
            const cls = badLines.has(i) ? ' class="line-bad"' : goodLines.has(i) ? ' class="line-good"' : '';
            return '<div' + cls + '>' + content + '</div>';
        }).join('');
        highlight.innerHTML = html;
    }

    function flashGoodLines(startLine, count) {
        if (goodTimer) { clearTimeout(goodTimer); goodTimer = null; }
        goodLines = new Set();
        for (let i = 0; i < count; i++) goodLines.add(startLine + i);
        renderHighlight();
        goodTimer = setTimeout(function () {
            goodLines = new Set();
            goodTimer = null;
            renderHighlight();
        }, 5000);
    }

    function clearGood() {
        if (!goodLines.size && !goodTimer) return;
        if (goodTimer) { clearTimeout(goodTimer); goodTimer = null; }
        goodLines = new Set();
    }

    function syncScroll() {
        highlight.scrollTop = editor.scrollTop;
        highlight.scrollLeft = editor.scrollLeft;
    }

    function clearBad() {
        badLines = new Set();
        renderHighlight();
    }

    async function runCheck(silent) {
        const parsed = linesToJson(editor.value);
        if (parsed.text !== null) editor.value = parsed.text;
        badLines = parsed.bad;

        const toResolve = parsed.items.filter(function (it) { return it.__needsResolve; });
        if (toResolve.length) {
            setStatus('Резолв ' + toResolve.length + ' домен(ов)...');
            for (const it of toResolve) {
                const ip = await resolveDoH(it.hostname);
                if (ip) {
                    it.ip = ip;
                } else {
                    parsed.bad.add(it.__line);
                }
            }
            applyResolvedToEditor(parsed.items);
        }

        const clean = parsed.items
            .filter(function (it) { return !parsed.bad.has(it.__line); })
            .map(function (it) { return { hostname: it.hostname, ip: it.ip }; });

        jsonView.value = JSON.stringify(clean, null, 4);
        renderHighlight();

        if (parsed.bad.size) {
            setStatus('Ошибок: ' + parsed.bad.size + ' (строки подсвечены)', 'error');
            return { ok: false, data: clean };
        }
        if (!silent) setStatus('OK: ' + clean.length + ' записей', 'success');
        return { ok: true, data: clean };
    }

    function applyResolvedToEditor(items) {
        const lines = editor.value.split('\n');
        for (const it of items) {
            if (it.__needsResolve && it.ip) {
                lines[it.__line] = it.hostname + ' ' + it.ip;
            }
        }
        const newText = lines.join('\n');
        if (newText !== editor.value) {
            editor.value = newText;
        }
    }

    async function handleFile(file) {
        if (!file) return;
        try {
            const text = await file.text();
            const data = JSON.parse(text);
            editor.value = jsonToLines(data);
            const parsed = linesToJson(editor.value);
            const clean = parsed.items.map(function (it) {
                return { hostname: it.hostname, ip: it.ip };
            });
            jsonView.value = JSON.stringify(clean, null, 4);
            clearBad();
            setStatus('Загружен: ' + file.name + ' (' + clean.length + ' записей)', 'success');
        } catch (e) {
            setStatus('Ошибка чтения файла: ' + e.message, 'error');
        }
    }

    function downloadJson(data) {
        const blob = new Blob([JSON.stringify(data, null, 4)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'amnezia_sites.json';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    uploadBtn.addEventListener('click', function () { fileInput.click(); });
    fileInput.addEventListener('change', function (e) {
        if (e.target.files && e.target.files[0]) handleFile(e.target.files[0]);
        fileInput.value = '';
    });

    let dragDepth = 0;
    function hasFiles(e) {
        if (!e.dataTransfer) return false;
        const types = e.dataTransfer.types;
        if (!types) return false;
        for (let i = 0; i < types.length; i++) {
            if (types[i] === 'Files') return true;
        }
        return false;
    }
    window.addEventListener('dragenter', function (e) {
        if (!hasFiles(e)) return;
        e.preventDefault();
        dragDepth++;
        dropOverlay.classList.add('active');
    });
    window.addEventListener('dragover', function (e) {
        if (hasFiles(e)) e.preventDefault();
    });
    window.addEventListener('dragleave', function (e) {
        if (!hasFiles(e)) return;
        dragDepth--;
        if (dragDepth <= 0) {
            dragDepth = 0;
            dropOverlay.classList.remove('active');
        }
    });
    window.addEventListener('drop', function (e) {
        e.preventDefault();
        dragDepth = 0;
        dropOverlay.classList.remove('active');
        const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
        if (f) handleFile(f);
    });

    editor.addEventListener('input', function () {
        clearGood();
        if (badLines.size) clearBad();
        renderHighlight();
    });
    editor.addEventListener('scroll', syncScroll);

    checkBtn.addEventListener('click', function () { runCheck(false); });
    downloadBtn.addEventListener('click', async function () {
        const res = await runCheck(true);
        if (!res.ok) {
            setStatus('Нельзя скачать: есть ошибки (строки подсвечены)', 'error');
            return;
        }
        downloadJson(res.data);
        setStatus('Скачан файл: ' + res.data.length + ' записей', 'success');
    });

    let servicesCache = null;

    async function loadServices() {
        if (servicesCache) return servicesCache;
        const res = await fetch('services.json', { cache: 'no-cache' });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        servicesCache = {
            categories: Array.isArray(data.categories) ? data.categories : [],
            services: Array.isArray(data.services) ? data.services : []
        };
        return servicesCache;
    }

    function createCard(svc) {
        const card = document.createElement('button');
        card.className = 'service-card';
        card.type = 'button';
        const name = document.createElement('div');
        name.className = 'service-card-name';
        name.textContent = svc.name || svc.id || '(без имени)';
        card.appendChild(name);
        if (svc.description) {
            const desc = document.createElement('div');
            desc.className = 'service-card-desc';
            desc.textContent = svc.description;
            card.appendChild(desc);
        }
        card.addEventListener('click', function () { insertService(svc); });
        return card;
    }

    function renderServices(data) {
        const { categories, services } = data;
        if (!services.length) {
            serviceGrid.innerHTML = '<div class="service-empty">Список сервисов пуст</div>';
            return;
        }
        serviceGrid.innerHTML = '';
        const sections = categories.length
            ? categories.map(function (c) { return { id: c.id, name: c.name }; })
            : [{ id: null, name: '' }];
        const seen = new Set();
        sections.forEach(function (sec) {
            const items = services.filter(function (s) {
                return sec.id ? s.category === sec.id : true;
            });
            if (!items.length) return;
            items.forEach(function (s) { seen.add(s); });
            const section = document.createElement('div');
            section.className = 'service-section';
            if (sec.name) {
                const title = document.createElement('div');
                title.className = 'service-section-title';
                title.textContent = sec.name;
                section.appendChild(title);
            }
            const grid = document.createElement('div');
            grid.className = 'service-section-grid';
            items.forEach(function (svc) { grid.appendChild(createCard(svc)); });
            section.appendChild(grid);
            serviceGrid.appendChild(section);
        });
        const orphans = services.filter(function (s) { return !seen.has(s); });
        if (orphans.length) {
            const section = document.createElement('div');
            section.className = 'service-section';
            const title = document.createElement('div');
            title.className = 'service-section-title';
            title.textContent = 'Прочее';
            section.appendChild(title);
            const grid = document.createElement('div');
            grid.className = 'service-section-grid';
            orphans.forEach(function (svc) { grid.appendChild(createCard(svc)); });
            section.appendChild(grid);
            serviceGrid.appendChild(section);
        }
    }

    function insertService(svc) {
        const entries = Array.isArray(svc.entries) ? svc.entries : [];
        if (!entries.length) return;
        const block = entries.join('\n');
        const cur = editor.value;
        let prefix;
        if (!cur.trim()) {
            prefix = '';
        } else {
            prefix = cur + (cur.endsWith('\n') ? '\n' : '\n\n');
        }
        const startLine = prefix ? prefix.split('\n').length - 1 : 0;
        editor.value = prefix + block + '\n';
        clearBad();
        flashGoodLines(startLine, entries.length);
        closeServiceModal();
        editor.focus();
        editor.scrollTop = editor.scrollHeight;
        setStatus('Добавлен сервис: ' + (svc.name || svc.id), 'success');
    }

    async function openServiceModal() {
        serviceModal.classList.add('active');
        try {
            const data = await loadServices();
            renderServices(data);
        } catch (e) {
            serviceGrid.innerHTML = '<div class="service-empty">Ошибка загрузки services.json: ' + escapeHtml(e.message) + '</div>';
        }
    }

    function closeServiceModal() {
        serviceModal.classList.remove('active');
    }

    addServiceBtn.addEventListener('click', openServiceModal);
    serviceModalClose.addEventListener('click', closeServiceModal);
    serviceModal.querySelector('.modal-backdrop').addEventListener('click', closeServiceModal);
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape' && serviceModal.classList.contains('active')) closeServiceModal();
    });

    renderHighlight();
})();
