#!/usr/bin/env python3
"""Export final cXXXXXX.txt translations to upstream json_cn.zip format.

Layout expected by translation_loop.py:
  <project>/FlowerKnightGirl_原文/译文/cXXXXXX.txt
  <project>/work/translation_loop/...
"""
from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import translation_loop as tl  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="output json_cn.zip")
    parser.add_argument(
        "--game-scenes",
        type=Path,
        default=tl.DEFAULT_GAME_SCENES,
        help="viewer package.nw/scenes directory",
    )
    parser.add_argument("--translations", type=Path, default=tl.TRANS_DIR)
    args = parser.parse_args()

    files = sorted(p for p in args.translations.glob("c*.txt") if tl.SCENE_ID_RE.fullmatch(p.stem))
    if not files:
        print(f"no translation files under {args.translations}", file=sys.stderr)
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    entries_total = 0
    with zipfile.ZipFile(args.output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        zf.writestr("json_cn/", "")
        for path in files:
            sid = path.stem
            try:
                scene = tl.build_scene(sid, game_scenes=args.game_scenes)
                lines = path.read_text(encoding="utf-8").splitlines()
                if len(lines) != scene.total_lines:
                    errors.append(f"{sid}: lines={len(lines)} expected={scene.total_lines}")
                    continue
                entries = []
                for i, (unit, line) in enumerate(zip(scene.units, lines), 1):
                    if unit.action == "preserve":
                        entries.append({"message": ""})
                        continue
                    if unit.speaker_zh:
                        match = tl.SPEAKER_RE.match(line)
                        if not match:
                            errors.append(f"{sid}:{i}: speaker prefix missing")
                            break
                        entries.append({"name": match.group(1).strip(), "message": match.group(2)})
                    else:
                        entries.append({"message": line})
                else:
                    data = json.dumps(entries, ensure_ascii=False, indent=2) + "\n"
                    zf.writestr(f"json_cn/{sid}_script.json", data)
                    entries_total += len(entries)
                    continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{sid}: {exc}")
    print(f"wrote {args.output} ({args.output.stat().st_size} bytes)")
    print(f"scene files: {len(files)}; entries: {entries_total}; errors: {len(errors)}")
    for error in errors[:30]:
        print(f"  {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
