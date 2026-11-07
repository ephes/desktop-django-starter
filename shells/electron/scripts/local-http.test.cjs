const test = require("node:test");
const assert = require("node:assert/strict");
const net = require("node:net");
const http = require("node:http");
const { once } = require("node:events");
const { loadMain } = require("./main-test-harness.cjs");

async function peer(t, handler, raw = false) {
  const sockets = new Set();
  const server = raw ? net.createServer(handler) : http.createServer(handler);
  server.on("connection", (socket) => {
    sockets.add(socket);
    socket.on("error", () => {});
    socket.on("close", () => sockets.delete(socket));
  });
  server.listen(0, "127.0.0.1");
  await once(server, "listening");
  t.after(async () => {
    for (const socket of sockets) socket.destroy();
    await new Promise((resolve) => server.close(resolve));
  });
  return `http://127.0.0.1:${server.address().port}`;
}

test("health accepts an on-time 200 and sends shell auth", async (t) => {
  const url = await peer(t, (req, res) => {
    assert.equal(req.url, "/health/");
    assert.equal(req.headers["x-desktop-django-token"], "synthetic");
    res.end("ok");
  });
  await loadMain().waitForDjango(url, "synthetic", 500);
});

for (const drip of [false, true]) {
  test(`startup rejects ${drip ? "dripping" : "delayed"} headers within its budget`, async (t) => {
    const url = await peer(t, (socket) => {
      const timer = drip
        ? setInterval(() => socket.write("X-Padding: a\r\n"), 20)
        : setTimeout(() => socket.end("HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n"), 350);
      if (drip) socket.write("HTTP/1.1 200 OK\r\n");
      socket.on("close", () => { clearTimeout(timer); clearInterval(timer); });
    }, true);
    const start = performance.now();
    await assert.rejects(loadMain().waitForDjango(url, "", 100), /did not become ready/);
    assert.ok(performance.now() - start < 300);
  });
}

test("failed health request cannot settle the next retry", async (t) => {
  let calls = 0;
  const url = await peer(t, (_req, res) => res.writeHead(++calls === 1 ? 503 : 200).end());
  await loadMain().waitForDjango(url, "", 1000);
  assert.equal(calls, 2);
});

for (const [name, reply] of [
  ["oversized", "HTTP/1.1 200 OK\r\n\r\n" + JSON.stringify({ padding: "é".repeat(9000) })],
  ["truncated", "HTTP/1.1 200 OK\r\nContent-Length: 100\r\n\r\n{}"],
  ["malformed", "HTTP/1.1 200 OK\r\n\r\nnot json"],
  ["status", "HTTP/1.1 503 Unavailable\r\n\r\n{}"]
]) {
  test(`activity rejects ${name} response`, async (t) => {
    const url = await peer(t, (socket) => socket.end(reply), true);
    await assert.rejects(loadMain().getActivity(url));
  });
}

test("activity accepts a tiny complete count object", async (t) => {
  const url = await peer(t, (_req, res) => res.end('{"running_tasks":1,"queued_tasks":2}'));
  const counts = await loadMain().getActivity(url);
  assert.equal(counts.running_tasks, 1);
  assert.equal(counts.queued_tasks, 2);
});

test("activity deadline closes a body trickle and clears owned timers", async (t) => {
  let closed;
  const disconnected = new Promise((resolve) => { closed = resolve; });
  const url = await peer(t, (socket) => {
    socket.write("HTTP/1.1 200 OK\r\n\r\n");
    const timer = setInterval(() => socket.write(" "), 100);
    socket.on("close", () => { clearInterval(timer); closed(); });
  }, true);
  const timers = new Set();
  const main = loadMain({}, {
    setTimeout: (fn, ms) => {
      const timer = setTimeout(fn, ms);
      timers.add(timer);
      return timer;
    },
    clearTimeout: (timer) => { timers.delete(timer); clearTimeout(timer); }
  });
  const start = performance.now();
  await assert.rejects(main.getActivity(url), /timed out/);
  assert.ok(performance.now() - start < 1800);
  assert.equal(timers.size, 0);
  await Promise.race([disconnected, new Promise((_, reject) => {
    const timer = setTimeout(() => reject(new Error("socket left open")), 500);
    t.after(() => clearTimeout(timer));
  })]);
});
