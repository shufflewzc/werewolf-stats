from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")


def china_now_label() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S 中国时间")


def load_ai_settings(
    load_meta_value: Callable[[str], str | None],
    *,
    settings_key: str,
    default_model: str,
) -> dict[str, str]:
    raw_value = load_meta_value(settings_key) or ""
    empty_payload = {
        "base_url": "",
        "api_key": "",
        "model": default_model,
    }
    if not raw_value.strip():
        return empty_payload
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return empty_payload
    return {
        "base_url": str(parsed.get("base_url") or "").strip(),
        "api_key": str(parsed.get("api_key") or "").strip(),
        "model": str(parsed.get("model") or default_model).strip() or default_model,
    }


def save_ai_settings(
    load_meta_value: Callable[[str], str | None],
    save_meta_value: Callable[[str, str], None],
    *,
    settings_key: str,
    default_model: str,
    base_url: str,
    api_key: str,
    model: str,
    preserve_existing_api_key: bool = True,
) -> None:
    existing_settings = load_ai_settings(
        load_meta_value,
        settings_key=settings_key,
        default_model=default_model,
    )
    normalized_api_key = str(api_key or "").strip()
    if preserve_existing_api_key and not normalized_api_key:
        normalized_api_key = existing_settings.get("api_key", "")
    payload = {
        "base_url": str(base_url or "").strip(),
        "api_key": normalized_api_key,
        "model": str(model or "").strip() or default_model,
    }
    save_meta_value(settings_key, json.dumps(payload, ensure_ascii=False))


def load_prompt_templates(
    load_meta_value: Callable[[str], str | None],
    *,
    templates_key: str,
    default_payload: dict[str, str],
) -> dict[str, str]:
    raw_value = load_meta_value(templates_key) or ""
    if not raw_value.strip():
        return dict(default_payload)
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return dict(default_payload)
    return {
        key: str(parsed.get(key) or default_value).strip() or default_value
        for key, default_value in default_payload.items()
    }


def save_prompt_templates(
    save_meta_value: Callable[[str, str], None],
    *,
    templates_key: str,
    default_payload: dict[str, str],
    values: dict[str, str],
) -> None:
    payload = {
        key: str(values.get(key) or "").strip() or default_value
        for key, default_value in default_payload.items()
    }
    save_meta_value(templates_key, json.dumps(payload, ensure_ascii=False))


def load_text_artifact(
    load_meta_value: Callable[[str], str | None],
    artifact_key: str,
) -> dict[str, str] | None:
    raw_value = load_meta_value(artifact_key) or ""
    if not raw_value.strip():
        return None
    try:
        parsed: Any = json.loads(raw_value)
    except json.JSONDecodeError:
        return {
            "content": raw_value,
            "generated_at": "",
            "model": "",
        }
    if not isinstance(parsed, dict):
        return {
            "content": raw_value,
            "generated_at": "",
            "model": "",
        }
    return {
        "content": str(parsed.get("content") or "").strip(),
        "generated_at": str(parsed.get("generated_at") or "").strip(),
        "model": str(parsed.get("model") or "").strip(),
    }


def save_text_artifact(
    save_meta_value: Callable[[str, str], None],
    artifact_key: str,
    *,
    content: str,
    model: str,
    default_model: str,
    generated_at: str | None = None,
) -> None:
    payload = {
        "content": str(content or "").strip(),
        "generated_at": str(generated_at or china_now_label()).strip(),
        "model": str(model or "").strip() or default_model,
    }
    save_meta_value(artifact_key, json.dumps(payload, ensure_ascii=False))

