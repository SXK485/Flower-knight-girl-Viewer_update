#!/usr/bin/env python3
"""Prototype sliding-window translation loop for FlowerKnightGirl scenes.

This prototype does NOT call an LLM. It builds the prompt and exercises the
state machine with a deterministic mock translator. Pass --command to plug in
an external translator that reads the prompt on stdin and writes one JSON
object to stdout.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import glossary_runtime as gr

ROOT = _THIS_DIR.parents[1]
SOURCE_ROOT = ROOT / "FlowerKnightGirl_原文"
TRANS_DIR = SOURCE_ROOT / "译文"
GLOSSARY_PATH = TRANS_DIR / "人名清单.csv"
OVERRIDES_PATH = ROOT / "work" / "preflight" / "structural_overrides.json"
DEFAULT_RUN_ROOT = ROOT / "work" / "translation_loop" / "runs"
DEFAULT_GAME_SCENES = Path(os.environ.get("FKG_GAME_SCENES", "/mnt/d1/gal/Flower Knight Girl 1.1/package.nw/scenes"))
SCENE_ID_RE = re.compile(r"^c\d{6}(?:_2)?$")
SPEAKER_RE = re.compile(r"^([^\n:：]{1,40})[:：]\s*(.*)$", re.S)
FORMAT_NAME_PREFIX_RE = re.compile(
    r"^([\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9\uFF10-\uFF19・ー 　＆&、＋+]{1,40})[:：]\s*(.*)$",
    re.S,
)
FORBIDDEN_TAGS = ("<NAME_PLATE>", "<PAUSE>")
JAPANESE_ONLY_HAN = ("膣",)
PROMPT_VERSION = "b-2026-11-22.4"
MAX_REPEATED_CHAR_RUN = 19
_GLOSSARY_SOURCE_RE_CACHE: dict[tuple[str, ...], re.Pattern[str]] = {}
_KNOWN_ZH_NAMES: set[str] | None = None


class TranslationLoopError(RuntimeError):
    """A deterministic setup or validation failure."""


class ValidationError(TranslationLoopError):
    """The translator's output failed one of the gates."""


@dataclass(frozen=True)
class Unit:
    line: int
    action: str  # "translate" | "preserve"
    speaker_ja: str
    speaker_zh: str
    source_text: str
    source_hash: str

    def source_for_prompt(self) -> str:
        return self.source_text.replace("\n", "\\n")


@dataclass(frozen=True)
class Scene:
    scene_id: str
    total_lines: int
    units: tuple[Unit, ...]
    structural_override: dict[str, Any] | None
    mentioned_names: tuple[tuple[str, str], ...] = ()
    mentioned_terms: tuple[dict[str, Any], ...] = ()
    character_policies: tuple[dict[str, Any], ...] = ()
    glossary_versions: tuple[str, str, str] = ("", "", "")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def atomic_write_json(path: Path, value: Any) -> None:
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


def append_jsonl(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + "\n")


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_glossary(path: Path = GLOSSARY_PATH) -> dict[str, str]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    glossary: dict[str, str] = {}
    for row in rows:
        ja = (row.get("出现名字") or "").strip()
        zh = (row.get("待定译文") or "").strip()
        if ja and zh:
            glossary[ja] = zh
    return glossary


def known_zh_names() -> set[str]:
    global _KNOWN_ZH_NAMES
    if _KNOWN_ZH_NAMES is None:
        _KNOWN_ZH_NAMES = {value for value in load_glossary().values() if value}
    return _KNOWN_ZH_NAMES


def load_overrides(path: Path = OVERRIDES_PATH) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    data = read_json(path)
    return data.get("files", {})


def split_source_blocks(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return [block for block in text.split("\n\n") if block.strip()]


def game_block_count(scene_id: str, game_scenes: Path) -> int:
    script = game_scenes / scene_id / "script.txt"
    if not script.is_file():
        raise TranslationLoopError(f"game script not found: {script}")
    text = script.read_text(encoding="utf-8", errors="replace")
    return len(re.findall(r"<NAME_PLATE>(.*?)<PAUSE>", text, re.S))


def parse_source_block(block: str) -> tuple[str, str]:
    """Return (speaker, message) with internal newlines preserved as real newlines."""
    lines = block.split("\n")
    first = lines[0]
    match = SPEAKER_RE.match(first)
    if match:
        speaker = match.group(1).strip()
        message = "\n".join([match.group(2), *lines[1:]]).strip()
        return speaker, message
    return "", block.strip()


def mentioned_glossary_names(text: str, glossary: dict[str, str]) -> tuple[tuple[str, str], ...]:
    """Return glossary entries that occur in the scene source text.

    The regex is cached by the glossary key so a batch process does not rebuild
    an 800-name alternation for every scene.
    """
    if not text or not glossary:
        return ()
    key = tuple(sorted(glossary, key=lambda item: (-len(item), item)))
    pattern = _GLOSSARY_SOURCE_RE_CACHE.get(key)
    if pattern is None:
        pattern = re.compile("|".join(re.escape(name) for name in key))
        _GLOSSARY_SOURCE_RE_CACHE[key] = pattern
    found = set(pattern.findall(text))
    return tuple((name, glossary[name]) for name in key if name in found)


def scene_family_id(scene_id: str) -> tuple[str, bool]:
    if scene_id.endswith("_2"):
        return scene_id[:-2], True
    return scene_id, False


def build_scene(
    scene_id: str,
    *,
    game_scenes: Path = DEFAULT_GAME_SCENES,
    glossary: dict[str, str] | None = None,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> Scene:
    if not SCENE_ID_RE.fullmatch(scene_id):
        raise TranslationLoopError(f"invalid scene id: {scene_id}")
    glossary = glossary if glossary is not None else load_glossary()
    overrides = overrides if overrides is not None else load_overrides()
    source_path = SOURCE_ROOT / f"{scene_id}.txt"
    if not source_path.is_file():
        raise TranslationLoopError(f"source file not found: {source_path}")
    source_blocks = split_source_blocks(source_path)
    expected_game_lines = game_block_count(scene_id, game_scenes)
    override = overrides.get(scene_id)

    units: list[Unit] = []
    if override is not None:
        extra_lines = {int(x) for x in override.get("extra_game_lines_1based", [])}
        if int(override.get("source_blocks", -1)) != len(source_blocks):
            raise TranslationLoopError(
                f"{scene_id}: override source_blocks={override.get('source_blocks')} but file has {len(source_blocks)}"
            )
        if int(override.get("game_blocks", -1)) != expected_game_lines:
            raise TranslationLoopError(
                f"{scene_id}: override game_blocks={override.get('game_blocks')} but game has {expected_game_lines}"
            )
        source_index = 0
        for line in range(1, expected_game_lines + 1):
            if line in extra_lines:
                units.append(Unit(line, "preserve", "", "", "", ""))
                continue
            if source_index >= len(source_blocks):
                raise TranslationLoopError(f"{scene_id}: ran out of source blocks at game line {line}")
            raw = source_blocks[source_index]
            source_index += 1
            speaker_ja, message = parse_source_block(raw)
            speaker_zh = ""
            if speaker_ja:
                speaker_zh = glossary.get(speaker_ja, "")
                if not speaker_zh:
                    raise TranslationLoopError(f"{scene_id}:{line}: no Chinese name for {speaker_ja!r}")
            source_hash = hashlib.sha1(message.encode("utf-8")).hexdigest()
            units.append(Unit(line, "translate", speaker_ja, speaker_zh, message, source_hash))
        if source_index != len(source_blocks):
            raise TranslationLoopError(
                f"{scene_id}: used {source_index}/{len(source_blocks)} source blocks"
            )
    else:
        if len(source_blocks) != expected_game_lines:
            raise TranslationLoopError(
                f"{scene_id}: source has {len(source_blocks)} blocks, game has {expected_game_lines}; "
                "run preflight and add an override first"
            )
        for line, raw in enumerate(source_blocks, 1):
            speaker_ja, message = parse_source_block(raw)
            speaker_zh = ""
            if speaker_ja:
                speaker_zh = glossary.get(speaker_ja, "")
                if not speaker_zh:
                    raise TranslationLoopError(f"{scene_id}:{line}: no Chinese name for {speaker_ja!r}")
            source_hash = hashlib.sha1(message.encode("utf-8")).hexdigest()
            units.append(Unit(line, "translate", speaker_ja, speaker_zh, message, source_hash))

    source_text = "\n".join(unit.source_text for unit in units if unit.action == "translate")
    names = mentioned_glossary_names(source_text, glossary)
    terms = gr.terms_for_text(source_text)
    speaker_ja = {unit.speaker_ja for unit in units if unit.speaker_ja}
    character_policies = gr.character_policies_for_speakers(speaker_ja, source_text)
    versions = gr.snapshot_versions()
    return Scene(
        scene_id,
        expected_game_lines,
        tuple(units),
        override,
        names,
        terms,
        character_policies,
        (versions["terms"], versions["characters"], versions["style"]),
    )


def unit_by_line(scene: Scene) -> dict[int, Unit]:
    return {unit.line: unit for unit in scene.units}


def new_state(scene: Scene, history_pairs: int, lookahead: int) -> dict[str, Any]:
    if history_pairs < 0:
        raise TranslationLoopError("history_pairs must be >= 0")
    if lookahead < 0:
        raise TranslationLoopError("lookahead must be >= 0")
    return {
        "version": 1,
        "scene_id": scene.scene_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "status": "running",
        "history_pairs": history_pairs,
        "lookahead": lookahead,
        "next_line": 1,
        "total_lines": scene.total_lines,
        "retries": 0,
        "last_error": None,
        "last_rejected_output": None,
        "rolling_summary": "",
        "accepted": [],
    }


def state_path(run_root: Path, scene_id: str) -> Path:
    return run_root / scene_id / "state.json"


def run_dir(run_root: Path, scene_id: str) -> Path:
    return run_root / scene_id


def load_state(run_root: Path, scene_id: str) -> dict[str, Any]:
    path = state_path(run_root, scene_id)
    if not path.is_file():
        raise TranslationLoopError(f"state not initialized: {path}")
    state = read_json(path)
    if state.get("scene_id") != scene_id:
        raise TranslationLoopError(f"state scene mismatch: {state.get('scene_id')} != {scene_id}")
    return state


def save_state(run_root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    atomic_write_json(state_path(run_root, state["scene_id"]), state)


def accepted_by_line(state: dict[str, Any]) -> dict[int, dict[str, Any]]:
    return {int(item["line"]): item for item in state.get("accepted", [])}


def advance_preserved(scene: Scene, state: dict[str, Any], run_root: Path) -> list[int]:
    units = unit_by_line(scene)
    accepted = accepted_by_line(state)
    advanced: list[int] = []
    while int(state["next_line"]) <= scene.total_lines:
        unit = units[int(state["next_line"])]
        if unit.action != "preserve":
            break
        if unit.line not in accepted:
            accepted[unit.line] = {
                "line": unit.line,
                "action": "preserve",
                "speaker": "",
                "text": "",
                "source_hash": "",
                "accepted_at": now_iso(),
            }
            state["accepted"].append(accepted[unit.line])
            append_jsonl(run_dir(run_root, scene.scene_id) / "ledger.jsonl", {
                "event": "preserved",
                "line": unit.line,
                "at": now_iso(),
                "reason": "out_of_scope_game_only_block",
            })
        state["next_line"] = unit.line + 1
        advanced.append(unit.line)
    return advanced


def select_history(scene: Scene, state: dict[str, Any]) -> list[tuple[Unit, dict[str, Any]]]:
    count = int(state["history_pairs"])
    if count <= 0:
        return []
    units = unit_by_line(scene)
    accepted = [item for item in state.get("accepted", []) if item.get("action") == "translate"]
    accepted.sort(key=lambda item: int(item["line"]))
    pairs: list[tuple[Unit, dict[str, Any]]] = []
    for item in accepted[-count:]:
        unit = units.get(int(item["line"]))
        if unit is not None and unit.action == "translate":
            pairs.append((unit, item))
    return pairs


def select_future(scene: Scene, state: dict[str, Any]) -> list[Unit]:
    count = int(state["lookahead"])
    if count <= 0:
        return []
    current_line = int(state["next_line"])
    return [
        unit for unit in scene.units
        if unit.line > current_line and unit.action == "translate"
    ][:count]


def build_prompt(scene: Scene, state: dict[str, Any]) -> tuple[str, Unit]:
    units = unit_by_line(scene)
    line = int(state["next_line"])
    current = units.get(line)
    if current is None or current.action != "translate":
        raise TranslationLoopError(f"{scene.scene_id}: no translatable unit at line {line}")
    history = select_history(scene, state)
    future = select_future(scene, state)
    names: dict[str, str] = {}
    # Include every named speaker in this scene, even outside the current
    # window, plus names merely mentioned in narration.  This prevents the
    # translator from inventing a Chinese name when a body-only mention falls
    # outside the usual history/lookahead window.
    for unit in scene.units:
        if unit.speaker_ja:
            names[unit.speaker_ja] = unit.speaker_zh
    for ja, zh in scene.mentioned_names:
        names[ja] = zh

    family_id, is_variant = scene_family_id(scene.scene_id)
    family_note = f"（当前为 `_2` 变体，与 `{family_id}` 同族）" if is_variant else ""
    lines = [
        "# 场景锚点",
        "",
        f"- scene_id: `{scene.scene_id}`",
        f"- 场景家族: `{family_id}`{family_note}",
        f"- prompt_version: `{PROMPT_VERSION}`",
        f"- terms_version: `{scene.glossary_versions[0]}`",
        f"- characters_version: `{scene.glossary_versions[1]}`",
        f"- style_version: `{scene.glossary_versions[2]}`",
        f"- 当前行: {current.line} / {scene.total_lines}",
        f"- 已定稿历史 pair: {len(history)}",
        f"- 后文参考: {len(future)}",
        "",
        "# 翻译规范",
        "",
        "严格忠实原文；只翻译当前行；不解释、不总结、不扩写、不续写。",
        "保留原文结构、标点、语气、专有名词、数字、URL、代码、占位符和文件路径。",
        "不要保留日文特有的生硬汉字写法；「膣」相关词必须译成中文，例如「阴道内」「小穴里」。",
        "台词外层引号：源文台词最外层有「」，译文保留一对；源文没有，就不要额外加。旁白不改。",
        "历史译文只用于参考语气和术语，不要照抄其中的格式；`text` 中不要出现 `角色名:` 前缀。",
        "游戏译文一行对应一个对话块；块内换行写为字面量 `\\n`，不要写真实换行。",
        "",
        "# 人名与术语",
        "",
    ]
    if names:
        for ja, zh in names.items():
            lines.append(f"- `{ja}` -> `{zh}`")
    else:
        lines.append("- 当前上下文没有角色名。")
    if scene.mentioned_terms:
        lines += ["", "# 术语", ""]
        for entry in scene.mentioned_terms:
            ja_forms = " / ".join(str(x) for x in entry.get("ja") or [])
            zh = entry.get("zh") or {}
            default = str(zh.get("default") or "")
            variants = [str(x) for x in zh.get("variants") or [] if str(x)]
            rendered = default
            if variants:
                rendered += "（可选用：" + " / ".join(variants) + "）"
            note = str(entry.get("notes") or "").strip()
            suffix = f"；{note}" if note else ""
            lines.append(f"- `{ja_forms}` -> {rendered}{suffix}")
    if scene.character_policies:
        policy_lines: list[str] = []
        for policy in scene.character_policies:
            forms = policy.get("address_forms") or []
            if forms:
                rendered_forms = []
                for rule in forms:
                    allowed = " / ".join(rule.get("allowed") or [])
                    rendered_forms.append(f"{rule.get('ja')} -> {rule.get('default')}（允许：{allowed}）")
                policy_lines.append(
                    f"- `{policy.get('ja')}` -> `{policy.get('zh')}`："
                    + "；".join(rendered_forms)
                )
            elif policy.get("zh"):
                policy_lines.append(f"- `{policy.get('ja')}` -> `{policy.get('zh')}`")
            note = str(policy.get("notes") or "").strip()
            if note:
                policy_lines.append(f"  - {note}")
        if policy_lines:
            lines += ["", "# 角色称呼策略", ""] + policy_lines
    lines += ["", "# 已定稿对话", ""]
    if history:
        for unit, item in history:
            lines.append(f"- 第 {unit.line} 行 原文：{unit.source_for_prompt()}")
            lines.append(f"  第 {unit.line} 行 译文：{format_output_line(item)}")
    else:
        lines.append("- 无（这是场景开头）。")
    if state.get("rolling_summary"):
        lines += [
            "",
            "# 角色与连续性",
            "",
            "（用于同角色跨场景的语气、称呼和前情连续性；只作参考，不增加原文没有的信息。）",
            "",
            str(state["rolling_summary"]).strip(),
        ]
    lines += [
        "",
        "# 当前原文",
        "",
        f">> 第 {current.line} 行：{current.source_for_prompt()}",
    ]
    if future:
        lines += ["", "# 后文参考", ""]
        for unit in future:
            lines.append(f"- 第 {unit.line} 行：{unit.source_for_prompt()}")
    lines += [
        "",
        "# 本次任务",
        "",
        f"只翻译第 {current.line} 行。",
    ]
    if future:
        lines.append(f"第 {', '.join(str(unit.line) for unit in future)} 行只作为后文参考，不要输出它们的译文。")
    if current.speaker_zh:
        lines.append(f"当前行有角色名，speaker 必须是 `{current.speaker_zh}`。")
    else:
        lines.append("当前行是旁白，speaker 必须是空字符串。")
    lines += [
        "",
        "# 输出协议",
        "",
        "只输出一个 JSON 对象，不要 Markdown 代码块，不要解释：",
        "",
        '{"line": <当前行号>, "speaker": "<角色名或空字符串>", "text": "<译文>"}',
        "",
        "`text` 中需要换行时写两个字符 `\\n`，不要写真实换行。",
        "`text` 只放当前行的正文；不要重复 `speaker` 名字，也不要再写一遍 `角色名: ` 前缀。",
        "",
        "# 输出前自检（不要输出自检内容）",
        "",
        "- `line` 是当前行号；`speaker` 与任务指定完全一致。",
        "- `text` 只含当前行正文，不含角色名前缀，不含真实换行或 Markdown 围栏。",
        "- 只输出一个 JSON 对象，不解释、不复述规则。",
    ]
    if int(state.get("retries", 0)) > 0 and state.get("last_error"):
        lines += [
            "",
            "# 上次输出未通过",
            "",
            f"- 错误：{state['last_error']}",
        ]
        if state.get("last_rejected_output"):
            lines.append(f"- 上次输出：`{str(state['last_rejected_output'])[:1200]}`")
        lines.append("- 请只修正这个问题，仍然只输出当前行的一个 JSON 对象。")
    return "\n".join(lines) + "\n", current

def validate_model_output(raw: str, unit: Unit) -> dict[str, Any]:
    text = raw.strip()
    if not text:
        raise ValidationError("empty translator output")
    if text.startswith("```"):
        raise ValidationError("Markdown fences are not allowed")
    raw_repeat = re.search(rf"(.)\1{{{MAX_REPEATED_CHAR_RUN},}}", text.replace("\\n", ""), re.S)
    if raw_repeat:
        raise ValidationError(
            "raw translator output contains excessive same-character repetition; "
            "condense moans to short onomatopoeia plus action/pause"
        )
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationError(f"output is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError("output must be a JSON object")
    if set(value) != {"line", "speaker", "text"}:
        raise ValidationError("output keys must be exactly line, speaker, text")
    line = value["line"]
    speaker = value["speaker"]
    translated = value["text"]
    if not isinstance(line, int) or isinstance(line, bool):
        raise ValidationError("line must be an integer")
    if line != unit.line:
        raise ValidationError(f"line mismatch: expected {unit.line}, got {line}")
    if not isinstance(speaker, str):
        raise ValidationError("speaker must be a string")
    if speaker != unit.speaker_zh:
        expected = unit.speaker_zh or "(空字符串，旁白)"
        raise ValidationError(f"speaker mismatch: expected {expected}, got {speaker!r}")
    if not isinstance(translated, str):
        raise ValidationError("text must be a string")
    translated = translated.strip()
    if not translated:
        raise ValidationError("text must not be empty")
    translated = gr.normalize_japanese_terms(translated)
    if "\n" in translated or "\r" in translated:
        raise ValidationError("text must use the literal characters \\n, not a real newline")
    for tag in FORBIDDEN_TAGS:
        if tag in translated:
            raise ValidationError(f"text contains forbidden tag {tag}")
    for char in JAPANESE_ONLY_HAN:
        if char in translated:
            raise ValidationError(f"text contains Japanese-only Han character {char!r}; translate it into Chinese")
    repeated = re.search(rf"(.)\1{{{MAX_REPEATED_CHAR_RUN},}}", translated.replace("\\n", ""), re.S)
    if repeated:
        raise ValidationError(
            "text contains excessive same-character repetition; condense moans to short onomatopoeia plus action/pause"
        )
    if unit.speaker_zh:
        repeated_speaker = re.match(
            rf"^{re.escape(unit.speaker_zh)}\s*[:：]",
            translated,
        )
        if repeated_speaker:
            raise ValidationError("text must not repeat the speaker name-plate prefix")
        translated = gr.apply_speaker_quote_policy(translated, unit.source_text)
    else:
        match = SPEAKER_RE.match(translated)
        if match and match.group(1).strip() in known_zh_names():
            raise ValidationError("narration text must not include a name-plate prefix")
        # The install-time format checker treats any leading Chinese-text run
        # followed by a colon as a name plate.  For narration only, turn that
        # ambiguous colon into a comma so legitimate prose such as
        # "她开口道：..." cannot be misclassified as a speaker prefix.
        format_match = FORMAT_NAME_PREFIX_RE.match(translated)
        if format_match:
            translated = format_match.group(1) + "，" + format_match.group(2)
    return {"line": line, "speaker": speaker, "text": translated}


def format_output_line(item: dict[str, Any]) -> str:
    speaker = item.get("speaker", "")
    text = item.get("text", "")
    return f"{speaker}: {text}" if speaker else text


def render_draft(scene: Scene, state: dict[str, Any]) -> list[str]:
    accepted = accepted_by_line(state)
    draft: list[str] = []
    for unit in scene.units:
        item = accepted.get(unit.line)
        if item is None:
            draft.append("")
        elif item["action"] == "preserve":
            draft.append("")
        else:
            draft.append(format_output_line(item))
    return draft


def write_draft(scene: Scene, state: dict[str, Any], run_root: Path) -> Path:
    path = run_dir(run_root, scene.scene_id) / "draft.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(render_draft(scene, state)) + "\n", encoding="utf-8")
    return path


def ledger_path(run_root: Path, scene_id: str) -> Path:
    return run_dir(run_root, scene_id) / "ledger.jsonl"


def save_prompt(run_root: Path, scene_id: str, line: int, prompt: str) -> Path:
    path = run_dir(run_root, scene_id) / "prompts" / f"line-{line:04d}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(prompt, encoding="utf-8")
    return path


class Translator(Protocol):
    def translate(self, prompt: str, unit: Unit) -> str: ...


class MockTranslator:
    def translate(self, prompt: str, unit: Unit) -> str:
        return json.dumps(
            {
                "line": unit.line,
                "speaker": unit.speaker_zh,
                "text": f"测试译文{unit.line}",
            },
            ensure_ascii=False,
        )


class CommandTranslator:
    def __init__(self, command: str):
        self.command = shlex.split(command)
        if not self.command:
            raise TranslationLoopError("--command is empty")

    def translate(self, prompt: str, unit: Unit) -> str:
        result = subprocess.run(
            self.command,
            input=prompt,
            text=True,
            encoding="utf-8",
            errors="replace",
            capture_output=True,
        )
        if result.returncode != 0:
            raise TranslationLoopError(
                f"translator command failed ({result.returncode}): {result.stderr.strip()[:500]}"
            )
        return result.stdout


def make_translator(command: str | None) -> Translator:
    return CommandTranslator(command) if command else MockTranslator()


def step_scene(scene: Scene, state: dict[str, Any], run_root: Path, translator: Translator) -> dict[str, Any]:
    if state["status"] == "completed":
        return {"status": "completed", "next_line": state["next_line"]}
    if state["status"] == "needs_human":
        return {"status": "needs_human", "error": state.get("last_error")}

    advanced = advance_preserved(scene, state, run_root)
    if int(state["next_line"]) > scene.total_lines:
        state["status"] = "completed"
        write_draft(scene, state, run_root)
        save_state(run_root, state)
        return {"status": "completed", "preserved": advanced}
    prompt, unit = build_prompt(scene, state)
    prompt_path = save_prompt(run_root, scene.scene_id, unit.line, prompt)
    raw = ""
    try:
        raw = translator.translate(prompt, unit)
        item = validate_model_output(raw, unit)
    except (ValidationError, TranslationLoopError) as exc:
        state["retries"] = int(state.get("retries", 0)) + 1
        state["last_error"] = str(exc)
        state["last_rejected_output"] = raw[-4000:] if raw else None
        append_jsonl(ledger_path(run_root, scene.scene_id), {
            "event": "rejected",
            "line": unit.line,
            "at": now_iso(),
            "error": str(exc),
            "prompt": str(prompt_path),
        })
        save_state(run_root, state)
        return {
            "status": "rejected",
            "line": unit.line,
            "error": str(exc),
            "retries": state["retries"],
        }

    item["action"] = "translate"
    item["source_hash"] = unit.source_hash
    item["accepted_at"] = now_iso()
    state["accepted"].append(item)
    state["next_line"] = unit.line + 1
    state["retries"] = 0
    state["last_error"] = None
    state["last_rejected_output"] = None
    append_jsonl(ledger_path(run_root, scene.scene_id), {
        "event": "accepted",
        "line": unit.line,
        "at": now_iso(),
        "speaker": item["speaker"],
        "text": item["text"],
        "source_hash": unit.source_hash,
        "prompt": str(prompt_path),
        "mock": isinstance(translator, MockTranslator),
    })
    advance_preserved(scene, state, run_root)
    write_draft(scene, state, run_root)
    if int(state["next_line"]) > scene.total_lines:
        state["status"] = "completed"
    save_state(run_root, state)
    return {
        "status": state["status"],
        "accepted_line": unit.line,
        "next_line": state["next_line"],
        "preserved": advanced,
    }


def review_scene(scene: Scene, state: dict[str, Any], run_root: Path) -> dict[str, Any]:
    accepted = accepted_by_line(state)
    draft = render_draft(scene, state) if state.get("accepted") else [""] * scene.total_lines
    issues: list[dict[str, Any]] = []
    if len(draft) != scene.total_lines:
        issues.append({"kind": "line_count", "expected": scene.total_lines, "actual": len(draft)})
    for unit in scene.units:
        item = accepted.get(unit.line)
        if item is None:
            issues.append({"kind": "missing_line", "line": unit.line})
            continue
        if unit.action == "preserve":
            if item.get("text", "") or draft[unit.line - 1] != "":
                issues.append({"kind": "preserve_not_blank", "line": unit.line})
            continue
        if not item.get("text"):
            issues.append({"kind": "empty_translation", "line": unit.line})
        if item.get("speaker", "") != unit.speaker_zh:
            issues.append({"kind": "speaker_mismatch", "line": unit.line, "expected": unit.speaker_zh, "actual": item.get("speaker")})
        text = item.get("text", "")
        if "\n" in text or "\r" in text:
            issues.append({"kind": "real_newline_in_text", "line": unit.line})
        for tag in FORBIDDEN_TAGS:
            if tag in text:
                issues.append({"kind": "forbidden_tag", "line": unit.line, "tag": tag})
    complete = int(state["next_line"]) > scene.total_lines and len(accepted) == scene.total_lines
    report = {
        "scene_id": scene.scene_id,
        "complete": complete,
        "total_lines": scene.total_lines,
        "accepted_lines": len(accepted),
        "translated_lines": sum(1 for i in accepted.values() if i.get("action") == "translate"),
        "preserved_lines": sum(1 for i in accepted.values() if i.get("action") == "preserve"),
        "issues": issues,
        "generated_at": now_iso(),
    }
    out = run_dir(run_root, scene.scene_id)
    atomic_write_json(out / "review.json", report)
    lines = [
        f"# 翻译原型审查：{scene.scene_id}",
        "",
        f"- 完成: {'是' if complete else '否'}",
        f"- 总行数: {scene.total_lines}",
        f"- 已接受: {len(accepted)}",
        f"- 已翻译: {report['translated_lines']}",
        f"- 保留空行: {report['preserved_lines']}",
        f"- 问题数: {len(issues)}",
        "",
    ]
    if issues:
        lines.append("## 问题")
        lines.append("")
        for issue in issues[:200]:
            lines.append(f"- {json.dumps(issue, ensure_ascii=False)}")
    else:
        lines.append("确定性检查通过。")
    (out / "review.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report


def status_summary(scene: Scene, state: dict[str, Any]) -> dict[str, Any]:
    accepted = state.get("accepted", [])
    return {
        "scene_id": scene.scene_id,
        "status": state.get("status"),
        "next_line": state.get("next_line"),
        "total_lines": scene.total_lines,
        "history_pairs": state.get("history_pairs"),
        "lookahead": state.get("lookahead"),
        "window_slots": min(len(accepted), int(state.get("history_pairs", 0))) + 1 + int(state.get("lookahead", 0)),
        "accepted": len(accepted),
        "translated": sum(1 for item in accepted if item.get("action") == "translate"),
        "preserved": sum(1 for item in accepted if item.get("action") == "preserve"),
        "retries": state.get("retries", 0),
        "last_error": state.get("last_error"),
    }


def cmd_init(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    out = run_dir(run_root, scene.scene_id)
    if out.exists() and not args.reset:
        raise TranslationLoopError(f"run already exists: {out}; use --reset to replace it")
    if out.exists():
        import shutil
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    state = new_state(scene, args.history_pairs, args.lookahead)
    save_state(run_root, state)
    write_draft(scene, state, run_root)
    append_jsonl(ledger_path(run_root, scene.scene_id), {
        "event": "initialized",
        "at": now_iso(),
        "scene_id": scene.scene_id,
        "history_pairs": args.history_pairs,
        "lookahead": args.lookahead,
        "structural_override": scene.structural_override is not None,
    })
    print(json.dumps(status_summary(scene, state), ensure_ascii=False, indent=2))
    return 0


def cmd_step(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    result = step_scene(scene, state, run_root, make_translator(args.command))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("status") not in ("rejected", "needs_human") else 1


def cmd_run(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    translator = make_translator(args.command)
    steps = 0
    while steps < args.limit and state.get("status") not in ("completed", "needs_human"):
        result = step_scene(scene, state, run_root, translator)
        steps += 1
        print(json.dumps(result, ensure_ascii=False))
        if result.get("status") == "rejected":
            if int(state.get("retries", 0)) >= args.max_retries:
                state["status"] = "needs_human"
                save_state(run_root, state)
                print(f"stopped after {state['retries']} retries", file=sys.stderr)
                break
        state = load_state(run_root, scene.scene_id)
    report = review_scene(scene, state, run_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["complete"] and not report["issues"] else 1


def cmd_status(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    print(json.dumps(status_summary(scene, state), ensure_ascii=False, indent=2))
    return 0


def cmd_prompt(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    out = advance_preserved(scene, state, run_root)
    if out:
        save_state(run_root, state)
    if int(state["next_line"]) > scene.total_lines:
        print("scene is complete")
        return 0
    prompt, unit = build_prompt(scene, state)
    path = save_prompt(run_root, scene.scene_id, unit.line, prompt)
    print(prompt)
    print(f"\n[saved: {path}]", file=sys.stderr)
    return 0


def cmd_review(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    report = review_scene(scene, state, run_root)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["complete"] and not report["issues"] else 1


def cmd_draft(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    print("\n".join(render_draft(scene, state)))
    return 0


def cmd_summary(args: argparse.Namespace, scene: Scene, run_root: Path) -> int:
    state = load_state(run_root, scene.scene_id)
    state["rolling_summary"] = args.text.strip()
    save_state(run_root, state)
    print(json.dumps({"scene_id": scene.scene_id, "rolling_summary": state["rolling_summary"]}, ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="FlowerKnightGirl sliding-window translation prototype")
    parser.add_argument("--run-root", type=Path, default=DEFAULT_RUN_ROOT)
    parser.add_argument("--game-scenes", type=Path, default=DEFAULT_GAME_SCENES)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_scene_args(p: argparse.ArgumentParser) -> None:
        p.add_argument("scene_id")

    p_init = sub.add_parser("init", help="initialize a scene run")
    add_scene_args(p_init)
    p_init.add_argument("--history-pairs", type=int, default=4, help="number of completed source/translation pairs kept")
    p_init.add_argument("--lookahead", type=int, default=0, help="number of future source lines shown as reference")
    p_init.add_argument("--reset", action="store_true")
    p_init.set_defaults(func=cmd_init)

    p_step = sub.add_parser("step", help="process one step (mock or external command)")
    add_scene_args(p_step)
    p_step.add_argument("--command", help="external translator command: prompt on stdin, JSON on stdout")
    p_step.set_defaults(func=cmd_step)

    p_run = sub.add_parser("run", help="run multiple steps and review")
    add_scene_args(p_run)
    p_run.add_argument("--command", help="external translator command: prompt on stdin, JSON on stdout")
    p_run.add_argument("--limit", type=int, default=10000)
    p_run.add_argument("--max-retries", type=int, default=2)
    p_run.set_defaults(func=cmd_run)

    p_status = sub.add_parser("status", help="print run status")
    add_scene_args(p_status)
    p_status.set_defaults(func=cmd_status)

    p_prompt = sub.add_parser("prompt", help="print the next prompt without translating")
    add_scene_args(p_prompt)
    p_prompt.set_defaults(func=cmd_prompt)

    p_review = sub.add_parser("review", help="run deterministic checks on the draft")
    add_scene_args(p_review)
    p_review.set_defaults(func=cmd_review)

    p_draft = sub.add_parser("draft", help="print the current draft")
    add_scene_args(p_draft)
    p_draft.set_defaults(func=cmd_draft)

    p_summary = sub.add_parser("summary", help="set the rolling summary")
    add_scene_args(p_summary)
    p_summary.add_argument("text")
    p_summary.set_defaults(func=cmd_summary)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        scene = build_scene(
            args.scene_id,
            game_scenes=args.game_scenes,
            glossary=load_glossary(),
            overrides=load_overrides(),
        )
        return int(args.func(args, scene, args.run_root))
    except TranslationLoopError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
