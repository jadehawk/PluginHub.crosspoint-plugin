// Plugin Hub browser UI — manage CrossPoint plugins from the generated Hub
// catalog plus optional user-supplied catalogs.
CrossPoint.registerPlugin(async (container, api) => {
  const CONFIG_PATH = '/.crosspoint/plugin-hub.json';
  const PLUGINS_DIR = '/.crosspoint/plugins';
  const DEFAULT_CATALOG =
    'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/catalog.json';

  let extraCatalogs = [];

  container.innerHTML =
    '<h2>Plugin Hub</h2>' +
    '<h3 style="margin:0.5em 0 0.2em">Catalogs</h3>' +
    '<div id="ph-catalogs"></div>' +
    '<div class="setting-row">' +
    '<span class="setting-control"><input type="text" id="ph-new" placeholder="https://.../catalog.json" style="width:100%"></span>' +
    '<button type="button" class="btn-small btn-add" id="ph-add">Add catalog</button></div>' +
    '<div class="setting-row"><button type="button" class="btn-small btn-add" id="ph-refresh">Save &amp; refresh</button></div>' +
    '<p id="ph-status"></p>' +
    '<div id="ph-list"></div>';

  const catalogsEl = document.getElementById('ph-catalogs');
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

  function allCatalogs() {
    const seen = new Set([DEFAULT_CATALOG]);
    const urls = [DEFAULT_CATALOG];
    for (const url of extraCatalogs) {
      const trimmed = String(url || '').trim();
      if (!trimmed || seen.has(trimmed)) continue;
      seen.add(trimmed);
      urls.push(trimmed);
    }
    return urls;
  }

  async function loadConfig() {
    try {
      const response = await fetch('/download?path=' + encodeURIComponent(CONFIG_PATH));
      if (!response.ok) return {};
      return JSON.parse(await response.text());
    } catch (e) {
      return {};
    }
  }

  function saveConfig() {
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
    try {
      const path = PLUGINS_DIR + '/' + name + '/manifest.json';
      const response = await fetch('/download?path=' + encodeURIComponent(path));
      if (!response.ok) return null;
      return (JSON.parse(await response.text()).version) || null;
    } catch (e) {
      return null;
    }
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

  async function relayText(url) {
    const response = await api.relay('GET', url, {}, '');
    if (response.error || (response.status && (response.status < 200 || response.status >= 300))) {
      throw new Error('HTTP ' + (response.status || response.error));
    }
    return response.body;
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

    const primary = document.createElement('div');
    primary.className = 'setting-row';
    primary.innerHTML =
      '<span class="setting-name"><strong>Plugin Hub</strong><br>' +
      '<span style="color:#666">Built-in community catalog</span></span>' +
      '<span class="setting-control"><input type="text" value="' +
      escapeHtml(DEFAULT_CATALOG) +
      '" style="width:100%" readonly></span>';
    catalogsEl.appendChild(primary);

    extraCatalogs.forEach((url, index) => {
      const row = document.createElement('div');
      row.className = 'setting-row';

      const input = document.createElement('input');
      input.type = 'text';
      input.value = url;
      input.style.width = '100%';
      input.oninput = () => {
        extraCatalogs[index] = input.value.trim();
      };

      const remove = document.createElement('button');
      remove.type = 'button';
      remove.className = 'btn-small';
      remove.textContent = 'Remove';
      remove.onclick = () => {
        extraCatalogs.splice(index, 1);
        renderCatalogs();
      };

      const control = document.createElement('span');
      control.className = 'setting-control';
      control.appendChild(input);

      row.appendChild(control);
      row.appendChild(remove);
      catalogsEl.appendChild(row);
    });
  }

  document.getElementById('ph-add').onclick = () => {
    const input = document.getElementById('ph-new');
    const url = input.value.trim();
    if (!url || url === DEFAULT_CATALOG || extraCatalogs.includes(url)) return;
    extraCatalogs.push(url);
    input.value = '';
    renderCatalogs();
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
    listEl.innerHTML = '';

    const urls = allCatalogs();
    status(
      'Loading ' +
      urls.length +
      ' catalog' +
      (urls.length === 1 ? '' : 's') +
      '…'
    );

    const names = await installedNames();
    const installed = new Map();
    for (const name of names) {
      installed.set(name, await installedVersion(name));
    }

    let total = 0;
    let updates = 0;
    const errors = [];

    for (const url of urls) {
      let catalog;
      try {
        catalog = JSON.parse(await relayText(url));
      } catch (e) {
        errors.push(hostOf(url) + ': ' + e.message);
        continue;
      }

      const catalogName =
        catalog.name ||
        (url === DEFAULT_CATALOG ? 'Plugin Hub' : hostOf(url));
      const plugins = Array.isArray(catalog.plugins) ? catalog.plugins : [];

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
        total += 1;
      }
    }

    let message =
      total +
      ' plugin' +
      (total === 1 ? '' : 's') +
      ' available';
    if (updates) {
      message +=
        ', ' +
        updates +
        ' update' +
        (updates === 1 ? '' : 's');
    }
    message += '.';

    if (errors.length) {
      message +=
        ' (' +
        errors.length +
        ' catalog' +
        (errors.length === 1 ? '' : 's') +
        ' failed: ' +
        errors.join('; ') +
        ')';
    }

    status(message);
  }

  document.getElementById('ph-refresh').onclick = refresh;

  const config = await loadConfig();
  if (Array.isArray(config.extraCatalogs)) {
    extraCatalogs = config.extraCatalogs;
  } else if (Array.isArray(config.catalogs)) {
    // Accept an early/legacy multi-catalog shape while keeping the Hub catalog
    // built in and non-removable.
    extraCatalogs = config.catalogs.filter((url) => url !== DEFAULT_CATALOG);
  } else if (config.catalog && config.catalog !== DEFAULT_CATALOG) {
    extraCatalogs = [config.catalog];
  }

  renderCatalogs();
  await refresh();
});
