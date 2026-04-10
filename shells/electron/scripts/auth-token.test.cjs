const test = require("node:test");
const assert = require("node:assert/strict");

const {
  DESKTOP_AUTH_HEADER,
  buildDesktopAuthHeaders,
  desktopAuthHeadersForRequest,
  getDesktopAuthWebRequestFilter,
  requestUrlMatchesOrigin
} = require("./auth-token.cjs");

test("requestUrlMatchesOrigin matches only the exact Django origin", () => {
  const origin = "http://127.0.0.1:4567";

  assert.equal(requestUrlMatchesOrigin("http://127.0.0.1:4567/", origin), true);
  assert.equal(requestUrlMatchesOrigin("http://127.0.0.1:4567/static/app.css", origin), true);
  assert.equal(requestUrlMatchesOrigin("http://127.0.0.1:4568/", origin), false);
  assert.equal(requestUrlMatchesOrigin("http://localhost:4567/", origin), false);
  assert.equal(requestUrlMatchesOrigin("https://127.0.0.1:4567/", origin), false);
  assert.equal(requestUrlMatchesOrigin("file:///tmp/splash.html", origin), false);
  assert.equal(requestUrlMatchesOrigin("not-a-url", origin), false);
});

test("desktop auth header is added only for the Django origin", () => {
  const origin = "http://127.0.0.1:4567";
  const token = "token";
  const originalHeaders = {
    Accept: "text/html"
  };

  assert.deepEqual(
    desktopAuthHeadersForRequest(
      { url: "http://127.0.0.1:4567/items/", requestHeaders: originalHeaders },
      origin,
      token
    ),
    {
      Accept: "text/html",
      [DESKTOP_AUTH_HEADER]: token
    }
  );

  assert.deepEqual(
    desktopAuthHeadersForRequest(
      { url: "http://example.test/", requestHeaders: originalHeaders },
      origin,
      token
    ),
    originalHeaders
  );
});

test("desktop auth helpers omit empty tokens", () => {
  assert.deepEqual(buildDesktopAuthHeaders(""), {});

  const headers = { Accept: "text/html" };
  assert.deepEqual(
    desktopAuthHeadersForRequest(
      { url: "http://127.0.0.1:4567/", requestHeaders: headers },
      "http://127.0.0.1:4567",
      ""
    ),
    headers
  );
});

test("webRequest filter is scoped to the exact Django origin", () => {
  assert.deepEqual(
    getDesktopAuthWebRequestFilter("http://127.0.0.1:4567"),
    { urls: ["http://127.0.0.1:4567/*"] }
  );
});
