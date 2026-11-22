#!/bin/bash
# 用法: ./装回.sh [译文目录] [package.nw目录]
# 译文目录里的 cXXXXXX.txt / cXXXXXX_2.txt 按文件名匹配场景。
# 每个非空行对应 script.txt 里的一个对话块；空行跳过。
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
GAME="${2:-/mnt/d1/gal/Flower Knight Girl 1.1/package.nw}"
SRC="${1:-$DIR}"

[ -d "$SRC" ] || { echo "错误：找不到译文目录: $SRC" >&2; exit 2; }
[ -d "$GAME/scenes" ] || { echo "错误：找不到游戏目录: $GAME" >&2; exit 2; }

if pgrep -f '/home/a7067567g/apps/nwjs/nw' >/dev/null 2>&1; then
  echo "提示：检测到游戏正在运行，建议先退出游戏，装回后重启。"
fi

python3 - "$SRC" "$GAME" <<'PY'
from __future__ import annotations
import json, re, sys, tarfile
from datetime import datetime
from pathlib import Path

src = Path(sys.argv[1]).resolve()
game = Path(sys.argv[2]).resolve()
BLOCK = re.compile(r'<NAME_PLATE>(.*?)<PAUSE>', re.S)
NAME_RE = re.compile(r'^c\d{6}(?:_2)?\.txt$')
# 行首的“角色名: ”或“角色名：”会被识别为名字；纯正文行则保留原角色名。
NAME_PREFIX = re.compile(r'^([\u3040-\u30ff\u4e00-\u9fffA-Za-z0-9\uFF10-\uFF19・ー 　＆&、＋+()（）·]{1,40})[:：]\s*(.+)$')

files = sorted([p for p in src.iterdir() if p.is_file() and NAME_RE.fullmatch(p.name)])
if not files:
    raise SystemExit(f'{src} 里没有找到 cXXXXXX.txt 译文文件')

pending = []
errors = []
modified_scenes = 0
translated_lines = 0
blank_lines = 0

for tf in files:
    sid = tf.stem
    script_path = game/'scenes'/sid/'script.txt'
    if not script_path.is_file():
        errors.append(f'{tf.name}: 游戏里找不到场景 {sid}')
        continue

    raw = script_path.read_bytes()
    bom = raw.startswith(b'\xef\xbb\xbf')
    if bom: raw = raw[3:]
    raw_text = raw.decode('utf-8')
    crlf = raw_text.count('\r\n') >= raw_text.count('\n')/2
    text = raw_text.replace('\r\n','\n').replace('\r','\n')
    matches = list(BLOCK.finditer(text))

    trans = tf.read_text(encoding='utf-8-sig').splitlines()
    while trans and not trans[-1].strip():
        trans.pop()
    if len(trans) > len(matches):
        errors.append(f'{tf.name}: 译文有 {len(trans)} 行，但游戏对话只有 {len(matches)} 条')
        continue

    parts, last, changed = [], 0, 0
    for i, m in enumerate(matches, 1):
        parts.append(text[last:m.start()])
        raw_line = trans[i-1].strip() if i <= len(trans) else ''
        if not raw_line:
            blank_lines += 1
            parts.append(m.group(0))
        else:
            content = m.group(1)
            old_name = '' if content.startswith('\n') else content.split('\n',1)[0]
            new_name, msg = old_name, raw_line

            # 明确指定名字：`角色名|译文` 或 `角色名: 译文`
            if '|' in raw_line:
                left, right = raw_line.split('|', 1)
                new_name, msg = left.strip(), right.strip()
            else:
                mm = NAME_PREFIX.match(raw_line)
                if mm:
                    new_name, msg = mm.group(1).strip(), mm.group(2).strip()

            if not msg:
                blank_lines += 1
                parts.append(m.group(0))
            else:
                if '<NAME_PLATE>' in msg or '<PAUSE>' in msg or '<NAME_PLATE>' in new_name or '<PAUSE>' in new_name:
                    errors.append(f'{tf.name}: 第 {i} 行含有保留标签')
                    break
                parts.append(f'<NAME_PLATE>{new_name}\n{msg}\n<PAUSE>')
                changed += 1
                translated_lines += 1
        last = m.end()
    if errors:
        continue
    parts.append(text[last:])

    if changed:
        new_text = ''.join(parts)
        if crlf:
            new_text = new_text.replace('\n','\r\n')
        data = new_text.encode('utf-8')
        if bom: data = b'\xef\xbb\xbf' + data
        pending.append((sid, data))
        modified_scenes += 1

if errors:
    print('装回未执行，发现问题：', file=sys.stderr)
    for e in errors[:80]:
        print(' -', e, file=sys.stderr)
    if len(errors) > 80:
        print(f' ... 共 {len(errors)} 条', file=sys.stderr)
    raise SystemExit(1)

if not pending:
    print(f'共检查 {len(files)} 个译文文件，没有非空译文，未修改游戏。')
    raise SystemExit(0)

stamp = datetime.now().strftime('%Y%m%d-%H%M%S')
backup = game/f'backup_translation_{stamp}.tar.gz'
with tarfile.open(backup, 'w:gz') as tf:
    for sid, _ in pending:
        p = game/'scenes'/sid/'script.txt'
        tf.add(p, arcname=f'scenes/{sid}/script.txt')
    sc = game/'data'/'scripts'/'data'/'sceneData.js'
    if sc.exists():
        tf.add(sc, arcname='data/scripts/data/sceneData.js')

for sid, data in pending:
    (game/'scenes'/sid/'script.txt').write_bytes(data)

# 重建 sceneData.js
scene_data = {}
for d in sorted((p for p in (game/'scenes').iterdir() if p.is_dir()), key=lambda p:p.name):
    sp = d/'script.txt'
    if not sp.is_file():
        continue
    sid7 = d.name[1:7]
    form = 2 if '_' in d.name else 1
    scene_data[d.name] = {'SCRIPTS': {'PART1': {
        'SCRIPT': sp.read_text(encoding='utf-8').split('\n'),
        'HIERARCHY': {'pairList': []},
        'NAME': d.name,
        'THUMBNAIL': f'r18_{sid7}_000' if form == 1 else f'r18_{sid7}_100',
        'ANIMATED': '1' if (d/'spines').exists() else '0',
    }}}
out = game/'data'/'scripts'/'data'/'sceneData.js'
out.parent.mkdir(parents=True, exist_ok=True)
text = 'sceneData = ' + json.dumps(scene_data, ensure_ascii=False, indent=2)
if out.exists() and b'\r\n' in out.read_bytes():
    text = text.replace('\n','\r\n')
out.write_bytes(text.encode('utf-8'))

print(f'检查译文文件: {len(files)} 个')
print(f'修改场景: {modified_scenes} 个')
print(f'写入译文: {translated_lines} 条')
print(f'跳过空行: {blank_lines} 条')
print(f'备份: {backup}')
print('已重建 sceneData.js，重启游戏后生效。')
PY
