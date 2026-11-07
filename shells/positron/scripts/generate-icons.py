from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def require_command(command: str, install_hint: str) -> None:
    if shutil.which(command):
        return
    raise SystemExit(f"{command} is required to regenerate Positron app icons. {install_hint}")


def run(command: str, *args: str) -> None:
    subprocess.run([command, *args], check=True)


def render_png(svg_path: Path, size: int, output_path: Path) -> None:
    run(
        "rsvg-convert",
        "--width",
        str(size),
        "--height",
        str(size),
        str(svg_path),
        "--output",
        str(output_path),
    )


def build_icns(svg_path: Path, output_path: Path) -> None:
    if sys.platform != "darwin":
        return

    with tempfile.TemporaryDirectory(
        prefix="app-icon-", suffix=".iconset", dir=output_path.parent
    ) as directory:
        iconset_dir = Path(directory)
        for size in [16, 32, 128, 256, 512]:
            for scale, suffix in [(1, ""), (2, "@2x")]:
                png = iconset_dir / f"icon_{size}x{size}{suffix}.png"
                render_png(svg_path, size * scale, png)
                require_output(png)
        run("iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path))
        require_output(output_path)


def require_output(path: Path) -> None:
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Icon renderer produced no nonempty file: {path}")


class IconRollbackError(RuntimeError):
    """Rollback is incomplete; retain the named recovery directory."""


def publish_icons(staged: Path, resources: Path, names: list[str], previous: Path) -> None:
    """Publish a rendered set with rollback for ordinary filesystem failures."""
    previous.mkdir()
    for name in names:
        current = resources / name
        if current.exists():
            shutil.copy2(current, previous / name)
    published = []
    try:
        for name in names:
            (staged / name).replace(resources / name)
            published.append(name)
    except BaseException:
        failures = []
        for name in reversed(published):
            try:
                backup = previous / name
                if backup.exists():
                    backup.replace(resources / name)
                else:
                    (resources / name).unlink()
            except BaseException as exc:
                failures.append(exc)
        if failures:
            raise IconRollbackError(
                f"Icon rollback failed; recovery directory retained at {previous}"
            ) from failures[0]
        raise


def main() -> int:
    shell_root = Path(__file__).resolve().parents[1]
    repo_root = shell_root.parents[1]
    brand_icon = repo_root / "assets" / "brand" / "flying-stable-app-icon.svg"
    resources_dir = shell_root / "resources"
    png_path = resources_dir / "app-icon.png"
    icns_path = resources_dir / "app-icon.icns"

    require_command("rsvg-convert", "Install librsvg so `rsvg-convert` is available on PATH.")
    if sys.platform == "darwin":
        require_command("iconutil", "iconutil ships with macOS command-line tools.")

    resources_dir.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix=".app-icons-", dir=resources_dir))
    staged = work / "staged"
    previous = work / "previous"
    failure: BaseException | None = None
    try:
        staged.mkdir()
        render_png(brand_icon, 512, staged / png_path.name)
        require_output(staged / png_path.name)
        names = [png_path.name]
        if sys.platform == "darwin":
            build_icns(brand_icon, staged / icns_path.name)
            names.append(icns_path.name)
        publish_icons(staged, resources_dir, names, previous)
    except BaseException as exc:
        failure = exc
        raise
    finally:
        try:
            if isinstance(failure, IconRollbackError):
                shutil.rmtree(staged)
            else:
                shutil.rmtree(work)
        except OSError as exc:
            if failure is None:
                raise
            print(f"Icon cleanup incomplete at {work}: {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
