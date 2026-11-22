# FKG 翻译工作流（可复现）

这套目录从当前翻译工程中抽取，用来复现和继续维护 FKG 场景译文。它只包含：

- 翻译人设
- 翻译状态机 / DeepSeek 适配器
- 术语、角色称呼和风格快照
- 人名清单
- 格式校对、装回、JSON 导出工具

**不包含原始游戏资源、游戏图片、语音、视频，也不包含原始日文场景全文。**

## 目录结构

```text
.
├── TRANSLATION-PERSONA.md              # 唯一 system prompt / 人设
├── requirements.txt
├── FlowerKnightGirl_原文/
│   └── 译文/
│       ├── 人名清单.csv                # 日文名 -> 中文主译名/称呼
│       ├── 格式校对.sh
│       └── 装回.sh
└── work/
    ├── preflight/
    │   └── structural_overrides.json    # 5 个结构性保留块
    └── translation_loop/
        ├── translation_loop.py          # 滑窗状态机
        ├── deepseek_translator.py       # DeepSeek 外部命令适配器
        ├── glossary_runtime.py
        ├── audit_consistency.py         # 跨场景审计
        ├── glossary_admin.py            # 术语快照管理
        ├── plan_batches.py / run_batch.py
        ├── normalize_quotes.py
        ├── compare_modes.py
        ├── export_json_cn.py            # 导出旧版 json_cn.zip
        ├── glossary/
        │   ├── current.json
        │   └── versions/
        │       ├── terms-v0006.json
        │       ├── characters-v0006.json
        │       └── style-v0002.json
        └── tests/test_translation_loop.py
```

## 1. 准备环境

需要 Python 3.10+，安装依赖：

```bash
python3 -m pip install -r requirements.txt
```

准备原始场景文本：

```text
FlowerKnightGirl_原文/c100001.txt
FlowerKnightGirl_原文/c100001_2.txt
...
```

这些文件是翻译输入，不放进 Git 仓库；从本地游戏/原始数据源取得。

准备 Viewer 的 `package.nw` 路径：

```bash
export FKG_GAME_PACKAGE="/path/to/Flower Knight Girl 1.1/package.nw"
export FKG_GAME_SCENES="$FKG_GAME_PACKAGE/scenes"
```

DeepSeek 适配器默认从：

```text
$DSH_HOME/.credentials.yaml
```

读取：

```yaml
refs:
  DEEPSEEK_API_KEY: "你的 key"
```

也可以按 `deepseek_translator.py` 的说明调整 `DSH_HOME`。

## 2. 翻译一个场景

以下命令都在本目录根执行。

初始化一个质量优先窗口（5 条已完成 pair + 当前原文 + 2 条后文参考）：

```bash
python3 work/translation_loop/translation_loop.py \
  --game-scenes "$FKG_GAME_PACKAGE/scenes" \
  --run-root work/translation_loop/runs/c100001 \
  init c100001 --history-pairs 5 --lookahead 2 --reset
```

运行真实 DeepSeek 翻译：

```bash
python3 work/translation_loop/translation_loop.py \
  --game-scenes "$FKG_GAME_PACKAGE/scenes" \
  --run-root work/translation_loop/runs/c100001 \
  run c100001 \
  --command "python3 $PWD/work/translation_loop/deepseek_translator.py" \
  --limit 500 --max-retries 3
```

查看状态、草稿和确定性 review：

```bash
python3 work/translation_loop/translation_loop.py \
  --run-root work/translation_loop/runs/c100001 status c100001
python3 work/translation_loop/translation_loop.py \
  --run-root work/translation_loop/runs/c100001 draft c100001
python3 work/translation_loop/translation_loop.py \
  --run-root work/translation_loop/runs/c100001 review c100001
```

审核后将最终译文放到：

```text
FlowerKnightGirl_原文/译文/c100001.txt
```

每行对应游戏中的一个 `<NAME_PLATE>...<PAUSE>` 对话块；行内换行使用字面量 `\n`。

## 3. 格式检查和装回

格式校对：

```bash
bash FlowerKnightGirl_原文/译文/格式校对.sh \
  "$PWD/FlowerKnightGirl_原文/译文" \
  "$FKG_GAME_PACKAGE"
```

装回游戏（会先备份并重建 `sceneData.js`）：

```bash
bash FlowerKnightGirl_原文/译文/装回.sh \
  "$PWD/FlowerKnightGirl_原文/译文" \
  "$FKG_GAME_PACKAGE"
```

## 4. 导出为仓库旧版翻译包格式

```bash
python3 work/translation_loop/export_json_cn.py \
  --output json_cn.zip \
  --game-scenes "$FKG_GAME_PACKAGE/scenes"
```

输出：

```text
json_cn/
  c100001_script.json
  ...
```

格式与仓库之前的 `全场景翻译(至2023-11-16)/json_cn.zip`、
`全场景翻译(至2024-01-18)/json_cn.zip` 一致：

```json
[
  {"name": "角色名", "message": "台词"},
  {"message": "旁白"}
]
```

`name` 字段使用当前译文里的中文角色名；旁白没有 `name`。

## 5. 术语和风格

- 术语快照由 `glossary/current.json` 指向。
- 不直接修改已经发布的快照；新词先进入 `glossary/pending/`。
- 修改后运行：

```bash
python3 work/translation_loop/glossary_admin.py validate
python3 work/translation_loop/translation_loop.py review <scene_id>
```

- `style-v0002.json` 的引号策略是 `preserve_source_outer`。
- 详细状态机和输出协议见 `work/translation_loop/README.md`。

## 6. 版权

本目录只放翻译流程与工具，不包含游戏资源或原始完整脚本。译文和游戏素材的使用请遵守原作品版权及所在地区法律。


## 7. 自测

```bash
export FKG_GAME_SCENES="$FKG_GAME_PACKAGE/scenes"
python3 -m unittest discover -s work/translation_loop/tests -v
```

测试需要原始 `c100001.txt` 等场景文件和本地 `package.nw/scenes`；如果未提供，会整体 skip，不会误报失败。
