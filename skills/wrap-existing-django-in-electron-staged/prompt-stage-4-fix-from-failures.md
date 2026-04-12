# Stage 4: Fix From Exact Failures

Use this prompt only after a concrete verification command fails.

Before launch:

1. replace the placeholders below
2. paste the exact failing command output into the failure block
3. restrict the allowed files to only those implicated by the failure

Read only what you need:

1. `../desktop-django-starter/skills/wrap-existing-django-in-electron-staged/SKILL.md`
2. the exact files implicated by the failing command
3. the exact failure output pasted below

## Scope

- Current stage: `{{CURRENT_STAGE}}`
- Allowed writes: `{{ALLOWED_WRITE_SET}}`
- Forbidden writes: everything else

## Failure output

```text
{{PASTE_EXACT_FAILURE_OUTPUT_HERE}}
```

## Your task

Fix only the failure shown above.

Constraints:

- do not broaden the scope
- do not re-run a full repo review
- do not rewrite unrelated files
- prefer the smallest defensible patch

## Verification

Re-run only the failed command and any directly adjacent sanity check needed to
confirm the fix.

At the end, report:

1. files changed
2. root cause
3. commands re-run
4. whether the failure is fixed or still blocked
