import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';
import vm from 'node:vm';

const root = new URL('../', import.meta.url);
const DEFAULT_CATALOG =
  'https://raw.githubusercontent.com/jadehawk/PluginHub.crosspoint-plugin/main/catalog.json';
const PRIVATE_CATALOG = 'https://example.test/private/catalog.json';

class Element {
  constructor(tag = 'div', id = '') {
    this.tagName = tag;
    this.id = id;
    this.children = [];
    this.className = '';
    this.innerHTML = '';
    this.textContent = '';
    this.value = '';
    this.style = {};
    this.disabled = false;
    this.onclick = null;
    this.oninput = null;
    this.type = '';
  }

  appendChild(child) {
    this.children.push(child);
    return child;
  }
}

function fakeDocument() {
  const ids = ['ph-catalogs', 'ph-new', 'ph-add', 'ph-refresh', 'ph-status', 'ph-list'];
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

  const defaultCatalog = {
    name: 'Plugin Hub',
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
      if (url === DEFAULT_CATALOG) {
        return { status: 200, body: JSON.stringify(defaultCatalog) };
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

  assert.deepEqual(relayCalls, [DEFAULT_CATALOG, PRIVATE_CATALOG]);
  assert.equal(writes.length, 1);
  assert.equal(writes[0].path, '/.crosspoint/plugin-hub.json');
  assert.deepEqual(JSON.parse(writes[0].data), {
    extraCatalogs: [PRIVATE_CATALOG],
  });

  const cards = document.elements['ph-list'].children.filter(
    (child) => child.className === 'setting-row'
  );
  assert.equal(cards.length, 3);

  const monthButton = cards[0].children[1].children[0];
  const sendButton = cards[1].children[1].children[0];
  const privateButton = cards[2].children[1].children[0];

  assert.equal(monthButton.textContent, 'Reinstall');
  assert.equal(sendButton.textContent, 'Update');
  assert.equal(privateButton.textContent, 'Install');
  assert.match(document.elements['ph-status'].textContent, /3 plugins available, 1 update/);
});
