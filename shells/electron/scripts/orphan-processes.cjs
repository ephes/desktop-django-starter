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

function readSession(appDataDir) {
  try {
    const session = JSON.parse(fs.readFileSync(getSessionPath(appDataDir), "utf8"));
    if (typeof session.app_key === "string" && /^[0-9a-f]{32}$/.test(session.app_key)) {
      return { app_key: session.app_key, running: session.running === true, shell_pid: session.shell_pid };
    }
  } catch (_error) {
    // Missing or unreadable: start a new session below.
  }

  return null;
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

function execFileText(command, args) {
  return new Promise((resolve, reject) => {
    execFile(command, args, { windowsHide: true, maxBuffer: 16 * 1024 * 1024 }, (error, stdout) => {
      if (error) {
        reject(error);
        return;
      }
      resolve(stdout);
    });
  });
}

function windowsSystemTool(name) {
  return path.join(process.env.SystemRoot || "C:\\Windows", "System32", name);
}

async function listProcesses(platform = process.platform, appKey = "") {
  if (platform === "win32") {
    // Filter in PowerShell so only candidate rows come back.
    const script = [
      "Get-CimInstance Win32_Process",
      `| Where-Object { $_.CommandLine -like '*${guardMarker(appKey)}*' }`,
      "| ForEach-Object { \"$($_.ProcessId)`t$($_.Name)`t$($_.CommandLine)\" }"
    ].join(" ");
    const output = await execFileText(
      windowsSystemTool(path.join("WindowsPowerShell", "v1.0", "powershell.exe")),
      ["-NoProfile", "-NonInteractive", "-Command", script]
    );
    return parseWindowsProcessListing(output);
  }

  const [programs, commandLines] = await Promise.all([
    execFileText("/bin/ps", ["-ax", "-o", "pid=,comm="]),
    execFileText("/bin/ps", ["-axww", "-o", "pid=,args="])
  ]);
  return parsePosixProcessListing(programs, commandLines);
}

function isAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (error) {
    return error.code === "EPERM";
  }
}

async function stopPid(pid, platform = process.platform) {
  if (platform === "win32") {
    await execFileText(windowsSystemTool("taskkill.exe"), ["/pid", String(pid), "/t", "/f"])
      .catch(() => {});
    return;
  }

  try {
    process.kill(pid, "SIGTERM");
  } catch (_error) {
    return;
  }

  const deadline = Date.now() + STOP_GRACE_PERIOD_MS;
  while (Date.now() < deadline && isAlive(pid)) {
    await new Promise((resolve) => setTimeout(resolve, 100));
  }

  if (isAlive(pid)) {
    try {
      process.kill(pid, "SIGKILL");
    } catch (_error) {
      // Already gone.
    }
  }
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
    await stopPid(pid, platform);
  }
  return pids;
}

module.exports = {
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
