import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';

export function buildOutputRoot({ tauriRoot, targetDirectory, target, profile = 'release' }) {
  if (target && (!/^[A-Za-z0-9_.-]+$/.test(target) || target === '.' || target === '..')) {
    throw new Error('Unsupported smoke target; pass a target triple');
  }
  return path.join(targetDirectory || path.join(tauriRoot, 'src-tauri', 'target'), ...(target ? [target] : []), profile, 'bundle');
}

// Cargo metadata resolves target-dir from environment/config. With no explicit
// target, observe host and triple subdirectories: Cargo may select build.target
// from configuration. Only one artifact changed by this exclusive build is eligible.
export function buildOutputRoots(options) {
  if (options.target) return [buildOutputRoot(options)];
  const directory = options.targetDirectory || path.join(options.tauriRoot, 'src-tauri', 'target');
  // Unrelated directories (for example in a shared target dir) are not triples; skip them.
  const names = fs.existsSync(directory) ? fs.readdirSync(directory, { withFileTypes: true })
    .filter(entry => entry.isDirectory() && /^[A-Za-z0-9_.-]+$/.test(entry.name)).map(entry => entry.name) : [];
  return [buildOutputRoot(options), ...names.map(target => buildOutputRoot({ ...options, target }))];
}

function candidates(root, platform) {
  if (Array.isArray(root)) return root.flatMap(entry => candidates(entry, platform));
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap(entry => {
    const name = path.join(root, entry.name);
    if ((platform === 'darwin' && entry.isDirectory() && name.endsWith('.app'))
        || (platform === 'linux' && entry.isFile() && name.endsWith('.AppImage'))) return [name];
    return entry.isDirectory() ? candidates(name, platform) : [];
  }).sort();
}

function fingerprint(name) {
  const info = fs.lstatSync(name, { bigint: true });
  if (info.isSymbolicLink()) throw new Error('Symlink in smoke artifact');
  return [info.ino, info.size, info.mtimeNs, info.ctimeNs].join(':')
    + (info.isDirectory() ? fs.readdirSync(name).sort().map(entry => entry + ':' + fingerprint(path.join(name, entry))).join('|') : '');
}

export function snapshotArtifacts(root, platform = process.platform) {
  return new Map(candidates(root, platform).map(name => [name, fingerprint(name)]));
}

export function resolveSmokeBinary(root, before, platform = process.platform) {
  if (platform === 'win32') throw new Error('Windows installers require manual installed-app smoke validation');
  const found = [...snapshotArtifacts(root, platform)]
    .filter(([name, state]) => before.get(name) !== state).map(([name]) => name);
  if (!found.length) throw new Error(`No current changed runnable artifact under ${root}; check --target and Cargo configuration`);
  if (found.length !== 1) throw new Error(`Ambiguous current smoke artifacts under ${root}`);
  if (platform === 'linux') return { command: found[0], args: [] };
  const bin = path.join(found[0], 'Contents/MacOS');
  const executables = fs.readdirSync(bin).map(entry => path.join(bin, entry)).filter(name => {
    const info = fs.lstatSync(name);
    if (!info.isFile() || info.isSymbolicLink()) return false;
    try { fs.accessSync(name, fs.constants.X_OK); return true; } catch { return false; }
  });
  if (executables.length !== 1) throw new Error('Ambiguous or missing app bundle executable');
  return { command: executables[0], args: [] };
}

export function smokeTimeout(env = process.env) {
  const value = Number(env.DESKTOP_DJANGO_PACKAGED_SMOKE_TIMEOUT_MS ?? 120000);
  if (!Number.isSafeInteger(value) || value < 1 || value > 600000) {
    throw new Error('DESKTOP_DJANGO_PACKAGED_SMOKE_TIMEOUT_MS must be 1..600000');
  }
  return value;
}

const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
async function retireGroup(pid) {
  try { process.kill(-pid, 'SIGKILL'); }
  catch (error) { if (error.code === 'ESRCH') return; throw error; }
  const until = Date.now() + 3000;
  while (Date.now() < until) {
    try { process.kill(-pid, 0); }
    catch (error) { if (error.code === 'ESRCH') return; throw error; }
    await delay(25);
  }
  throw new Error('Owned smoke process group retirement is uncertain');
}

export async function runPackagedSmoke(command, args, { timeoutMs = smokeTimeout(), ...options } = {}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 600000) throw new Error('Invalid smoke deadline');
  const windows = process.platform === 'win32';
  const child = spawn(command, args, { ...options, detached: !windows, stdio: ['ignore', 'pipe', 'pipe'] });
  let diagnostics = Buffer.alloc(0);
  const collect = chunk => {
    diagnostics = Buffer.concat([diagnostics, chunk.subarray(-8192)]).subarray(-8192);
  };
  child.stdout.on('data', collect);
  child.stderr.on('data', collect);
  let timedOut = false;
  let cleanupError;
  let cleanup;
  const retire = () => {
    if (cleanup) return cleanup;
    cleanup = (async () => {
      if (!child.pid) return;
      if (windows) {
        const result = spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { timeout: 3000, maxBuffer: 8192, windowsHide: true });
        if (result.error || result.status !== 0) throw new Error('Owned smoke Windows tree retirement is uncertain');
      } else await retireGroup(child.pid);
    })().catch(error => { cleanupError = error; });
    return cleanup;
  };
  // Start cleanup on exit, not close: inherited pipes must not prolong ownership.
  const outcome = new Promise(resolve => {
    child.once('error', error => resolve({ error }));
    child.once('exit', (status, signal) => { void retire(); resolve({ status, signal }); });
  });
  let timer;
  const deadline = new Promise(resolve => {
    timer = setTimeout(() => { timedOut = true; void retire(); resolve({}); }, timeoutMs);
  });
  let result;
  try {
    result = await Promise.race([outcome, deadline]);
    await retire();
  } finally {
    clearTimeout(timer);
    child.stdout.destroy();
    child.stderr.destroy();
  }
  if (timedOut || cleanupError || result.error || result.status !== 0) {
    const reason = [timedOut ? 'deadline exceeded' : result.error?.message
      || (result.status !== 0 ? `exit ${result.status} (${result.signal || 'no signal'})` : ''),
      cleanupError?.message].filter(Boolean).join('; ');
    throw new Error(`Packaged smoke failed: ${reason}\n${diagnostics.toString('utf8')}`);
  }
  if (diagnostics.length) process.stdout.write(diagnostics);
}
