const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { spawnSync } = require('node:child_process');
const test = require('node:test');
const assert = require('node:assert/strict');

const scriptRoot = path.resolve(__dirname, '../../scripts');

function fixture(fn) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dds-stage-'));
  try {
    fs.mkdirSync(path.join(root, 'scripts'));
    for (const name of fs.readdirSync(scriptRoot).filter(n => n.endsWith('.cjs'))) {
      fs.copyFileSync(path.join(scriptRoot, name), path.join(root, 'scripts', name));
    }
    fs.copyFileSync(path.join(scriptRoot, 'desktop_process_guard.py'), path.join(root, 'scripts/desktop_process_guard.py'));
    fs.mkdirSync(path.join(root, 'src'));
    fs.writeFileSync(path.join(root, 'src/new.txt'), 'new-source');
    fs.writeFileSync(path.join(root, 'manage.py'), 'new-manage');
    fs.mkdirSync(path.join(root, '.stage/backend'), { recursive: true });
    fs.writeFileSync(path.join(root, '.stage/backend/last-success'), 'old-backend');
    fs.mkdirSync(path.join(root, '.stage/runtime-data'));
    fs.writeFileSync(path.join(root, '.stage/runtime-data/sentinel'), 'runtime-data');
    fs.writeFileSync(path.join(root, '.stage/unrelated'), 'unrelated');
    fs.writeFileSync(path.join(root, 'runner.cjs'), `
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const fail = process.argv[2];
const realRename = fs.renameSync;
let failedRename = false;
fs.renameSync = (source, dest) => {
  if (fail === 'publish' && dest === path.join(root, '.stage/backend') && !failedRename) {
    failedRename = true;
    fs.appendFileSync(path.join(root, 'trace'), 'publish\\n');
    throw new Error('injected publication failure');
  }
  return realRename(source, dest);
};
require('node:child_process').spawnSync = (command, args, options = {}) => {
  const operation = args[0] === 'manage.py' ? args[1] : args.slice(0, 2).join(' ');
  fs.appendFileSync(path.join(root, 'trace'), operation + '\\n');
  if ((fail === 'download' && operation === 'python install') ||
      (fail === 'install' && operation === 'pip install') ||
      (fail === 'runtime-info' && args[0] === '-c') ||
      (fail === 'collectstatic' && operation === 'collectstatic')) {
    return { status: 7, stderr: 'injected failure' };
  }
  if (operation === 'python install') {
    const installRoot = path.join(args[args.indexOf('--install-dir') + 1], 'runtime');
    fs.mkdirSync(path.join(installRoot, 'bin'), { recursive: true });
    fs.writeFileSync(path.join(installRoot, 'bin/python3'), 'synthetic-interpreter', { mode: 0o755 });
    fs.writeFileSync(path.join(installRoot, 'python.exe'), 'synthetic-interpreter');
    if (fail === 'runtime-cycle') fs.symlinkSync('.', path.join(installRoot, 'cycle'), 'junction');
  } else if (args[0] === '-c') {
    const pythonRoot = process.platform === 'win32' ? path.dirname(command) : path.dirname(path.dirname(command));
    return { status: 0, stdout: JSON.stringify({ version: '3.14.0', root: pythonRoot, executable: command, purelib: path.join(pythonRoot, "lib/site-packages"), scripts: path.join(pythonRoot, "bin") }) };
  } else if (args[0] === 'build') {
    fs.writeFileSync(path.join(args[args.indexOf('--out-dir') + 1], 'synthetic.whl'), 'wheel');
  } else if (operation === 'collectstatic') {
    fs.mkdirSync(path.join(options.env.DESKTOP_DJANGO_BUNDLE_DIR, 'staticfiles'));
    fs.writeFileSync(path.join(options.env.DESKTOP_DJANGO_BUNDLE_DIR, 'staticfiles/new.txt'), 'static');
    fs.writeFileSync(path.join(options.env.DESKTOP_DJANGO_APP_DATA_DIR, 'build-only'), 'synthetic');
  }
  return { status: 0, stdout: '' };
};
require('./scripts/stage-backend.cjs');
`);
    fn(root);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
}

function run(root, fail) {
  return spawnSync(process.execPath, [path.join(root, 'runner.cjs'), fail], { encoding: 'utf8', timeout: 10000 });
}

function preserved(root) {
  assert.equal(fs.readFileSync(path.join(root, '.stage/backend/last-success'), 'utf8'), 'old-backend');
  assert.equal(fs.readFileSync(path.join(root, '.stage/runtime-data/sentinel'), 'utf8'), 'runtime-data');
  assert.equal(fs.readFileSync(path.join(root, '.stage/unrelated'), 'utf8'), 'unrelated');
  assert.deepEqual(fs.readdirSync(path.join(root, '.stage')).sort(), ['backend', 'runtime-data', 'unrelated']);
}

for (const failure of ['missing-input', 'download', 'runtime-cycle', 'runtime-info', 'install', 'collectstatic', 'publish']) {
  test(`staging preserves last success and runtime data on ${failure}`, () => fixture(root => {
    if (failure === 'missing-input') fs.unlinkSync(path.join(root, 'manage.py'));
    const result = run(root, failure);
    assert.notEqual(result.status, 0);
    if (failure !== 'missing-input') {
      const operation = { 'runtime-cycle': 'python install', download: 'python install', 'runtime-info': '-c ', install: 'pip install', collectstatic: 'collectstatic', publish: 'publish' }[failure];
      assert.match(fs.readFileSync(path.join(root, 'trace'), 'utf8'), new RegExp(operation));
    }
    if (failure === 'runtime-cycle') {
      assert.match(result.stderr, /symlink cycle/);
      assert.doesNotMatch(fs.readFileSync(path.join(root, 'trace'), 'utf8'), /-c /);
    }
    preserved(root);
  }));
}

test('staging publishes a complete backend and preserves runtime data', () => fixture(root => {
  const result = run(root, 'success');
  assert.equal(result.status, 0, result.stderr);
  assert.equal(fs.existsSync(path.join(root, '.stage/backend/last-success')), false);
  assert.equal(fs.readFileSync(path.join(root, '.stage/backend/manage.py'), 'utf8'), 'new-manage');
  assert.equal(fs.readFileSync(path.join(root, '.stage/backend/staticfiles/new.txt'), 'utf8'), 'static');
  assert.ok(fs.existsSync(path.join(root, '.stage/backend/runtime-manifest.json')));
  assert.equal(fs.readFileSync(path.join(root, '.stage/runtime-data/sentinel'), 'utf8'), 'runtime-data');
  assert.equal(fs.existsSync(path.join(root, '.stage/runtime-data/build-only')), false);
  assert.deepEqual(fs.readdirSync(path.join(root, '.stage')).sort(), ['backend', 'runtime-data', 'unrelated']);
}));
