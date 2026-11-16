const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { pruneBundledPythonRuntime } = require('../../../scripts/prune-bundled-python-runtime.cjs');

for (const parent of ['.', 'bin', 'lib', 'lib/python3.14', 'lib/python3.14/lib-dynload']) {
  test(`pruning preflights symlinked parent ${parent} before any removal`, () => {
    const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'dds-prune-'));
    const root = path.join(temp, 'python');
    const external = path.join(temp, 'external');
    try {
      for (const base of [root, external]) {
        fs.mkdirSync(path.join(base, 'bin'), { recursive: true });
        fs.mkdirSync(path.join(base, 'lib/python3.14/lib-dynload'), { recursive: true });
        for (const name of ['bin/idle3', 'lib/tcl8.6', 'lib/python3.14/idlelib', 'lib/python3.14/lib-dynload/_tkinter.so']) {
          fs.writeFileSync(path.join(base, name), 'canary');
        }
      }
      const target = path.join(root, parent);
      fs.rmSync(target, { recursive: true });
      fs.symlinkSync(path.join(external, parent), target, 'junction');
      assert.throws(() => pruneBundledPythonRuntime(root), /Unsafe runtime directory/);
      assert.equal(fs.readFileSync(path.join(external, 'bin/idle3'), 'utf8'), 'canary');
      assert.equal(fs.readFileSync(path.join(external, 'lib/tcl8.6'), 'utf8'), 'canary');
      if (parent !== '.' && parent !== 'bin') assert.equal(fs.readFileSync(path.join(root, 'bin/idle3'), 'utf8'), 'canary');
    } finally { fs.rmSync(temp, { recursive: true, force: true }); }
  });
}

test('ordinary runtime prunes only Tk and IDLE and retains internal interpreter links', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'dds-prune-'));
  try {
    fs.mkdirSync(path.join(root, 'lib/python3.14/lib-dynload'), { recursive: true });
    fs.mkdirSync(path.join(root, 'bin'));
    for (const name of ['bin/idle3', 'lib/tcl8.6', 'lib/python3.14/tkinter', 'lib/python3.14/lib-dynload/_tkinter.so', 'bin/python3.14']) fs.writeFileSync(path.join(root, name), 'x');
    fs.symlinkSync('python3.14', path.join(root, 'bin/python3'));
    assert.deepEqual(pruneBundledPythonRuntime(root), ['bin/idle3', 'lib/python3.14/lib-dynload/_tkinter.so', 'lib/python3.14/tkinter', 'lib/tcl8.6']);
    assert.equal(fs.readFileSync(path.join(root, 'bin/python3'), 'utf8'), 'x');
  } finally { fs.rmSync(root, { recursive: true, force: true }); }
});
