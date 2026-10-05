// Plugin Hub browser UI — manage CrossPoint plugins from the generated Hub
// catalog plus optional user-supplied catalogs.
CrossPoint.registerPlugin(async (container, api) => {
  const LEGACY_CONFIG_PATH = '/.crosspoint/plugin-hub.json';
  const PLUGIN_DIR =
    api && typeof api.dir === 'string' && api.dir.startsWith('/')
      ? api.dir.replace(/\/+$/, '')
      : null;
  const CONFIG_PATH = PLUGIN_DIR ? PLUGIN_DIR + '/config.json' : LEGACY_CONFIG_PATH;
  const PLUGINS_DIR = '/.crosspoint/plugins';
  const RELEASE_API_URL = 'https://api.github.com/repos/jadehawk/PluginHub.crosspoint-plugin/releases/latest';
  const LEGACY_CATALOG =
    'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/catalog.json';
  const OFFICIAL_CATALOG =
    'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/official-catalog.json';
  const COMMUNITY_CATALOG =
    'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/community-catalog.json';
  const LIST_INDEX_URL =
    'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/catalog-lists.json';
  let BUILT_IN_CATALOGS = [];

  let selectedCatalog = "";
  let extraCatalogs = [];

  container.innerHTML =
    '<h2>Plugin Hub</h2>' +
    '<p id="ph-version" style="color:#666">Version: checking...</p>' +
    '<h3 style="margin:0.5em 0 0.2em">Browse plugins</h3>' +
    '<div id="ph-catalogs"></div>' +
    '<details style="margin-top:0.8em"><summary>Custom catalogs</summary>' +
    '<div id="ph-custom-catalogs"></div>' +
    '<div class="setting-row">' +
    '<span class="setting-control"><input type="text" id="ph-new" placeholder="https://.../catalog.json" style="width:100%"></span>' +
    '<button type="button" class="btn-small btn-add" id="ph-add">Add catalog</button></div>' +
    '</details>' +
    '<div class="setting-row"><button type="button" class="btn-small btn-add" id="ph-refresh">Refresh selected catalog</button></div>' +
    '<p id="ph-status"></p>' +
    '<div id="ph-list"></div>';

  const catalogsEl = document.getElementById('ph-catalogs');
  const customCatalogsEl = document.getElementById('ph-custom-catalogs');
  const listEl = document.getElementById('ph-list');
  const status = (text) => {
    document.getElementById('ph-status').textContent = text;
  };

  function escapeHtml(value) {
    return String(value).replace(/[&<>"]/g, (c) => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;'
    }[c]));
  }

  function hostOf(url) {
    try {
      return new URL(url).host;
    } catch (e) {
      return url;
    }
  }

  function b64(str) {
    const bytes = new TextEncoder().encode(str);
    let bin = '';
    for (const byte of bytes) bin += String.fromCharCode(byte);
    return btoa(bin);
  }

  function isReservedCatalog(url) {
    return (
      url === LEGACY_CATALOG ||
      url === OFFICIAL_CATALOG ||
      url === COMMUNITY_CATALOG ||
      BUILT_IN_CATALOGS.some((catalog) => catalog.url === url)
    );
  }

  function normalizeExtraCatalogs(urls) {
    const seen = new Set();
    const normalized = [];
    for (const url of urls || []) {
      const trimmed = String(url || '').trim();
      if (!trimmed || isReservedCatalog(trimmed) || seen.has(trimmed)) continue;
      seen.add(trimmed);
      normalized.push(trimmed);
    }
    return normalized;
  }

  function selectedCatalogLabel() {
    const builtIn = BUILT_IN_CATALOGS.find((catalog) => catalog.url === selectedCatalog);
    return builtIn ? builtIn.title : hostOf(selectedCatalog);
  }

  async function readJsonFile(path) {
    try {
      const response = await fetch('/download?path=' + encodeURIComponent(path));
      if (!response.ok) return null;
      return JSON.parse(await response.text());
    } catch (e) {
      return null;
    }
  }

  async function loadConfig() {
    const current = await readJsonFile(CONFIG_PATH);
    if (current) return current;

    if (CONFIG_PATH !== LEGACY_CONFIG_PATH) {
      const legacy = await readJsonFile(LEGACY_CONFIG_PATH);
      if (legacy) return legacy;
    }
    return {};
  }

  function saveConfig() {
    extraCatalogs = normalizeExtraCatalogs(extraCatalogs);
    if (
      !BUILT_IN_CATALOGS.some((catalog) => catalog.url === selectedCatalog) &&
      !extraCatalogs.includes(selectedCatalog)
    ) {
      selectedCatalog = BUILT_IN_CATALOGS[0]?.url || "";
    }
    return api.writeFile(
      CONFIG_PATH,
      b64(JSON.stringify({ extraCatalogs }, null, 2))
    );
  }

  async function installedNames() {
    try {
      const response = await fetch('/api/files?path=' + encodeURIComponent(PLUGINS_DIR));
      if (!response.ok) return new Set();
      const entries = await response.json();
      return new Set(
        entries.filter((entry) => entry.isDirectory).map((entry) => entry.name)
      );
    } catch (e) {
      return new Set();
    }
  }

  async function installedVersion(name) {
    const manifest = await readJsonFile(PLUGINS_DIR + '/' + name + '/manifest.json');
    return manifest && manifest.version ? manifest.version : null;
  }

  async function hubInstalledVersion() {
    if (PLUGIN_DIR) {
      const manifest = await readJsonFile(PLUGIN_DIR + '/manifest.json');
      if (manifest && manifest.version) return manifest.version;
    }
    return installedVersion('pluginhub');
  }

  function numericVersion(version) {
    const match = String(version || '').trim().match(/^v?(\d+(?:\.\d+){1,3})$/i);
    if (!match) return null;
    const parts = match[1].split('.').map((part) => Number(part));
    while (parts.length < 4) parts.push(0);
    return parts;
  }

  function compareVersions(left, right) {
    const a = numericVersion(left);
    const b = numericVersion(right);
    if (!a || !b) return null;
    for (let i = 0; i < 4; i++) {
      if (a[i] !== b[i]) return a[i] > b[i] ? 1 : -1;
    }
    return 0;
  }

  function hasUpdate(localVersion, remoteVersion) {
    if (!remoteVersion) return false;
    if (!localVersion) return true;

    const comparison = compareVersions(remoteVersion, localVersion);
    if (comparison !== null) return comparison > 0;

    // Unknown legacy formats cannot be ordered safely, so retain the old
    // mismatch behavior rather than silently hiding a possible update.
    return String(remoteVersion) !== String(localVersion);
  }

  function installedLabel(localVersion, remoteVersion) {
    if (!localVersion) return 'Installed';

    const comparison = compareVersions(localVersion, remoteVersion);
    if (remoteVersion && comparison !== null && comparison > 0) {
      return 'Installed v' + localVersion + ' (catalog v' + remoteVersion + ')';
    }
    return 'Installed v' + localVersion;
  }

  async function checkHubVersion() {
    const versionEl = document.getElementById('ph-version');
    const installed = String((await hubInstalledVersion()) || '').trim();
    if (!numericVersion(installed)) {
      versionEl.textContent = 'Version: unavailable';
      return;
    }

    versionEl.textContent = 'Version: v' + installed;
    versionEl.style.color = '#666';

    try {
      const response = await api.relay(
        'GET',
        RELEASE_API_URL,
        {
          Accept: 'application/vnd.github+json',
          'User-Agent': 'PluginHub-CrossPoint'
        },
        ''
      );
      if (response.error || (response.status && (response.status < 200 || response.status >= 300))) {
        return;
      }

      const release = response.body ? JSON.parse(response.body) : {};
      const latest = String(release.tag_name || '').trim().replace(/^v/i, '');
      const comparison = compareVersions(latest, installed);
      if (comparison > 0) {
        versionEl.textContent =
          'Version: v' + installed + ' — Update available: v' + latest;
        versionEl.style.color = '#c0392b';
      }
    } catch (e) {}
  }

  async function fetchLargeText(url) {
    const cachePath = (PLUGIN_DIR || PLUGINS_DIR + '/pluginhub') + '/.catalog-cache.json';
    const response = await api.fetchToSd(url, cachePath, {});
    if (response.error || (response.status && (response.status < 200 || response.status >= 300))) {
      throw new Error('download failed (' + (response.status || response.error) + ')');
    }
    try {
      const downloaded = await fetch('/download?path=' + encodeURIComponent(cachePath));
      if (!downloaded.ok) throw new Error('could not read downloaded catalog');
      return await downloaded.text();
    } finally {
      try {
        await fetch('/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'path=' + encodeURIComponent(cachePath)
        });
      } catch (e) {}
    }
  }

  async function relayText(url) {
    let response;
    try {
      response = await api.relay('GET', url, {}, '');
    } catch (error) {
      const detail = String(error && error.message ? error.message : error);
      if (detail.includes('large bodies need /api/fetch') || detail.includes('/api/relay 502')) {
        return fetchLargeText(url);
      }
      throw error;
    }
    if (response.error || (response.status && (response.status < 200 || response.status >= 300))) {
      const detail = String(response.error || response.body || '');
      if (response.status === 502 || detail.includes('large bodies need /api/fetch')) {
        return fetchLargeText(url);
      }
      throw new Error('HTTP ' + (response.status || response.error));
    }
    return response.body;
  }

  async function loadBuiltInCatalogs() {
    const payload = JSON.parse(await relayText(LIST_INDEX_URL));
    const lists = Array.isArray(payload.lists) ? payload.lists : [];
    const normalized = lists
      .filter((entry) => entry && entry.title && entry.url)
      .map((entry) => ({
        title: String(entry.title),
        description: String(entry.title).startsWith('Community Plugins')
          ? 'Third-party plugins from CrossPoint community developers.'
          : 'Curated and recognized for the CrossPoint ecosystem.',
        url: String(entry.url)
      }));
    if (!normalized.length) throw new Error('catalog list index is empty');
    BUILT_IN_CATALOGS = normalized;
    if (!BUILT_IN_CATALOGS.some((catalog) => catalog.url === selectedCatalog)) {
      selectedCatalog = BUILT_IN_CATALOGS[0].url;
    }
  }

  async function mkdir(path) {
    try {
      await fetch('/mkdir', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'path=' + encodeURIComponent(path)
      });
    } catch (e) {}
  }

  function validatePlugin(plugin) {
    if (!plugin || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(String(plugin.name || ''))) {
      throw new Error('invalid plugin id');
    }
    if (!plugin.base || !Array.isArray(plugin.files) || plugin.files.length === 0) {
      throw new Error('catalog entry is missing base/files');
    }
  }

  function safeRelativePath(path) {
    const rel = String(path || '').replace(/^\/+/, '');
    if (
      !rel ||
      rel.includes('\\') ||
      rel.split('/').some((part) => part === '' || part === '.' || part === '..')
    ) {
      throw new Error('unsafe plugin file path: ' + path);
    }
    return rel;
  }

  async function installPlugin(plugin, onProgress) {
    validatePlugin(plugin);
    const dir = PLUGINS_DIR + '/' + plugin.name;
    await mkdir(dir);

    const base = String(plugin.base).replace(/\/*$/, '/');
    const files = plugin.files;
    for (let i = 0; i < files.length; i++) {
      if (onProgress) onProgress(i, files.length);
      const rel = safeRelativePath(files[i]);

      const segments = rel.split('/');
      segments.pop();
      let current = dir;
      for (const segment of segments) {
        current += '/' + segment;
        await mkdir(current);
      }

      const response = await api.fetchToSd(base + rel, dir + '/' + rel, {});
      if (response.error || (response.status && (response.status < 200 || response.status >= 300))) {
        throw new Error(
          'download failed for ' + rel + ' (' + (response.status || response.error) + ')'
        );
      }
    }

    if (onProgress) onProgress(files.length, files.length);
  }

  async function uninstallPlugin(plugin) {
    validatePlugin(plugin);
    const dir = PLUGINS_DIR + '/' + plugin.name;

    for (const file of plugin.files) {
      let rel;
      try {
        rel = safeRelativePath(file);
      } catch (e) {
        continue;
      }

      try {
        await fetch('/delete', {
          method: 'POST',
          headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
          body: 'path=' + encodeURIComponent(dir + '/' + rel)
        });
      } catch (e) {}
    }

    try {
      await fetch('/delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: 'path=' + encodeURIComponent(dir)
      });
    } catch (e) {}
  }

  function renderCatalogs() {
    catalogsEl.innerHTML = '';
    customCatalogsEl.innerHTML = '';

    BUILT_IN_CATALOGS.forEach((catalog) => {
      const row = document.createElement('div');
      row.className = 'setting-row';

      const meta = document.createElement('span');
      meta.className = 'setting-name';
      meta.innerHTML =
        '<strong>' + escapeHtml(catalog.title) + '</strong>' +
        '<br><span style="color:#666">' + escapeHtml(catalog.description) + '</span>';

      const browse = document.createElement('button');
      browse.type = 'button';
      browse.className = 'btn-small btn-add';
      browse.textContent = selectedCatalog === catalog.url ? 'Selected' : 'Browse';
      browse.disabled = selectedCatalog === catalog.url;
      browse.onclick = async () => {
        selectedCatalog = catalog.url;
        renderCatalogs();
        await refresh();
      };

      row.appendChild(meta);
      row.appendChild(browse);
      catalogsEl.appendChild(row);
    });

    extraCatalogs.forEach((url, index) => {
      const row = document.createElement('div');
      row.className = 'setting-row';

      const input = document.createElement('input');
      input.type = 'text';
      input.value = url;
      input.style.width = '100%';
      input.oninput = () => {
        const previous = extraCatalogs[index];
        const next = input.value.trim();
        extraCatalogs[index] = next;
        if (selectedCatalog === previous) selectedCatalog = next;
      };

      const controls = document.createElement('span');
      controls.className = 'setting-control';

      const browse = document.createElement('button');
      browse.type = 'button';
      browse.className = 'btn-small btn-add';
      browse.textContent = selectedCatalog === url ? 'Selected' : 'Browse';
      browse.disabled = selectedCatalog === url;
      browse.onclick = async () => {
        selectedCatalog = url;
        renderCatalogs();
        await refresh();
      };

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn-small';
      remove.textContent = 'Remove';
      remove.onclick = async () => {
        const removed = extraCatalogs[index];
        extraCatalogs.splice(index, 1);
        if (selectedCatalog === removed) selectedCatalog = OFFICIAL_CATALOG;
        renderCatalogs();
        await saveConfig();
        if (selectedCatalog === OFFICIAL_CATALOG) await refresh();
      };

      const inputControl = document.createElement('span');
      inputControl.className = 'setting-name';
      inputControl.appendChild(input);
      controls.appendChild(browse);
      controls.appendChild(document.createTextNode(' '));
      controls.appendChild(remove);

      row.appendChild(inputControl);
      row.appendChild(controls);
      customCatalogsEl.appendChild(row);
    });
  }

  document.getElementById('ph-add').onclick = async () => {
    const input = document.getElementById('ph-new');
    const url = input.value.trim();
    if (!url || isReservedCatalog(url) || extraCatalogs.includes(url)) return;
    extraCatalogs.push(url);
    extraCatalogs = normalizeExtraCatalogs(extraCatalogs);
    input.value = '';
    renderCatalogs();
    await saveConfig();
  };

  function pluginCard(plugin, installed) {
    const isInstalled = installed.has(plugin.name);
    const localVersion = isInstalled ? installed.get(plugin.name) : null;
    const updateAvailable =
      isInstalled && hasUpdate(localVersion, plugin.version);

    const card = document.createElement('div');
    card.className = 'setting-row';

    let state = '';
    if (updateAvailable) {
      state =
        ' <span style="color:#c0392b">Update available (v' +
        escapeHtml(localVersion || '?') +
        ' → v' +
        escapeHtml(plugin.version) +
        ')</span>';
    } else if (isInstalled) {
      state =
        ' <span style="color:#27ae60">' +
        escapeHtml(installedLabel(localVersion, plugin.version)) +
        '</span>';
    } else if (plugin.version) {
      state =
        ' <span style="color:#888">v' +
        escapeHtml(plugin.version) +
        '</span>';
    }

    const meta = document.createElement('span');
    meta.className = 'setting-name';
    meta.innerHTML =
      '<strong>' +
      escapeHtml(plugin.title || plugin.name) +
      '</strong>' +
      (plugin.author
        ? ' <span style="color:#888">by ' +
          escapeHtml(plugin.author) +
          '</span>'
        : '') +
      state +
      '<br><span style="color:#666">' +
      escapeHtml(plugin.description || '') +
      '</span>';

    const controls = document.createElement('span');
    controls.className = 'setting-control';

    const install = document.createElement('button');
    install.type = 'button';
    install.className = 'btn-small btn-add';
    const originalLabel = updateAvailable
      ? 'Update'
      : (isInstalled ? 'Reinstall' : 'Install');
    install.textContent = originalLabel;
    install.onclick = async () => {
      install.disabled = true;
      const verb = updateAvailable ? 'Updating' : 'Installing';
      status(verb + ' ' + (plugin.title || plugin.name) + '…');

      try {
        await installPlugin(plugin, (done, total) => {
          install.textContent = verb + '… ' + done + '/' + total;
        });
        status(
          (updateAvailable ? 'Updated ' : 'Installed ') +
          (plugin.title || plugin.name) +
          '. Reconnect or reopen Settings to use it.'
        );
        await refresh();
      } catch (e) {
        status('Error: ' + e.message);
        install.textContent = originalLabel;
        install.disabled = false;
      }
    };
    controls.appendChild(install);

    if (isInstalled) {
      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn-small';
      remove.textContent = 'Remove';
      remove.onclick = async () => {
        remove.disabled = true;
        status('Removing ' + (plugin.title || plugin.name) + '…');

        try {
          await uninstallPlugin(plugin);
          status('Removed ' + (plugin.title || plugin.name) + '.');
          await refresh();
        } catch (e) {
          status('Error: ' + e.message);
          remove.disabled = false;
        }
      };
      controls.appendChild(document.createTextNode(' '));
      controls.appendChild(remove);
    }

    card.appendChild(meta);
    card.appendChild(controls);
    return card;
  }

  async function refresh() {
    await saveConfig();
    renderCatalogs();
    listEl.innerHTML = '';

    const url = selectedCatalog;
    status('Loading ' + selectedCatalogLabel() + '…');

    let catalog;
    try {
      catalog = JSON.parse(await relayText(url));
    } catch (e) {
      status('Error loading ' + selectedCatalogLabel() + ': ' + e.message);
      return;
    }

    const names = await installedNames();
    const installed = new Map();
    for (const name of names) {
      installed.set(name, await installedVersion(name));
    }

    const catalogName = catalog.name || selectedCatalogLabel();
    const plugins = Array.isArray(catalog.plugins) ? catalog.plugins : [];
    let updates = 0;

    if (plugins.length) {
      const header = document.createElement('h3');
      header.textContent = catalogName;
      header.style.margin = '0.8em 0 0.2em';
      listEl.appendChild(header);
    }

    for (const plugin of plugins) {
      if (
        installed.has(plugin.name) &&
        hasUpdate(installed.get(plugin.name), plugin.version)
      ) {
        updates += 1;
      }
      listEl.appendChild(pluginCard(plugin, installed));
    }

    let message =
      plugins.length +
      ' plugin' +
      (plugins.length === 1 ? '' : 's') +
      ' available';
    if (updates) {
      message +=
        ', ' +
        updates +
        ' update' +
        (updates === 1 ? '' : 's');
    }
    status(message + '.');
  }

  document.getElementById('ph-refresh').onclick = refresh;

  try {
    await loadBuiltInCatalogs();
  } catch (e) {
    status('Error loading catalog index: ' + e.message);
    renderCatalogs();
    return;
  }

  const config = await loadConfig();
  if (Array.isArray(config.extraCatalogs)) {
    extraCatalogs = normalizeExtraCatalogs(config.extraCatalogs);
  } else if (Array.isArray(config.catalogs)) {
    // Accept an early/legacy multi-catalog shape without surfacing any built-in
    // or compatibility feed as a removable custom catalog.
    extraCatalogs = normalizeExtraCatalogs(config.catalogs);
  } else if (config.catalog) {
    extraCatalogs = normalizeExtraCatalogs([config.catalog]);
  }

  renderCatalogs();
  await checkHubVersion();
  await refresh();
});
