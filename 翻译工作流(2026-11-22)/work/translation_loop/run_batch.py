#!/usr/bin/env python3
"""Run a planned translation batch with bounded concurrency.

Default behavior is a dry run.  This script never promotes drafts into
`译文/` and never calls `装回.sh`; each scene stays under its worker run-root.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import glossary_runtime as gr
import translation_loop as tl

ROOT = Path(__file__).resolve().parents[2]
LOOP = ROOT / "work" / "translation_loop" / "translation_loop.py"
PERSONA = ROOT / "TRANSLATION-PERSONA.md"
DEFAULT_MANIFEST = ROOT / "work" / "translation_loop" / "batches" / "pilot-200" / "manifest.json"
DEFAULT_RUN_ROOT = ROOT / "work" / "translation_loop" / "results" / "pilot-200"


def now_iso() -> str:
    from datetime import datetime
    return datetime.now().astimezone().isoformat(timespec="seconds")


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value) -> None:
    import tempfile
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass
        raise


def tail_context(draft: Path, max_chars: int = 700) -> str:
    if not draft.is_file():
        return ""
    lines = [line.strip() for line in draft.read_text(encoding="utf-8").splitlines() if line.strip()]
    text = " / ".join(lines[-2:])
    return text[-max_chars:]


def status_for_scene(run_root: Path, scene_id: str) -> dict:
    p = run_root / scene_id / "state.json"
    return load_json(p) if p.is_file() else {}


def review_ok(run_root: Path, scene_id: str) -> bool:
    p = run_root / scene_id / "review.json"
    if not p.is_file():
        return False
    report = load_json(p)
    return bool(report.get("complete")) and not report.get("issues")


def run_cmd(args: list[str], env: dict[str, str], timeout: int, cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def build_summary(scene_id: str, family: dict, family_tails: dict[str, str], char_tails: dict[str, str]) -> str:
    parts: list[str] = []
    if scene_id.endswith("_2"):
        base_id = scene_id[:-2]
        base_tail = family_tails.get(base_id, "")
        if base_tail:
            parts.append(f"同家族本体 `{base_id}` 已译末尾（只参考称呼、语气和露骨度）：{base_tail}")
    for ch in family.get("characters", []):
        tail = char_tails.get(ch, "")
        if tail and tail not in " ".join(parts):
            parts.append(f"角色 `{ch}` 上一已译场景末尾（只参考称呼、语气和露骨度）：{tail}")
    text = "\n".join(parts).strip()
    return text[-1600:]


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--concurrency", type=int, default=6, help="number of concurrently running worker batches (1-32)")
    parser.add_argument("--dry-run", action="store_true", help="plan commands without calling the translator")
    parser.add_argument("--reset", action="store_true", help="reset any existing scene state")
    parser.add_argument("--stop-after", type=int, default=0, help="debug: process at most N scenes per worker")
    parser.add_argument("--scene-timeout", type=int, default=3600, help="per-scene timeout seconds")
    parser.add_argument(
        "--glossary-mode",
        choices=("frozen", "rolling"),
        default="frozen",
        help="frozen pins the manifest snapshots; rolling switches at family boundaries",
    )
    args = parser.parse_args(argv)

    if not 1 <= args.concurrency <= 32:
        raise SystemExit("--concurrency must be between 1 and 32")
    manifest = load_json(args.manifest)
    if manifest.get("assumptions", {}).get("prompt_version") != tl.PROMPT_VERSION:
        raise SystemExit("manifest prompt version does not match current translation_loop prompt")
    persona_sha = hashlib.sha256(PERSONA.read_bytes()).hexdigest()
    if manifest.get("persona_sha256") != persona_sha:
        raise SystemExit("manifest persona hash does not match current TRANSLATION-PERSONA.md")

    def verify_snapshot_map(files: dict[str, str], hashes: dict[str, str] | None = None) -> None:
        for unit in ("terms", "characters", "style"):
            raw = str(files.get(unit) or "").strip()
            if not raw:
                raise SystemExit(f"missing glossary snapshot path for {unit}")
            path = Path(raw).expanduser().resolve()
            if not path.is_file():
                raise SystemExit(f"glossary snapshot not found for {unit}: {path}")
            if hashes and hashes.get(unit):
                actual = hashlib.sha256(path.read_bytes()).hexdigest()
                if actual != hashes[unit]:
                    raise SystemExit(f"glossary snapshot hash mismatch for {unit}: {path}")

    frozen_glossary = manifest.get("glossary") or {}
    frozen_files = dict(frozen_glossary.get("files") or {})
    frozen_hashes = dict(frozen_glossary.get("sha256") or {})
    verify_snapshot_map(frozen_files, frozen_hashes)

    def current_snapshot_map() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
        pointer = gr.current_pointer()
        if not pointer:
            raise RuntimeError("glossary current.json is missing")
        files = {}
        hashes = {}
        for unit in ("terms", "characters", "style"):
            rel = str(pointer.get(f"{unit}_file") or "").strip()
            if not rel:
                raise RuntimeError(f"glossary current.json missing {unit}_file")
            path = (gr.GLOSSARY_DIR / rel).resolve()
            files[unit] = str(path)
            hashes[unit] = str(pointer.get(f"{unit}_sha256") or "")
        verify_snapshot_map(files, hashes)
        versions = {
            "terms": str(pointer.get("terms_version") or ""),
            "characters": str(pointer.get("characters_version") or ""),
            "style": str(pointer.get("style_version") or ""),
        }
        return files, hashes, versions

    workers = manifest.get("workers", [])
    if not workers:
        raise SystemExit("manifest has no workers")
    family_by_scene: dict[str, dict] = {}
    for family_id, info in manifest["families"].items():
        for scene_id in info["members"]:
            family_by_scene[scene_id] = {**info, "family_id": family_id}

    def make_env(files: dict[str, str]) -> dict[str, str]:
        env = os.environ.copy()
        env.update({
            "DSH_HOME": str(Path.home() / ".dsh-translation"),
            "FKG_PERSONA_FILE": str(PERSONA),
            "FKG_TERMS_FILE": files["terms"],
            "FKG_CHARACTERS_FILE": files["characters"],
            "FKG_STYLE_FILE": files["style"],
            "FKG_TRANSLATOR_MODEL": str(manifest.get("model", "deepseek-chat")),
            "FKG_TRANSLATOR_TEMPERATURE": str(manifest.get("temperature", 0)),
            "FKG_TRANSLATOR_CACHE": "0",
            "PYTHONUNBUFFERED": "1",
        })
        return env

    frozen_versions = (frozen_glossary.get("versions") or {})
    frozen_env = make_env(frozen_files)
    common = ["/usr/bin/python3", str(LOOP)]
    command = "/usr/bin/python3 " + str(ROOT / "work" / "translation_loop" / "deepseek_translator.py")

    lock = threading.Lock()
    status = {
        "manifest": str(args.manifest),
        "run_root": str(args.run_root),
        "started_at": now_iso(),
        "mode": "dry-run" if args.dry_run else "run",
        "glossary_mode": args.glossary_mode,
        "glossary_start": {
            "versions": frozen_versions,
            "files": frozen_files,
            "sha256": frozen_hashes,
        },
        "workers": {w["worker"]: {"state": "pending", "scenes": []} for w in workers},
    }

    def update_worker(worker_id: str, patch: dict):
        with lock:
            status["workers"][worker_id].update(patch)
            status["updated_at"] = now_iso()
            if not args.dry_run:
                atomic_json(args.run_root / "batch-status.json", status)

    def run_worker(worker: dict) -> dict:
        worker_id = worker["worker"]
        worker_root = args.run_root / worker_id
        family_tails: dict[str, str] = {}
        char_tails: dict[str, str] = {}
        scenes = worker["scenes"]
        if args.stop_after > 0:
            scenes = scenes[: args.stop_after]
        update_worker(worker_id, {"state": "running", "started_at": now_iso()})
        completed = 0
        active_family = ""
        active_files = frozen_files
        active_versions = frozen_versions
        scene_env = frozen_env
        for scene_id in scenes:
            family = family_by_scene[scene_id]
            if args.glossary_mode == "rolling" and family["family_id"] != active_family:
                active_files, _active_hashes, active_versions = current_snapshot_map()
                scene_env = make_env(active_files)
                active_family = family["family_id"]
            elif args.glossary_mode == "frozen":
                scene_env = frozen_env
                active_versions = frozen_versions
            summary = build_summary(scene_id, family, family_tails, char_tails)
            scene_root = worker_root / scene_id
            state = status_for_scene(worker_root, scene_id)
            record = {
                "scene_id": scene_id,
                "family_id": family["family_id"],
                "state_before": state.get("status", "absent"),
                "continuity_chars": len(summary),
                "glossary_versions": active_versions,
                "glossary_files": active_files,
            }
            try:
                if args.dry_run:
                    record["status"] = "planned"
                    with lock:
                        status["workers"][worker_id]["scenes"].append(record)
                    completed += 1
                    continue

                # Do not create the scene directory before `init`: the loop's
                # init command treats an existing directory as an existing run
                # and refuses to proceed without --reset.  init creates it.

                # Completed scenes are not re-sent to the model.  This makes a
                # resumed batch cheap and keeps the accepted ledger intact.
                if state.get("status") == "completed":
                    if not review_ok(worker_root, scene_id):
                        raise RuntimeError("completed scene has an unclean review; rerun with --reset")
                    draft = scene_root / "draft.txt"
                    tail = tail_context(draft)
                    if tail:
                        family_tails[family["family_id"]] = tail
                        for ch in family.get("characters", []):
                            char_tails[ch] = tail
                    record["status"] = "skipped_completed"
                    with lock:
                        status["workers"][worker_id]["scenes"].append(record)
                    completed += 1
                    continue

                if state.get("status") == "needs_human" and not args.reset:
                    raise RuntimeError("scene is needs_human; inspect it or rerun with --reset")

                if not state or args.reset:
                    init_args = ["--run-root", str(worker_root), "init", scene_id,
                                 "--history-pairs", "5", "--lookahead", "2"]
                    if args.reset:
                        init_args.append("--reset")
                    init = run_cmd(common + init_args, scene_env, args.scene_timeout, ROOT)
                    if init.returncode != 0:
                        raise RuntimeError(f"init failed: {init.stderr.strip()[:800]}")
                if summary:
                    summ = run_cmd(
                        common + ["--run-root", str(worker_root), "summary", scene_id, summary],
                        scene_env, args.scene_timeout, ROOT,
                    )
                    if summ.returncode != 0:
                        raise RuntimeError(f"summary failed: {summ.stderr.strip()[:800]}")
                run = run_cmd(
                    common + ["--run-root", str(worker_root), "run", scene_id,
                              "--command", command, "--limit", "200", "--max-retries", "3"],
                    scene_env, args.scene_timeout, ROOT,
                )
                (scene_root / "run.log").write_text(
                    (run.stdout or "") + ("\n[stderr]\n" + run.stderr if run.stderr else ""),
                    encoding="utf-8",
                )
                if run.returncode != 0:
                    raise RuntimeError(f"run failed ({run.returncode}): {run.stderr.strip()[:800]}")
                if not review_ok(worker_root, scene_id):
                    raise RuntimeError("review not clean")
                draft = scene_root / "draft.txt"
                tail = tail_context(draft)
                if tail:
                    family_tails[family["family_id"]] = tail
                    for ch in family.get("characters", []):
                        char_tails[ch] = tail
                record["status"] = "completed"
                record["draft_sha256"] = hashlib.sha256(draft.read_bytes()).hexdigest()
                record["tail_chars"] = len(tail)
                completed += 1
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = str(exc)
                with lock:
                    status["workers"][worker_id]["scenes"].append(record)
                update_worker(worker_id, {"state": "failed", "finished_at": now_iso(), "error": str(exc)})
                return {"worker": worker_id, "ok": False, "completed": completed, "error": str(exc)}
            with lock:
                status["workers"][worker_id]["scenes"].append(record)
        update_worker(worker_id, {
            "state": "completed",
            "finished_at": now_iso(),
            "completed_scenes": completed,
        })
        return {"worker": worker_id, "ok": True, "completed": completed}

    if args.dry_run:
        # Keep the same thread/worker ordering but do not invoke anything.
        results = [run_worker(w) for w in workers]
    else:
        args.run_root.mkdir(parents=True, exist_ok=True)
        atomic_json(args.run_root / "batch-status.json", status)
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as pool:
            futures = [pool.submit(run_worker, w) for w in workers]
            results = [f.result() for f in futures]
        status["finished_at"] = now_iso()
        status["ok"] = all(r.get("ok") for r in results)
        atomic_json(args.run_root / "batch-status.json", status)

    print(json.dumps({
        "mode": "dry-run" if args.dry_run else "run",
        "run_root": str(args.run_root),
        "workers": results,
        "batch_status": str(args.run_root / "batch-status.json"),
    }, ensure_ascii=False, indent=2))
    return 0 if all(r.get("ok") for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
