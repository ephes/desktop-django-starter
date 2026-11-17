const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getNavigationGuardAction,
  getRedirectGuardAction,
  getWindowOpenGuardResponse,
  isExternalOpenableUrl,
  isTrustedIpcSender
} = require("./window-guards.cjs");

test("isExternalOpenableUrl allows only expected external protocols", () => {
  assert.equal(isExternalOpenableUrl("https://example.com/docs"), true);
  assert.equal(isExternalOpenableUrl("http://example.com/docs"), true);
  assert.equal(isExternalOpenableUrl("mailto:support@example.com"), true);
  assert.equal(isExternalOpenableUrl("file:///tmp/local.html"), false);
  assert.equal(isExternalOpenableUrl("javascript:alert(1)"), false);
  assert.equal(isExternalOpenableUrl("not-a-url"), false);
});

test("navigation guard allows in-app localhost navigation", () => {
  assert.deepEqual(
    getNavigationGuardAction("http://127.0.0.1:4567/tasks/", "http://127.0.0.1:4567"),
    {
      allowNavigation: true,
      openExternal: false
    }
  );
});

test("navigation guard blocks external navigation and opens safe external URLs", () => {
  assert.deepEqual(
    getNavigationGuardAction("https://example.com/docs", "http://127.0.0.1:4567"),
    {
      allowNavigation: false,
      openExternal: true
    }
  );

  assert.deepEqual(
    getNavigationGuardAction("javascript:alert(1)", "http://127.0.0.1:4567"),
    {
      allowNavigation: false,
      openExternal: false
    }
  );
});

test("window open guard always denies child windows", () => {
  assert.deepEqual(
    getWindowOpenGuardResponse({ url: "http://127.0.0.1:4567/tasks/", referrer: { url: "http://127.0.0.1:4567/" } }, "http://127.0.0.1:4567"),
    {
      action: "deny",
      openExternal: false
    }
  );

  assert.deepEqual(
    getWindowOpenGuardResponse({ url: "https://example.com/docs", referrer: { url: "http://127.0.0.1:4567/" } }, "http://127.0.0.1:4567"),
    {
      action: "deny",
      openExternal: true
    }
  );
});

const DJANGO_ORIGIN = "http://127.0.0.1:4567";

test("redirect guard keeps same-origin main-frame redirects in the app", () => {
  assert.deepEqual(
    getRedirectGuardAction({ url: "http://127.0.0.1:4567/tasks/", isMainFrame: true }, DJANGO_ORIGIN),
    {
      allowNavigation: true,
      openExternal: false
    }
  );
});

test("redirect guard blocks off-origin main-frame redirects and opens safe URLs externally", () => {
  assert.deepEqual(
    getRedirectGuardAction(
      { url: "https://accounts.example.com/o/oauth2/auth?client_id=x", isMainFrame: true },
      DJANGO_ORIGIN
    ),
    {
      allowNavigation: false,
      openExternal: true
    }
  );

  // Same host, different port is a different origin.
  assert.deepEqual(
    getRedirectGuardAction({ url: "http://127.0.0.1:9999/", isMainFrame: true }, DJANGO_ORIGIN),
    {
      allowNavigation: false,
      openExternal: true
    }
  );

  assert.deepEqual(
    getRedirectGuardAction({ url: "file:///etc/passwd", isMainFrame: true }, DJANGO_ORIGIN),
    {
      allowNavigation: false,
      openExternal: false
    }
  );
});

test("redirect guard fails closed when the redirect target is missing or malformed", () => {
  for (const details of [{}, { isMainFrame: true }, { url: "not-a-url", isMainFrame: true }, null, undefined]) {
    assert.deepEqual(getRedirectGuardAction(details, DJANGO_ORIGIN), {
      allowNavigation: false,
      openExternal: false
    });
  }
});

test("redirect guard leaves subframe redirects to the subframe policy", () => {
  assert.deepEqual(
    getRedirectGuardAction({ url: "https://www.youtube.com/embed/x", isMainFrame: false }, DJANGO_ORIGIN),
    {
      allowNavigation: true,
      openExternal: false
    }
  );
});

test("IPC sender check accepts only frames on the Django origin", () => {
  assert.equal(
    isTrustedIpcSender({ senderFrame: { url: "http://127.0.0.1:4567/tasks/" } }, DJANGO_ORIGIN),
    true
  );
  assert.equal(
    isTrustedIpcSender({ senderFrame: { url: "https://evil.example/" } }, DJANGO_ORIGIN),
    false
  );
  assert.equal(
    isTrustedIpcSender({ senderFrame: { url: "http://127.0.0.1:9999/" } }, DJANGO_ORIGIN),
    false
  );
  assert.equal(
    isTrustedIpcSender({ senderFrame: { url: "file:///splash.html" } }, DJANGO_ORIGIN),
    false
  );
  assert.equal(isTrustedIpcSender({ senderFrame: null }, DJANGO_ORIGIN), false);
  assert.equal(isTrustedIpcSender({}, DJANGO_ORIGIN), false);
  assert.equal(isTrustedIpcSender(undefined, DJANGO_ORIGIN), false);
  assert.equal(
    isTrustedIpcSender({ senderFrame: { url: "http://127.0.0.1:4567/" } }, null),
    false
  );
});

test("main.js wires the redirect guard and the IPC sender check", () => {
  const fs = require("node:fs");
  const path = require("node:path");
  const mainSource = fs.readFileSync(path.join(__dirname, "..", "main.js"), "utf8");

  for (const snippet of [
    'webContents.on("will-redirect"',
    "getRedirectGuardAction(",
    "isTrustedIpcSender(event, currentAppUrl)"
  ]) {
    assert.ok(mainSource.includes(snippet), `main.js should contain ${snippet}`);
  }
});

function permissionFixture(permissions) {
  const handlers = {};
  const owner = {
    isDestroyed: () => false,
    getURL: () => `${DJANGO_ORIGIN}/`,
    session: {
      setPermissionRequestHandler: (handler) => { handlers.request = handler; },
      setPermissionCheckHandler: (handler) => { handlers.check = handler; }
    }
  };
  require('./window-guards.cjs').registerSessionPermissionPolicy(owner, DJANGO_ORIGIN, permissions);
  const request = (permission, details, contents = owner) => {
    const answers = [];
    handlers.request(contents, permission, (answer) => answers.push(answer), details);
    assert.equal(answers.length, 1);
    return answers[0];
  };
  return { owner, handlers, request };
}

test('session permission handlers deny every capability without explicit app policy', () => {
  const { owner, handlers, request } = permissionFixture();
  for (const permission of ['media', 'geolocation', 'notifications', 'clipboard-read', 'unknown']) {
    for (const requestingUrl of [DJANGO_ORIGIN, 'https://remote.invalid/', undefined]) {
      const details = { requestingUrl, isMainFrame: true };
      assert.equal(request(permission, details), false);
      assert.equal(handlers.check(owner, permission, requestingUrl, details), false);
    }
  }
});

test('explicit capabilities require the live owned Django main frame in both handlers', () => {
  const { owner, handlers, request } = permissionFixture(['geolocation']);
  const trusted = { requestingUrl: `${DJANGO_ORIGIN}/tasks/`, isMainFrame: true };
  assert.equal(request('geolocation', trusted), true);
  assert.equal(handlers.check(owner, 'geolocation', DJANGO_ORIGIN, trusted), true);
  assert.equal(request('media', trusted), false);
  assert.equal(handlers.check(owner, 'media', DJANGO_ORIGIN, trusted), false);
  for (const details of [undefined, {}, { ...trusted, isMainFrame: false },
    { ...trusted, requestingUrl: 'https://remote.invalid/' },
    { ...trusted, requestingUrl: 'http://127.0.0.1:9999/' },
    { ...trusted, requestingUrl: 'about:blank' }, { isMainFrame: true }]) {
    assert.equal(request('geolocation', details), false);
    assert.equal(handlers.check(owner, 'geolocation', DJANGO_ORIGIN, details), false);
  }
  for (const contents of [null, { ...owner }, { ...owner, isDestroyed: () => true }]) {
    assert.equal(request('geolocation', trusted, contents), false);
    assert.equal(handlers.check(contents, 'geolocation', DJANGO_ORIGIN, trusted), false);
  }
  for (const origin of [undefined, 'null', 'https://remote.invalid/', 'http://127.0.0.1:9999/']) {
    assert.equal(handlers.check(owner, 'geolocation', origin, trusted), false);
  }
  owner.getURL = () => 'https://remote.invalid/';
  assert.equal(request('geolocation', trusted), false);
  assert.equal(handlers.check(owner, 'geolocation', DJANGO_ORIGIN, trusted), false);
});

test('main window installs both permission handlers before loading any app content', () => {
  const fs = require('node:fs');
  const path = require('node:path');
  const vm = require('node:vm');
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');
  const createWindowSource = source.slice(source.indexOf('function createWindow('), source.indexOf('\nasync function stopDjango('));
  const installed = {};
  const contents = {
    session: {
      setPermissionRequestHandler: (handler) => { installed.request = handler; },
      setPermissionCheckHandler: (handler) => { installed.check = handler; }
    },
    once() {}
  };
  let loads = 0;
  class BrowserWindow {
    constructor() { this.webContents = contents; }
    on() {}
    once() {}
    loadURL(url) {
      assert.equal(url, DJANGO_ORIGIN);
      assert.equal(typeof installed.request, 'function');
      assert.equal(typeof installed.check, 'function');
      loads += 1;
    }
  }
  vm.runInNewContext(`${createWindowSource}\ncreateWindow(origin, 'test-token');`, {
    BrowserWindow, origin: DJANGO_ORIGIN, path, __dirname,
    getWindowIconOptions: () => ({}),
    registerDesktopAuthHeaderInjection() {}, registerWindowNavigationGuards() {},
    registerSessionPermissionPolicy: require('./window-guards.cjs').registerSessionPermissionPolicy
  });
  assert.equal(loads, 1);
});

function installedPopupFixture() {
  const fs = require('node:fs');
  const path = require('node:path');
  const vm = require('node:vm');
  const guards = require('./window-guards.cjs');
  const source = fs.readFileSync(path.join(__dirname, '..', 'main.js'), 'utf8');
  const registration = source.slice(source.indexOf('function registerWindowNavigationGuards('), source.indexOf('\nfunction applyNavigationGuardAction('));
  let popup;
  let alive = true;
  let currentUrl = `${DJANGO_ORIGIN}/`;
  const dispatched = [];
  const win = { webContents: {
    setWindowOpenHandler: (handler) => { popup = handler; },
    on() {}, isDestroyed: () => !alive, getURL: () => currentUrl
  } };
  vm.runInNewContext(`${registration}\nregisterWindowNavigationGuards(win, origin);`, {
    ...guards, win, origin: DJANGO_ORIGIN,
    shell: { openExternal: async (url) => { dispatched.push(url); } }
  });
  return {
    popup: (details) => {
      // The callback belongs to another VM realm.
      assert.equal(JSON.stringify(popup(details)), JSON.stringify({ action: 'deny' }));
    },
    dispatched,
    destroy: () => { alive = false; },
    navigate: (url) => { currentUrl = url; }
  };
}

test('installed popup callback refuses native dispatch for foreign or unknown requesters', () => {
  const fixture = installedPopupFixture();
  for (const details of [
    undefined, null, {},
    { url: 'https://popup.invalid/', referrer: { url: 'https://remote.invalid/' } },
    { url: 'https://popup.invalid/', referrer: { url: 'http://127.0.0.1:9999/' } },
    { url: 'https://popup.invalid/', referrer: { url: 'about:blank' } },
    { url: 'https://popup.invalid/', referrer: { url: '' } },
    { url: 'https://popup.invalid/', referrer: {} },
    { url: 'https://popup.invalid/', referrer: { url: DJANGO_ORIGIN, policy: 'no-referrer' } },
    { url: 'https://popup.invalid/', disposition: 'foreground-tab' }
  ]) fixture.popup(details);
  assert.deepEqual(fixture.dispatched, []);
});

test('installed popup callback dispatches a trusted safe outbound link exactly once', () => {
  const fixture = installedPopupFixture();
  const referrer = { url: `${DJANGO_ORIGIN}/tasks/` };
  fixture.popup({ url: 'https://popup.invalid/', referrer });
  assert.deepEqual(fixture.dispatched, ['https://popup.invalid/']);
  for (const url of ['javascript:alert(1)', 'file:///tmp/local.html', 'not-a-url', `${DJANGO_ORIGIN}/tasks/`]) {
    fixture.popup({ url, referrer });
  }
  fixture.navigate('https://remote.invalid/');
  fixture.popup({ url: 'https://popup.invalid/stale', referrer });
  fixture.destroy();
  fixture.popup({ url: 'https://popup.invalid/destroyed', referrer });
  assert.deepEqual(fixture.dispatched, ['https://popup.invalid/']);
});
