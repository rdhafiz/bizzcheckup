"""Download the Tailwind CSS standalone CLI for this computer into .bin/.

The standalone CLI is a single program, so we don't need Node.js or npm.

Usage:
    python scripts/get_tailwind.py
Then build the CSS:
    .bin/tailwindcss -i frontend/tailwind.css -o static/css/app.css --minify
"""

import platform
import stat
import sys
import urllib.request
from pathlib import Path

TAILWIND_VERSION = "v4.3.3"
BASE_URL = f"https://github.com/tailwindlabs/tailwindcss/releases/download/{TAILWIND_VERSION}"

ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = ROOT / ".bin"


def asset_name() -> str:
    """Pick the right download for this operating system and processor."""
    system = platform.system().lower()  # "windows", "linux", "darwin"
    machine = platform.machine().lower()  # "amd64", "x86_64", "arm64", "aarch64"
    arch = "arm64" if machine in ("arm64", "aarch64") else "x64"

    if system == "windows":
        return f"tailwindcss-windows-{arch}.exe"
    if system == "darwin":
        return f"tailwindcss-macos-{arch}"
    if system == "linux":
        return f"tailwindcss-linux-{arch}"
    sys.exit(f"Unsupported system: {system}")


def main() -> None:
    name = asset_name()
    suffix = ".exe" if name.endswith(".exe") else ""
    target = BIN_DIR / f"tailwindcss{suffix}"

    BIN_DIR.mkdir(exist_ok=True)
    print(f"Downloading {name} ({TAILWIND_VERSION}) ...")
    urllib.request.urlretrieve(f"{BASE_URL}/{name}", target)

    # Linux/macOS need the "executable" permission bit; Windows ignores it.
    target.chmod(target.stat().st_mode | stat.S_IEXEC)
    print(f"Saved to {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
