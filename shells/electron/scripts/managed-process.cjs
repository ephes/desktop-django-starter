const path = require("node:path");
const { execFileText } = require("./orphan-processes.cjs");

// killed means signal delivery only. The exit event/status is the authority.
async function stopManagedProcess(child, {
  platform = process.platform, run = execFileText, graceMs = 2000, reapMs = 500
} = {}) {
  if (!child || !child.pid || child.exitCode != null || child.signalCode != null) return true;
  let exited = false;
  let notify = () => {};
  const onExit = () => { exited = true; notify(true); };
  child.once("exit", onExit);
  const wait = duration => new Promise(resolve => {
    if (exited || child.exitCode != null || child.signalCode != null) return resolve(true);
    const timer = setTimeout(() => { notify = () => {}; resolve(false); }, duration);
    notify = result => { clearTimeout(timer); notify = () => {}; resolve(result); };
  });
  try {
    if (platform === "win32") {
      const taskkill = path.join(process.env.SystemRoot || "C:\\Windows", "System32", "taskkill.exe");
      await run(taskkill, ["/pid", String(child.pid), "/t", "/f"]);
      return await wait(reapMs);
    }
    child.kill("SIGTERM");
    if (await wait(graceMs)) return true;
    child.kill("SIGKILL");
    return await wait(reapMs);
  } finally {
    child.removeListener("exit", onExit);
  }
}

module.exports = { stopManagedProcess };
