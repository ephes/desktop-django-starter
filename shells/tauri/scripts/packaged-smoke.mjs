import { spawn, spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { performance } from 'node:perf_hooks';

const ENTRY_LIMIT = 100000;
const CANDIDATE_LIMIT = 128;

function scanBudget() {
  let remaining = ENTRY_LIMIT;
  return () => {
    if (remaining === 0) {
      throw new Error(`Tauri bundle scan entry limit (${ENTRY_LIMIT}) exceeded; use a dedicated Cargo target directory`);
    }
    remaining--;
  };
}

function* directoryEntries(directory, visit) {
  const handle = fs.opendirSync(directory);
  try {
    for (let entry = handle.readSync(); entry; entry = handle.readSync()) {
      visit();
      yield entry;
    }
  } finally {
    handle.closeSync();
  }
}

export function buildOutputRoot({ tauriRoot, targetDirectory, target, profile = 'release' }) {
  if (target && (!/^[A-Za-z0-9_.-]+$/.test(target) || target === '.' || target === '..')) {
    throw new Error('Unsupported smoke target; pass a target triple');
  }
  if (typeof profile !== 'string' || !/^[\p{Alphabetic}\p{Number}_-]+$/u.test(profile)) {
    throw new Error('Expected a single Cargo profile name');
  }
  const profileDirectory = profile === 'dev' ? 'debug' : profile;
  return path.join(targetDirectory || path.join(tauriRoot, 'src-tauri', 'target'), ...(target ? [target] : []), profileDirectory, 'bundle');
}

// Cargo metadata resolves target-dir from environment/config. With no explicit
// target, observe host and triple subdirectories: Cargo may select build.target
// from configuration. Only one artifact changed by this exclusive build is eligible.
export function buildOutputRoots(options) {
  if (options.target) return [buildOutputRoot(options)];
  const directory = options.targetDirectory || path.join(options.tauriRoot, 'src-tauri', 'target');
  // Unrelated directories (for example in a shared target dir) are not triples; skip them.
  const roots = [buildOutputRoot(options)];
  if (fs.existsSync(directory)) {
    for (const entry of directoryEntries(directory, scanBudget())) {
      if (entry.isDirectory() && /^[A-Za-z0-9_.-]+$/.test(entry.name)) {
        roots.push(buildOutputRoot({ ...options, target: entry.name }));
      }
    }
  }
  return roots.sort();
}

export function findBundleArtifacts(roots, matches, visit = scanBudget()) {
  const found = [];
  for (const root of roots) {
    visit();
    if (!fs.existsSync(root)) continue;
    const pending = [root];
    while (pending.length) {
      const directory = pending.pop();
      for (const entry of directoryEntries(directory, visit)) {
        const name = path.join(directory, entry.name);
        if (matches(name, entry, root)) {
          if (found.length === CANDIDATE_LIMIT) {
            throw new Error(`Tauri bundle scan candidate limit (${CANDIDATE_LIMIT}) exceeded; use a dedicated Cargo target directory`);
          }
          found.push(name);
        } else if (entry.isDirectory()) {
          pending.push(name);
        }
      }
    }
  }
  return found.sort();
}

function fingerprint(name, visit) {
  const hash = createHash('sha256');
  const pending = [name];
  visit();
  while (pending.length) {
    const current = pending.pop();
    const info = fs.lstatSync(current, { bigint: true });
    if (info.isSymbolicLink()) throw new Error('Symlink in Tauri bundle artifact');
    const directory = info.isDirectory();
    const metadata = [info.ino, info.size, info.mtimeNs, info.ctimeNs].map(String);
    hash.update(JSON.stringify([current.slice(name.length), directory, ...metadata]) + '\n');
    if (directory) {
      const names = Array.from(directoryEntries(current, visit), entry => entry.name).sort();
      for (let index = names.length - 1; index >= 0; index--) {
        pending.push(path.join(current, names[index]));
      }
    }
  }
  return hash.digest('hex');
}

export function snapshotBundleArtifacts(root, matches) {
  const visit = scanBudget();
  const found = findBundleArtifacts(Array.isArray(root) ? root : [root], matches, visit);
  return new Map(found.map(name => [name, fingerprint(name, visit)]));
}

export function snapshotArtifacts(root, platform = process.platform) {
  return snapshotBundleArtifacts(root, (name, entry) => (
    (platform === 'darwin' && entry.isDirectory() && name.endsWith('.app'))
    || (platform === 'linux' && entry.isFile() && name.endsWith('.AppImage'))
  ));
}

export function changedArtifacts(before, after) {
  return [...after].filter(([name, state]) => before.get(name) !== state).map(([name]) => name);
}

export function resolveSmokeBinary(root, before, platform = process.platform) {
  if (platform === 'win32') throw new Error('Windows installers require manual installed-app smoke validation');
  const found = changedArtifacts(before, snapshotArtifacts(root, platform));
  if (!found.length) throw new Error(`No current changed runnable artifact under ${root}; check --target and Cargo configuration`);
  if (found.length !== 1) throw new Error(`Ambiguous current smoke artifacts under ${root}`);
  if (platform === 'linux') return { command: found[0], args: [] };
  const bin = path.join(found[0], 'Contents/MacOS');
  let executable;
  for (const entry of directoryEntries(bin, scanBudget())) {
    const name = path.join(bin, entry.name);
    if (!fs.lstatSync(name).isFile()) continue;
    try { fs.accessSync(name, fs.constants.X_OK); } catch { continue; }
    if (executable) throw new Error('Ambiguous or missing app bundle executable');
    executable = name;
  }
  if (!executable) throw new Error('Ambiguous or missing app bundle executable');
  return { command: executable, args: [] };
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
  const until = performance.now() + 3000;
  while (performance.now() < until) {
    try { process.kill(-pid, 0); }
    catch (error) { if (error.code === 'ESRCH') return; throw error; }
    await delay(25);
  }
  throw new Error('Owned smoke process group retirement is uncertain');
}

export async function runPackagedSmoke(command, args, { timeoutMs = smokeTimeout(), signal, ...options } = {}) {
  if (!Number.isSafeInteger(timeoutMs) || timeoutMs < 1 || timeoutMs > 600000) throw new Error('Invalid smoke deadline');
  if (signal?.aborted) throw new Error(`Packaged smoke interrupted by ${signal.reason}`);
  const windows = process.platform === 'win32';
  const deadline = performance.now() + timeoutMs;
  const child = spawn(command, args, { ...options, detached: !windows, stdio: ['ignore', 'pipe', 'pipe'] });
  let diagnostics = Buffer.alloc(0);
  const collect = chunk => {
    diagnostics = Buffer.concat([diagnostics, chunk.subarray(-8192)]).subarray(-8192);
  };
  child.stdout.on('data', collect);
  child.stderr.on('data', collect);
  // Settle execution on the first terminal event, before starting cleanup.
  // Do not wait for close: descendants can keep inherited pipes open.
  const result = await new Promise(resolve => {
    let settled = false;
    const finish = result => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', interrupt);
      resolve(result);
    };
    const interrupt = () => finish({});
    const remainingMs = Math.max(1, Math.ceil(deadline - performance.now()));
    const timer = setTimeout(() => finish({ timedOut: true }), remainingMs);
    child.once('error', error => finish({ error }));
    child.once('exit', (status, exitSignal) => {
      finish(performance.now() >= deadline ? { timedOut: true } : { status, signal: exitSignal });
    });
    signal?.addEventListener('abort', interrupt);
    if (signal?.aborted) interrupt();
  });
  let cleanupError;
  try {
    if (child.pid) {
      if (windows) {
        const result = spawnSync('taskkill', ['/pid', String(child.pid), '/t', '/f'], { timeout: 3000, maxBuffer: 8192, windowsHide: true });
        if (result.error || result.status !== 0) throw new Error('Owned smoke Windows tree retirement is uncertain');
      } else await retireGroup(child.pid);
    }
  } catch (error) {
    cleanupError = error;
  } finally {
    child.stdout.destroy();
    child.stderr.destroy();
  }
  if (signal?.aborted || result.timedOut || cleanupError || result.error || result.status !== 0) {
    const failure = signal?.aborted ? `interrupted by ${signal.reason}`
      : result.timedOut ? 'deadline exceeded'
      : result.error?.message || (result.status !== 0 ? `exit ${result.status} (${result.signal || 'no signal'})` : '');
    const reason = [failure,
      cleanupError?.message].filter(Boolean).join('; ');
    throw new Error(`Packaged smoke failed: ${reason}\n${diagnostics.toString('utf8')}`);
  }
  if (diagnostics.length) process.stdout.write(diagnostics);
}
