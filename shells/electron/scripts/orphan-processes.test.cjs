const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const {
  beginSession,
  endSession,
  findOrphanPids,
  getSessionPath,
  parsePosixProcessListing,
  parseWindowsProcessListing,
  stopOrphanedBackendProcesses
} = require("./orphan-processes.cjs");

const KEY = "0123456789abcdef0123456789abcdef";

function tempDir() {
  return fs.mkdtempSync(path.join(os.tmpdir(), "orphans-"));
}

test("first session gets a new key and no unclean flag", () => {
  const dir = tempDir();

  const { session, previousRunWasUnclean } = beginSession(dir, 42);

  assert.match(session.app_key, /^[0-9a-f]{32}$/);
  assert.equal(session.running, true);
  assert.equal(previousRunWasUnclean, false);
  if (process.platform !== "win32") {
    assert.equal(fs.statSync(getSessionPath(dir)).mode & 0o777, 0o600);
  }
});

test("a session that was never ended marks the next run as unclean and keeps the key", () => {
  const dir = tempDir();
  const first = beginSession(dir, 1).session;

  const second = beginSession(dir, 2);

  assert.equal(second.previousRunWasUnclean, true);
  assert.equal(second.session.app_key, first.app_key);
});

test("an ended session marks the next run as clean", () => {
  const dir = tempDir();
  const first = beginSession(dir, 1).session;
  endSession(dir, first);

  assert.equal(beginSession(dir, 2).previousRunWasUnclean, false);
});

test("existing unsafe markers are preserved and refuse session publication", () => {
  for (const bytes of ["{not json", "null", "{}", JSON.stringify({ app_key: KEY }),
    JSON.stringify({ app_key: KEY, running: "false", shell_pid: 1 })]) {
    const dir = tempDir();
    fs.writeFileSync(getSessionPath(dir), bytes);
    assert.throws(() => beginSession(dir, 1), /session marker/i);
    assert.equal(fs.readFileSync(getSessionPath(dir), "utf8"), bytes);
  }
});

test("orphans match only this app's guarded Python processes", () => {
  const programs = [
    "  101 /Applications/Desktop Django Starter.app/Contents/Resources/backend/python/bin/python3.14",
    "  102 uv",
    "  103 /other/python3",
    "  104 /usr/bin/python3",
    "  105 /bin/zsh",
    "  106 /Applications/Desktop Django Starter.app/Contents/MacOS/Desktop Django Starter",
    "  107 /usr/bin/python3"
  ].join("\n");
  const commandLines = [
    `  101 /Applications/Desktop Django Starter.app/Contents/Resources/backend/python/bin/python3.14 /Applications/Desktop Django Starter.app/Contents/Resources/backend/desktop_process_guard.py --app-key ${KEY} --instance a --watch-stdin -- manage.py runserver`,
    `  102 uv run python /repo/scripts/desktop_process_guard.py --app-key ${KEY} --instance a -- manage.py db_worker`,
    "  103 /other/python3 desktop_process_guard.py --app-key ffffffffffffffffffffffffffffffff -- manage.py runserver",
    "  104 /usr/bin/python3 manage.py runserver",
    `  105 /bin/zsh -c python3 scripts/desktop_process_guard.py --app-key ${KEY} -- sleepy.py`,
    `  106 /Applications/Desktop Django Starter.app/Contents/MacOS/Desktop Django Starter --app-key ${KEY}`,
    `  107 /usr/bin/python3 desktop_process_guard.py --app-key ${KEY}0 -- manage.py runserver`
  ].join("\n");

  const processes = parsePosixProcessListing(programs, commandLines);

  assert.deepEqual(findOrphanPids(processes, KEY, []), [101, 102]);
  assert.deepEqual(findOrphanPids(processes, KEY, [101]), [102]);
});

test("Windows listings are parsed", () => {
  const listing = [
    `4321\tpython.exe\t"C:\\Program Files\\App\\resources\\backend\\python\\python.exe" "C:\\Program Files\\App\\resources\\backend\\desktop_process_guard.py" --app-key ${KEY} --instance b --watch-stdin -- manage.py runserver\r`,
    `4322\tpowershell.exe\tpowershell.exe -Command ... --app-key ${KEY} ...\r`,
    ""
  ].join("\n");

  assert.deepEqual(findOrphanPids(parseWindowsProcessListing(listing), KEY, []), [4321]);
});

test("leftover guarded processes are stopped", { skip: process.platform === "win32" }, async (t) => {
  const dir = tempDir();
  const manage = path.join(dir, "manage.py");
  fs.writeFileSync(manage, "import time\nif __name__ == '__main__':\n    time.sleep(60)\n");
  const guard = path.join(__dirname, "..", "..", "..", "scripts", "desktop_process_guard.py");
  const leftover = spawn("python3", [guard, "--app-key", KEY, "--instance", "old", "--", manage], {
    stdio: "ignore"
  });
  await new Promise((resolve) => leftover.once("spawn", resolve));
  const exited = new Promise((resolve) => leftover.once("exit", resolve));

  const quietLog = { warn: () => {} };
  try {
    const stopped = await stopOrphanedBackendProcesses(KEY, { log: quietLog });
    if (stopped.status === "unknown" && /EPERM/.test(stopped.detail)) {
      t.skip("Sandbox blocks /bin/ps; real orphan inventory unavailable.");
      return;
    }
    assert.deepEqual(stopped, { status: "confirmed", pids: [leftover.pid] });
    await exited;
  } finally {
    if (leftover.exitCode === null && leftover.signalCode === null) leftover.kill("SIGKILL");
    await exited;
  }
});

const { execFileText, stopPid, listProcesses } = require("./orphan-processes.cjs");
const candidate = (generation = "old") => ({
  pid: 321, generation, program: "python3",
  commandLine: `python3 desktop_process_guard.py --app-key ${KEY} --instance old -- manage.py`
});

test("owned commands have a deadline, hard cancellation and bounded reap wait", async () => {
  let signal;
  await assert.rejects(execFileText("hung", [], {
    timeoutMs: 5, reapMs: 5,
    execute: (_cmd, _args, options, _callback) => {
      assert.equal(options.killSignal, "SIGKILL");
      assert.equal(options.timeout, 5);
      return { kill: value => { signal = value; } };
    }
  }), /deadline/);
  assert.equal(signal, "SIGKILL");
});

test("command launch errors and output overflow reject and reap", async () => {
  await assert.rejects(execFileText("/dds-no-such-command", []), /ENOENT/);
  await assert.rejects(execFileText(process.execPath, ["-e", "process.stdout.write('x'.repeat(4096))"], {
    maxBuffer: 64
  }), /maxBuffer/);
  await assert.rejects(execFileText(process.execPath, ["-e", "setInterval(()=>{}, 1000)"], {
    timeoutMs: 30, reapMs: 100
  }));
});

test("POSIX inventory refuses two listings from different process generations", async () => {
  await assert.rejects(listProcesses("darwin", KEY, async (_command, args) =>
    args.at(-1).includes("comm")
      ? "321 Sun Nov 15 12:00:00 2026 python3"
      : `321 Sun Nov 15 12:00:01 2026 ${candidate().commandLine}`), /identity changed/);
});

for (const replacementAt of [0, 1]) {
  test(`PID replacement before signal boundary ${replacementAt} is never signalled`, async () => {
    const signals = [];
    let probes = 0;
    const result = await stopPid(candidate(), KEY, {
      platform: "darwin", graceMs: 0, reapMs: 0,
      inventory: async () => [candidate(probes++ >= replacementAt ? "replacement" : "old")],
      signal: (pid, value) => signals.push([pid, value])
    });
    assert.equal(result, true);
    assert.deepEqual(signals, replacementAt === 0 ? [] : [[321, "SIGTERM"]]);
  });
}

test("still-owned backend escalates and must be confirmed absent", async () => {
  const signals = [];
  let probes = 0;
  assert.equal(await stopPid(candidate(), KEY, {
    platform: "darwin", graceMs: 0, reapMs: 0,
    inventory: async () => ++probes < 3 ? [candidate()] : [],
    signal: (_pid, value) => signals.push(value)
  }), true);
  assert.deepEqual(signals, ["SIGTERM", "SIGKILL"]);
});

test("permission failure preserves marker and never rotates ownership", () => {
  const dir = tempDir();
  const marker = getSessionPath(dir);
  fs.writeFileSync(marker, "retained");
  const read = fs.openSync;
  fs.openSync = (name, ...args) => {
    if (name === marker) throw Object.assign(Error("denied"), { code: "EACCES" });
    return read(name, ...args);
  };
  try { assert.throws(() => beginSession(dir), /session marker.*EACCES/i); }
  finally { fs.openSync = read; }
  assert.equal(fs.readFileSync(marker, "utf8"), "retained");
});

for (const kind of ["oversized", "symlink", "directory", "fifo"]) {
  test(`session input ${kind} is refused before reading or replacing it`, { skip: kind === "fifo" && process.platform === "win32" }, () => {
    const dir = tempDir();
    const marker = getSessionPath(dir);
    if (kind === "oversized") fs.writeFileSync(marker, " ".repeat(4097));
    if (kind === "symlink") {
      fs.writeFileSync(path.join(dir, "target"), "canary");
      fs.symlinkSync(path.join(dir, "target"), marker);
    }
    if (kind === "directory") fs.mkdirSync(marker);
    if (kind === "fifo") require("node:child_process").execFileSync("mkfifo", [marker]);
    // Guard the pre-fix read to demonstrate rejection before any bulk/blocking
    // read, without hanging the regression suite on a real FIFO.
    const readFile = fs.readFileSync;
    let unsafeRead = false;
    fs.readFileSync = (name, ...args) => {
      if (name === marker) { unsafeRead = true; throw Error("unsafe pathname read"); }
      return readFile(name, ...args);
    };
    try {
      assert.throws(() => beginSession(dir), /session marker/i);
      assert.equal(unsafeRead, false);
    } finally { fs.readFileSync = readFile; }
  });
}

for (const kind of ["file", "symlink"]) {
  test(`publication preserves a foreign PID temporary ${kind}`, () => {
    const dir = tempDir();
    const session = beginSession(dir).session;
    const stale = `${getSessionPath(dir)}.${process.pid}.tmp`;
    const target = path.join(dir, "canary");
    fs.writeFileSync(target, "foreign", { mode: 0o644 });
    if (kind === "symlink") fs.symlinkSync(target, stale);
    else fs.writeFileSync(stale, "foreign", { mode: 0o644 });
    endSession(dir, session);
    assert.equal(fs.readFileSync(stale, "utf8"), "foreign");
    assert.equal(fs.readFileSync(target, "utf8"), "foreign");
    assert.equal(fs.statSync(target).mode & 0o777, 0o644);
  });
}

for (const boundary of ["write", "rename"]) {
  test(`failed marker ${boundary} removes only its own temporary`, () => {
    const dir = tempDir();
    const session = beginSession(dir).session;
    const original = fs.readFileSync(getSessionPath(dir), "utf8");
    const method = boundary === "write" ? "writeFileSync" : "renameSync";
    const real = fs[method];
    fs[method] = () => { throw Error(`${boundary} failed`); };
    try { assert.throws(() => endSession(dir, session), /failed/); }
    finally { fs[method] = real; }
    assert.equal(fs.readFileSync(getSessionPath(dir), "utf8"), original);
    assert.deepEqual(fs.readdirSync(dir), ["desktop-shell-session.json"]);
  });
}

test("publication collision never truncates or removes an unowned temporary", () => {
  const dir = tempDir();
  const session = beginSession(dir).session;
  const realOpen = fs.openSync;
  let foreign;
  fs.openSync = (name, flags, mode) => {
    foreign = name;
    const descriptor = realOpen(name, "w");
    fs.writeFileSync(descriptor, "foreign");
    fs.closeSync(descriptor);
    return realOpen(name, flags, mode);
  };
  try { assert.throws(() => endSession(dir, session), /EEXIST/); }
  finally { fs.openSync = realOpen; }
  assert.equal(fs.readFileSync(foreign, "utf8"), "foreign");
});

for (const kind of ["inventory failure", "unconfirmed stop", "signal error"]) {
  test(`orphan ${kind} is unknown rather than proven empty`, async () => {
    const result = await stopOrphanedBackendProcesses(KEY, {
      log: { warn() {} },
      inventory: async () => {
        if (kind === "inventory failure") throw Error("tool unavailable");
        return [candidate()];
      },
      stop: async () => { if (kind === "signal error") throw Error("denied"); return false; }
    });
    assert.equal(result.status, "unknown");
    assert.match(result.detail, /retry/i);
  });
}

test("proven empty inventory and confirmed orphan cleanup succeed", async () => {
  const options = { log: { warn() {} }, inventory: async () => [], stop: async () => true };
  assert.deepEqual(await stopOrphanedBackendProcesses(KEY, options), { status: "confirmed", pids: [] });
  let calls = 0;
  options.inventory = async () => calls++ === 0 ? [candidate()] : [];
  assert.deepEqual(await stopOrphanedBackendProcesses(KEY, options), { status: "confirmed", pids: [321] });
});

test("a still-guarded replacement after cleanup keeps recovery unknown", async () => {
  const result = await stopOrphanedBackendProcesses(KEY, {
    log: { warn() {} }, inventory: async () => [candidate("replacement")], stop: async () => true
  });
  assert.equal(result.status, "unknown");
  assert.match(result.detail, /remain/);
});

test("malformed inventory cannot prove an empty process set", async () => {
  await assert.rejects(listProcesses("darwin", KEY, async () => "unexpected format"), /Incomplete/);
});

test("replaced publication temporary is preserved and never renamed over the marker", () => {
  const dir = tempDir();
  const session = beginSession(dir).session;
  const original = fs.readFileSync(getSessionPath(dir), "utf8");
  const realWrite = fs.writeFileSync;
  let foreign;
  fs.writeFileSync = (descriptor, ...args) => {
    realWrite(descriptor, ...args);
    foreign = path.join(dir, fs.readdirSync(dir).find(name => name.endsWith(".tmp")));
    fs.unlinkSync(foreign);
    realWrite(foreign, "foreign replacement");
  };
  try { assert.throws(() => endSession(dir, session), /ownership/); }
  finally { fs.writeFileSync = realWrite; }
  assert.equal(fs.readFileSync(getSessionPath(dir), "utf8"), original);
  assert.equal(fs.readFileSync(foreign, "utf8"), "foreign replacement");
});

test("Windows inventory retains creation identity and termination rechecks its full marker", async () => {
  const entry = { ...candidate(), program: "python.exe", generation: "2026-11-15T12:00:00.0000000Z" };
  const rows = await listProcesses("win32", KEY, async () =>
    `${entry.pid}\t${entry.generation}\t${entry.program}\t${entry.commandLine}`);
  assert.deepEqual(rows, [entry]);
  let calls = 0;
  let command;
  assert.equal(await stopPid(entry, KEY, {
    platform: "win32", reapMs: 0,
    inventory: async () => calls++ === 0 ? rows : [],
    run: async (_tool, args) => { command = args.at(-1); }
  }), true);
  assert.ok(command.includes(entry.generation));
  assert.ok(command.includes(`$p.Name -ceq '${entry.program}'`));
  assert.ok(command.includes(`$p.CommandLine -ceq '${entry.commandLine}'`));
});
