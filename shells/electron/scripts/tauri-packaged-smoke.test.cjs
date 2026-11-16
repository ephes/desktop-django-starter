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

test('target directory and explicit target triple determine artifact root', async () => {
  const { buildOutputRoot } = await helpers;
  assert.equal(buildOutputRoot({ tauriRoot: '/repo/shells/tauri', targetDirectory: '/custom/target', target: 'aarch64-apple-darwin', profile: 'debug' }), '/custom/target/aarch64-apple-darwin/debug/bundle');
});

test('packaged smoke has a deadline and bounded diagnostics', async () => {
  const { runPackagedSmoke } = await helpers;
  const started = Date.now();
  await assert.rejects(runPackagedSmoke(process.execPath, ['-e', "process.stdout.write('x'.repeat(100000));setTimeout(()=>{},5000)"], { timeoutMs: 100 }), /deadline|timed out/i);
  assert.ok(Date.now() - started < 3000);
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

for (const buildArgs of [
  ['--debug', '--target', 'synthetic-triple'],
  ['-d', '-tsynthetic-triple'],
  ['--target=synthetic-triple', '--', '--profile', 'dev', '--target-dir', '../../../custom-target']
]) {
 test(`build wrapper runs the newly built artifact from the explicit custom target: ${buildArgs.join(' ')}`, { skip: process.platform === 'win32' }, async () => {
  const { spawnSync } = require('node:child_process');
  const root = fixture();
  try {
    const tauri = path.join(root, 'shells/tauri');
    const scripts = path.join(tauri, 'scripts');
    const tools = path.join(root, 'tools');
    const output = path.join(root, 'custom-target/synthetic-triple/debug/bundle');
    const marker = path.join(root, 'ran-current');
    fs.mkdirSync(scripts, { recursive: true });
    fs.mkdirSync(path.join(tauri, 'node_modules/.bin'), { recursive: true });
    fs.mkdirSync(tools);
    for (const file of ['build-tauri.mjs', 'packaged-smoke.mjs']) {
      fs.copyFileSync(path.join(__dirname, '../../tauri/scripts', file), path.join(scripts, file));
    }
    const executable = (name, body) => fs.writeFileSync(name, `#!${process.execPath}\n${body}\n`, { mode: 0o755 });
    executable(path.join(tools, 'cargo'), `console.log(JSON.stringify({target_directory:${JSON.stringify(path.join(root, 'custom-target'))}}));`);
    executable(path.join(tools, 'npm'), 'process.exit(0);');
    artifact(output, 'a-stale', process.platform);
    const current = artifact(output, 'z-current', process.platform);
    // Snapshot an existing current artifact too: changing a nested binary must count.
    const program = `#!/bin/sh\nprintf current > '${marker}'\n`;
    executable(path.join(tauri, 'node_modules/.bin/tauri'), `require('node:fs').writeFileSync(${JSON.stringify(current)}, ${JSON.stringify(program)}, {mode:0o755});`);
    const result = spawnSync(process.execPath, [path.join(scripts, 'build-tauri.mjs'), '--smoke-test', ...buildArgs], {
      env: { ...process.env, PATH: tools + path.delimiter + process.env.PATH },
      encoding: 'utf8', timeout: 10000
    });
    assert.equal(result.status, 0, result.stderr);
    assert.equal(fs.readFileSync(marker, 'utf8'), 'current');
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});

}
