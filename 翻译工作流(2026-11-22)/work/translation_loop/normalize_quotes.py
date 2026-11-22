#!/usr/bin/env python3
"""Normalize outer dialogue quotes in existing translation files.

Default policy comes from the versioned style snapshot and is
`preserve_source_outer`: speaker lines whose source text is wrapped in 「」 keep
one outer pair; speaker lines whose source is not wrapped lose any extra pair.

This is a rendering policy, not a retranslation. Narration is untouched.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import glossary_runtime as gr
import translation_loop as tl


def split_output_line(text: str):
    match = tl.SPEAKER_RE.match(text)
    if not match:
        return "", text
    prefix = text[: match.start(2)]
    return prefix, match.group(2)


def normalize_file(path: Path, scene, style: dict):
    original = path.read_text(encoding="utf-8").splitlines()
    units = scene.units
    out: list[str] = []
    changes = []
    for idx, line in enumerate(original):
        if idx >= len(units):
            out.append(line)
            continue
        unit = units[idx]
        if unit.action != "translate" or not unit.speaker_zh:
            out.append(line)
            continue
        prefix, body = split_output_line(line)
        if not prefix:
            out.append(line)
            changes.append({"line": idx + 1, "kind": "missing_speaker_prefix", "before": line})
            continue
        normalized = gr.apply_speaker_quote_policy(body, unit.source_text, style)
        new_line = prefix + normalized
        out.append(new_line)
        if new_line != line:
            changes.append({"line": idx + 1, "kind": "quote", "before": line, "after": new_line})
    return "\n".join(out) + ("\n" if original else ""), changes


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-dir", type=Path, default=Path("FlowerKnightGirl_原文/译文"))
    parser.add_argument("--scene", action="append", default=[], help="scene id to normalize; repeatable; default all translation files")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--backup-dir", type=Path, default=Path("work/backups"))
    args = parser.parse_args(argv)
    style = gr.load_style()
    scenes = args.scene or sorted(
        p.stem for p in args.translation_dir.glob("c*.txt") if tl.SCENE_ID_RE.fullmatch(p.stem)
    )
    if not scenes:
        raise SystemExit("no translation files found")
    timestamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    report = {"policy": ((style.get("quotes") or {}).get("speaker_outer") or ""), "files": []}
    for scene_id in scenes:
        path = args.translation_dir / f"{scene_id}.txt"
        if not path.is_file():
            raise SystemExit(f"translation file not found: {path}")
        scene = tl.build_scene(scene_id)
        normalized, changes = normalize_file(path, scene, style)
        report["files"].append({"scene_id": scene_id, "path": str(path), "changes": changes})
        if not args.dry_run and changes:
            args.backup_dir.mkdir(parents=True, exist_ok=True)
            backup = args.backup_dir / f"{scene_id}.txt.before-quote-normalize-{timestamp}"
            shutil.copy2(path, backup)
            path.write_text(normalized, encoding="utf-8")
            report["files"][-1]["backup"] = str(backup)
    total = sum(len(x["changes"]) for x in report["files"])
    report["total_changes"] = total
    import json
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
