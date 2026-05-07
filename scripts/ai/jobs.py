from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .pipelines import generate_text_from_settings


def summarize_ai_prompt_for_job(prompt: str, max_length: int = 1200) -> str:
    normalized = "\n".join(
        line.strip() for line in str(prompt or "").splitlines() if line.strip()
    )
    if len(normalized) <= max_length:
        return normalized
    return normalized[: max_length - 3].rstrip() + "..."


def run_ai_generation_job(
    *,
    job_type: str,
    scope_type: str,
    scope_key: str,
    system_prompt: str,
    user_prompt: str,
    missing_config_message: str,
    load_ai_settings: Callable[[], dict[str, str]],
    default_model: str,
    now_label: Callable[[], str],
    create_ai_job: Callable[..., str],
    add_ai_job_step: Callable[..., str],
    update_ai_job_status: Callable[..., None],
    created_by: str = "",
    metadata: dict[str, Any] | None = None,
) -> tuple[str, str]:
    started_at = now_label()
    settings = load_ai_settings()
    configured_model = (
        str(settings.get("model") or default_model).strip()
        or default_model
    )
    job_id = create_ai_job(
        job_type=job_type,
        scope_type=scope_type,
        scope_key=scope_key,
        model=configured_model,
        created_by=created_by,
        created_at=started_at,
        metadata=metadata or {},
    )
    add_ai_job_step(
        job_id=job_id,
        step_order=1,
        step_name="build_prompt",
        status="succeeded",
        started_at=started_at,
        finished_at=now_label(),
        input_summary=f"system={len(system_prompt)} chars; user={len(user_prompt)} chars",
        output_summary=summarize_ai_prompt_for_job(user_prompt),
    )
    call_started_at = now_label()
    try:
        report_text, model = generate_text_from_settings(
            load_ai_settings=load_ai_settings,
            default_model=default_model,
            missing_config_message=missing_config_message,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )
    except Exception as exc:
        error_message = str(exc)
        add_ai_job_step(
            job_id=job_id,
            step_order=2,
            step_name="request_model",
            status="failed",
            started_at=call_started_at,
            finished_at=now_label(),
            input_summary=f"model={configured_model}",
            error_message=error_message,
        )
        update_ai_job_status(
            job_id,
            status="failed",
            updated_at=now_label(),
            error_message=error_message,
        )
        raise
    finished_at = now_label()
    add_ai_job_step(
        job_id=job_id,
        step_order=2,
        step_name="request_model",
        status="succeeded",
        started_at=call_started_at,
        finished_at=finished_at,
        input_summary=f"model={model}",
        output_summary=summarize_ai_prompt_for_job(report_text),
    )
    update_ai_job_status(
        job_id,
        status="succeeded",
        updated_at=finished_at,
        model=model,
    )
    return report_text, model
