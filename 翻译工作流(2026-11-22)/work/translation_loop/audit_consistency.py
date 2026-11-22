#!/usr/bin/env python3
"""Cross-scene consistency audit for final translations or staged drafts.

Reads only. Writes a JSON/Markdown report; never edits translations.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from functools import lru_cache
from pathlib import Path

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

import glossary_runtime as gr
import translation_loop as tl

KANA_RE = re.compile(r"[\u3040-\u30ff]")
ADDRESS_SEPARATORS_RE = re.compile(r"[、,，・\s]+")
ADDRESS_SUFFIXES = [
    "大人", "先生", "殿下", "殿", "阁下", "小姐", "哥哥", "同学",
    "酱", "ちゃん", "小弟", "君", "喵", "桑", "さん", "様",
    "弟弟", "妹妹",
]


def normalize_address_text(text: str) -> str:
    """Normalize punctuation/spacing inside an address token for exact comparison."""
    return ADDRESS_SEPARATORS_RE.sub("", str(text or ""))


def address_bases_for(source_form: str) -> tuple[str, ...]:
    if source_form == "ダンナ":
        return ("老板", "老公")
    if source_form == "お兄さん":
        return ("哥哥",)
    return ("团长", "團長")


@lru_cache(maxsize=None)
def address_token_re(bases: tuple[str, ...]):
    base_alt = "|".join(re.escape(x) for x in sorted(bases, key=len, reverse=True))
    suffix_alt = "|".join(re.escape(x) for x in sorted(ADDRESS_SUFFIXES, key=len, reverse=True))
    # 「小」「亲」只有在与名字直接相连时才是称呼后缀：
    #   - 团长小 / 团长亲，是昵称；
    #   - 团长，小穴 / 团长，亲我，中的「小/亲」不是称呼后缀。
    special_suffix = r"小(?=$|[，。！？、…\s」』～〜ー])|亲(?=$|[，。！？、…\s」』]|以外|的)"
    return re.compile(
        r"(?:" + base_alt + r")(?:"
        r"[、,，・\s]+(?:" + suffix_alt + r")?"
        r"|(?:" + suffix_alt + r")"
        r"|(?:" + special_suffix + r")"
        r")?"
    )


def extract_address_tokens(body: str, source_form: str) -> list[str]:
    pattern = address_token_re(address_bases_for(source_form))
    seen: set[str] = set()
    out: list[str] = []
    for match in pattern.finditer(body):
        token = normalize_address_text(match.group(0))
        if token and token not in seen:
            seen.add(token)
            out.append(token)
    return out


def now_iso():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def split_output_line(text: str):
    match = tl.SPEAKER_RE.match(text)
    if not match:
        return "", text
    return text[: match.start(2)], match.group(2)


def load_character_rows():
    data = gr.load_characters()
    rows = {}
    for row in data.get("characters") or []:
        if isinstance(row, dict) and row.get("ja"):
            rows[str(row["ja"])] = row
    return data, rows


def address_rules_for(ja: str, data: dict, rows: dict):
    forms = dict(data.get("address_forms_default") or {})
    override = (data.get("overrides") or {}).get(ja) or {}
    for key, rule in (override.get("address_forms") or {}).items():
        forms[key] = rule
    return forms


def find_drafts(root: Path):
    out = []
    for p in sorted(root.rglob("draft.txt")):
        sid = p.parent.name
        if tl.SCENE_ID_RE.fullmatch(sid):
            out.append((sid, p))
    return out


def audit_file(scene_id: str, path: Path, data: dict, rows: dict, style: dict, terms_data: dict):
    scene = tl.build_scene(scene_id)
    lines = path.read_text(encoding="utf-8").splitlines()
    errors = []
    warnings = []
    info = []
    character_usage: dict[str, dict] = {}
    term_forms = []
    for entry in terms_data.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        for form in entry.get("ja") or []:
            form = str(form)
            # Han-only shared forms (精液, 肉棒, 乳房) are valid Chinese output;
            # only kana-bearing or Japanese-only Han forms indicate residue.
            if form and (KANA_RE.search(form) or any(ch in form for ch in tl.JAPANESE_ONLY_HAN)):
                term_forms.append(form)

    def add(bucket, kind, line, message, **extra):
        item = {"scene_id": scene_id, "line": line, "kind": kind, "message": message}
        item.update(extra)
        bucket.append(item)

    if len(lines) != scene.total_lines:
        add(errors, "line_count", 0, f"译文 {len(lines)} 行，游戏/原文 {scene.total_lines} 行")

    names_zh = {str(row.get("zh")) for row in rows.values() if row.get("zh")}
    # Canonical names whose Japanese and Chinese spellings are identical (e.g. 茜)
    # are valid Chinese output, not Japanese residue.  Also covers 茜色 because
    # removing 茜 leaves 色 and prevents a name match.
    self_identical_names = {
        ja for ja, row in rows.items()
        if ja and ja == str(row.get("zh") or "")
    }
    name_regex = None
    if scene.mentioned_names:
        name_regex = re.compile("|".join(re.escape(x) for x in sorted((j for j, _ in scene.mentioned_names), key=len, reverse=True)))

    for idx, raw in enumerate(lines, 1):
        if idx > len(scene.units):
            break
        unit = scene.units[idx - 1]
        if unit.action == "preserve":
            if raw.strip():
                add(errors, "preserve_not_blank", idx, "结构 override 行必须为空")
            continue
        prefix, body = split_output_line(raw)
        # The versioned characters snapshot is the source of truth for display
        # names.  This lets a temporary FKG_CHARACTERS_FILE=v0003 audit verify
        # renamed speakers before publication, while the CSV remains untouched.
        expected_speaker_zh = str((rows.get(unit.speaker_ja) or {}).get("zh") or unit.speaker_zh)
        if expected_speaker_zh:
            if not prefix:
                add(errors, "missing_speaker_prefix", idx, f"缺少角色名前缀：{expected_speaker_zh}")
                continue
            actual_speaker = prefix.split(":", 1)[0].split("：", 1)[0].strip()
            if actual_speaker != expected_speaker_zh:
                add(errors, "speaker_mismatch", idx, f"角色名 {actual_speaker!r} != {expected_speaker_zh!r}", actual=actual_speaker, expected=expected_speaker_zh)
            if actual_speaker not in names_zh:
                add(warnings, "unknown_speaker_name", idx, f"角色名 {actual_speaker!r} 不在 characters 快照中")
            repeated = re.match(rf"^{re.escape(expected_speaker_zh)}\s*[:：]", body)
            if repeated:
                add(errors, "duplicate_speaker_prefix", idx, "text 又重复了一遍角色名前缀")
            src_q = gr.source_has_outer_quote(unit.source_text)
            out_q = gr.output_has_outer_quote(body)
            if src_q != out_q:
                add(errors, "quote_policy", idx, f"源文引号={src_q}，译文引号={out_q}")
        else:
            if prefix:
                actual = prefix.split(":", 1)[0].split("：", 1)[0].strip()
                if actual in names_zh or actual in tl.known_zh_names():
                    add(errors, "narration_has_speaker_prefix", idx, f"旁白带角色名前缀：{prefix!r}")
                elif tl.FORMAT_NAME_PREFIX_RE.match(raw):
                    add(errors, "narration_colon_format_risk", idx, "旁白句首冒号会被格式校对误判为角色名前缀")

        for tag in tl.FORBIDDEN_TAGS:
            if tag in body:
                add(errors, "forbidden_tag", idx, tag)
        for ch in tl.JAPANESE_ONLY_HAN:
            if ch in body:
                add(errors, "japanese_only_han", idx, f"残留日文专用汉字 {ch}")
        if KANA_RE.search(body):
            add(warnings, "kana_residue", idx, "正文残留日文假名：" + "".join(KANA_RE.findall(body))[:20])
        if name_regex:
            body_for_name_scan = body
            for self_name in sorted(self_identical_names, key=len, reverse=True):
                body_for_name_scan = body_for_name_scan.replace(self_name, "")
            found = name_regex.findall(body_for_name_scan)
            if found:
                add(warnings, "japanese_name_in_text", idx, "正文残留日文名：" + ", ".join(sorted(set(found))))

        # Term residue audit.
        for form in term_forms:
            if form in body:
                add(warnings, "japanese_term_in_text", idx, f"正文残留日文术语 {form}")
                break

        # Address-form audit and cross-scene character usage.  Address tokens
        # are matched as complete, longest tokens (e.g. 团长先生 is not
        # satisfied by allowing only 团长), instead of substring containment.
        if unit.speaker_ja:
            forms = address_rules_for(unit.speaker_ja, data, rows)
            usage = character_usage.setdefault(unit.speaker_ja, {
                "zh": set(), "scenes": set(), "lines": 0,
                "address_checked": 0, "address_pronoun_allowed": 0,
                "address_usage": Counter(),
            })
            usage["zh"].add(actual_speaker if expected_speaker_zh else "")
            usage["scenes"].add(scene_id)
            usage["lines"] += 1
            normalized_source = normalize_address_text(unit.source_text)
            present = [
                (src, rule)
                for src, rule in forms.items()
                if normalize_address_text(src) and normalize_address_text(src) in normalized_source
            ]
            if present:
                src, rule = max(present, key=lambda pair: len(normalize_address_text(pair[0])))
                allowed = [str(x) for x in rule.get("allowed") or [] if str(x)]
                default = str(rule.get("default") or "")
                if default and default not in allowed:
                    allowed.insert(0, default)
                allowed_norm = [normalize_address_text(x) for x in allowed if normalize_address_text(x)]
                usage["address_checked"] += 1
                if src in body:
                    add(warnings, "japanese_address_in_text", idx, f"正文残留日文称呼 {src}")
                tokens = extract_address_tokens(body, src)
                bad_tokens = [token for token in tokens if token not in allowed_norm]
                if bad_tokens:
                    add(
                        warnings,
                        "address_not_in_allowed",
                        idx,
                        f"源文称呼 {src}，正文出现未允许称呼 {bad_tokens}（allowed: {allowed}）",
                        actual_tokens=bad_tokens,
                        allowed=allowed,
                    )
                    used = " + ".join(bad_tokens)
                elif tokens:
                    used = " + ".join(tokens)
                elif rule.get("allow_pronoun"):
                    used = "<pronoun/omission>"
                    usage["address_pronoun_allowed"] += 1
                    info.append({
                        "scene_id": scene_id,
                        "line": idx,
                        "kind": "address_pronoun_allowed",
                        "message": f"源文称呼 {src}，正文使用自然代词/省略（允许）",
                        "source_form": src,
                    })
                else:
                    used = "<missing>"
                    add(warnings, "address_missing", idx, f"源文称呼 {src}，正文既无允许称呼也无代词/省略例外")
                usage["address_usage"][f"{src} -> {used}"] += 1

    # Family-level information: base/_2 speaker sets differ or both files exist.
    if scene_id.endswith("_2"):
        base = scene_id[:-2]
        info.append({"scene_id": scene_id, "kind": "family_variant", "message": f"属于 {base} 家族"})
    serializable_usage = {
        ja: {
            "zh": sorted(x for x in usage["zh"] if x),
            "scenes": sorted(usage["scenes"]),
            "lines": usage["lines"],
            "address_checked": usage["address_checked"],
            "address_pronoun_allowed": usage["address_pronoun_allowed"],
            "address_usage": dict(usage["address_usage"]),
        }
        for ja, usage in character_usage.items()
    }
    return {
        "scene_id": scene_id,
        "path": str(path),
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "character_usage": serializable_usage,
    }


def render_markdown(report: dict):
    lines = [
        "# 跨场景一致性审计",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- source: {report['source']}",
        f"- files: {report['file_count']}",
        f"- errors: {report['error_count']}",
        f"- warnings: {report['warning_count']}",
        f"- address_checked: {report.get('address_stats', {}).get('checked_lines', 0)}",
        f"- address_not_in_allowed: {report.get('address_stats', {}).get('not_in_allowed', 0)}",
        f"- address_missing: {report.get('address_stats', {}).get('missing', 0)}",
        f"- address_pronoun_allowed: {report.get('address_stats', {}).get('pronoun_allowed', 0)}",
        f"- glossary_versions: terms={report['glossary_versions']['terms']}, characters={report['glossary_versions']['characters']}, style={report['glossary_versions']['style']}",
        "",
    ]
    for row in report["files"]:
        if not row["errors"] and not row["warnings"]:
            continue
        lines.append(f"## {row['scene_id']}")
        lines.append("")
        for bucket, title in (("errors", "错误"), ("warnings", "警告")):
            for item in row[bucket]:
                lines.append(f"- **{title}** `{item['kind']}` 第 {item['line']} 行：{item['message']}")
        lines.append("")

    if report.get("cross_scene_warnings"):
        lines += ["## 跨场景警告", ""]
        for item in report["cross_scene_warnings"]:
            lines.append(f"- `{item['kind']}` {item['ja']} -> {item['zh']}（{item['scenes']} 个场景）")
        lines.append("")
    lines += ["## 跨场景角色汇总", "", "| 日文名 | 中文名 | 场景数 | 台词行数 | 称呼使用 |", "|---|---|---:|---:|---|"]
    for row in report.get("character_summary", [])[:200]:
        address = "; ".join(f"{k} x{v}" for k, v in sorted(row["address_usage"].items()))
        lines.append(
            f"| {row['ja']} | {' / '.join(row['zh'])} | {row['scene_count']} | {row['line_count']} | {address} |"
        )
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--translation-dir", type=Path)
    parser.add_argument("--draft-root", type=Path)
    parser.add_argument("--output-dir", type=Path, default=Path("work/translation_loop/audit"))
    args = parser.parse_args(argv)
    if bool(args.translation_dir) == bool(args.draft_root):
        raise SystemExit("specify exactly one of --translation-dir or --draft-root")

    if args.translation_dir:
        files = [
            (p.stem, p)
            for p in sorted(args.translation_dir.glob("c*.txt"))
            if tl.SCENE_ID_RE.fullmatch(p.stem)
        ]
        source = str(args.translation_dir)
    else:
        files = find_drafts(args.draft_root)
        source = str(args.draft_root)
    if not files:
        raise SystemExit("no translation files or drafts found")

    data, rows = load_character_rows()
    style = gr.load_style()
    terms_data = gr.load_terms()
    audited = [audit_file(sid, path, data, rows, style, terms_data) for sid, path in files]
    merged_usage: dict[str, dict] = {}
    for row in audited:
        for ja, usage in row.get("character_usage", {}).items():
            agg = merged_usage.setdefault(ja, {
                "zh": set(), "scenes": set(), "lines": 0,
                "address_checked": 0, "address_pronoun_allowed": 0,
                "address_usage": Counter(),
            })
            agg["zh"].update(usage["zh"])
            agg["scenes"].update(usage["scenes"])
            agg["lines"] += usage["lines"]
            agg["address_checked"] += usage.get("address_checked", 0)
            agg["address_pronoun_allowed"] += usage.get("address_pronoun_allowed", 0)
            agg["address_usage"].update(usage["address_usage"])
    character_summary = [
        {
            "ja": ja,
            "zh": sorted(x for x in usage["zh"] if x),
            "scene_count": len(usage["scenes"]),
            "line_count": usage["lines"],
            "address_checked": usage.get("address_checked", 0),
            "address_pronoun_allowed": usage.get("address_pronoun_allowed", 0),
            "address_usage": dict(usage["address_usage"]),
        }
        for ja, usage in sorted(merged_usage.items())
    ]
    cross_scene_warnings = []
    for row in character_summary:
        if len(row["zh"]) > 1:
            cross_scene_warnings.append({
                "kind": "same_character_multiple_chinese_names",
                "ja": row["ja"],
                "zh": row["zh"],
                "scenes": row["scene_count"],
            })
    warning_kind_counts = Counter()
    info_kind_counts = Counter()
    for row in audited:
        for warning in row["warnings"]:
            warning_kind_counts[warning["kind"]] += 1
        for info in row.get("info", []):
            info_kind_counts[info.get("kind", "")] += 1
    address_stats = {
        "checked_lines": sum(row.get("address_checked", 0) for row in character_summary),
        "not_in_allowed": warning_kind_counts.get("address_not_in_allowed", 0),
        "missing": warning_kind_counts.get("address_missing", 0),
        "pronoun_allowed": info_kind_counts.get("address_pronoun_allowed", 0),
    }
    report = {
        "generated_at": now_iso(),
        "source": source,
        "file_count": len(audited),
        "error_count": sum(len(x["errors"]) for x in audited),
        "warning_count": sum(len(x["warnings"]) for x in audited) + len(cross_scene_warnings),
        "glossary_versions": gr.snapshot_versions(),
        "address_stats": address_stats,
        "character_summary": character_summary,
        "cross_scene_warnings": cross_scene_warnings,
        "files": audited,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().astimezone().strftime("%Y%m%d-%H%M%S")
    json_path = args.output_dir / f"audit-{stamp}.json"
    md_path = args.output_dir / f"audit-{stamp}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    # stable latest paths for convenience
    (args.output_dir / "latest-audit.json").write_text(json_path.read_text(encoding="utf-8"), encoding="utf-8")
    (args.output_dir / "latest-audit.md").write_text(md_path.read_text(encoding="utf-8"), encoding="utf-8")
    print(json.dumps({
        "files": report["file_count"],
        "errors": report["error_count"],
        "warnings": report["warning_count"],
        "json": str(json_path),
        "markdown": str(md_path),
    }, ensure_ascii=False, indent=2))
    return 0 if report["error_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
