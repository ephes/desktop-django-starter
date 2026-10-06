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
