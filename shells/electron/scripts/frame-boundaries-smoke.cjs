// Real Chromium fixture: synthetic loopback origins, no personal data or OS grants.
const { app, BrowserWindow } = require('electron');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const os = require('node:os');
const path = require('node:path');
const { registerSessionPermissionPolicy, registerWindowOpenGuard } = require('./window-guards.cjs');
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
  // Record auth headers and assert after the loads, so an isolation regression
  // fails through finish(1) instead of an uncaught exception in a handler.
  const remoteTokens = [];
  const trustedTokens = [];
  const remote = await serve((req, res) => {
    remoteTokens.push(req.headers['x-desktop-django-token']);
    res.setHeader('Content-Type', 'text/html');
    res.end('<!doctype html><title>Remote fixture</title>Ordinary remote embed');
  });
  const trusted = await serve((req, res) => {
    trustedTokens.push(req.headers['x-desktop-django-token']);
    // Mirror the starter's Django SECURE_REFERRER_POLICY; Django's default
    // same-origin is exercised separately on /same-origin/.
    res.setHeader('Referrer-Policy', req.url === '/same-origin/' ? 'same-origin' : 'strict-origin-when-cross-origin');
    res.setHeader('Content-Type', 'text/html');
    res.end(`<!doctype html><title>Trusted fixture</title><iframe src="${remote}/" allow="camera *; microphone *; geolocation *"></iframe>`);
  });
  win = new BrowserWindow({ show: false, webPreferences: { contextIsolation: true, nodeIntegration: false } });
  const contents = win.webContents;
  registerSessionPermissionPolicy(contents, trusted);
  contents.session.webRequest.onBeforeSendHeaders(getDesktopAuthWebRequestFilter(trusted), (details, callback) => {
    callback({ requestHeaders: desktopAuthHeadersForRequest(details, trusted, token) });
  });
  const dispatched = [];
  const attempts = [];
  registerWindowOpenGuard({
    getURL: () => contents.getURL(),
    isDestroyed: () => contents.isDestroyed(),
    setWindowOpenHandler: (handler) => contents.setWindowOpenHandler((details) => {
      attempts.push(details);
      const response = handler(details);
      assert.deepEqual(response, { action: 'deny' });
      return response;
    })
  }, trusted, async (url) => { dispatched.push(url); });
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
  await frame.executeJavaScript(`window.open('https://popup.invalid/remote');
    window.open('https://popup.invalid/no-referrer', '_blank', 'noreferrer'); undefined;`, true);
  assert.equal(attempts.length, 2, 'real remote frame reached installed popup handler');
  assert.deepEqual(dispatched, []);
  await contents.executeJavaScript("window.open('https://popup.invalid/trusted'); window.open('mailto:fixture@popup.invalid'); undefined;", true);
  assert.equal(attempts.length, 4, 'trusted app reached the same installed handler');
  const trustedDispatches = ['https://popup.invalid/trusted', 'mailto:fixture@popup.invalid'];
  assert.deepEqual(dispatched, trustedDispatches);
  await win.loadURL(`${trusted}/same-origin/`);
  await contents.executeJavaScript("window.open('https://popup.invalid/same-origin-policy'); undefined;", true);
  assert.equal(attempts.length, 5, 'same-origin policy page reached the installed handler');
  assert.equal(attempts[4].referrer.url, '', 'same-origin policy strips the cross-origin referrer');
  assert.deepEqual(dispatched, trustedDispatches, 'stripped referrer fails closed');
  assert.equal(BrowserWindow.getAllWindows().length, 1, 'no popup window created');
  assert.ok(remoteTokens.length > 0, 'remote embed was requested');
  assert.deepEqual(remoteTokens.filter((value) => value !== undefined), [], 'no auth header reaches the remote embed');
  assert.ok(trustedTokens.length > 0, 'trusted app was requested');
  assert.deepEqual(trustedTokens.filter((value) => value !== token), [], 'every trusted request carries the auth header');
  console.log('PASS: remote iframe capabilities and popup dispatch denied; trusted HTTPS and mailto outbound links dispatch once under the starter referrer policy; same-origin referrer policy fails closed; embed and exact-origin auth headers preserved');
}).then(() => finish(0), (error) => { console.error(error); finish(1); });

function finish(code) {
  clearTimeout(deadline);
  if (win && !win.isDestroyed()) win.destroy();
  for (const server of servers) server.close();
  // Only this fixture's private temporary profile is removed.
  app.once('quit', () => fs.rmSync(fixtureData, { recursive: true, force: true }));
  app.exit(code);
}
