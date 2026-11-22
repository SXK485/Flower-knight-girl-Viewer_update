# FKG Translation Workflow (Reproducible)

This directory contains the translation workflow used for this project:

- translation persona
- sliding-window translation state machine and DeepSeek adapter
- versioned terminology, character-address and style snapshots
- name glossary
- format checker, game installer, and json_cn exporter

It does NOT contain game assets, audio, images, videos, or the full original
Japanese scene scripts.

## Setup

```bash
python3 -m pip install -r requirements.txt
export FKG_GAME_PACKAGE="/path/to/package.nw"
```

Put the original scene files in:

```text
FlowerKnightGirl_原文/cXXXXXX.txt
```

The DeepSeek adapter reads `$DSH_HOME/.credentials.yaml`:

```yaml
refs:
  DEEPSEEK_API_KEY: "your key"
```

## Run

```bash
python3 work/translation_loop/translation_loop.py \
  --game-scenes "$FKG_GAME_PACKAGE/scenes" \
  --run-root work/translation_loop/runs/c100001 \
  init c100001 --history-pairs 5 --lookahead 2 --reset

python3 work/translation_loop/translation_loop.py \
  --game-scenes "$FKG_GAME_PACKAGE/scenes" \
  --run-root work/translation_loop/runs/c100001 \
  run c100001 \
  --command "python3 $PWD/work/translation_loop/deepseek_translator.py" \
  --limit 500 --max-retries 3
```

Final translated files go to:

```text
FlowerKnightGirl_原文/译文/cXXXXXX.txt
```

## Validate, install, export

```bash
bash FlowerKnightGirl_原文/译文/格式校对.sh \
  "$PWD/FlowerKnightGirl_原文/译文" "$FKG_GAME_PACKAGE"

bash FlowerKnightGirl_原文/译文/装回.sh \
  "$PWD/FlowerKnightGirl_原文/译文" "$FKG_GAME_PACKAGE"

python3 work/translation_loop/export_json_cn.py \
  --output json_cn.zip --game-scenes "$FKG_GAME_PACKAGE/scenes"
```

The exported `json_cn.zip` matches the format used by previous translation
packs in this repository: a `json_cn/` directory of per-scene JSON arrays.

No game assets are included.


## Self-test

```bash
export FKG_GAME_SCENES="$FKG_GAME_PACKAGE/scenes"
python3 -m unittest discover -s work/translation_loop/tests -v
```

The tests skip cleanly when the original scene fixtures or local game scenes are
not present.
