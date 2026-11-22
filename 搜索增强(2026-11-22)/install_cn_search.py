#!/usr/bin/env python3
"""Install Chinese/series search support into a Flower Knight Girl Viewer package.nw.

Tested with Flower Knight Girl Viewer 1.1 / package.nw data/scripts layout.
Only viewer script files and the HTML loader are touched. Game assets and
translation data are never modified.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import shutil
import sys
from pathlib import Path

FILE_MAP = {
    "cn-names.js": Path("data/scripts/data/cn-names.js"),
    "cn-search.js": Path("data/scripts/cn-search.js"),
    "search.js": Path("data/scripts/search.js"),
    "autocomplete.js": Path("data/scripts/autocomplete.js"),
}
HTML_NAME = "Flower knight girl Viewer.html"
META_TAG = '<script src="data/scripts/data/meta.js"></script>'
CN_SEARCH_TAG = '<script src="data/scripts/cn-search.js"></script>'


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def backup_file(package: Path, backup_root: Path, rel: Path) -> None:
    source = package / rel
    if not source.exists():
        return
    target = backup_root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def patch_html(package: Path) -> None:
    html_path = package / HTML_NAME
    if not html_path.is_file():
        fail(f"viewer HTML not found: {html_path}")
    text = html_path.read_text(encoding="utf-8")
    if CN_SEARCH_TAG not in text:
        if META_TAG not in text:
            fail("meta.js script tag not found in viewer HTML")
        text = text.replace(META_TAG, META_TAG + "\n    " + CN_SEARCH_TAG, 1)
    # Keeps the series-search affordance visible in the character field.
    text = text.replace(
        'placeholder="中文 / 日本語 / English"',
        'placeholder="中文 / 日本語 / English / 系列"',
        1,
    )
    html_path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install FKG Chinese/series search support into package.nw"
    )
    parser.add_argument(
        "package_nw",
        nargs="?",
        default="package.nw",
        help="path to the viewer's package.nw directory (default: ./package.nw)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="check paths and print actions without writing files",
    )
    args = parser.parse_args()

    package = Path(args.package_nw).expanduser().resolve()
    files_dir = Path(__file__).resolve().parent / "files"

    if not (package / "data/scripts").is_dir():
        fail(f"not a viewer package.nw (missing data/scripts): {package}")
    for name in FILE_MAP:
        if not (files_dir / name).is_file():
            fail(f"bundled file missing: {files_dir / name}")

    backup_root = package / (
        "cn-search-backup-" + _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    print(f"package: {package}")
    print(f"backup:  {backup_root}")
    print("files:")
    for rel in FILE_MAP.values():
        print(f"  {rel}")

    if args.dry_run:
        print("dry-run: no files written")
        return

    for rel in FILE_MAP.values():
        backup_file(package, backup_root, rel)
    # The HTML is backed up separately because it is patched in place.
    backup_file(package, backup_root, Path(HTML_NAME))

    for name, rel in FILE_MAP.items():
        target = package / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(files_dir / name, target)

    patch_html(package)
    print("installed. Restart the viewer to apply.")


if __name__ == "__main__":
    main()
