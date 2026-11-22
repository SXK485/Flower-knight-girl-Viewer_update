#!/usr/bin/env python3
"""Compare two translation-mode drafts line by line."""
from __future__ import annotations

import argparse
import difflib
import json
import re
from datetime import datetime
from pathlib import Path

KANA_RE = re.compile(r"[\u3040-\u30ff]")
SPEAKER_PREFIX_RE = re.compile(r"^([^:：]{1,40})[:：]\s*")


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()


def prefix(line: str) -> str:
    match = SPEAKER_PREFIX_RE.match(line)
    return match.group(1).strip() if match else ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--a", type=Path, required=True)
    parser.add_argument("--b", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True, help="markdown output file; JSON uses the same stem")
    parser.add_argument("--label-a", default="模式 A")
    parser.add_argument("--label-b", default="模式 B")
    args = parser.parse_args()

    a = read_lines(args.a)
    b = read_lines(args.b)
    if len(a) != len(b):
        raise SystemExit(f"line count mismatch: {len(a)} != {len(b)}")

    rows = []
    ratios = []
    same_names = 0
    for n, (left, right) in enumerate(zip(a, b), 1):
        ratio = difflib.SequenceMatcher(None, left, right, autojunk=False).ratio()
        ratios.append(ratio)
        if prefix(left) == prefix(right):
            same_names += 1
        rows.append({"line": n, "a": left, "b": right, "ratio": round(ratio, 4)})

    total_chars_a = sum(len(x) for x in a)
    total_chars_b = sum(len(x) for x in b)
    stats = {
        "total_lines": len(a),
        "identical_lines": sum(1 for x, y in zip(a, b) if x == y),
        "different_lines": sum(1 for x, y in zip(a, b) if x != y),
        "same_speaker_prefix": same_names,
        "total_chars_a": total_chars_a,
        "total_chars_b": total_chars_b,
        "avg_chars_a": round(total_chars_a / len(a), 2),
        "avg_chars_b": round(total_chars_b / len(b), 2),
        "avg_similarity": round(sum(ratios) / len(ratios), 4),
        "ratio_lt_0_80": sum(1 for x in ratios if x < 0.80),
        "ratio_0_80_to_0_95": sum(1 for x in ratios if 0.80 <= x < 0.95),
        "ratio_ge_0_95": sum(1 for x in ratios if x >= 0.95),
        "a_internal_literal_newlines": sum(1 for x in a if "\\n" in x),
        "b_internal_literal_newlines": sum(1 for x in b if "\\n" in x),
        "a_residual_kana_lines": sum(1 for x in a if KANA_RE.search(x)),
        "b_residual_kana_lines": sum(1 for x in b if KANA_RE.search(x)),
        "a_longer_lines": sum(1 for x, y in zip(a, b) if len(x) > len(y)),
        "b_longer_lines": sum(1 for x, y in zip(a, b) if len(y) > len(x)),
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    md_path = args.out.with_suffix(".md")
    json_path = args.out.with_suffix(".json")
    md_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(
        json.dumps({"stats": stats, "rows": rows}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"# c100001 对比：{args.label_a} vs {args.label_b}",
        "",
        f"生成时间：{stats['generated_at']}",
        "",
        "## 指标",
        "",
        f"| 指标 | {args.label_a} | {args.label_b} |",
        "|---|---:|---:|",
        f"| 总行数 | {stats['total_lines']} | {stats['total_lines']} |",
        f"| 完全相同行 | {stats['identical_lines']} | {stats['identical_lines']} |",
        f"| 不同行 | {stats['different_lines']} | {stats['different_lines']} |",
        f"| 平均字符数 | {stats['avg_chars_a']} | {stats['avg_chars_b']} |",
        f"| 总字符数 | {stats['total_chars_a']} | {stats['total_chars_b']} |",
        f"| 含字面量换行行数 | {stats['a_internal_literal_newlines']} | {stats['b_internal_literal_newlines']} |",
        f"| 残留假名行数 | {stats['a_residual_kana_lines']} | {stats['b_residual_kana_lines']} |",
        "",
        "## 差异分布",
        "",
        f"- 平均文本相似度：{stats['avg_similarity']}",
        f"- 相似度 < 0.80：{stats['ratio_lt_0_80']} 行",
        f"- 0.80 ≤ 相似度 < 0.95：{stats['ratio_0_80_to_0_95']} 行",
        f"- 相似度 ≥ 0.95：{stats['ratio_ge_0_95']} 行",
        f"- A 比 B 长：{stats['a_longer_lines']} 行",
        f"- B 比 A 长：{stats['b_longer_lines']} 行",
        "",
        "## 逐行对照",
        "",
        f"| 行 | {args.label_a} | {args.label_b} | 相似度 |",
        "|---:|---|---|---:|",
    ]
    for row in rows:
        left = row["a"].replace("|", "\\|")
        right = row["b"].replace("|", "\\|")
        lines.append(f"| {row['line']} | {left} | {right} | {row['ratio']} |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print(f"report={md_path}")
    print(f"json={json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
