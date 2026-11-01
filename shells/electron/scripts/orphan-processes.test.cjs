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

test("a corrupt session file starts a fresh session", () => {
  const dir = tempDir();
  fs.writeFileSync(getSessionPath(dir), "{not json");

  const { session, previousRunWasUnclean } = beginSession(dir, 1);

  assert.match(session.app_key, /^[0-9a-f]{32}$/);
  assert.equal(previousRunWasUnclean, false);
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

test("leftover guarded processes are stopped", { skip: process.platform === "win32" }, async () => {
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
  const stopped = await stopOrphanedBackendProcesses(KEY, { log: quietLog });

  assert.deepEqual(stopped, [leftover.pid]);
  await exited;
});
