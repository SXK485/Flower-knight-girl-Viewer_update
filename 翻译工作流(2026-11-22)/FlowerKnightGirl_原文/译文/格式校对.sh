#!/bin/bash
# 用法: ./格式校对.sh [译文目录] [package.nw目录]
# 只读检查，不修改任何文件。
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
SRC="${1:-$DIR}"
GAME="${2:-/mnt/d1/gal/Flower Knight Girl 1.1/package.nw}"

[ -d "$SRC" ] || { echo "错误：找不到译文目录: $SRC" >&2; exit 2; }
[ -d "$GAME/scenes" ] || { echo "错误：找不到游戏目录: $GAME" >&2; exit 2; }

python3 - "$SRC" "$GAME" <<'PY'
from __future__ import annotations
import re, sys
from pathlib import Path

src = Path(sys.argv[1]).resolve()
game = Path(sys.argv[2]).resolve()
BLOCK = re.compile(r'<NAME_PLATE>(.*?)<PAUSE>', re.S)
NAME_RE = re.compile(r'^c\d{6}(?:_2)?\.txt$')
NAME_PREFIX = re.compile(r'^([\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9\uFF10-\uFF19・ー 　＆&、＋+()（）·]{1,40})[:：]\s*(.+)$')

files = sorted([p for p in src.iterdir() if p.is_file() and NAME_RE.fullmatch(p.name)])
if not files:
    print(f'{src} 里没有找到 cXXXXXX.txt 译文文件')
    raise SystemExit(0)

too_many_files = 0
too_many_lines = 0
too_few_files = 0
too_few_lines = 0
missing_name = 0
extra_name = 0
details = []

def parse_name(c: str):
    if c.startswith('\n'):
        return ''
    return c.split('\n', 1)[0]

for tf in files:
    sid = tf.stem
    sp = game/'scenes'/sid/'script.txt'
    if not sp.is_file():
        details.append(f'[缺场景] {tf.name}: 游戏里找不到这个场景')
        too_few_files += 1
        continue
    text = sp.read_text(encoding='utf-8')
    blocks = BLOCK.findall(text)
    trans = tf.read_text(encoding='utf-8-sig').splitlines()
    while trans and not trans[-1].strip():
        trans.pop()

    if len(trans) > len(blocks):
        n = len(trans) - len(blocks)
        too_many_files += 1
        too_many_lines += n
        details.append(f'[多行] {tf.name}: 译文 {len(trans)} 行，游戏只有 {len(blocks)} 条（多 {n} 行）')
    elif len(trans) < len(blocks):
        n = len(blocks) - len(trans)
        too_few_files += 1
        too_few_lines += n
        details.append(f'[缺行] {tf.name}: 译文 {len(trans)} 行，游戏有 {len(blocks)} 条（少 {n} 行）')

    for i, c in enumerate(blocks[:len(trans)], 1):
        raw = trans[i-1].strip()
        if not raw:
            continue  # 空行表示跳过，不检查名字

        game_name = parse_name(c)
        explicit = False
        trans_name = ''
        msg = raw

        if '|' in raw:
            left, right = raw.split('|', 1)
            explicit = True
            trans_name = left.strip()
            msg = right.strip()
        else:
            m = NAME_PREFIX.match(raw)
            if m:
                explicit = True
                trans_name = m.group(1).strip()
                msg = m.group(2).strip()

        # 空正文视为跳过
        if not msg:
            continue

        if game_name and not trans_name:
            missing_name += 1
            if explicit:
                details.append(f'[有名字的没名字] {tf.name} 第 {i} 行: 游戏名字「{game_name}」，译文显式清空了名字')
            else:
                details.append(f'[有名字的没名字] {tf.name} 第 {i} 行: 游戏名字「{game_name}」，译文没写名字')
        elif not game_name and trans_name:
            extra_name += 1
            details.append(f'[没名字的有名字] {tf.name} 第 {i} 行: 游戏里没有名字，译文写了「{trans_name}」')

print(f'检查译文文件: {len(files)} 个')
print(f'多行: {too_many_files} 个文件 / {too_many_lines} 行')
print(f'缺行: {too_few_files} 个文件 / {too_few_lines} 行')
print(f'有名字的没名字: {missing_name} 条')
print(f'没名字的有名字: {extra_name} 条')

if details:
    print('\n问题明细（最多显示 200 条）：')
    for d in details[:200]:
        print(' ', d)
    if len(details) > 200:
        print(f'  ... 共 {len(details)} 条')
    raise SystemExit(1)
else:
    print('\n格式检查通过。')
    raise SystemExit(0)
PY
