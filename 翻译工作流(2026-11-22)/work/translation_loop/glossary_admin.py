#!/usr/bin/env python3
"""Validate, publish, diff and impact-scan versioned glossary snapshots.

This tool never translates. `publish` is an explicit admin operation; batch
workers must be pinned to immutable snapshots and never call this themselves.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import translation_loop as tl

GLOSSARY_DIR = _THIS_DIR / "glossary"
CURRENT = GLOSSARY_DIR / "current.json"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with open(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        Path(tmp).replace(path)
    except Exception:
        try:
            Path(tmp).unlink(missing_ok=True)
        except Exception:
            pass
        raise


def validate_snapshot(unit: str, data: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return [f"{unit}: snapshot is not an object"]
    if not data.get("version"):
        errors.append(f"{unit}: missing version")
    if unit == "terms":
        seen_ids = set()
        seen_ja = set()
        for i, entry in enumerate(data.get("entries") or []):
            if not isinstance(entry, dict):
                errors.append(f"terms[{i}]: not an object")
                continue
            tid = str(entry.get("id") or "")
            if not tid:
                errors.append(f"terms[{i}]: missing id")
            elif tid in seen_ids:
                errors.append(f"terms[{i}]: duplicate id {tid}")
            seen_ids.add(tid)
            forms = [str(x) for x in entry.get("ja") or [] if str(x)]
            if not forms:
                errors.append(f"terms[{i}]: missing ja forms")
            for form in forms:
                if form in seen_ja:
                    errors.append(f"terms[{i}]: duplicate ja form {form!r}")
                seen_ja.add(form)
            zh = entry.get("zh") or {}
            if not isinstance(zh, dict) or not str(zh.get("default") or ""):
                errors.append(f"terms[{i}]: missing zh.default")
    elif unit == "characters":
        seen_ja = set()
        for i, row in enumerate(data.get("characters") or []):
            if not isinstance(row, dict):
                errors.append(f"characters[{i}]: not an object")
                continue
            ja = str(row.get("ja") or "")
            zh = str(row.get("zh") or "")
            if not ja or not zh:
                errors.append(f"characters[{i}]: missing ja/zh")
            if ja in seen_ja:
                errors.append(f"characters[{i}]: duplicate ja {ja}")
            seen_ja.add(ja)
        style = data.get("address_forms_default") or {}
        if not isinstance(style, dict):
            errors.append("characters: address_forms_default must be an object")
    elif unit == "style":
        quote_policy = str((data.get("quotes") or {}).get("speaker_outer") or "")
        if quote_policy not in {"preserve_source_outer", "strip_outer", "convert_cn"}:
            errors.append(f"style: unsupported speaker_outer policy {quote_policy!r}")
        if data.get("newline") != "literal_backslash_n":
            errors.append("style: newline must be literal_backslash_n")
    else:
        errors.append(f"unknown unit {unit}")
    return errors


def current_paths() -> dict[str, Path]:
    current = read_json(CURRENT)
    return {key: (GLOSSARY_DIR / current[f"{key}_file"]).resolve() for key in ("terms", "characters", "style")}


def cmd_validate(_args) -> int:
    all_errors = []
    current = read_json(CURRENT)
    paths = current_paths()
    for unit, path in paths.items():
        if not path.is_file():
            all_errors.append(f"{unit}: missing {path}")
            continue
        expected = current.get(f"{unit}_sha256")
        actual = sha(path)
        if expected and expected != actual:
            all_errors.append(f"{unit}: hash mismatch expected={expected} actual={actual}")
        all_errors.extend(validate_snapshot(unit, read_json(path)))
    print(json.dumps({
        "ok": not all_errors,
        "current": current,
        "errors": all_errors,
    }, ensure_ascii=False, indent=2))
    return 0 if not all_errors else 1


def cmd_publish(args) -> int:
    files = {"terms": args.terms, "characters": args.characters, "style": args.style}
    data = {}
    errors = []
    for unit, path in files.items():
        if not path.is_file():
            errors.append(f"{unit}: missing {path}")
            continue
        value = read_json(path)
        errors.extend(validate_snapshot(unit, value))
        data[unit] = value
    if errors:
        raise SystemExit("cannot publish:\n- " + "\n- ".join(errors))
    version = args.version.strip()
    if not version:
        raise SystemExit("--version is required")
    dest = GLOSSARY_DIR / "versions"
    dest.mkdir(parents=True, exist_ok=True)
    targets = {unit: dest / f"{unit}-{version}.json" for unit in files}
    if any(p.exists() for p in targets.values()) and not args.force:
        raise SystemExit("version already exists; use --force only for an unpublished draft")
    # Validate duplicate / schema before copying.
    for unit, path in files.items():
        shutil.copy2(path, targets[unit])
    current = {
        **{f"{unit}_version": version for unit in files},
        **{f"{unit}_file": f"versions/{unit}-{version}.json" for unit in files},
        **{f"{unit}_sha256": sha(targets[unit]) for unit in files},
        "published_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }
    atomic_json(CURRENT, current)
    print(json.dumps({"published": version, "current": current, "files": {k: str(v) for k, v in targets.items()}}, ensure_ascii=False, indent=2))
    return 0


def term_index(data: dict) -> dict[str, dict]:
    return {str(x.get("id")): x for x in data.get("entries") or [] if isinstance(x, dict) and x.get("id")}


def cmd_diff(args) -> int:
    old = term_index(read_json(args.old))
    new = term_index(read_json(args.new))
    rows = []
    for tid in sorted(set(old) | set(new)):
        if tid not in old:
            rows.append({"id": tid, "kind": "added", "new": new[tid]})
        elif tid not in new:
            rows.append({"id": tid, "kind": "removed", "old": old[tid]})
        elif old[tid] != new[tid]:
            rows.append({"id": tid, "kind": "changed", "old": old[tid], "new": new[tid]})
    print(json.dumps({"changes": rows}, ensure_ascii=False, indent=2))
    return 0


def cmd_impact(args) -> int:
    old = read_json(args.old)
    new = read_json(args.new)
    old_idx = term_index(old)
    new_idx = term_index(new)
    affected_forms: set[str] = set()
    for tid in set(old_idx) | set(new_idx):
        if old_idx.get(tid) == new_idx.get(tid):
            continue
        for item in (old_idx.get(tid), new_idx.get(tid)):
            if isinstance(item, dict):
                affected_forms.update(str(x) for x in item.get("ja") or [] if str(x))
    if not affected_forms:
        print(json.dumps({"affected_forms": [], "hits": []}, ensure_ascii=False, indent=2))
        return 0
    hits = []
    for source in sorted(tl.SOURCE_ROOT.glob("c*.txt")):
        sid = source.stem
        if not tl.SCENE_ID_RE.fullmatch(sid):
            continue
        blocks = tl.split_source_blocks(source)
        for line_no, block in enumerate(blocks, 1):
            found = sorted(form for form in affected_forms if form in block)
            if found:
                hits.append({"scene_id": sid, "line": line_no, "forms": found})
    print(json.dumps({
        "affected_forms": sorted(affected_forms),
        "scene_count": len({h["scene_id"] for h in hits}),
        "hit_count": len(hits),
        "hits": hits,
    }, ensure_ascii=False, indent=2))
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p_validate = sub.add_parser("validate")
    p_validate.set_defaults(func=cmd_validate)

    p_publish = sub.add_parser("publish")
    p_publish.add_argument("--version", required=True)
    p_publish.add_argument("--terms", type=Path, required=True)
    p_publish.add_argument("--characters", type=Path, required=True)
    p_publish.add_argument("--style", type=Path, required=True)
    p_publish.add_argument("--force", action="store_true")
    p_publish.set_defaults(func=cmd_publish)

    p_diff = sub.add_parser("diff")
    p_diff.add_argument("--old", type=Path, required=True)
    p_diff.add_argument("--new", type=Path, required=True)
    p_diff.set_defaults(func=cmd_diff)

    p_impact = sub.add_parser("impact")
    p_impact.add_argument("--old", type=Path, required=True)
    p_impact.add_argument("--new", type=Path, required=True)
    p_impact.set_defaults(func=cmd_impact)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
