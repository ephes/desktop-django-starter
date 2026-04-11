const test = require("node:test");
const assert = require("node:assert/strict");

const {
  getNavigationGuardAction,
  getWindowOpenGuardResponse,
  isExternalOpenableUrl
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
