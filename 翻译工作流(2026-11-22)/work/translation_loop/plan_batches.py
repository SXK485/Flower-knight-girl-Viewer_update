#!/usr/bin/env python3
"""Deterministic, read-only batch planner for the translation loop.

This script only reads source files and existing translation filenames. It
writes a plan manifest; it never calls the translator or modifies译文 files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import glossary_runtime as gr
import translation_loop as tl

EDGE_FAMILIES = [
    "c130901",      # structural override
    "c131925",      # structural override on c131925_2
    "c144403",      # structural override
    "c147501",      # structural override on c147501_2
    "c162701",      # structural override
    "c135801",      # base/_2 speaker-set change
    "c150025",      # multi-character scene: アオ / シロ
    "c150051",      # multi-character scene: シロ / アオ
    "c163405",      # multi-character scene: ヒメカイウ / ミズバショウ
    "c163407",      # multi-character scene
    "c100841",      # ジニア / ヒャクニチソウ alias pair
    "c100843",      # pair with different character sets
    "c100845",      # ジニア / ヒャクニチソウ alias pair
]


def family_id(scene_id: str) -> str:
    return scene_id[:-2] if scene_id.endswith("_2") else scene_id


def discover():
    all_ids = sorted(
        p.stem for p in tl.SOURCE_ROOT.glob("c*.txt") if tl.SCENE_ID_RE.fullmatch(p.stem)
    )
    ids = set(all_ids)
    scene_data = {}
    for sid in all_ids:
        blocks = tl.split_source_blocks(tl.SOURCE_ROOT / f"{sid}.txt")
        chars = set()
        for block in blocks:
            speaker, _ = tl.parse_source_block(block)
            if speaker:
                chars.add(speaker)
        scene_data[sid] = {"chars": chars, "lines": len(blocks)}
    family_data = {}
    for b in sorted((s for s in all_ids if not s.endswith("_2")), key=lambda s: int(s[1:])):
        members = [b] + ([b + "_2"] if b + "_2" in ids else [])
        chars = set()
        lines = 0
        for sid in members:
            chars |= scene_data[sid]["chars"]
            lines += scene_data[sid]["lines"]
        family_data[b] = {"members": members, "chars": chars, "lines": lines}
    return all_ids, scene_data, family_data


def select_pilot(family_data, existing, target_files: int):
    selected: set[str] = set()

    def can_add(fid: str) -> bool:
        return fid in family_data and not any(m in existing for m in family_data[fid]["members"])

    def add(fid: str) -> None:
        if can_add(fid):
            selected.add(fid)

    # High-frequency characters first: they carry the strongest cross-scene
    # consistency risk and are the most useful pilot signal.
    by_char = defaultdict(list)
    for fid, info in family_data.items():
        for ch in info["chars"]:
            by_char[ch].append(fid)
    ranked_chars = sorted(by_char, key=lambda ch: (-len(by_char[ch]), ch))
    for ch in ranked_chars[:10]:
        for fid in sorted(by_char[ch], key=lambda s: int(s[1:])):
            add(fid)

    for fid in EDGE_FAMILIES:
        add(fid)

    def count_files(ids):
        return sum(len(family_data[fid]["members"]) for fid in ids)

    needed = target_files - count_files(selected)
    if needed < 0:
        raise SystemExit(f"curated seed already exceeds target: {-needed} extra files")

    remaining = [fid for fid in family_data if fid not in selected and can_add(fid)]
    pairs = [fid for fid in remaining if len(family_data[fid]["members"]) == 2]
    singles = [fid for fid in remaining if len(family_data[fid]["members"]) == 1]

    def spaced(items, n):
        if n <= 0:
            return []
        if n > len(items):
            raise SystemExit(f"not enough candidates: need {n}, have {len(items)}")
        if n == len(items):
            return list(items)
        if n == 1:
            return [items[len(items) // 2]]
        # deterministic spread over the ordered candidate list
        return [items[round(i * (len(items) - 1) / (n - 1))] for i in range(n)]

    if needed % 2:
        if not singles:
            raise SystemExit("need one single-file family to hit an odd target")
        picked = spaced(singles, 1)
        for fid in picked:
            add(fid)
        needed -= 1

    pair_need = needed // 2
    for fid in spaced(pairs, pair_need):
        add(fid)

    actual = count_files(selected)
    if actual != target_files:
        raise SystemExit(f"selection mismatch: expected {target_files}, got {actual}")
    return selected


def partition(family_data, selected, workers_count):
    # Union-find over characters so families sharing any character (including
    # multi-character scenes such as シロ/アオ/シロ　アオ) stay on one worker.
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for fid in selected:
        chars = sorted(family_data[fid]["chars"])
        for other in chars[1:]:
            union(chars[0], other)

    groups = defaultdict(list)
    for fid in selected:
        chars = sorted(family_data[fid]["chars"])
        gate = find(chars[0]) if chars else "<旁白>"
        groups[gate].append(fid)

    workers = [
        {"worker": f"w{i+1}", "family_ids": [], "files": 0, "lines": 0}
        for i in range(workers_count)
    ]
    # Largest character group first; assign to the currently lightest worker.
    for gate, fids in sorted(
        groups.items(),
        key=lambda kv: (-sum(family_data[f]["lines"] for f in kv[1]), kv[0]),
    ):
        target = min(workers, key=lambda w: (w["lines"], w["files"], w["worker"]))
        target["family_ids"].extend(fids)
        target["files"] += sum(len(family_data[f]["members"]) for f in fids)
        target["lines"] += sum(family_data[f]["lines"] for f in fids)

    for w in workers:
        w["family_ids"] = sorted(w["family_ids"], key=lambda s: int(s[1:]))
        w["files"] = sum(len(family_data[f]["members"]) for f in w["family_ids"])
        w["lines"] = sum(family_data[f]["lines"] for f in w["family_ids"])
        w["scenes"] = [m for f in w["family_ids"] for m in family_data[f]["members"]]
        w["characters"] = sorted({ch for f in w["family_ids"] for ch in family_data[f]["chars"]})
    return workers


def build_manifest(args, family_data, selected, workers):
    persona = Path("TRANSLATION-PERSONA.md")
    persona_sha = hashlib.sha256(persona.read_bytes()).hexdigest() if persona.is_file() else ""
    glossary_files = {}
    glossary_sha = {}
    for unit, env_var, field in (
        ("terms", "FKG_TERMS_FILE", "terms_file"),
        ("characters", "FKG_CHARACTERS_FILE", "characters_file"),
        ("style", "FKG_STYLE_FILE", "style_file"),
    ):
        path = gr.resolve_snapshot(env_var, field)
        if path is None or not path.is_file():
            raise SystemExit(f"glossary snapshot missing for {unit}: {path}")
        glossary_files[unit] = str(path)
        glossary_sha[unit] = hashlib.sha256(path.read_bytes()).hexdigest()
    return {
        "version": 1,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "assumptions": {
            "target_unit": "scene files",
            "families_are_atomic": True,
            "workers_are_concurrent": args.workers,
            "prompt_version": tl.PROMPT_VERSION,
        },
        "target_files": args.target_files,
        "selected_files": 0,
        "family_count": len(selected),
        "total_lines": sum(family_data[f]["lines"] for f in selected),
        "persona_sha256": persona_sha,
        "glossary": {
            "versions": gr.snapshot_versions(),
            "files": glossary_files,
            "sha256": glossary_sha,
        },
        "model": "deepseek-chat",
        "temperature": 0,
        "excluded_existing_files": sorted(args.existing_files),
        "families": {
            f: {
                "members": family_data[f]["members"],
                "full_members": family_data[f].get("full_members", family_data[f]["members"]),
                "characters": sorted(family_data[f]["chars"]),
                "lines": family_data[f]["lines"],
            }
            for f in sorted(selected, key=lambda s: int(s[1:]))
        },
        "workers": workers,
    }


def render_markdown(manifest):
    lines = [
        "# Pilot batch plan",
        "",
        f"- generated: {manifest['generated_at']}",
        f"- target scene files: {manifest['target_files']}",
        f"- family count: {manifest['family_count']}",
        f"- total source lines: {manifest['total_lines']}",
        f"- workers: {len(manifest['workers'])}",
        f"- model: {manifest['model']} (temperature {manifest['temperature']})",
        f"- prompt version: {manifest['assumptions']['prompt_version']}",
        f"- glossary versions: {manifest['glossary']['versions']}",
        f"- persona sha256: `{manifest['persona_sha256']}`",
        "",
        "## Worker batches",
        "",
        "| worker | files | families | lines | characters |",
        "|---|---:|---:|---:|---|",
    ]
    for w in manifest["workers"]:
        lines.append(
            f"| {w['worker']} | {w['files']} | {len(w['family_ids'])} | {w['lines']} | "
            + ", ".join(w["characters"])
            + " |"
        )
    lines += ["", "## Scene files by worker", ""]
    for w in manifest["workers"]:
        lines.append(f"### {w['worker']}")
        lines.append("")
        lines.append("```text")
        lines.extend(w["scenes"])
        lines.append("```")
        lines.append("")
    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--target-files", type=int, default=200)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--out-dir", type=Path, default=Path("work/translation_loop/batches/pilot-200"))
    parser.add_argument("--allow-existing", action="store_true")
    parser.add_argument("--all-remaining", action="store_true", help="select every family not already present in译文")
    args = parser.parse_args(argv)
    if args.workers < 1:
        raise SystemExit("--workers must be positive")
    all_ids, scene_data, family_data = discover()
    existing = set()
    if not args.allow_existing:
        existing = {p.stem for p in tl.TRANS_DIR.glob("c*.txt") if tl.SCENE_ID_RE.fullmatch(p.stem)}
    args.existing_files = existing
    if args.all_remaining:
        # Include missing members of a partially translated family too.  The
        # original family_data entry is left untouched for existing files; the
        # batch manifest describes only the members that still need work.
        effective = {}
        for fid, info in family_data.items():
            missing = [m for m in info["members"] if m not in existing]
            if not missing:
                continue
            chars: set[str] = set()
            lines = 0
            for member in missing:
                chars |= scene_data[member]["chars"]
                lines += scene_data[member]["lines"]
            effective[fid] = {
                "members": missing,
                "chars": chars,
                "lines": lines,
                "full_members": info["members"],
            }
        family_data = effective
        selected = set(family_data)
        args.target_files = sum(len(family_data[fid]["members"]) for fid in selected)
    else:
        selected = select_pilot(family_data, existing, args.target_files)
    workers = partition(family_data, selected, args.workers)
    manifest = build_manifest(args, family_data, selected, workers)
    # replace the placeholder selected_files calculation with the real count
    manifest["selected_files"] = sum(len(family_data[f]["members"]) for f in selected)
    if manifest["selected_files"] != args.target_files:
        raise SystemExit("internal error: selected file count mismatch")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (args.out_dir / "PLAN.md").write_text(render_markdown(manifest), encoding="utf-8")
    print(json.dumps({
        "out_dir": str(args.out_dir),
        "files": manifest["selected_files"],
        "families": manifest["family_count"],
        "lines": manifest["total_lines"],
        "workers": [
            {"worker": w["worker"], "files": w["files"], "families": len(w["family_ids"]), "lines": w["lines"]}
            for w in workers
        ],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
