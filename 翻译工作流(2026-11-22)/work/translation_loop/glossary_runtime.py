"""Versioned glossary/style runtime for the translation loop.

A worker pins immutable snapshot files through environment variables:
  FKG_TERMS_FILE, FKG_CHARACTERS_FILE, FKG_STYLE_FILE

When unset, the loader resolves `glossary/current.json`.  Batch runners set the
three environment variables per worker/family so a mutable `current.json` can
never change a scene mid-flight.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GLOSSARY_DIR = ROOT / "work" / "translation_loop" / "glossary"
_CURRENT_FILE = GLOSSARY_DIR / "current.json"
_CACHE: dict[tuple[str, int], Any] = {}


def current_pointer() -> dict[str, Any]:
    if not _CURRENT_FILE.is_file():
        return {}
    return json.loads(_CURRENT_FILE.read_text(encoding="utf-8"))


def resolve_snapshot(env_var: str, default_field: str) -> Path | None:
    raw = os.environ.get(env_var, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    current = current_pointer()
    rel = current.get(default_field)
    if isinstance(rel, str) and rel:
        return (GLOSSARY_DIR / rel).resolve()
    return None


def load_json(path: Path | None) -> dict[str, Any]:
    if path is None or not path.is_file():
        return {}
    key = (str(path), path.stat().st_mtime_ns)
    cached = _CACHE.get(key)
    if cached is None:
        cached = json.loads(path.read_text(encoding="utf-8"))
        _CACHE[key] = cached
    return cached


def load_terms() -> dict[str, Any]:
    return load_json(resolve_snapshot("FKG_TERMS_FILE", "terms_file"))


def load_characters() -> dict[str, Any]:
    return load_json(resolve_snapshot("FKG_CHARACTERS_FILE", "characters_file"))


def load_style() -> dict[str, Any]:
    return load_json(resolve_snapshot("FKG_STYLE_FILE", "style_file"))


def _snapshot_version(data: dict[str, Any]) -> str:
    return str(data.get("version_label") or data.get("version") or "")


def snapshot_versions() -> dict[str, str]:
    return {
        "terms": _snapshot_version(load_terms()),
        "characters": _snapshot_version(load_characters()),
        "style": _snapshot_version(load_style()),
    }


def terms_for_text(text: str) -> tuple[dict[str, Any], ...]:
    entries = load_terms().get("entries") or []
    found = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        ja_forms = [str(x) for x in entry.get("ja") or [] if str(x)]
        if ja_forms and any(form in text for form in ja_forms):
            found.append(entry)
    return tuple(found)


def character_policies_for_speakers(speakers: set[str], source_text: str) -> tuple[dict[str, Any], ...]:
    data = load_characters()
    rows = data.get("characters") or []
    by_ja = {str(row.get("ja")): row for row in rows if isinstance(row, dict) and row.get("ja")}
    default_forms = data.get("address_forms_default") or {}
    overrides = data.get("overrides") or {}
    policies = []
    for ja in sorted(speakers):
        row = by_ja.get(ja) or {}
        override = overrides.get(ja) or {}
        zh = str(override.get("zh_primary") or row.get("zh") or "")
        forms = dict(default_forms)
        for key, rule in (override.get("address_forms") or {}).items():
            forms[key] = rule
        active_forms = []
        for src, rule in forms.items():
            if src not in source_text:
                continue
            if not isinstance(rule, dict):
                continue
            default = str(rule.get("default") or "")
            allowed = [str(x) for x in rule.get("allowed") or [] if str(x)]
            if not allowed and default:
                allowed = [default]
            active_forms.append({
                "ja": src,
                "default": default,
                "allowed": allowed,
            })
        if zh or active_forms or override.get("notes"):
            policies.append({
                "ja": ja,
                "zh": zh,
                "address_forms": active_forms,
                "notes": str(override.get("notes") or ""),
            })
    return tuple(policies)


def source_has_outer_quote(text: str) -> bool:
    value = text.strip()
    return len(value) >= 2 and value.startswith("「") and value.endswith("」")


def output_has_outer_quote(text: str) -> bool:
    return source_has_outer_quote(text)


def _strip_one_outer_pair(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value.startswith("「") and value.endswith("」"):
        return value[1:-1]
    return value


def apply_speaker_quote_policy(text: str, source_text: str, style: dict[str, Any] | None = None) -> str:
    """Apply the configured outer-quote policy to one speaker line.

    `preserve_source_outer` is intentionally deterministic: it does not ask the
    model to decide.  Inner quotes are preserved; only one outer pair is
    normalized.
    """
    if style is None:
        style = load_style()
    policy = str(((style.get("quotes") or {}).get("speaker_outer") or "preserve_source_outer"))
    src_quoted = source_has_outer_quote(source_text)
    out_quoted = output_has_outer_quote(text)
    if policy == "preserve_source_outer":
        if src_quoted and not out_quoted:
            return "「" + text.strip() + "」"
        if not src_quoted and out_quoted:
            return _strip_one_outer_pair(text)
        return text.strip()
    if policy == "strip_outer":
        return _strip_one_outer_pair(text) if out_quoted else text.strip()
    if policy == "convert_cn":
        inner = _strip_one_outer_pair(text) if out_quoted else text.strip()
        return "“" + inner + "”" if src_quoted else inner
    return text


JAPANESE_TERM_FALLBACKS = (
    ("膣内", "小穴里"),
    ("膣奥", "阴道深处"),
    ("膣道", "阴道"),
    ("膣", "阴道"),
)


def normalize_japanese_terms(text: str) -> str:
    """Deterministically replace Japanese-only term forms with Chinese defaults."""
    for ja, zh in JAPANESE_TERM_FALLBACKS:
        text = text.replace(ja, zh)
    return text
