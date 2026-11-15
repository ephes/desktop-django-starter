// Finds and stops backend processes left behind by a previous run that did
// not shut down cleanly (a crash, a force quit, power loss).
//
// Every backend process is started through desktop_process_guard.py with
// `--app-key <key>` on its command line. The key is random, generated once per
// app-data directory and stored in the session file below, so it identifies
// this app's processes without matching other apps built from the starter.
// The single-instance lock guarantees that no other live instance of this app
// owns such processes, so any match at startup is an orphan.

const { execFile } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const SESSION_FILENAME = "desktop-shell-session.json";
const STOP_GRACE_PERIOD_MS = 2000;

function getSessionPath(appDataDir) {
  return path.join(appDataDir, SESSION_FILENAME);
}

class SessionMarkerError extends Error {
  constructor(detail) {
    super(`Unsafe or unreadable session marker: ${detail}. Preserve the marker, repair it and restart.`);
    this.code = "DDS_SESSION_MARKER_UNSAFE";
  }
}

function readSession(appDataDir) {
  let bytes;
  let descriptor;
  try {
    const marker = getSessionPath(appDataDir);
    // lstat distinguishes an absent leaf from a dangling symlink. O_NOFOLLOW
    // is authoritative where supported; descriptor checks precede all reads.
    const named = fs.lstatSync(marker);
    if (!named.isFile() || named.isSymbolicLink()) throw new SessionMarkerError("not a regular direct file");
    descriptor = fs.openSync(marker, fs.constants.O_RDONLY
      | (fs.constants.O_NOFOLLOW || 0) | (fs.constants.O_NONBLOCK || 0));
    const opened = fs.fstatSync(descriptor);
    if (!opened.isFile() || opened.nlink !== 1 || opened.size > 4096
      || opened.dev !== named.dev || opened.ino !== named.ino) {
      throw new SessionMarkerError("not an admitted regular marker (maximum 4096 bytes)");
    }
    const buffer = Buffer.alloc(4097);
    let length = 0;
    while (length < buffer.length) {
      const count = fs.readSync(descriptor, buffer, length, buffer.length - length, null);
      if (count === 0) break;
      length += count;
    }
    const after = fs.fstatSync(descriptor);
    if (length > 4096 || length !== opened.size || after.size !== opened.size
      || after.mtimeMs !== opened.mtimeMs || after.ctimeMs !== opened.ctimeMs) {
      throw new SessionMarkerError("oversized or changed marker");
    }
    bytes = buffer.subarray(0, length).toString("utf8");
  } catch (error) {
    if (error.code === "ENOENT" && descriptor === undefined) {
      // Only a genuinely absent path is a first launch (not an open race).
      try { fs.lstatSync(getSessionPath(appDataDir)); }
      catch (probeError) { if (probeError.code === "ENOENT") return null; }
    }
    if (error instanceof SessionMarkerError) throw error;
    throw new SessionMarkerError(error.code || "read failed");
  } finally {
    if (descriptor !== undefined) fs.closeSync(descriptor);
  }
  try {
    const session = JSON.parse(bytes);
    if (session && typeof session.app_key === "string" && /^[0-9a-f]{32}$/.test(session.app_key)
      && typeof session.running === "boolean" && Number.isSafeInteger(session.shell_pid) && session.shell_pid > 0) {
      return { app_key: session.app_key, running: session.running, shell_pid: session.shell_pid };
    }
  } catch (_) { /* Refuse malformed input below. */ }
  throw new SessionMarkerError("invalid document");
}

function writeSession(appDataDir, session) {
  fs.mkdirSync(appDataDir, { recursive: true });
  const sessionPath = getSessionPath(appDataDir);
  const temporaryPath = `${sessionPath}.${process.pid}.tmp`;
  fs.writeFileSync(temporaryPath, `${JSON.stringify(session, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporaryPath, sessionPath);
}

// Returns the session for this run and whether the previous run ended uncleanly.
function beginSession(appDataDir, shellPid = process.pid) {
  const previous = readSession(appDataDir);
  const session = {
    app_key: previous?.app_key || crypto.randomBytes(16).toString("hex"),
    running: true,
    shell_pid: shellPid
  };
  writeSession(appDataDir, session);
  return { session, previousRunWasUnclean: previous?.running === true };
}

function endSession(appDataDir, session) {
  writeSession(appDataDir, { ...session, running: false });
}

function guardMarker(appKey) {
  return `--app-key ${appKey}`;
}

function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

// The executable must be Python (or `uv`, which runs Python in development)
// and the arguments must name the guard and this app's key. A shell, editor
// or grep whose command line merely mentions the key does not match.
const BACKEND_PROGRAM = /^(?:python[0-9.]*|uv)(?:\.exe)?$/i;

function isGuardedBackendProcess({ program, commandLine }, appKey) {
  const programName = path.basename(String(program).replace(/\\/g, "/"));
  if (!BACKEND_PROGRAM.test(programName)) {
    return false;
  }
  const marker = new RegExp(
    `desktop_process_guard\\.py"?\\s(?:.*\\s)?--app-key\\s+${escapeRegExp(appKey)}(?:\\s|$)`
  );
  return marker.test(commandLine);
}

function parsePidColumns(text) {
  const rows = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^\s*(\d+)\s(.*)$/);
    if (match) {
      rows.set(Number(match[1]), match[2].trim());
    }
  }
  return rows;
}

// POSIX: `ps -o pid=,comm=` and `ps -o pid=,args=` output.
function parsePosixProcessListing(programsText, argumentsText) {
  const programs = parsePidColumns(programsText);
  const commandLines = parsePidColumns(argumentsText);
  return [...commandLines].map(([pid, commandLine]) => ({
    pid,
    program: programs.get(pid) || "",
    commandLine
  }));
}

// Windows: "pid<TAB>name<TAB>command line" lines from PowerShell.
function parseWindowsProcessListing(text) {
  return text.split(/\r?\n/)
    .map((line) => line.split("\t"))
    .filter((columns) => columns.length >= 3 && /^\d+$/.test(columns[0].trim()))
    .map(([pid, program, ...rest]) => ({
      pid: Number(pid.trim()),
      program: program.trim(),
      commandLine: rest.join("\t").trim()
    }));
}

function findOrphanPids(processes, appKey, ownPids = [process.pid]) {
  return processes
    .filter((entry) => !ownPids.includes(entry.pid) && isGuardedBackendProcess(entry, appKey))
    .map((entry) => entry.pid);
}

// execFile's hard timeout bounds the helper; the outer deadline also bounds
// waiting for its callback/stdio to close. A late callback cannot settle twice.
function execFileText(command, args, {
  execute = execFile, timeoutMs = 3000, reapMs = 500, maxBuffer = 16 * 1024 * 1024
} = {}) {
  return new Promise((resolve, reject) => {
    let child;
    const deadline = setTimeout(() => {
      try { child?.kill("SIGKILL"); } catch (_) { /* Already gone. */ }
      reject(new Error("Process helper exceeded its deadline; repair the process tool and retry."));
    }, timeoutMs + reapMs);
    try {
      child = execute(command, args, {
        windowsHide: true, maxBuffer, timeout: timeoutMs, killSignal: "SIGKILL"
      }, (error, stdout) => {
        clearTimeout(deadline);
        if (error) reject(error);
        else resolve(stdout);
      });
    } catch (error) {
      clearTimeout(deadline);
      reject(error);
    }
  });
}

function windowsSystemTool(name) {
  return path.join(process.env.SystemRoot || "C:\\Windows", "System32", name);
}

function parseGenerationColumns(text) {
  const rows = new Map();
  for (const line of text.split(/\r?\n/)) {
    const match = line.match(/^\s*(\d+)\s+(\S+\s+\S+\s+\d+\s+\d+:\d+:\d+\s+\d+)\s+(.*)$/);
    if (match) rows.set(Number(match[1]), { generation: match[2].replace(/\s+/g, " "), value: match[3].trim() });
  }
  return rows;
}

async function listProcesses(platform = process.platform, appKey = "", run = execFileText) {
  if (platform === "win32") {
    const script = [
      "Get-CimInstance Win32_Process -ErrorAction Stop",
      `| Where-Object { $_.CommandLine -like '*${guardMarker(appKey)}*' }`,
      '| ForEach-Object { "$($_.ProcessId)`t$($_.CreationDate.ToUniversalTime().ToString(\'o\'))`t$($_.Name)`t$($_.CommandLine)" }'
    ].join(" ");
    const output = await run(
      windowsSystemTool(path.join("WindowsPowerShell", "v1.0", "powershell.exe")),
      ["-NoProfile", "-NonInteractive", "-Command", script]
    );
    return output.split(/\r?\n/).filter(Boolean).map(line => {
      const [pid, generation, program, ...args] = line.split("\t");
      if (!/^\d+$/.test(pid) || !generation || !program || !args.length) {
        throw new Error("Incomplete Windows process identity.");
      }
      return { pid: Number(pid), generation, program, commandLine: args.join("\t") };
    });
  }

  // Both observations carry start time. Never join program/arguments by PID
  // alone: it may have been reused between the two ps commands.
  const programs = parseGenerationColumns(await run("/bin/ps", ["-ax", "-o", "pid=,lstart=,comm="]));
  const args = parseGenerationColumns(await run("/bin/ps", ["-axww", "-o", "pid=,lstart=,args="]));
  return [...args].flatMap(([pid, entry]) => {
    const program = programs.get(pid);
    if (!program || program.generation !== entry.generation) return [];
    return [{ pid, generation: entry.generation, program: program.value, commandLine: entry.value }];
  });
}

function sameProcess(current, observed, appKey) {
  return !!observed.generation && current.generation === observed.generation
    && current.program === observed.program && current.commandLine === observed.commandLine
    && isGuardedBackendProcess(current, appKey);
}

async function stopPid(observed, appKey, {
  platform = process.platform, inventory = () => listProcesses(platform, appKey),
  signal = process.kill, run = execFileText,
  graceMs = STOP_GRACE_PERIOD_MS, reapMs = 500
} = {}) {
  if (!observed.generation) throw new Error("Missing process generation; refusing to signal.");
  async function stillOwned() {
    const current = (await inventory()).find(entry => entry.pid === observed.pid);
    return current && sameProcess(current, observed, appKey);
  }
  async function waitGone(duration) {
    const deadline = Date.now() + duration;
    do {
      if (!await stillOwned()) return true;
      if (Date.now() >= deadline) return false;
      await new Promise(resolve => setTimeout(resolve, Math.min(100, deadline - Date.now())));
    } while (true);
  }
  if (!await stillOwned()) return true;
  if (platform === "win32") {
    // Recheck the CIM creation time inside the terminating helper too. Avoid
    // taskkill /t: descendants have not individually passed identity admission.
    const stamp = observed.generation.replace(/'/g, "''");
    const script = `$p = Get-CimInstance Win32_Process -Filter "ProcessId = ${observed.pid}" -ErrorAction Stop; `
      + `if ($p -and $p.CreationDate.ToUniversalTime().ToString('o') -eq '${stamp}') { `
      + "$r = Invoke-CimMethod -InputObject $p -MethodName Terminate -ErrorAction Stop; "
      + "if ($r.ReturnValue -ne 0) { throw 'Termination refused' } }";
    await run(windowsSystemTool(path.join("WindowsPowerShell", "v1.0", "powershell.exe")),
      ["-NoProfile", "-NonInteractive", "-Command", script]);
    return waitGone(reapMs);
  }
  try { signal(observed.pid, "SIGTERM"); } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
  if (await waitGone(graceMs)) return true;
  // waitGone's last observation immediately precedes escalation.
  try { signal(observed.pid, "SIGKILL"); } catch (error) {
    if (error.code !== "ESRCH") throw error;
  }
  return waitGone(reapMs);
}

// Stops leftovers of this app and returns their PIDs. Never throws: a failed
// cleanup must not block startup.
async function stopOrphanedBackendProcesses(appKey, { platform = process.platform, log = console } = {}) {
  let processes;
  try {
    processes = await listProcesses(platform, appKey);
  } catch (error) {
    log.warn(`Could not list processes to look for leftovers: ${error.message}`);
    return [];
  }

  const pids = findOrphanPids(processes, appKey);
  for (const pid of pids) {
    log.warn(`Stopping leftover backend process ${pid} from a previous run.`);
    await stopPid(processes.find(entry => entry.pid === pid), appKey, { platform });
  }
  return pids;
}

module.exports = {
  execFileText,
  listProcesses,
  stopPid,
  SESSION_FILENAME,
  beginSession,
  endSession,
  findOrphanPids,
  getSessionPath,
  guardMarker,
  isGuardedBackendProcess,
  parsePosixProcessListing,
  parseWindowsProcessListing,
  readSession,
  stopOrphanedBackendProcesses
};
