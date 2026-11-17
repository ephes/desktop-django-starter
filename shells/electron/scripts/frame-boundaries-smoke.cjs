// Real Chromium fixture: synthetic loopback origins, no personal data or OS grants.
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { registerSessionPermissionPolicy } = require('./window-guards.cjs');
const { desktopAuthHeadersForRequest, getDesktopAuthWebRequestFilter } = require('./auth-token.cjs');

const fixtureData = fs.mkdtempSync(path.join(os.tmpdir(), 'dds-frame-fixture-'));
app.setPath('userData', fixtureData);
app.commandLine.appendSwitch('use-fake-device-for-media-stream');
const servers = [];
let win;
const deadline = setTimeout(() => {
  console.error('Frame boundary fixture timed out');
  app.exit(1);
}, 20000);

async function serve(handler) {
  const server = http.createServer(handler);
  servers.push(server);
  await new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(0, '127.0.0.1', resolve);
  });
  return `http://127.0.0.1:${server.address().port}`;
}

app.whenReady().then(async () => {
  const token = 'synthetic-frame-fixture-token';
  const remote = await serve((req, res) => {
    assert.equal(req.headers['x-desktop-django-token'], undefined);
    res.setHeader('Content-Type', 'text/html');
    res.end('<!doctype html><title>Remote fixture</title>Ordinary remote embed');
  });
  const trusted = await serve((req, res) => {
    assert.equal(req.headers['x-desktop-django-token'], token);
    res.setHeader('Content-Type', 'text/html');
    res.end(`<!doctype html><title>Trusted fixture</title><iframe src="${remote}/" allow="camera *; microphone *; geolocation *"></iframe>`);
  });
  win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, nodeIntegration: false } });
  const contents = win.webContents;
  registerSessionPermissionPolicy(contents, trusted);
  contents.session.webRequest.onBeforeSendHeaders(getDesktopAuthWebRequestFilter(trusted), (details, callback) => {
    callback({ requestHeaders: desktopAuthHeadersForRequest(details, trusted, token) });
  });
  await win.loadURL(trusted);
  const frame = contents.mainFrame.frames.find((candidate) => candidate.url === `${remote}/`);
  assert.ok(frame, 'remote embed loaded normally');
  const results = await frame.executeJavaScript(`(async () => {
    const states = {};
    for (const name of ['camera', 'microphone', 'geolocation', 'notifications']) {
      states[name] = (await navigator.permissions.query({name})).state;
    }
    const media = [];
    for (const constraints of [{audio:true}, {video:true}]) {
      try {
        const stream = await navigator.mediaDevices.getUserMedia(constraints);
        stream.getTracks().forEach(track => track.stop());
        media.push('granted');
      } catch (error) { media.push(error.name); }
    }
    const geolocation = await new Promise(resolve => navigator.geolocation.getCurrentPosition(
      () => resolve('granted'), error => resolve(error.code), {timeout:3000}));
    const notifications = await Notification.requestPermission();
    return {states, media, geolocation, notifications};
  })()`);
  assert.deepEqual(results.states, { camera: 'denied', microphone: 'denied', geolocation: 'denied', notifications: 'denied' });
  assert.deepEqual(results.media, ['NotAllowedError', 'NotAllowedError']);
  assert.equal(results.geolocation, 1);
  assert.equal(results.notifications, 'denied');
  console.log('PASS: remote iframe capabilities denied; embed and exact-origin auth headers preserved');
}).then(() => finish(0), (error) => { console.error(error); finish(1); });

function finish(code) {
  clearTimeout(deadline);
  if (win && !win.isDestroyed()) win.destroy();
  for (const server of servers) server.close();
  // Only this fixture's private temporary profile is removed.
  app.once('quit', () => fs.rmSync(fixtureData, { recursive: true, force: true }));
  app.exit(code);
}
