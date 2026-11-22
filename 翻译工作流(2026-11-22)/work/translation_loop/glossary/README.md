# 版本化术语与人设策略

## 目录

```text
glossary/
├── current.json
├── versions/
│   ├── terms-v0001.json
│   ├── terms-v0002.json
│   ├── characters-v0001.json
│   ├── characters-v0002.json
│   ├── style-v0001.json
│   └── style-v0002.json
├── pending/
└── README.md
```

- `versions/*` 是**不可变快照**，发布后不要再手工修改。
- `current.json` 只是当前版本指针，带各文件 SHA-256。
- `pending/*` 收集尚未批准的新词、称呼和风格变更。
- worker 不读 `current.json`；它由 runner 固定到 manifest 里记录的三个快照路径。

## 启动前

```bash
python3 work/translation_loop/glossary_admin.py validate
```

## 发布新版本

1. 从当前快照复制出候选文件，例如 `terms-v0003.json`。
2. 修改候选文件，写入 `pending/` 或临时目录。
3. 运行 `validate` 和 `diff`：

```bash
python3 work/translation_loop/glossary_admin.py \
  diff --old work/translation_loop/glossary/versions/terms-v0002.json \
       --new /tmp/terms-v0003.json
```

4. 扫描影响场景：

```bash
python3 work/translation_loop/glossary_admin.py \
  impact --old work/translation_loop/glossary/versions/terms-v0002.json \
         --new /tmp/terms-v0003.json
```

5. 审批后发布：

```bash
python3 work/translation_loop/glossary_admin.py publish \
  --version v0003 \
  --terms /tmp/terms-v0003.json \
  --characters /tmp/characters-v0003.json \
  --style /tmp/style-v0003.json
```

## 并发运行时的更新规则

- **Pilot 200 默认冻结 v0002。** 运行中只把新发现写入 `pending/`，不热更。
- 长期全量运行才开启家族边界热更：
  - 当前场景家族继续使用旧快照；
  - 下一个场景家族开始时，runner 读取 `current.json`；
  - 同一场景家族（base + `_2`）必须使用同一快照；
  - 发布后由 `impact` 生成受影响场景列表，后续修复批次重跑 `stale` 场景。
- 禁止：中途覆盖正在使用的快照、直接改 `current.json`、让多个 worker 共用可变的术语对象。
- 术语变化会改变 prompt；旧缓存不会误用新结果。

## 引号策略

`style-v0002.json` 当前使用：

```text
speaker_outer = preserve_source_outer
```

规则：

- 源文台词最外层有 `「」`，译文保留一对；
- 源文没有，译文不要额外添加；
- 旁白不改；
- 嵌套引号保留，只有最外层做统一。

该策略由 `glossary_runtime.apply_speaker_quote_policy()` 在 JSON 校验通过后确定性执行；引号策略变化不需要重跑模型，可以用 `normalize_quotes.py` 对已有文件或 staging 做统一重渲染。
