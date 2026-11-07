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
    getWindowOpenGuardResponse("http://127.0.0.1:4567/tasks/", "http://127.0.0.1:4567"),
    {
      action: "deny",
      openExternal: false
    }
  );

  assert.deepEqual(
    getWindowOpenGuardResponse("https://example.com/docs", "http://127.0.0.1:4567"),
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

const { EventEmitter } = require("node:events");
const { loadMain } = require("./main-test-harness.cjs");

test("registered Electron navigation listeners enforce target and frame policy", async () => {
  const opened = [];
  const webContents = new EventEmitter();
  let windowOpen;
  webContents.setWindowOpenHandler = (handler) => { windowOpen = handler; };
  const main = loadMain({ electron: {
    app: Object.assign(new EventEmitter(), {
      requestSingleInstanceLock: () => true, whenReady: () => new Promise(() => {})
    }),
    ipcMain: { handle() {} },
    shell: { openExternal: async (url) => { opened.push(url); } }
  } });
  main.registerWindowNavigationGuards({ webContents }, DJANGO_ORIGIN);
  for (const [name, url, frame, cancelled, external] of [
    ["will-navigate", `${DJANGO_ORIGIN}/tasks/`, true, false, false],
    ["will-navigate", "https://foreign.example/", true, true, true],
    ["will-redirect", "https://redirect.example/", true, true, true],
    ["will-redirect", "http://127.0.0.1:9999/", true, true, true],
    ["will-redirect", "file:///synthetic.html", true, true, false],
    ["will-redirect", `${DJANGO_ORIGIN}/tasks/`, true, false, false],
    ["will-redirect", "https://frame.example/", false, false, false]
  ]) {
    let prevented = 0;
    const before = opened.length;
    const event = { url, isMainFrame: frame, preventDefault: () => { prevented++; } };
    // Redirects carry the target on the event; navigation uses the second arg.
    webContents.emit(name, event, name === "will-navigate" ? url : "https://decoy.example/");
    assert.equal(prevented, Number(cancelled), `${name}: ${url}`);
    assert.deepEqual(opened.slice(before), external ? [url] : []);
  }
  for (const [url, external] of [[`${DJANGO_ORIGIN}/`, false], ["https://child.example/", true], ["javascript:bad()", false]]) {
    const before = opened.length;
    assert.equal(windowOpen({ url }).action, "deny");
    assert.deepEqual(opened.slice(before), external ? [url] : []);
  }
});

test("registered session header hook injects shell auth only for the exact origin", () => {
  let filter;
  let hook;
  const win = { webContents: { session: { webRequest: {
    onBeforeSendHeaders: (selected, handler) => { filter = selected; hook = handler; }
  } } } };
  loadMain().registerDesktopAuthHeaderInjection(win, DJANGO_ORIGIN, "synthetic-shell-key");
  assert.deepEqual(Array.from(filter.urls), [`${DJANGO_ORIGIN}/*`]);
  for (const url of [`${DJANGO_ORIGIN}/tasks/`, "http://127.0.0.1:9999/", "https://foreign.example/", "http://localhost:4567/"]) {
    let calls = 0;
    hook({ url, requestHeaders: { Accept: "text/html" } }, ({ requestHeaders }) => {
      calls++;
      assert.equal(requestHeaders.Accept, "text/html");
      assert.equal(requestHeaders["X-Desktop-Django-Token"], url.startsWith(DJANGO_ORIGIN)
        ? "synthetic-shell-key" : undefined);
    });
    assert.equal(calls, 1);
  }
});
