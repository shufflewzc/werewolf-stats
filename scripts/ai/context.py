from __future__ import annotations

from typing import Any


def render_ai_prompt_template(
    template: str,
    values: dict[str, Any],
    template_label: str,
) -> str:
    try:
        return str(template).format_map(
            {key: str(value) for key, value in values.items()}
        )
    except KeyError as exc:
        missing_key = str(exc).strip("'")
        raise ValueError(f"{template_label} 缺少占位符参数：{missing_key}") from exc

