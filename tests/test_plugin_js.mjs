import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const LEGACY_CATALOG =
  'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/catalog.json';
const OFFICIAL_CATALOG =
  'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/official-catalog.json';
const COMMUNITY_CATALOG =
  'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/community-catalog.json';
const PRIVATE_CATALOG = 'https://example.test/private/catalog.json';

class Element {
  constructor(tag = 'div', id = '') {
    this.tagName = tag;
    this.id = id;
    this.children = [];
    this.className = '';
    this._innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.style = {};
    this.disabled = false;
    this.onclick = null;
    this.oninput = null;
    this.type = '';
  }

  set innerHTML(value) {
    this._innerHTML = value;
    if (value === '') this.children = [];
  }

  get innerHTML() {
    return this._innerHTML;
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }
}

function fakeDocument() {
  const ids = [
    'ph-version',
    'ph-catalogs',
    'ph-custom-catalogs',
    'ph-new',
    'ph-add',
    'ph-refresh',
    'ph-status',
    'ph-list',
  ];
  const elements = Object.fromEntries(ids.map((id) => [id, new Element('div', id)]));
  return {
    elements,
    getElementById(id) {
      assert.ok(elements[id], 'unexpected element lookup: ' + id);
      return elements[id];
    },
    createElement(tag) {
      return new Element(tag);
    },
    createTextNode(text) {
      const node = new Element('#text');
      node.textContent = text;
      return node;
    },
  };
}

function response({ status = 200, json, text = '' } = {}) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() {
      return json;
    },
    async text() {
      return text;
    },
  };
}

async function loadPlugin(globals = {}) {
  let render;
  const context = vm.createContext({
    CrossPoint: {
      registerPlugin(fn) {
        render = fn;
      },
    },
    URL,
    TextEncoder,
    Set,
    Map,
    Array,
    String,
    Number,
    Object,
    Promise,
    JSON,
    encodeURIComponent,
    btoa: (value) => Buffer.from(value, 'binary').toString('base64'),
    ...globals,
  });

  const source = await readFile(new URL('../plugin.js', import.meta.url), 'utf8');
  vm.runInContext(source, context, { filename: 'plugin.js' });
  assert.equal(typeof render, 'function');
  return render;
}

test('browser hub loads custom catalogs and only offers directional updates', async () => {
  const document = fakeDocument();
  const writes = [];
  const relayCalls = [];

  const officialCatalog = {
    name: 'Official Plugins',
    plugins: [
      {
        name: 'monthwallpaper',
        title: 'Month Wallpaper',
        version: '1.0.0',
        base: 'https://example.test/month/',
        files: ['manifest.json', 'plugin.js'],
      },
      {
        name: 'send2ereader',
        title: 'Send2Ereader',
        version: '0.1.2.2',
        base: 'https://example.test/send/',
        files: ['manifest.json', 'device.json', 'plugin.js'],
      },
    ],
  };
  const communityCatalog = {
    name: 'Community Plugins',
    plugins: [
      {
        name: 'community-only',
        title: 'Community Only',
        version: '1.0.0',
        base: 'https://example.test/community/',
        files: ['manifest.json', 'plugin.js'],
      },
    ],
  };
  const privateCatalog = {
    name: 'Private Test Plugins',
    plugins: [
      {
        name: 'private-test',
        title: 'Private Test',
        version: '0.0.1',
        base: 'https://example.test/private/',
        files: ['manifest.json', 'plugin.js'],
      },
    ],
  };

  async function fetch(url) {
    if (url.startsWith('/download?path=')) {
      const path = new URL(url, 'http://device').searchParams.get('path');
      if (path === '/.crosspoint/plugin-hub.json') {
        return response({
          text: JSON.stringify({ extraCatalogs: [PRIVATE_CATALOG] }),
        });
      }
      if (path === '/.crosspoint/plugins/pluginhub/manifest.json') {
        return response({ text: JSON.stringify({ version: '0.1.1' }) });
      }
      if (path === '/.crosspoint/plugins/monthwallpaper/manifest.json') {
        return response({ text: JSON.stringify({ version: '1.1.0' }) });
      }
      if (path === '/.crosspoint/plugins/send2ereader/manifest.json') {
        return response({ text: JSON.stringify({ version: '0.1.2.1' }) });
      }
      return response({ status: 404 });
    }

    if (url.startsWith('/api/files?path=')) {
      return response({
        json: [
          { name: 'monthwallpaper', isDirectory: true },
          { name: 'send2ereader', isDirectory: true },
        ],
      });
    }

    throw new Error('unexpected fetch: ' + url);
  }

  const api = {
    async writeFile(path, dataB64) {
      writes.push({
        path,
        data: Buffer.from(dataB64, 'base64').toString('utf8'),
      });
      return { ok: true };
    },
    async relay(method, url) {
      assert.equal(method, 'GET');
      relayCalls.push(url);
      if (url.includes('/repos/jadehawk/PluginHub.crosspoint-plugin/releases/latest')) {
        return { status: 200, body: JSON.stringify({ tag_name: 'v0.1.1' }) };
      }
      if (url === OFFICIAL_CATALOG) {
        return { status: 200, body: JSON.stringify(officialCatalog) };
      }
      if (url === COMMUNITY_CATALOG) {
        return { status: 200, body: JSON.stringify(communityCatalog) };
      }
      if (url === PRIVATE_CATALOG) {
        return { status: 200, body: JSON.stringify(privateCatalog) };
      }
      return { status: 404, body: '' };
    },
    async fetchToSd() {
      return { status: 200 };
    },
  };

  const render = await loadPlugin({ document, fetch });
  await render({ innerHTML: '' }, api);

  assert.equal(relayCalls.length, 2);
  assert.match(relayCalls[0], /PluginHub\.crosspoint-plugin\/releases\/latest$/);
  assert.deepEqual(relayCalls.slice(1), [OFFICIAL_CATALOG]);
  assert.equal(document.elements['ph-version'].textContent, 'Version: v0.1.1');

  const catalogRows = document.elements['ph-catalogs'].children;
  assert.equal(catalogRows.length, 2);
  assert.match(catalogRows[0].children[0].innerHTML, /Official Plugins/);
  assert.equal(catalogRows[0].children[1].textContent, 'Selected');
  assert.equal(catalogRows[0].children[1].disabled, true);
  assert.match(catalogRows[1].children[0].innerHTML, /Community Plugins/);
  assert.equal(catalogRows[1].children[1].textContent, 'Browse');

  const customRows = document.elements['ph-custom-catalogs'].children;
  assert.equal(customRows.length, 1);
  assert.equal(customRows[0].children[0].children[0].value, PRIVATE_CATALOG);
  assert.equal(customRows[0].children[1].children[0].textContent, 'Browse');

  assert.equal(writes.length, 1);
  assert.equal(writes[0].path, '/.crosspoint/plugin-hub.json');
  assert.deepEqual(JSON.parse(writes[0].data), {
    extraCatalogs: [PRIVATE_CATALOG],
  });

  let cards = document.elements['ph-list'].children.filter(
    (child) => child.className === 'setting-row'
  );
  assert.equal(cards.length, 2);
  assert.equal(cards[0].children[1].children[0].textContent, 'Reinstall');
  assert.equal(cards[1].children[1].children[0].textContent, 'Update');
  assert.match(document.elements['ph-status'].textContent, /2 plugins available, 1 update/);

  await catalogRows[1].children[1].onclick();
  assert.equal(relayCalls.at(-1), COMMUNITY_CATALOG);
  cards = document.elements['ph-list'].children.filter(
    (child) => child.className === 'setting-row'
  );
  assert.equal(cards.length, 1);
  assert.equal(cards[0].children[1].children[0].textContent, 'Install');

  const privateBrowse = document.elements['ph-custom-catalogs'].children[0].children[1].children[0];
  await privateBrowse.onclick();
  assert.equal(relayCalls.at(-1), PRIVATE_CATALOG);
  cards = document.elements['ph-list'].children.filter(
    (child) => child.className === 'setting-row'
  );
  assert.equal(cards.length, 1);
  assert.equal(cards[0].children[1].children[0].textContent, 'Install');

  const selectedPrivateInput = document.elements['ph-custom-catalogs'].children[0].children[0].children[0];
  selectedPrivateInput.value = LEGACY_CATALOG;
  selectedPrivateInput.oninput();
  await document.elements['ph-refresh'].onclick();
  assert.deepEqual(JSON.parse(writes.at(-1).data), { extraCatalogs: [] });
  assert.equal(document.elements['ph-custom-catalogs'].children.length, 0);
  assert.equal(relayCalls.at(-1), OFFICIAL_CATALOG);
});

test('browser hub adopts api.dir while migrating legacy config', async () => {
  const document = fakeDocument();
  const writes = [];
  const downloadPaths = [];
  const relayCalls = [];

  async function fetch(url) {
    if (url.startsWith('/download?path=')) {
      const path = new URL(url, 'http://device').searchParams.get('path');
      downloadPaths.push(path);
      if (path === '/plugins/pluginhub/config.json') {
        return response({ status: 404 });
      }
      if (path === '/.crosspoint/plugin-hub.json') {
        return response({
          text: JSON.stringify({
            catalogs: [
              LEGACY_CATALOG,
              OFFICIAL_CATALOG,
              COMMUNITY_CATALOG,
              PRIVATE_CATALOG,
            ],
          }),
        });
      }
      if (path === '/plugins/pluginhub/manifest.json') {
        return response({ text: JSON.stringify({ version: '0.1.4' }) });
      }
      return response({ status: 404 });
    }

    if (url.startsWith('/api/files?path=')) {
      return response({ json: [] });
    }

    throw new Error('unexpected fetch: ' + url);
  }

  const api = {
    dir: '/plugins/pluginhub/',
    async writeFile(path, dataB64) {
      writes.push({
        path,
        data: Buffer.from(dataB64, 'base64').toString('utf8'),
      });
      return { ok: true };
    },
    async relay(method, url) {
      assert.equal(method, 'GET');
      relayCalls.push(url);
      if (url.includes('/repos/jadehawk/PluginHub.crosspoint-plugin/releases/latest')) {
        return { status: 200, body: JSON.stringify({ tag_name: 'v0.1.4' }) };
      }
      if (url === OFFICIAL_CATALOG) {
        return { status: 200, body: JSON.stringify({ name: 'Official Plugins', plugins: [] }) };
      }
      if (url === PRIVATE_CATALOG) {
        return { status: 200, body: JSON.stringify({ name: 'Private', plugins: [] }) };
      }
      return { status: 404, body: '' };
    },
    async fetchToSd() {
      return { status: 200 };
    },
  };

  const render = await loadPlugin({ document, fetch });
  await render({ innerHTML: '' }, api);

  assert.deepEqual(downloadPaths.slice(0, 3), [
    '/plugins/pluginhub/config.json',
    '/.crosspoint/plugin-hub.json',
    '/plugins/pluginhub/manifest.json',
  ]);
  assert.equal(document.elements['ph-version'].textContent, 'Version: v0.1.4');
  assert.equal(writes.length, 1);
  assert.equal(writes[0].path, '/plugins/pluginhub/config.json');
  assert.deepEqual(JSON.parse(writes[0].data), {
    extraCatalogs: [PRIVATE_CATALOG],
  });
  assert.deepEqual(relayCalls.slice(1), [OFFICIAL_CATALOG]);
  const customRows = document.elements['ph-custom-catalogs'].children;
  assert.equal(customRows.length, 1);
  assert.equal(customRows[0].children[0].children[0].value, PRIVATE_CATALOG);
});
