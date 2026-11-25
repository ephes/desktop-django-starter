const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const helpers = import('../../tauri/scripts/packaged-smoke.mjs');

function fixture() { return fs.mkdtempSync(path.join(os.tmpdir(), 'dds-smoke-')); }
function artifact(root, name, platform) {
  const target = path.join(root, name + (platform === 'darwin' ? '.app/Contents/MacOS/app' : '.AppImage'));
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, 'synthetic executable', { mode: 0o755 });
  return target;
}

for (const platform of ['darwin', 'linux']) {
  test(`only the changed ${platform} artifact is smoked; ambiguity and stale-only fail`, async () => {
    const { snapshotArtifacts, resolveSmokeBinary } = await helpers;
    const root = fixture();
    try {
      artifact(root, 'a-stale', platform);
      artifact(root, 'b-stale', platform);
      const before = snapshotArtifacts(root, platform);
      assert.throws(() => resolveSmokeBinary(root, before, platform), /current|changed/i);
      const current = artifact(root, 'z-current', platform);
      assert.equal(resolveSmokeBinary(root, before, platform).command, current);
      artifact(root, 'y-ambiguous', platform);
      assert.throws(() => resolveSmokeBinary(root, before, platform), /ambiguous/i);
      const prior = snapshotArtifacts(root, platform);
      fs.appendFileSync(current, 'rebuilt');
      assert.equal(resolveSmokeBinary(root, prior, platform).command, current);
      assert.ok(fs.existsSync(path.join(root, 'a-stale' + (platform === 'darwin' ? '.app' : '.AppImage'))));
    } finally { fs.rmSync(root, { recursive: true, force: true }); }
  });
}

test('smoke snapshots share a walk limit across discovery and bundle fingerprints', async t => {
  const { snapshotArtifacts, resolveSmokeBinary, buildOutputRoots } = await helpers;
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  artifact(root, 'a-stale', 'darwin');
  const current = artifact(root, 'nested/z-current', 'darwin');
  const wide = path.join(root, 'wide');
  fs.mkdirSync(wide);

  // Five discovery visits and eight fingerprint visits use the rest of the budget.
  const entryLimit = 100000;
  let extraEntries = entryLimit - 13;
  let reads = 0;
  let closes = 0;
  const open = fs.opendirSync;
  t.mock.method(fs, 'opendirSync', (name, options) => {
    if (name !== wide) return open(name, options);
    let remaining = extraEntries;
    return {
      readSync() {
        reads++;
        return remaining-- > 0 ? { name: 'ignored', isDirectory: () => false } : null;
      },
      closeSync() { closes++; },
    };
  });
  const stat = t.mock.method(fs, 'lstatSync');

  const before = snapshotArtifacts(root, 'darwin');
  assert.deepEqual([...before.keys()], [path.join(root, 'a-stale.app'), path.join(root, 'nested/z-current.app')]);
  assert.equal(reads, extraEntries + 1);
  assert.equal(stat.mock.callCount(), 8);
  assert.throws(() => resolveSmokeBinary(root, before, 'darwin'), /no current changed/i);
  fs.appendFileSync(current, 'rebuilt');
  assert.equal(resolveSmokeBinary(root, before, 'darwin').command, current);

  extraEntries++;
  stat.mock.resetCalls();
  assert.throws(() => snapshotArtifacts(root, 'darwin'), /entry limit.*100000/i);
  assert.ok(stat.mock.callCount() < 8);

  extraEntries = entryLimit + 1000;
  reads = 0;
  closes = 0;
  assert.throws(() => buildOutputRoots({ targetDirectory: wide }), /entry limit.*100000/i);
  assert.equal(reads, entryLimit + 1);
  assert.equal(closes, 1);
});

test('smoke rejects too many candidates across roots before fingerprinting', async t => {
  const { snapshotArtifacts } = await helpers;
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const roots = [path.join(root, 'b'), path.join(root, 'a')];
  for (const dir of roots) {
    for (let index = 0; index < 64; index++) artifact(dir, String(index), 'linux');
  }
  const stat = t.mock.method(fs, 'lstatSync');
  assert.equal(snapshotArtifacts(roots, 'linux').size, 128);
  assert.equal(stat.mock.callCount(), 128);
  artifact(roots[1], 'extra', 'linux');
  stat.mock.resetCalls();
  assert.throws(() => snapshotArtifacts(roots, 'linux'), /candidate limit.*128/i);
  assert.equal(stat.mock.callCount(), 0);
});

test('target directory and explicit target triple determine artifact root', async () => {
  const { buildOutputRoot } = await helpers;
  assert.equal(buildOutputRoot({ tauriRoot: '/repo/shells/tauri', targetDirectory: '/custom/target', target: 'aarch64-apple-darwin', profile: 'debug' }), '/custom/target/aarch64-apple-darwin/debug/bundle');
});

test('Cargo profiles are admitted before the artifact filesystem is inspected', async t => {
  const { buildOutputRoot, buildOutputRoots } = await helpers;
  const targetDirectory = path.join(os.tmpdir(), 'synthetic-cargo-target');
  const options = { targetDirectory };
  const exists = t.mock.method(fs, 'existsSync', () => false);
  const open = t.mock.method(fs, 'opendirSync');

  for (const profile of ['..', '../outside', 'nested/build', 'nested\\build', 'C:debug', '.', '', 'release\n']) {
    assert.throws(() => buildOutputRoot({ ...options, profile }), /Cargo profile name/i);
    assert.throws(() => buildOutputRoots({ ...options, profile }), /Cargo profile name/i);
  }
  assert.equal(exists.mock.callCount(), 0);
  assert.equal(open.mock.callCount(), 0);

  assert.deepEqual(buildOutputRoots(options), [path.join(targetDirectory, 'release', 'bundle')]);
  assert.deepEqual(buildOutputRoots({ ...options, profile: 'dev' }), [path.join(targetDirectory, 'debug', 'bundle')]);
  assert.deepEqual(buildOutputRoots({ ...options, profile: 'optimisé_2-lto' }), [
    path.join(targetDirectory, 'optimisé_2-lto', 'bundle'),
  ]);
});

test('packaged smoke has a deadline and bounded diagnostics', async () => {
  const { runPackagedSmoke } = await helpers;
  const started = Date.now();
  await assert.rejects(runPackagedSmoke(process.execPath, ['-e', "process.stdout.write('x'.repeat(100000));setTimeout(()=>{},5000)"], { timeoutMs: 100 }), /deadline|timed out/i);
  assert.ok(Date.now() - started < 3000);
});

test('smoke execution and process group cleanup have independent deadlines', { skip: process.platform === 'win32' }, async t => {
  const childProcess = require('node:child_process');
  const { EventEmitter } = require('node:events');
  const { PassThrough } = require('node:stream');
  const { syncBuiltinESMExports } = require('node:module');
  const { performance } = require('node:perf_hooks');
  const { runPackagedSmoke } = await helpers;
  let now = 0;
  t.mock.method(performance, 'now', () => now);
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const spawn = t.mock.method(childProcess, 'spawn', () => {
    const child = new EventEmitter();
    Object.assign(child, { pid: 12345, stdout: new PassThrough(), stderr: new PassThrough() });
    return child;
  });
  t.after(() => { spawn.mock.restore(); syncBuiltinESMExports(); });
  syncBuiltinESMExports();

  let groupAlive = true;
  let cleanupRefused = false;
  const kill = t.mock.method(process, 'kill', (pid, signal) => {
    assert.equal(pid, -12345);
    if (cleanupRefused) throw Object.assign(new Error('cleanup refused'), { code: 'EPERM' });
    if (signal === 0 && !groupAlive) throw Object.assign(new Error('group gone'), { code: 'ESRCH' });
  });
  const lastChild = () => spawn.mock.calls.at(-1).result;

  const timely = runPackagedSmoke('fixture', [], { timeoutMs: 100 });
  now += 99;
  t.mock.timers.tick(99);
  lastChild().emit('exit', 0, null);
  await Promise.resolve();
  assert.equal(kill.mock.callCount(), 2);
  groupAlive = false;
  now += 25;
  t.mock.timers.tick(25);
  await timely;

  const late = runPackagedSmoke('fixture', [], { timeoutMs: 100 });
  now += 100;
  t.mock.timers.tick(100);
  lastChild().emit('exit', 0, null);
  await assert.rejects(late, /deadline exceeded/);

  // Observe a late exit before the event loop dispatches the runtime timer.
  kill.mock.resetCalls();
  const delayedExit = runPackagedSmoke('fixture', [], { timeoutMs: 100 });
  const child = lastChild();
  now += 101;
  child.emit('exit', 0, null);
  await assert.rejects(delayedExit, /deadline exceeded/);
  assert.deepEqual(kill.mock.calls.map(call => call.arguments), [[-12345, 'SIGKILL'], [-12345, 0]]);
  assert.ok(child.stdout.destroyed && child.stderr.destroyed);

  cleanupRefused = true;
  const uncertain = runPackagedSmoke('fixture', [], { timeoutMs: 100 });
  lastChild().emit('exit', 0, null);
  await assert.rejects(uncertain, /cleanup refused/);
});

test('smoke retirement follows monotonic time through wall-clock jumps', { skip: process.platform === 'win32' }, async t => {
  const childProcess = require('node:child_process');
  const { EventEmitter } = require('node:events');
  const { PassThrough } = require('node:stream');
  const { syncBuiltinESMExports } = require('node:module');
  const { performance } = require('node:perf_hooks');
  const { runPackagedSmoke } = await helpers;
  const child = Object.assign(new EventEmitter(), {
    pid: 12345, stdout: new PassThrough(), stderr: new PassThrough()
  });
  const spawn = t.mock.method(childProcess, 'spawn', () => child);
  t.after(() => { spawn.mock.restore(); syncBuiltinESMExports(); });
  syncBuiltinESMExports();

  let elapsed = 0;
  let wall = 100000;
  t.mock.timers.enable({ apis: ['setTimeout'] });
  t.mock.method(performance, 'now', () => elapsed);
  t.mock.method(Date, 'now', () => wall);
  const kill = t.mock.method(process, 'kill', () => {});
  const smoke = runPackagedSmoke('fixture', [], { timeoutMs: 100 });
  const failed = assert.rejects(smoke, /retirement is uncertain/);
  child.emit('exit', 0, null);
  await Promise.resolve();
  assert.equal(kill.mock.callCount(), 2);

  wall += 86400000;
  elapsed = 25;
  t.mock.timers.tick(25);
  await Promise.resolve();
  assert.equal(kill.mock.callCount(), 3);

  wall -= 2 * 86400000;
  elapsed = 3000;
  t.mock.timers.tick(2975);
  await Promise.resolve();
  assert.equal(kill.mock.callCount(), 3);
  await failed;
});

test('successful smoke leader cannot leave its owned child running', { skip: process.platform === 'win32' }, async () => {
  const { runPackagedSmoke } = await helpers;
  const root = fixture();
  const pidFile = path.join(root, 'pid');
  let pid;
  try {
    const code = `const cp=require('node:child_process');const fs=require('node:fs');const c=cp.spawn(process.execPath,['-e','setTimeout(()=>{},10000)'],{stdio:'ignore'});fs.writeFileSync(${JSON.stringify(pidFile)},String(c.pid));c.unref();`;
    await runPackagedSmoke(process.execPath, ['-e', code], { timeoutMs: 1000 });
    pid = Number(fs.readFileSync(pidFile, 'utf8'));
    assert.throws(() => process.kill(pid, 0), { code: 'ESRCH' });
  } finally {
    if (!pid && fs.existsSync(pidFile)) pid = Number(fs.readFileSync(pidFile, 'utf8'));
    if (pid) { try { process.kill(pid, 'SIGKILL'); } catch {} }
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('Cargo configured target output is observed without admitting stale other targets', async () => {
  const { buildOutputRoots, snapshotArtifacts, resolveSmokeBinary } = await helpers;
  const root = fixture();
  try {
    const options = { targetDirectory: root, profile: 'release' };
    artifact(path.join(root, 'old-triple/release/bundle'), 'old', 'linux');
    const before = snapshotArtifacts(buildOutputRoots(options), 'linux');
    const current = artifact(path.join(root, 'configured-triple/release/bundle'), 'current', 'linux');
    assert.equal(resolveSmokeBinary(buildOutputRoots(options), before, 'linux').command, current);
    const explicit = { ...options, target: 'old-triple' };
    assert.throws(() => resolveSmokeBinary(buildOutputRoots(explicit), before, 'linux'), /current|changed/i);
    // A stray non-triple directory in a shared target dir is skipped, not fatal.
    fs.mkdirSync(path.join(root, 'shared cache+tmp'));
    assert.ok(buildOutputRoots(options).every(entry => !entry.includes('shared cache+tmp')));
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

test('smoke deadline configuration is finite and bounded', async () => {
  const { smokeTimeout } = await helpers;
  assert.equal(smokeTimeout({}), 120000);
  for (const value of ['0', '-1', 'Infinity', 'NaN', '600001', '1.5']) {
    assert.throws(() => smokeTimeout({ DESKTOP_DJANGO_PACKAGED_SMOKE_TIMEOUT_MS: value }), /1..600000/);
  }
});

test('launch errors and nonzero smoke outcomes fail with bounded output', async () => {
  const { runPackagedSmoke } = await helpers;
  await assert.rejects(runPackagedSmoke('/no/such/smoke', [], { timeoutMs: 500 }), /smoke failed/i);
  await assert.rejects(runPackagedSmoke(process.execPath, ['-e', "process.stderr.write('x'.repeat(100000));process.exit(7)"], { timeoutMs: 1000 }), error => {
    assert.match(error.message, /exit 7/);
    assert.ok(error.message.length < 8500);
    return true;
  });
});

function stubBuild(root, current, program, { cargoBody, stageBody = 'process.exit(0);' } = {}) {
  const tauri = path.join(root, 'shells/tauri');
  const scripts = path.join(tauri, 'scripts');
  const tools = path.join(root, 'tools');
  fs.mkdirSync(scripts, { recursive: true });
  fs.mkdirSync(path.join(tauri, 'node_modules/.bin'), { recursive: true });
  fs.mkdirSync(tools);
  for (const file of ['build-tauri.mjs', 'packaged-smoke.mjs']) {
    fs.copyFileSync(path.join(__dirname, '../../tauri/scripts', file), path.join(scripts, file));
  }
  const executable = (name, body) => fs.writeFileSync(name, '#!' + process.execPath + '\n' + body + '\n', { mode: 0o755 });
  const metadata = JSON.stringify({ target_directory: path.join(root, 'custom-target') });
  executable(path.join(tools, 'cargo'), cargoBody ?? 'console.log(' + JSON.stringify(metadata) + ');');
  executable(path.join(tools, 'npm'), stageBody);
  const bundler = `require('node:fs').writeFileSync(${JSON.stringify(current)}, ${JSON.stringify(program)}, { mode: 0o755 });`;
  executable(path.join(tauri, 'node_modules/.bin/tauri'), bundler);
  return {
    entry: path.join(scripts, 'build-tauri.mjs'),
    env: { ...process.env, PATH: tools + path.delimiter + process.env.PATH },
  };
}

for (const [name, cargoBody, diagnostic] of [
  ['stalled', "process.on('SIGTERM', () => {}); setTimeout(() => console.log('{}'), 1500);",
    /Cargo metadata timed out after 200 ms.*check for a stuck Cargo process/i],
  ['failed', "console.error('synthetic Cargo manifest error'); process.exit(7);", /synthetic Cargo manifest error/],
]) {
  test(`build wrapper stops before staging when Cargo metadata is ${name}`, { skip: process.platform === 'win32' }, t => {
    const { spawnSync } = require('node:child_process');
    const root = fixture();
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const staged = path.join(root, 'staged');
    const { entry, env } = stubBuild(root, path.join(root, 'built'), '', {
      cargoBody,
      stageBody: `require('node:fs').writeFileSync(${JSON.stringify(staged)}, 'staged');`,
    });
    const result = spawnSync(process.execPath, [entry], {
      env: { ...env, DESKTOP_DJANGO_CARGO_METADATA_TIMEOUT_MS: name === 'stalled' ? '200' : '10000' },
      encoding: 'utf8', timeout: 5000,
    });
    assert.ifError(result.error);
    assert.equal(result.status, 1, result.stderr);
    assert.match(result.stderr, diagnostic);
    assert.equal(fs.existsSync(staged), false);
  });
}

test('build wrapper rejects invalid Cargo target-directory metadata before staging', { skip: process.platform === 'win32' }, t => {
  const { spawnSync } = require('node:child_process');
  const fixtures = [
    ['missing field', '{}'], ['relative path', '{"target_directory":"relative/target"}'],
    ['empty path', '{"target_directory":""}'], ['numeric path', '{"target_directory":1}'],
    ['null metadata', 'null'], ['array metadata', '[]'], ['invalid JSON', '{'],
  ];
  for (const [name, stdout] of fixtures) {
    const root = fixture();
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const staged = path.join(root, 'staged');
    const { entry, env } = stubBuild(root, path.join(root, 'built'), '', {
      cargoBody: `console.log(${JSON.stringify(stdout)});`,
      stageBody: `require('node:fs').writeFileSync(${JSON.stringify(staged)}, 'staged');`,
    });
    const result = spawnSync(process.execPath, [entry], { env, encoding: 'utf8', timeout: 5000 });
    assert.ifError(result.error);
    assert.equal(fs.existsSync(staged), false, name);
    assert.equal(result.status, 1, name);
    assert.match(result.stderr, /Cargo metadata.*target_directory.*absolute path/i, name);
  }
});

test('an explicit Cargo target directory takes precedence over unusable metadata', { skip: process.platform === 'win32' }, t => {
  const { spawnSync } = require('node:child_process');
  const root = fixture();
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const target = path.join(root, 'explicit-target');
  const output = path.join(target, 'release/bundle', process.platform === 'darwin' ? 'macos' : 'appimage');
  const current = artifact(output, 'override', process.platform);
  const { entry, env } = stubBuild(root, current, 'synthetic rebuild', {
    cargoBody: 'console.log("{}");',
  });
  const result = spawnSync(process.execPath, [entry, '--', '--target-dir', target], {
    env, encoding: 'utf8', timeout: 5000,
  });
  assert.ifError(result.error);
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /Built Tauri artifacts:[\s\S]*explicit-target[\s\S]*override/);
});

for (const buildArgs of [
  [],
  ['--debug', '--target', 'synthetic-triple'],
  ['-d', '-tsynthetic-triple'],
  ['--target=synthetic-triple', '--', '--profile', 'dev', '--target-dir', '../../../custom-target']
]) {
  test('build wrapper reports only changed artifacts: ' + (buildArgs.join(' ') || 'ordinary release'), { skip: process.platform === 'win32' }, t => {
    const { spawnSync } = require('node:child_process');
    const root = fixture();
    t.after(() => fs.rmSync(root, { recursive: true, force: true }));
    const smoke = buildArgs.length > 0;
    const profileDir = smoke ? 'custom-target/synthetic-triple/debug/bundle' : 'custom-target/release/bundle';
    const output = path.join(root, profileDir, process.platform === 'darwin' ? 'macos' : 'appimage');
    const marker = path.join(root, 'ran-current');
    const stale = artifact(output, 'a-stale', process.platform);
    const staleBundle = process.platform === 'darwin' ? path.join(stale, '../../..') : stale;
    const recent = new Date(Date.now() + 10000);
    fs.utimesSync(staleBundle, recent, recent);
    // Changing a binary inside an existing macOS bundle must also count.
    const current = artifact(output, 'z-current', process.platform);
    const program = "#!/bin/sh\nprintf current > '" + marker + "'\n";
    const { entry, env } = stubBuild(root, current, program);
    const args = smoke ? ['--smoke-test', ...buildArgs] : buildArgs;
    const result = spawnSync(process.execPath, [entry, ...args], { env, encoding: 'utf8', timeout: 10000 });
    assert.equal(result.status, 0, result.stderr);
    assert.match(result.stdout, /Built Tauri artifacts:[\s\S]*z-current/);
    assert.doesNotMatch(result.stdout, /a-stale/);
    if (smoke) assert.equal(fs.readFileSync(marker, 'utf8'), 'current');
    else assert.equal(fs.existsSync(marker), false);
  });
}

for (const signal of ['SIGINT', 'SIGTERM']) {
  test('build wrapper retires the packaged smoke on ' + signal, { skip: process.platform === 'win32' }, async t => {
    const { spawn } = require('node:child_process');
    const { once } = require('node:events');
    const { setTimeout: sleep } = require('node:timers/promises');
    const root = fixture();
    const marker = path.join(root, 'smoke-pid');
    const current = artifact(path.join(root, 'custom-target/release/bundle'), 'current', process.platform);
    const program = [
      '#!' + process.execPath,
      'const fs = require("node:fs");',
      'const marker = ' + JSON.stringify(marker) + ';',
      'fs.writeFileSync(marker + ".tmp", String(process.pid));',
      'fs.renameSync(marker + ".tmp", marker);',
      'setTimeout(() => {}, 15000);',
    ].join('\n');
    const { entry, env } = stubBuild(root, current, program);
    const wrapper = spawn(process.execPath, [entry, '--smoke-test'], {
      env: { ...env, DESKTOP_DJANGO_PACKAGED_SMOKE_TIMEOUT_MS: '10000' },
      stdio: ['ignore', 'ignore', 'pipe'], timeout: 12000, killSignal: 'SIGKILL',
    });
    const closed = once(wrapper, 'close');
    t.after(() => {
      if (wrapper.exitCode === null && wrapper.signalCode === null) wrapper.kill('SIGKILL');
      if (fs.existsSync(marker)) {
        try { process.kill(Number(fs.readFileSync(marker, 'utf8')), 'SIGKILL'); } catch {}
      }
      fs.rmSync(root, { recursive: true, force: true });
    });
    let stderr = '';
    wrapper.stderr.setEncoding('utf8').on('data', chunk => { stderr += chunk; });
    const startupDeadline = performance.now() + 5000;
    while (!fs.existsSync(marker) && wrapper.exitCode === null && wrapper.signalCode === null
      && performance.now() < startupDeadline) {
      await sleep(10);
    }
    assert.ok(fs.existsSync(marker), stderr);
    const pid = Number(fs.readFileSync(marker, 'utf8'));
    assert.ok(wrapper.kill(signal));
    const [code, exitSignal] = await closed;
    assert.throws(() => process.kill(-pid, 0), { code: 'ESRCH' });
    assert.equal(exitSignal, null);
    assert.equal(code, 128 + os.constants.signals[signal], stderr);
    assert.match(stderr, new RegExp('interrupted by ' + signal));
  });
}
