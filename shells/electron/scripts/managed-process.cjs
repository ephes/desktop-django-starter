const { spawn } = require("node:child_process");
const path = require("node:path");
const { execFileText } = require("./orphan-processes.cjs");

function spawnManagedProcess(invocation, environment) {
  const child = spawn(invocation.command, invocation.args, {
    cwd: invocation.cwd,
    env: environment,
    // A separate POSIX group lets shutdown reach descendants even if the
    // leader exits first. Keep the pipe open to cover abrupt shell loss.
    detached: process.platform !== "win32",
    stdio: ["pipe", "pipe", "pipe"],
    windowsHide: true
  });
  child.desktopProcessGroup = process.platform !== "win32";
  child.stdin.on("error", () => {});
  return child;
}

// killed means signal delivery only. The exit event/status is the authority.
async function stopManagedProcess(child, {
  platform = process.platform, run = execFileText, graceMs = 2000, reapMs = 500,
  killGroup = process.kill.bind(process)
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
    const signal = name => {
      if (!child.desktopProcessGroup) return child.kill(name);
      try {
        killGroup(-child.pid, name);
      } catch (error) {
        if (error.code !== "ESRCH") throw error;
      }
    };
    // Closing stdin also reaches a guard behind a development uv launcher,
    // whose Python process can own a different group from uv itself.
    child.stdin?.destroy();
    signal("SIGTERM");
    const retired = await wait(graceMs);
    if (retired && !child.desktopProcessGroup) return true;
    // The leader exiting does not prove that all group members exited.
    signal("SIGKILL");
    return retired || await wait(reapMs);
  } finally {
    child.removeListener("exit", onExit);
  }
}

module.exports = { spawnManagedProcess, stopManagedProcess };
