# Pending Glossary Changes

这里放尚未发布的术语/称呼/风格候选。

建议命名：

```text
YYYYMMDD-<short-slug>.json
```

每个候选至少写：

```json
{
  "kind": "term",
  "target_id": "term-vagina-inner",
  "reason": "pilot 中发现同一场景出现「膣内」和「膣道」混用",
  "proposed": {
    "ja": ["膣内"],
    "zh": {"default": "小穴里", "variants": ["阴道内"]}
  },
  "affected_scenes": ["c154413"]
}
```

规则：

- 不直接修改 `versions/` 下已发布快照。
- pilot 期间只收集，不热更。
- 审批后通过 `glossary_admin.py publish` 发布新版本。
- 发布后运行 `impact`，把受影响场景标为 `stale` 并安排修复批次。
