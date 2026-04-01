# Release and Update Guide

This starter now includes the packaging scaffolding needed to make signing, notarization, and manual updates explicit without turning the repository into a full production release system.

## Packaging Workflow

Two packaging paths are intentionally supported:

- local packaging with `just package-dist` or `just package-dist-dir`
- GitHub Actions packaging with `.github/workflows/desktop-packages.yml`

The repo now also includes one narrower Tauri-only local packaging command:

- `just tauri-build` for a local host bundle, defaulting to a macOS DMG on macOS

The repo also includes one narrower Positron-only local packaging command:

- `just positron-package-dmg` for a local macOS DMG built with Briefcase ad-hoc signing

Local packaging remains usable when no release credentials are configured. In that case, the build should still complete, but the resulting installer is expected to be unsigned and, on macOS, not notarized.

The GitHub Actions workflow uses the same `electron-builder` config and only turns on signing/notarization when the relevant secrets are present. This keeps the starter teachable while still making the public-distribution requirements concrete.

Tauri is explicitly out of that release lane in this slice:

- there is no dedicated Tauri GitHub packaging workflow
- there is no Tauri checksum-artifact lane
- local Tauri bundles are for experiment validation, not release parity
- Windows packaged proof for Tauri is still deferred

Positron is explicitly out of that release lane as well:

- there is no dedicated Positron GitHub packaging workflow
- there is no Positron checksum-artifact lane
- local Positron bundles are for experiment validation, not release parity
- local macOS packaging currently depends on Briefcase ad-hoc signing
- Windows packaged proof for Positron is still deferred

Current output artifacts:

- macOS: DMG (`desktop-django-starter-macos-<version>-<arch>.dmg`)
- Windows: NSIS installer (`desktop-django-starter-windows-<version>-<arch>.exe`)
- Linux: AppImage (`desktop-django-starter-linux-<version>-<arch>.AppImage`)

Current checksum artifacts:

- macOS: `desktop-django-starter-macos-sha256.txt`, containing SHA-256 lines for the DMG upload set
- Windows: `desktop-django-starter-windows-sha256.txt`, containing SHA-256 lines for the NSIS `.exe` upload set
- Linux: `desktop-django-starter-linux-sha256.txt`, containing SHA-256 lines for the AppImage upload set

Linux output remains available for parity, but Linux signing and Linux verification are not baseline requirements in this slice.

## Tauri Local Bundle Scope

The experimental Tauri shell under `shells/tauri/` can build a local host bundle and, on macOS, a local DMG through `just tauri-build`.

That path intentionally stays narrower than Electron:

- it reuses the shared `.stage/backend` payload as bundled resources
- it does not participate in `.github/workflows/desktop-packages.yml`
- it does not add checksum uploads, signing automation, or notarization scaffolding
- it should be described as local-only experiment scope until a dedicated release lane exists

## Positron Local Bundle Scope

The experimental Positron shell under `shells/positron/` can build a local macOS app bundle through `just positron-build` and package a local DMG through `just positron-package-dmg`.

That path intentionally stays narrower than Electron:

- it uses Briefcase rather than the shared staged-backend subprocess contract
- it does not participate in `.github/workflows/desktop-packages.yml`
- it does not add checksum uploads, signing automation, or notarization scaffolding
- `just positron-package-dmg` currently relies on Briefcase ad-hoc signing, so the resulting app is suitable only for the machine that built it
- splashscreen parity is intentionally not required on macOS for this shell
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

The packaging workflow now stops at two explicit artifact uploads per platform:

- the installer artifact upload (`desktop-django-starter-macos`, `desktop-django-starter-windows`, or `desktop-django-starter-linux`)
- the matching checksum upload (`desktop-django-starter-macos-checksums`, `desktop-django-starter-windows-checksums`, or `desktop-django-starter-linux-checksums`)

Each checksum file is a plain-text SHA-256 manifest with one line per packaged installer file:

```text
<sha256>  <artifact filename>
```

That format is intentional: it is easy to move through email, ticketing systems, internal package portals, or offline media without introducing starter-specific tooling.

For connected promotion, the minimal operator flow is:

1. download the installer artifact and the matching `*-sha256.txt` artifact from the successful GitHub Actions run
2. verify the downloaded installer against the checksum file before publishing it onward
3. promote both files together into the next release channel, such as a GitHub Release draft, internal package portal, or shared download location
4. tell users or administrators to install from that promoted location

Simple verification commands:

- macOS: `shasum -a 256 desktop-django-starter-macos-<version>-<arch>.dmg`
- Windows PowerShell: `Get-FileHash .\desktop-django-starter-windows-<version>-<arch>.exe -Algorithm SHA256`

Compare the resulting digest with the line in the matching `*-sha256.txt` file. The repo does not automate release publication; the promotion step is still a human-admin action by design.

## Connected Release and Update Story

This repository still does not include auto-update infrastructure.

For connected environments, the expected v1 flow is manual installation of a newer signed artifact:

1. build the installer in GitHub Actions or locally on the target platform
2. verify the installer against the matching workflow checksum file
3. promote the resulting DMG or `.exe` plus its `*-sha256.txt` file into your normal release channel
4. have the user or administrator download, verify, and run the newer installer manually

The current repo only automates the build-and-artifact step. Promoting those artifacts to GitHub Releases, an internal package portal, or another distribution system is still follow-on work.

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

The starter does not currently build a separate offline-update mechanism, delta updater, or background service. Manual installer replacement is the baseline path by design.

Windows-specific note:

- the starter currently outputs an NSIS installer, not an MSI
- that keeps the example minimal, but teams with stricter enterprise deployment needs should expect additional follow-on work

## What Survives Reinstall or Update

Packaged mode keeps writable state outside the app bundle.

Electron sets `DESKTOP_DJANGO_APP_DATA_DIR` from `app.getPath("userData")`, and packaged Django settings store the SQLite database there as `app.sqlite3`.

That means a normal reinstall or manual update should replace the installed application files while leaving user data in place, including:

- the SQLite database at `app.sqlite3`
- future writable files placed under the same per-user app-data directory

Local state is only lost if the user or administrator explicitly removes the app-data directory, or if a future installer is configured to wipe that directory.

## Production Gaps

This slice is intentionally incomplete in a few areas:

- no auto-update feed or release manifest
- no GitHub Release publication automation, signed-release publication automation, or in-app promotion workflow
- no Linux signing baseline and no Linux verification expectation for this slice
- no opinionated Windows EV-token or self-hosted-runner guidance
- no release promotion workflow beyond uploading GitHub Actions artifacts and their checksum manifests
