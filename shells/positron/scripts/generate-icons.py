from __future__ import annotations

import shutil
import subprocess
import sys
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

    iconset_dir = output_path.parent / "app-icon.iconset"
    shutil.rmtree(iconset_dir, ignore_errors=True)
    iconset_dir.mkdir(parents=True, exist_ok=True)

    for size in [16, 32, 128, 256, 512]:
        render_png(svg_path, size, iconset_dir / f"icon_{size}x{size}.png")
        render_png(svg_path, size * 2, iconset_dir / f"icon_{size}x{size}@2x.png")

    run("iconutil", "-c", "icns", str(iconset_dir), "-o", str(output_path))
    shutil.rmtree(iconset_dir, ignore_errors=True)


def main() -> int:
    shell_root = Path(__file__).resolve().parents[1]
    repo_root = shell_root.parents[1]
    brand_icon = repo_root / "assets" / "brand" / "flying-stable-app-icon.svg"
    resources_dir = shell_root / "resources"
    png_path = resources_dir / "app-icon.png"
    icns_path = resources_dir / "app-icon.icns"

    resources_dir.mkdir(parents=True, exist_ok=True)
    require_command("rsvg-convert", "Install librsvg so `rsvg-convert` is available on PATH.")
    render_png(brand_icon, 512, png_path)
    if sys.platform == "darwin":
        require_command("iconutil", "iconutil ships with macOS command-line tools.")
        build_icns(brand_icon, icns_path)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
