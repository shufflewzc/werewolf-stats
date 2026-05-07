from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


DEFAULT_COMPLETION_MAX_RETRIES = 10
DEFAULT_COMPLETION_RETRY_DELAY_SECONDS = 1.0


def normalize_openai_compatible_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    lowered = normalized.lower()
    if lowered.endswith("/chat/completions"):
        return normalized
    if lowered.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def extract_openai_compatible_text(response_payload: dict[str, Any]) -> str:
    output_text = str(response_payload.get("output_text") or "").strip()
    if output_text:
        return output_text
    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0] if isinstance(choices[0], dict) else {}
        message = first_choice.get("message") if isinstance(first_choice, dict) else {}
        content = message.get("content") if isinstance(message, dict) else ""
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    if isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
                    elif item.get("type") == "output_text" and isinstance(item.get("text"), str):
                        text_parts.append(item["text"])
            return "\n".join(part.strip() for part in text_parts if part.strip()).strip()
    output = response_payload.get("output")
    if isinstance(output, list):
        text_parts = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content_items = item.get("content")
            if not isinstance(content_items, list):
                continue
            for content_item in content_items:
                if (
                    isinstance(content_item, dict)
                    and isinstance(content_item.get("text"), str)
                ):
                    text_parts.append(content_item["text"])
        return "\n".join(part.strip() for part in text_parts if part.strip()).strip()
    return ""


def request_openai_compatible_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    default_model: str,
    max_retries: int = DEFAULT_COMPLETION_MAX_RETRIES,
    retry_delay_seconds: float = DEFAULT_COMPLETION_RETRY_DELAY_SECONDS,
    timeout_seconds: int = 90,
) -> str:
    endpoint = normalize_openai_compatible_base_url(base_url)
    payload = {
        "model": model.strip() or default_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.7,
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error: ValueError | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
            try:
                payload_data = json.loads(response_body)
            except json.JSONDecodeError as exc:
                raise ValueError("AI 接口返回了无法解析的 JSON 响应。") from exc
            output_text = extract_openai_compatible_text(payload_data)
            if not output_text:
                raise ValueError("AI 接口已返回结果，但没有解析到正文内容。")
            return output_text.strip()
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="ignore").strip()
            detail = error_body[:400] if error_body else exc.reason
            last_error = ValueError(f"AI 接口返回 {exc.code}：{detail}")
            if exc.code < 500 and exc.code not in {408, 409, 429}:
                raise last_error from exc
        except urllib.error.URLError as exc:
            last_error = ValueError(f"AI 接口请求失败：{exc.reason}")
        except TimeoutError as exc:
            last_error = ValueError("AI 接口请求超时，请稍后重试。")
        except ValueError as exc:
            last_error = exc

        if attempt < max_retries:
            time.sleep(retry_delay_seconds)

    if last_error is not None:
        raise last_error
    raise ValueError("AI 接口请求失败，请稍后重试。")

