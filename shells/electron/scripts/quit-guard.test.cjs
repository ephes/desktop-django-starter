const assert = require("node:assert/strict");
const test = require("node:test");

const { createQuitGuard, describeActivity } = require("./quit-guard.cjs");

function guardWith({ activity, answer = true, skip = () => false, fails = false }) {
  const calls = { fetch: 0, confirm: [] };
  const guard = createQuitGuard({
    fetchActivity: async () => {
      calls.fetch += 1;
      if (fails) {
        throw new Error("Django is gone");
      }
      return activity;
    },
    confirmQuit: async (detail) => {
      calls.confirm.push(detail);
      return answer;
    },
    skip
  });
  return { guard, calls };
}

test("quits without asking when no tasks are running", async () => {
  const { guard, calls } = guardWith({ activity: { running_tasks: 0, queued_tasks: 0 } });

  assert.equal(await guard.shouldProceed(), true);
  assert.deepEqual(calls.confirm, []);
  assert.equal(guard.needsCheck(), false);
});

test("asks when a task is running and respects Cancel", async () => {
  const { guard, calls } = guardWith({
    activity: { running_tasks: 1, queued_tasks: 0 },
    answer: false
  });

  assert.equal(await guard.shouldProceed(), false);
  assert.deepEqual(calls.confirm, ["Quitting now stops 1 running background task."]);
  assert.equal(guard.needsCheck(), true);
});

test("asks once per quit even when close and before-quit both fire", async () => {
  const { guard, calls } = guardWith({ activity: { running_tasks: 2, queued_tasks: 1 } });

  const [first, second] = await Promise.all([guard.shouldProceed(), guard.shouldProceed()]);
  const third = await guard.shouldProceed();

  assert.deepEqual([first, second, third], [true, true, true]);
  assert.equal(calls.fetch, 1);
  assert.equal(calls.confirm.length, 1);
});

test("a failed activity check never blocks quitting", async () => {
  const { guard, calls } = guardWith({ fails: true });

  assert.equal(await guard.shouldProceed(), true);
  assert.deepEqual(calls.confirm, []);
});

test("skipped checks quit immediately and stay confirmed", async () => {
  const { guard, calls } = guardWith({ activity: { running_tasks: 1 }, skip: () => true });

  assert.equal(guard.needsCheck(), false);
  assert.equal(await guard.shouldProceed(), true);
  assert.equal(calls.fetch, 0);
  assert.equal(guard.isConfirmed(), true);
});

test("describes running and queued work", () => {
  assert.equal(
    describeActivity({ running_tasks: 2, queued_tasks: 3 }),
    "Quitting now stops 2 running background tasks. 3 queued tasks will start the next time the app runs."
  );
  assert.equal(
    describeActivity({ running_tasks: 0, queued_tasks: 1 }),
    "1 queued task will start the next time the app runs."
  );
});
