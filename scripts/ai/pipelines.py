from __future__ import annotations

from collections.abc import Callable

from .client import request_openai_compatible_completion


def generate_text_from_settings(
    *,
    load_ai_settings: Callable[[], dict[str, str]],
    default_model: str,
    missing_config_message: str,
    system_prompt: str,
    user_prompt: str,
) -> tuple[str, str]:
    settings = load_ai_settings()
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or default_model).strip() or default_model
    if not base_url or not api_key:
        raise ValueError(missing_config_message)
    report_text = request_openai_compatible_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        default_model=default_model,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
    )
    return report_text, model
