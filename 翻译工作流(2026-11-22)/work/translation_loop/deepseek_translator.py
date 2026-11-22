#!/usr/bin/env python3
"""External translator adapter for translation_loop.py.

Reads the sliding-window prompt from stdin, calls DeepSeek chat completion with
TRANSLATION-PERSONA.md as the system message, and prints exactly the model's
JSON text to stdout.

Environment:
  DSH_HOME                 credential home (default: ~/.dsh)
  FKG_TRANSLATOR_MODEL     model id (default: deepseek-chat)
  FKG_TRANSLATOR_CACHE     set to 0 to disable the prompt cache
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
PERSONA_FILE = Path(os.environ.get("FKG_PERSONA_FILE", str(ROOT / "TRANSLATION-PERSONA.md")))
CACHE_DIR = ROOT / "work" / "translation_loop" / "cache" / "deepseek"


def load_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def load_api_key() -> str:
    dsh_home = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh")))
    credentials = dsh_home / ".credentials.yaml"
    if not credentials.is_file():
        raise RuntimeError(f"credentials file not found: {credentials}")
    data = yaml.safe_load(credentials.read_text(encoding="utf-8")) or {}
    key = (data.get("refs") or {}).get("DEEPSEEK_API_KEY")
    if not key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    return str(key)


def install_proxy_env() -> None:
    dsh_home = Path(os.environ.get("DSH_HOME", str(Path.home() / ".dsh")))
    values = load_env_file(dsh_home / ".env")
    for key in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY"):
        if values.get(key) and not os.environ.get(key):
            os.environ[key] = values[key]



def normalize_content(content: str) -> str:
    """Normalize JSON text newlines to the literal backslash-n form expected by the loop."""
    try:
        value = json.loads(content)
    except json.JSONDecodeError:
        return content
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        value["text"] = value["text"].replace("\r\n", "\\n").replace("\r", "\\n").replace("\n", "\\n")
    return json.dumps(value, ensure_ascii=False)


def request_translation(prompt: str) -> str:
    install_proxy_env()
    persona = PERSONA_FILE.read_text(encoding="utf-8").strip()
    model = os.environ.get("FKG_TRANSLATOR_MODEL", "deepseek-chat")
    cache_enabled = os.environ.get("FKG_TRANSLATOR_CACHE", "1") != "0"
    cache_key = hashlib.sha256((model + "\0" + persona + "\0" + prompt).encode("utf-8")).hexdigest()
    cache_file = CACHE_DIR / f"{cache_key}.json"
    if cache_enabled and cache_file.is_file():
        cached = json.loads(cache_file.read_text(encoding="utf-8"))
        return normalize_content(str(cached["content"]))

    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": persona},
            {"role": "user", "content": prompt},
        ],
        "temperature": float(os.environ.get("FKG_TRANSLATOR_TEMPERATURE", "0")),
        "max_tokens": int(os.environ.get("FKG_TRANSLATOR_MAX_TOKENS", "1200")),
        "response_format": {"type": "json_object"},
    }
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {load_api_key()}",
    }
    url = "https://api.deepseek.com/chat/completions"
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, data=payload, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str) or not content.strip():
                raise RuntimeError("provider returned empty content")
            content = normalize_content(content)
            if cache_enabled:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(json.dumps({
                    "model": model,
                    "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                    "content": content,
                }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            return content
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code not in (429, 500, 502, 503, 504) or attempt == 4:
                detail = exc.read().decode("utf-8", "replace")[:800]
                raise RuntimeError(f"DeepSeek HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, RuntimeError) as exc:
            last_error = exc
            if attempt == 4:
                raise
        time.sleep(min(2 ** attempt, 16))
    raise RuntimeError(f"DeepSeek request failed: {last_error}")


def main() -> int:
    prompt = sys.stdin.read()
    if not prompt.strip():
        print("empty prompt on stdin", file=sys.stderr)
        return 2
    try:
        content = request_translation(prompt)
    except Exception as exc:
        print(f"translation request failed: {exc}", file=sys.stderr)
        return 1
    print(content)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
