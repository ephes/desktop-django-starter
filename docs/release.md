# Release and Update Guide

This starter now includes the packaging scaffolding needed to make signing, notarization, a minimal Electron connected updater, and manual updates explicit without turning the repository into a full production release system.

## Packaging Workflow

Three packaging paths are intentionally supported:

- local packaging with `just package-dist` or `just package-dist-dir`
- Electron GitHub Actions packaging with `.github/workflows/desktop-packages.yml`
- Tauri GitHub Actions packaging with `.github/workflows/tauri-packages.yml`

The repo now also includes one narrower Tauri-only local packaging command:

- `just tauri-build` for a local host bundle, defaulting to `dmg` on macOS, `nsis` on Windows, and `appimage` on Linux

The repo also includes one narrower Positron-only local packaging command:

- `just positron-package-dmg` for a local macOS DMG built with Briefcase ad-hoc signing

Local packaging remains usable when no release credentials are configured. In that case, the build should still complete, but the resulting installer is expected to be unsigned and, on macOS, not notarized.

The Electron GitHub Actions workflow uses the same `electron-builder` config and only turns on signing/notarization when the relevant secrets are present. It also generates Electron updater metadata and can publish the Electron artifacts to a draft GitHub Release when the manual `publish_release` workflow input is set to `true`. This keeps the starter teachable while still making the public-distribution requirements concrete.

Electron packaging keeps an explicit `files` allowlist for shell-local main-process helpers under `shells/electron/scripts/`. When `main.js` starts requiring a new helper, add that file to the builder config in the same change or the packaged app will fail at startup even if local development still works.

The Tauri GitHub workflow is intentionally narrower than the Electron lane:

- there is now a dedicated Tauri GitHub packaging workflow at `.github/workflows/tauri-packages.yml`
- it uses the official-style `tauri-action` flow in build-only mode, rather than publishing a GitHub Release
- it uploads per-platform Tauri artifacts and per-platform checksum manifests
- it is still experimental and is not a release-parity path
- it does not yet wire Tauri signing/notarization secrets or updater publication
- Tauri-served shell assets now use a minimal CSP for the local splash/bootstrap surface only; the localhost-served Django UI is not presented here as a hardened release renderer
- the Windows claim is limited to a prepared, CI-built NSIS installer path plus a required manual Windows validation path
- the current Windows bundle config keeps Tauri's default `downloadBootstrapper` WebView2 installer behavior rather than switching to `offlineInstaller`

Positron is explicitly out of that release lane as well:

- there is no dedicated Positron GitHub packaging workflow
- there is no Positron checksum-artifact lane
- local Positron bundles are for experiment validation, not release parity
- local macOS packaging currently depends on Briefcase ad-hoc signing
- Positron is not a release-parity path in this slice
- Windows packaged proof for Positron is still deferred

Current output artifacts:

- macOS: DMG (`desktop-django-starter-macos-<version>-<arch>.dmg`) plus an Electron updater ZIP artifact
- Windows: NSIS installer (`desktop-django-starter-windows-<version>-<arch>.exe`)
- Linux: AppImage (`desktop-django-starter-linux-<version>-<arch>.AppImage`)

Current checksum artifacts:

- macOS: `desktop-django-starter-macos-sha256.txt`, containing SHA-256 lines for the DMG, updater ZIP, updater metadata, and blockmap upload set
- Windows: `desktop-django-starter-windows-sha256.txt`, containing SHA-256 lines for the NSIS `.exe`, updater metadata, and blockmap upload set
- Linux: `desktop-django-starter-linux-sha256.txt`, containing SHA-256 lines for the AppImage, updater metadata, and blockmap upload set
- Tauri macOS: `desktop-django-starter-tauri-macos-sha256.txt`, containing SHA-256 lines for the DMG upload set
- Tauri Windows: `desktop-django-starter-tauri-windows-sha256.txt`, containing SHA-256 lines for the NSIS `.exe` upload set
- Tauri Linux: `desktop-django-starter-tauri-linux-sha256.txt`, containing SHA-256 lines for the AppImage upload set

Linux output remains available for parity, but Linux signing and Linux verification are not baseline requirements in this slice.

## Tauri Local Bundle Scope

The experimental Tauri shell under `shells/tauri/` can build a local host bundle through `just tauri-build`. The wrapper now defaults to one host-native experiment target: `dmg` on macOS, `nsis` on Windows, and `appimage` on Linux.

That path intentionally stays narrower than Electron:

- it reuses the shared `.stage/backend` payload as bundled resources
- it now pairs with `.github/workflows/tauri-packages.yml`, which builds hosted artifacts from the same shell tree
- it does not yet add signing automation, notarization scaffolding, or GitHub Release publication
- it now applies a minimal CSP to Tauri-served shell assets such as the local splash window, without claiming production-hardening for the Django pages served over localhost
- on Windows, the current scope is limited to generating the local NSIS installer path; install/run still needs a real live Windows machine test
- the current `tauri.conf.json` makes `downloadBootstrapper` explicit for WebView2 installation, matching Tauri's default Windows installer behavior
- the build wrapper now prints a Windows NSIS validation checklist, but that checklist is still preparation work rather than proof
- it should still be described as experimental artifact scope rather than release parity

## Tauri GitHub Workflow Scope

The dedicated Tauri workflow under `.github/workflows/tauri-packages.yml` follows the official Tauri GitHub pipeline shape closely:

- it uses `tauri-apps/tauri-action@v0`
- it sets `projectPath: shells/tauri` because the Tauri app is not at repo root
- it runs in build-only mode by omitting `tagName`, `releaseName`, and `releaseId`
- it stages `.stage/backend` before bundling so the hosted build uses the same packaged-runtime contract as local Tauri packaging
- it uploads explicit workflow artifacts and checksum manifests instead of publishing a GitHub Release

Current hosted bundle targets:

- macOS: DMG
- Windows: NSIS `.exe`
- Linux: AppImage

Current workflow boundaries:

- the workflow is artifact-only and does not publish releases
- it is intentionally narrower than the Electron lane's signing/notarization posture
- it should not be read as proof that Windows installer install/run behavior has been validated end to end
- the Windows NSIS artifacts currently rely on Tauri's default `downloadBootstrapper` WebView2 behavior, so they are not the repo's offline-ready installer story
- the Linux AppImage job currently sets `NO_STRIP=true` as a workflow-level workaround for the current upstream `linuxdeploy` strip failure on hosted Ubuntu runners
- the staged bundled Python runtime now prunes unused Tk/IDLE pieces before packaging so hosted AppImage builds do not have to resolve Tcl/Tk GUI dependencies the starter does not use

Windows NSIS validation checklist:

1. Run `just tauri-build` on a Windows machine and note the generated `.exe` path under `shells/tauri/src-tauri/target/release/bundle/nsis/`.
2. Install that NSIS artifact on the same or another clean Windows machine.
3. Launch the installed app and confirm the splash appears before the localhost Django UI loads.
4. Confirm startup does not depend on a system Python install and that the staged bundled runtime is the interpreter actually used.
5. Confirm app shutdown stops both Django and `db_worker`; for Electron on Windows the current implementation uses explicit forced process-tree termination via `taskkill /t /f`, not a graceful drain.
6. Confirm per-user writable state survives relaunches under the Windows app-data directory.

## Positron Local Bundle Scope

The experimental Positron shell under `shells/positron/` can build a local macOS app bundle through `just positron-build` and package a local DMG through `just positron-package-dmg`.

That path intentionally stays narrower than Electron:

- it uses Briefcase rather than the shared staged-backend subprocess contract
- it does not participate in `.github/workflows/desktop-packages.yml`
- it does not add checksum uploads, signing automation, or notarization scaffolding
- `just positron-package-dmg` currently relies on Briefcase ad-hoc signing, so the resulting app is suitable only for the machine that built it
- splashscreen parity is intentionally not required on macOS for this shell
- it is not a release-parity path in this slice
- it should be described as local-only experiment scope until a dedicated release lane exists

## macOS Signing and Notarization Inputs

The Electron builder config now enables hardened runtime and points at explicit entitlements files under `shells/electron/signing/`.

macOS code-signing inputs:

- `CSC_LINK` or `CSC_NAME`
- `CSC_KEY_PASSWORD` when the certificate export requires one

Recommended macOS notarization inputs:

- `APPLE_API_KEY`
- `APPLE_API_KEY_ID`
- `APPLE_API_ISSUER`

For local packaging, `APPLE_API_KEY` should be the filesystem path to the App Store Connect `.p8` key file.

In GitHub Actions, the `APPLE_API_KEY` secret should contain the raw `.p8` contents. The workflow writes that secret to a temporary file and then exports `APPLE_API_KEY` as the path that `electron-builder` expects.

Alternative notarization credential sets are also supported by the current config when a team prefers them:

- `APPLE_ID`, `APPLE_APP_SPECIFIC_PASSWORD`, and `APPLE_TEAM_ID`
- `APPLE_KEYCHAIN_PROFILE`, optionally with `APPLE_KEYCHAIN`

If none of those complete credential sets are present, macOS notarization stays off and the build remains usable for local teaching or internal dry runs.

## Windows Signing Inputs

Windows signing is intentionally optional in this starter.

Baseline certificate inputs:

- `WIN_CSC_LINK`
- `WIN_CSC_KEY_PASSWORD`

Optional metadata or certificate-selection inputs that the starter now passes through when present:

- `WINDOWS_SIGNING_PUBLISHER`
- `WIN_SIGN_CERT_SUBJECT_NAME`
- `WIN_SIGN_CERT_SHA1`
- `WIN_SIGN_TIMESTAMP_URL`
- `WIN_SIGN_TIMESTAMP_RFC3161_URL`

This is enough for a typical starter-level secret-driven signing path without committing the repo to a specific EV-token workflow, self-hosted runner setup, or enterprise release pipeline.

## Checksum Files and Minimal Release Promotion

The Electron packaging workflow now uploads two artifact groups per platform:

- the installer plus updater artifact upload (`desktop-django-starter-macos`, `desktop-django-starter-windows`, or `desktop-django-starter-linux`)
- the matching checksum upload (`desktop-django-starter-macos-checksums`, `desktop-django-starter-windows-checksums`, or `desktop-django-starter-linux-checksums`)

The Electron artifact upload includes the primary installer plus the updater metadata files generated by `electron-builder`:

- macOS: the DMG, updater ZIP, `latest-mac.yml`, and blockmap files
- Windows: the NSIS `.exe`, `latest.yml`, and blockmap files
- Linux: the AppImage, `latest-linux.yml`, and blockmap files

The Tauri workflow uses the same checksum pattern:

- `desktop-django-starter-tauri-macos` plus `desktop-django-starter-tauri-macos-checksums`
- `desktop-django-starter-tauri-windows` plus `desktop-django-starter-tauri-windows-checksums`
- `desktop-django-starter-tauri-linux` plus `desktop-django-starter-tauri-linux-checksums`

Each checksum file is a plain-text SHA-256 manifest with one line per packaged installer, updater artifact, or metadata file:

```text
<sha256>  <artifact filename>
```

That format is intentional: it is easy to move through email, ticketing systems, internal package portals, or offline media without introducing starter-specific tooling.

For connected manual promotion, the minimal operator flow is:

1. download the installer artifact and the matching `*-sha256.txt` artifact from the successful GitHub Actions run
2. verify the downloaded installer against the checksum file before publishing it onward
3. promote both files together into the next release channel, such as a GitHub Release draft, internal package portal, or shared download location
4. tell users or administrators to install from that promoted location

Simple verification commands:

- macOS: `shasum -a 256 desktop-django-starter-macos-<version>-<arch>.dmg`
- Windows PowerShell: `Get-FileHash .\desktop-django-starter-windows-<version>-<arch>.exe -Algorithm SHA256`

Compare the resulting digest with the line in the matching `*-sha256.txt` file. Manual promotion remains available even when the optional Electron GitHub Release publication path is not used.

## Connected Release and Update Story

Electron now includes a minimal connected updater path.

Electron packages use `electron-updater` and an `electron-builder` publish config. By default, the GitHub update feed is resolved from the build context: `DESKTOP_DJANGO_UPDATE_GITHUB_OWNER` plus `DESKTOP_DJANGO_UPDATE_GITHUB_REPO` override everything, otherwise the builder uses `GITHUB_REPOSITORY` in GitHub Actions, then falls back to the local `origin` Git remote. `DESKTOP_DJANGO_UPDATE_URL` remains available for a generic HTTPS feed.

The packaged Electron app exposes the user action as `Help > Check for Updates...`. Update checks stay in the Electron main process; no Django localhost endpoint and no broader preload bridge is added. The app prompts before downloading an available update, prompts again before restart/install, and stops the supervised Django plus `db_worker` processes before handing off to `autoUpdater.quitAndInstall()`.

The `.github/workflows/desktop-packages.yml` workflow always uploads updater metadata with the normal artifacts. When manually triggered with `publish_release=true`, it also runs `electron-builder --publish always` so the artifacts and `latest*.yml` metadata can be published to a draft GitHub Release. When `publish_release=false`, the workflow remains an artifact-only packaging run.

Important GitHub Releases constraint:

- Electron updater checks only see published GitHub releases. A draft release is useful for staging or review, but `Help > Check for Updates...` will not discover it until the release is published.

For connected Electron auto-update validation:

1. build a signed/notarized macOS artifact set and a signed Windows NSIS artifact set from GitHub Actions
2. trigger the workflow with `publish_release=true`, then publish the resulting GitHub Release so the updater metadata is visible to clients, or publish the same artifact set to the configured generic feed
3. install an older packaged app on the target platform
4. use `Help > Check for Updates...` to confirm the app detects, downloads, and restarts into the newer version
5. confirm the SQLite app-data directory and `app.sqlite3` survive the update

That validation is required before strengthening the release-readiness claim beyond "minimal connected updater path."

Connected manual installation is still supported:

1. build the installer in GitHub Actions or locally on the target platform
2. verify the installer against the matching workflow checksum file
3. promote the resulting DMG or `.exe` plus its `*-sha256.txt` file into your normal release channel
4. have the user or administrator download, verify, and run the newer installer manually

## Air-Gapped and Manual Installs

For air-gapped or tightly controlled environments, the update model is still manual:

- transfer the installer artifact and its matching `*-sha256.txt` file through the approved offline channel
- verify version and integrity before installation
- run the installer on the destination machine

The artifact to transfer is the same installer a connected user would install:

- macOS: the DMG
- Windows: the NSIS `.exe`

The checksum file should travel with that installer:

- macOS: `desktop-django-starter-macos-sha256.txt`
- Windows: `desktop-django-starter-windows-sha256.txt`

Suggested offline/manual flow:

1. copy the installer and checksum file from the successful packaging run onto the approved transfer media
2. move both files through the offline approval path
3. on the receiving side, run the same checksum command used for connected promotion and compare it to the transferred checksum file
4. install only after the digest matches and the version is the one you intend to promote

The starter does not build a separate offline-update mechanism or background service. Manual installer replacement remains the air-gapped baseline by design.

Windows-specific note:

- the starter currently outputs an NSIS installer, not an MSI
- that keeps the example minimal, but teams with stricter enterprise deployment needs should expect additional follow-on work

## What Survives Reinstall or Update

Packaged mode keeps writable state outside the app bundle.

Electron sets `DESKTOP_DJANGO_APP_DATA_DIR` from `app.getPath("userData")`, and packaged Django settings store the SQLite database there as `app.sqlite3`.

The packaged SQLite config is intentionally stronger than the repo-default development database setup: it keeps the single writable app-data database file, sets `transaction_mode=IMMEDIATE`, raises the timeout to 20 seconds, and initializes SQLite with `PRAGMA journal_mode=WAL;`, `PRAGMA synchronous=NORMAL;`, plus modest cache and mmap settings that fit a small teaching starter.

That means a normal reinstall or manual update should replace the installed application files while leaving user data in place, including:

- the SQLite database at `app.sqlite3`
- future writable files placed under the same per-user app-data directory

Local state is only lost if the user or administrator explicitly removes the app-data directory, or if a future installer is configured to wipe that directory.

## Production Gaps

This slice is intentionally incomplete in a few areas:

- no Tauri or Positron auto-update feed or release manifest
- no always-on signed-release publication workflow; Electron GitHub Release publication is an explicit manual workflow-dispatch option
- Electron updater readiness still needs real signed/notarized macOS and Windows NSIS update dry runs before being called production-ready
- Electron now adds a per-session shell-to-Django auth token for the localhost request channel through exact-origin header injection, but this is still a starter-level baseline rather than a full production localhost-hardening story
- Tauri and Positron now add comparable per-session shell-to-Django request authentication through a Django bootstrap URL that sets an HttpOnly same-origin cookie, because their current public web view APIs do not expose Electron's external-localhost per-request header injection hook
- Electron on Windows currently relies on explicit forced child-process tree termination via `taskkill /t /f`, which is acceptable for this starter slice but is not equivalent to graceful drain or broader production orphan-control work
- no Linux signing baseline and no Linux verification expectation for this slice
- no opinionated Windows EV-token or self-hosted-runner guidance
- no release promotion workflow beyond uploading GitHub Actions artifacts and their checksum manifests
