#!/usr/bin/env bash
set -euo pipefail

if (( $# != 1 )); then
  echo "usage: $0 TARGET_REPO" >&2
  exit 2
fi

target_root_input="$1"
starter_root="$(cd "$(dirname "$0")/../../.." && pwd)"

if [[ ! -d "$target_root_input" ]]; then
  echo "error: target repo not found: $target_root_input" >&2
  exit 1
fi

target_root="$(cd "$target_root_input" && pwd)"

if ! git -C "$target_root" rev-parse --show-toplevel >/dev/null 2>&1; then
  echo "error: target is not a git worktree: $target_root" >&2
  exit 1
fi

if [[ -n "$(git -C "$target_root" status --short)" ]]; then
  echo "error: target repo is dirty; reset or clean it before scaffolding" >&2
  exit 1
fi

target_electron="$target_root/electron"
mkdir -p \
  "$target_electron/assets/icons" \
  "$target_electron/scripts" \
  "$target_electron/signing"

cp "$starter_root/shells/electron/main.js" "$target_electron/main.js"
cp "$starter_root/shells/electron/preload.cjs" "$target_electron/preload.cjs"
cp "$starter_root/shells/electron/package.json" "$target_electron/package.json"
cp "$starter_root/shells/electron/electron-builder.config.cjs" "$target_electron/electron-builder.config.cjs"
cp "$starter_root/shells/electron/assets/icons/app-icon.icns" "$target_electron/assets/icons/app-icon.icns"
cp "$starter_root/shells/electron/assets/icons/app-icon.png" "$target_electron/assets/icons/app-icon.png"
cp "$starter_root/shells/electron/signing/"* "$target_electron/signing/"
cp "$starter_root/shells/electron/scripts/"*.cjs "$target_electron/scripts/"

# Wrapped targets should use the full helper implementations, not the starter's
# repo-relative proxy wrappers.
cp "$starter_root/scripts/bundled-python.cjs" "$target_electron/scripts/bundled-python.cjs"
cp "$starter_root/scripts/materialize-symlinks.cjs" "$target_electron/scripts/materialize-symlinks.cjs"
cp "$starter_root/scripts/stage-backend.cjs" "$target_electron/scripts/stage-backend.cjs"
cp "$starter_root/scripts/prune-bundled-python-runtime.cjs" "$target_electron/scripts/prune-bundled-python-runtime.cjs"

node "$starter_root/skills/wrap-existing-django-in-electron-staged/scripts/prepare-electron-scaffold.cjs" \
  "$target_root"
node "$starter_root/skills/wrap-existing-django-in-electron-staged/scripts/prepare-django-desktop-scaffold.cjs" \
  "$target_root"

echo "Scaffolded Electron baseline into $target_electron"
echo "Scaffolded deterministic Django desktop baseline for Stage 3"
echo "Next step: launch Stage 2 with prompt-stage-2-electron.md"
