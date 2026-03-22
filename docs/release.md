# Release and Update Guide

This starter now includes the packaging scaffolding needed to make signing, notarization, and manual updates explicit without turning the repository into a full production release system.

## Packaging Workflow

Two packaging paths are intentionally supported:

- local packaging with `just package-dist` or `just package-dist-dir`
- GitHub Actions packaging with `.github/workflows/desktop-packages.yml`

Local packaging remains usable when no release credentials are configured. In that case, the build should still complete, but the resulting installer is expected to be unsigned and, on macOS, not notarized.

The GitHub Actions workflow uses the same `electron-builder` config and only turns on signing/notarization when the relevant secrets are present. This keeps the starter teachable while still making the public-distribution requirements concrete.

Current output artifacts:

- macOS: DMG (`desktop-django-starter-macos-<version>-<arch>.dmg`)
- Windows: NSIS installer (`desktop-django-starter-windows-<version>-<arch>.exe`)
- Linux: AppImage (`desktop-django-starter-linux-<version>-<arch>.AppImage`)

Linux output remains available for parity, but Linux signing and Linux verification are not baseline requirements in this slice.

## macOS Signing and Notarization Inputs

The Electron builder config now enables hardened runtime and points at explicit entitlements files under `electron/signing/`.

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

## Connected Release and Update Story

This repository still does not include auto-update infrastructure.

For connected environments, the expected v1 flow is manual installation of a newer signed artifact:

1. build the installer in GitHub Actions or locally on the target platform
2. promote the resulting DMG or `.exe` into your normal release channel
3. have the user or administrator download and run the newer installer manually

The current repo only automates the build-and-artifact step. Promoting those artifacts to GitHub Releases, an internal package portal, or another distribution system is still follow-on work.

## Air-Gapped and Manual Installs

For air-gapped or tightly controlled environments, the update model is still manual:

- transfer the installer artifact through the approved offline channel
- verify version and integrity before installation
- run the installer on the destination machine

The artifact to transfer is the same installer a connected user would install:

- macOS: the DMG
- Windows: the NSIS `.exe`

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
- no checksum publication or signed-release publication automation
- no Linux signing baseline and no Linux verification expectation for this slice
- no opinionated Windows EV-token or self-hosted-runner guidance
- no release promotion workflow beyond uploading GitHub Actions artifacts
