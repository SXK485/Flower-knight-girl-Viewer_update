# 翻译滑窗原型

这是 `translation_loop.py` 的第一版原型。默认使用 mock 跑通状态机，也可以通过外部命令接真实模型：

- 原文对话块解析
- 5 个结构 override 的保留空行
- 已定稿的“原文 + 译文”pair 滚动窗口
- 后文参考窗口
- 单行 JSON 输出门禁
- 接受/拒绝 ledger
- 草稿落盘
- 确定性 review

真实模型通过 `--command` 接入；目前内置了一个 DeepSeek 适配器。

## 文件位置

```text
work/translation_loop/
├── translation_loop.py
├── deepseek_translator.py
├── plan_batches.py
├── run_batch.py
├── compare_modes.py
├── README.md
├── tests/test_translation_loop.py
└── results/
    ├── c100001-mode-a/
    ├── c100001-mode-b/
    └── c100001-comparison/
```

`results/` 里是用真实 DeepSeek 模型跑完的 c100001 双模式结果：

- A：严格 5 槽；
- B：质量优先；
- `c100001-comparison/comparison.md` 是 88 行逐行对照。

每个 run 目录还保留 prompt、ledger、review 和确定性的 mock/真实测试记录。

## 快速使用

```bash
cd /home/a7067567g/下载/deepseek/70-翻译专用

# 严格 5 槽：4 条已完成 pair + 当前原文
python3 work/translation_loop/translation_loop.py \
  init c100001 --history-pairs 4 --lookahead 0 --reset

# 质量优先：5 条已完成 pair + 当前原文 + 2 条后文参考
python3 work/translation_loop/translation_loop.py \
  init c100001 --history-pairs 5 --lookahead 2 --reset

# 看下一步 prompt
python3 work/translation_loop/translation_loop.py prompt c100001

# 走一步（默认 mock）
python3 work/translation_loop/translation_loop.py step c100001

# 一次跑完并 review
python3 work/translation_loop/translation_loop.py \
  run c100001 --limit 200

# 查看状态 / 草稿 / review
python3 work/translation_loop/translation_loop.py status c100001
python3 work/translation_loop/translation_loop.py draft c100001
python3 work/translation_loop/translation_loop.py review c100001
```

指定其他输出目录：

```bash
python3 work/translation_loop/translation_loop.py \
  --run-root /tmp/fkg-loop init c100001 --history-pairs 4 --lookahead 0
```

## 参数语义

| 参数 | 默认 | 含义 |
|---|---:|---|
| `--history-pairs` | 4 | 保留多少条已定稿的“原文 + 译文”pair |
| `--lookahead` | 0 | 当前行之后再看多少条原文作为后文参考 |
| `--limit` | 10000 | 一次 `run` 最多执行多少步 |
| `--max-retries` | 2 | 同一行连续拒绝多少次后标记 `needs_human` |

严格 5 槽：`history-pairs=4, lookahead=0`，即 4 条 pair + 当前原文。  
质量优先：`history-pairs=5, lookahead=2`，即 5 条 pair + 当前原文 + 2 条后文参考。

## 单步状态机

```text
检查当前行是否为 preserve
  -> 是：自动写入空行，ledger 记 preserved，推进下一行
  -> 否：构建窗口 prompt
        -> 调 translator
        -> G0 JSON 校验
        -> G1 line 必须等于 next_line
        -> G2 speaker 必须匹配术语表
        -> G3 text 不带真实换行/禁止标签/旁白名字牌/重复 speaker 前缀/日文专用汉字
        -> 通过：写 accepted、ledger、draft，推进
        -> 失败：不推进，只增加 retries 和 last_error
```

## 输出协议

模型必须只输出一个 JSON 对象：

```json
{"line": 17, "speaker": "忍冬", "text": "译文内容"}
```

旁白：

```json
{"line": 18, "speaker": "", "text": "旁白译文"}
```

`text` 内部需要换行时写两个字符 `\n`，不能写真实换行。  
禁止 Markdown 代码块、解释、`<NAME_PLATE>`、`<PAUSE>`。

## 真实模型接口

内置了一个 DeepSeek 外部命令适配器：

```text
work/translation_loop/deepseek_translator.py
```

它把 `TRANSLATION-PERSONA.md` 作为 system message，温度 0，JSON 模式，并带 prompt 缓存。
运行真实模型：

```bash
DSH_HOME=/home/a7067567g/.dsh-translation \
python3 work/translation_loop/translation_loop.py \
  --run-root work/translation_loop/results/real-test \
  run c100001 \
  --command '/usr/bin/python3 work/translation_loop/deepseek_translator.py' \
  --limit 200
```

## 外部翻译器接口

mock 仅用于跑状态机。真实接入时传：

```bash
python3 work/translation_loop/translation_loop.py \
  run c100001 --command 'your-translator-command'
```

外部命令约定：

- 从 stdin 读取完整 prompt；
- 向 stdout 输出一个 JSON 对象；
- 退出码必须为 0。

## 产出结构

```text
<run-root>/<scene_id>/
├── state.json
├── draft.txt
├── ledger.jsonl
├── review.json
├── review.md
└── prompts/
    ├── line-0001.md
    └── ...
```

## 5 个结构 override

`work/preflight/structural_overrides.json` 会被自动读取。

例如 `c130901` 的游戏第 10 行是原文中没有的旧译文块：

- 第 10 行自动写成空行；
- 不调用 translator；
- ledger 记录 `preserved`；
- 后续原文行继续对齐。

## 当前限制

- 默认 mock，真实模型需要 `--command` 接外部适配器；
- 没有自动生成 `rolling_summary`，目前只能通过 `summary` 子命令手动写；
- review 只做确定性结构检查，不做语义 QA；
- 不写 `译文/`，不运行 `装回.sh`；
- 不是最终编排，只是滑窗执行器的原型。

## 测试

```bash
cd /home/a7067567g/下载/deepseek/70-翻译专用
python3 -m unittest discover -s work/translation_loop/tests -v
```

当前覆盖：

- 5 个 override 的行数/空行位置；
- 窗口连续性；
- prompt 分节；
- JSON/speaker/line/标签/真实换行/代码围栏/重复 speaker 前缀/日文专用汉字拒绝；
- 拒绝不推进、重试后接受；
- c130901 全量 mock 跑完并 review 通过。


## 当前 Prompt 版本与批量试点

Prompt 版本：`b-2026-11-22.4`。

当前 prompt 在原有 B 窗口上增加了：

- 场景家族标记，`_2` 会显示与本体同族；
- 本场景所有 named speaker 的人名映射，以及旁白/正文中出现的 glossary 名字；
- 可选的 `# 角色与连续性` 区块，由批处理 runner 注入同角色上一场景尾部或同族本体尾部；
- 按场景注入匹配的术语快照和角色称呼策略；
- 输出前自检，以及重复 speaker 前缀、日文专用汉字、引号策略等机械门禁。

术语/风格/角色策略使用版本化快照：

```text
work/translation_loop/glossary/current.json
work/translation_loop/glossary/versions/
work/translation_loop/glossary/pending/
```

新增工具：

- `glossary_admin.py`：校验、发布、diff、影响扫描；
- `normalize_quotes.py`：按 `preserve_source_outer` 统一已有译文引号；
- `audit_consistency.py`：跨场景名字/称呼/引号/日文残留审计。

批量规划：

```bash
python3 work/translation_loop/plan_batches.py \
  --target-files 200 --workers 6 \
  --out-dir work/translation_loop/batches/pilot-200
```

批量执行器默认只读 dry-run，不会调用翻译 API，也不会写 `译文/`：

```bash
python3 work/translation_loop/run_batch.py \
  --manifest work/translation_loop/batches/pilot-200/manifest.json \
  --run-root work/translation_loop/results/pilot-200 \
  --concurrency 6 --glossary-mode frozen --dry-run
```

去掉 `--dry-run` 才会真正开始逐场景翻译。pilot 建议使用 `--glossary-mode frozen`，让所有 worker 固定到 manifest 里的 v0002 快照；长期运行时才考虑 `--glossary-mode rolling`，并且只在场景家族边界切换版本。

批处理输出保留在 run-root，提升到正式 `译文/` 和装回游戏都需要单独验收。

## 真实双模式结果

`results/c100001-comparison/REAL_RUN.md` 记录了 88 句 c100001 的真实模型对比：

- A：4 条已完成 pair + 当前原文；
- B：5 条已完成 pair + 当前原文 + 2 条后文参考；
- 两者都 88/88 完成，`格式校对.sh` 均通过；
- 23 行完全相同，65 行不同，平均相似度 0.9176；
- 完整逐行对照见 `results/c100001-comparison/comparison.md`。
