# Proposed eMudhra security backport

**Status: PROPOSED — awaiting owner approval.** Research date: October 21, 2026.
This document records a plan, not an implemented fix or a release announcement.
Implementation, application builds, signing/notarization, release publication and
installed-app replacement have not been approved by this plan.

## Recommended candidate and release base

Prepare a security-only branch, `security/emudhra-v0.1.6`, from the exact
`v0.1.6` installed-release source:
[`ab18d68f49c7a726143ca9ef33495a5801e17d8b`](https://github.com/ephes/desktop-django-starter/commit/ab18d68f49c7a726143ca9ef33495a5801e17d8b).
Use proposed candidate version **`0.1.7-rc.1`** for an identifiable artifact-only
build after implementation approval. Neither that candidate nor a later stable
`0.1.7` tag or public release is authorized by recording this plan.

Do not rebuild the entire current main branch for this incident. At researched
main commit `82a9b9df25339147d8a5bdcc38ffea233475d19f`, that would ship 55 commits
and 254 changed files beyond the installed source, including migration `0003`,
new per-install secret-key behavior and unrelated application/UI/task changes.
The release-base backport instead preserves existing models, migrations,
templates, task behavior, user-data location and session-secret behavior. The
old shared-secret fallback remains separate, preexisting security debt; this
candidate is not a complete application security audit.

Another deliberately excluded known issue is the redirect/preload-origin security
hardening in
[`a233c00ff5edce03941740c90dd7ad5dce299569`](https://github.com/ephes/desktop-django-starter/commit/a233c00ff5edce03941740c90dd7ad5dce299569).
The release base can follow a server-side redirect off the Django origin inside
the main window with its `window.desktop` preload bridge attached, and its
app-data IPC handler does not validate the sender's origin. Current main fixes
that boundary; the CA-focused backport proposed here does not include it.
Before implementation approval, the owner must knowingly accept that temporary
exclusion or explicitly add this bounded shell security change to the candidate.
It requires no database migration, but changes navigation and IPC permissions,
so it must not be hidden under a promise of unchanged shell behavior.

## Bounded dependency changes

Backport the existing dependency-only security work, then update Electron to the
fixed patch release:

1. [`9b498b06dbe374f03cc2a453a4a62256602c7e8c`](https://github.com/ephes/desktop-django-starter/commit/9b498b06dbe374f03cc2a453a4a62256602c7e8c):
   shell dependency security refresh, including builder/updater and vulnerable
   transitive packages.
2. [`05a6ee8f589ff834ac97bcfa984e1872eb62e8e7`](https://github.com/ephes/desktop-django-starter/commit/05a6ee8f589ff834ac97bcfa984e1872eb62e8e7):
   Electron 44 transition in package manifests, lock and documentation, with no
   application-code change. Its compatibility assessment found no Electron
   41–44 breaking API changes affecting this shell; the new candidate still
   requires its own tests.
3. Pin **Electron `44.9.1`**, retaining `electron-builder 26.15.3`,
   `electron-updater 6.8.9` and the existing `global-agent 4` override from that
   security work. Inspect the lock diff and avoid a general dependency refresh.
4. Backport the packaging-only checksum hardening in
   [`1b95f38a307666176f614324f69aa852935f0e62`](https://github.com/ephes/desktop-django-starter/commit/1b95f38a307666176f614324f69aa852935f0e62),
   including its tests and matching release documentation. It rejects unsafe or
   duplicate input names and output/input collisions, and publishes the manifest
   atomically. This changes artifact integrity handling, not application behavior
   or user data.
5. Backport the development-lock certifi correction from main commit `82a9b9d`
   without including later application changes. It does not by itself repair
   packaged Python or pip's vendored trust store.

As of the research date, Electron's latest-three-major support policy covers
45, 44 and 43. `43.8.1` is the lowest maintained fixed line, but `44.9.1` reuses
this repository's existing 44 transition without adopting the newly released 45
major. `44.9.1` is the recommended bounded target, not a claim that the candidate
has already passed compatibility tests. Recheck support and fix availability
before implementing if this proposal is resumed later.

The [official 44.9.1 release](https://github.com/electron/electron/releases/tag/v44.9.1)
and [fix commit](https://github.com/electron/electron/commit/e02265be96c5e13ae43644ef482b718e1e800499)
apply certificate SPKI blocklisting, including Node. This is not a promise that
every affected root disappears from Electron's bundled certificate inventory.
See the [official support policy](https://www.electronjs.org/docs/latest/tutorial/electron-timelines).

## Python packaging and application isolation

The release-base build workflow, bundled-Python helper and `pyproject.toml` match
researched main; the backend stager differs only in comments. There is no need
to import the intervening Django application changes to rebuild the runtime.
The `scripts/write-checksums.py` script that the unchanged workflow calls does
differ between these revisions; the explicit checksum backport above keeps candidate artifact handling
consistent with the current release guide without importing application changes.

Preserve the installed release's application dependency baseline by constraining
the staging wheel installation to a frozen runtime export of the release-base
`uv.lock`. The existing unconstrained staging install must not resolve newer
application dependencies merely because it is rebuilding. The researched
baseline is:

| Distribution | Version |
| --- | --- |
| Django | 6.0.3 |
| django-tasks | 0.12.0 |
| django-tasks-db | 0.12.0 |
| django-browser-reload | 1.21.0 |
| asgiref | 3.11.1 |
| django-stubs-ext | 6.0.2 |
| sqlparse | 0.5.5 |
| typing-extensions | 4.15.0 |

Pin the proposed bundled Python patch to `3.14.8` rather than a floating `3.14`.
A Python patch alone is insufficient: inspected Python 3.14.8 standalone
`ensurepip` still seeds pip `26.2.1`, whose vendored CA bundle remains affected.
The installed-release Python `3.14.4` ships pip `26.0.1` with an affected vendored
bundle too. Top-level certifi is not required by this application's runtime.

Prefer removing unused pip distributions, entrypoints and metadata **and
`ensurepip`** from the unsigned staging runtime before signing. App startup does
not call these installers; staging uses the external build tool. Preserve all
actual application dependencies and verify the packaged app still runs without
installers. Updating installed pip alone would leave the old `ensurepip` seed
behind. If an installer proves necessary, redesign that part explicitly around
verified fixed pip `26.2.2`, including seed handling, before any network package
operation; do not modify standard-library vendored code casually.

Set `PYTHONDONTWRITEBYTECODE=1` for packaged Python children, including migrations,
server and worker, to prevent generated bytecode from modifying signed bundle
contents. Verify candidate bytes and strict signature validity before and after
smoke execution. Do not repair or edit an existing installed signed bundle.

The current packaged-smoke path uses the normal Electron user-data directory.
Add a smoke-only scratch profile before startup or single-instance handling and
keep smoke windows hidden. Migrations, seed data, server and worker must use only
that isolated profile. Never use the real installed database as the acceptance
fixture. Normal application identity and data paths remain unchanged.

Expected runtime differences are Electron 40→44, its Chromium/Node changes and
macOS 13 floor, plus Python/OpenSSL patch changes and the packaging safeguards
above. No new application migration or user-data migration is proposed. Preserve
Windows/Linux packaging behavior; this proposal does not establish additional
Windows updater validation.

## Candidate validation after implementation approval

- Run `just check`, including backend checks, Electron Node tests and docs build.
  Add meaningful coverage for frozen staging dependencies, installer removal,
  bytecode prevention, scratch-profile isolation and backend-child cleanup.
- Run `just packaged-smoke` only after profile isolation is effective. Check
  scratch-state persistence and confirm no orphan server/worker processes.
- Inspect the actual artifact's runtime versions and distribution inventory,
  including absence of unused pip and `ensurepip` seeds. Verify every retained
  trust bundle rather than relying on version strings alone.
- Exercise actual Electron Node HTTPS and Chromium networking separately:
  both affected research chains must fail and an ordinary trusted control must
  succeed. One client's result does not prove the other's behavior.
- Verify packaged Python stdlib TLS against the same negative and positive
  controls. Its observed default CA path uses the host OS trust bundle, so the
  host's shared CA remediation must also be verified before claiming protection.
  Do not duplicate that host repair with an ad hoc application trust override.
- Verify artifact checksums, architecture, expected bundle identifier and signing
  identity, strict code-signature validation, notarization ticket and platform
  acceptance. Repeat byte/signature checks after isolated smoke.

## Existing build and deployment boundaries

Use the existing [release workflow](../release.md) and
`.github/workflows/desktop-packages.yml`; do not invent another signing pipeline.
Its manual `publish_release=false` lane produces artifacts without publishing a
release. `true` prepares a draft, which still requires separate publication.
After approved implementation and source review, use only the artifact-only
lane first, from the exact reviewed ref. Current signing/notarization provider
usability remains unproven until an approved build exercises it. Do not accept
new contracts, replace credentials or weaken signing to make a build pass.

The app already has a documented `electron-updater`/Squirrel.Mac path and a
manual DMG replacement path. The connected updater consumes published release
metadata; artifact-only candidates and drafts are not proof of a production
update. Do not patch a signed update-feed file or use private updater internals
to bypass that boundary. Refer to the existing [Electron shell guide](../shells/electron.md)
and [updater validation backlog](../backlog.md).

No new generic macOS installer framework is proposed. If a candidate is later
approved for private installation, first choose the existing supported installer
path; any required automation should remain app-specific, verify the exact
signed artifact, refuse active app/backend processes, preserve application data
and a rollback copy, and prove replacement idempotence. Published updater use,
app quit/restart and installed-app replacement remain separate owner decisions.

This proposed plan changes no product source, dependency lock, application
version, release tag or installed application. The next phase requires explicit
owner approval of this bounded implementation scope.
