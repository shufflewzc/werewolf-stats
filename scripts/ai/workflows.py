from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any

from .jobs import summarize_ai_prompt_for_job
from .pipelines import generate_text_from_settings


MATCH_DAY_HIGHLIGHTS_SYSTEM_PROMPT = (
    "你是一名狼人杀赛事数据分析助手。"
    "请只基于输入的真实比赛数据提炼结构化要点，禁止虚构。"
)

MATCH_DAY_HIGHLIGHTS_USER_PROMPT = """请基于下面的比赛日报数据，先提炼结构化要点。
要求：
1. 只输出 JSON，不要输出 Markdown，不要输出代码块。
2. highlights 写 3 到 6 条，每条包含 title、detail、evidence。
3. claims 写可以被数据支持的事实性结论，每条包含 text、evidence。
4. risks 写数据不足、可能需要人工确认或不宜展开的点。
5. 所有 evidence 必须引用输入数据中出现的战队、队员、积分、胜率、比赛 ID 或比赛日。

输出格式：
{{
  "highlights": [
    {{"title": "...", "detail": "...", "evidence": "..."}}
  ],
  "claims": [
    {{"text": "...", "evidence": "..."}}
  ],
  "risks": ["..."]
}}

比赛日报数据：
{data_prompt}
"""


def extract_json_object(text: str) -> dict[str, Any]:
    raw_text = str(text or "").strip()
    if not raw_text:
        raise ValueError("AI 要点提取没有返回内容。")
    fenced_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw_text, re.S)
    json_text = fenced_match.group(1) if fenced_match else raw_text
    if not json_text.lstrip().startswith("{"):
        start = json_text.find("{")
        end = json_text.rfind("}")
        if start >= 0 and end > start:
            json_text = json_text[start : end + 1]
    parsed = json.loads(json_text)
    if not isinstance(parsed, dict):
        raise ValueError("AI 要点提取返回的 JSON 顶层必须是对象。")
    return parsed


def normalize_match_day_highlights(raw_highlights: dict[str, Any]) -> dict[str, Any]:
    highlights = []
    for item in raw_highlights.get("highlights") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if title or detail or evidence:
            highlights.append(
                {
                    "title": title,
                    "detail": detail,
                    "evidence": evidence,
                }
            )
    claims = []
    for item in raw_highlights.get("claims") or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        if text or evidence:
            claims.append({"text": text, "evidence": evidence})
    risks = [
        str(item or "").strip()
        for item in (raw_highlights.get("risks") or [])
        if str(item or "").strip()
    ]
    return {
        "highlights": highlights[:8],
        "claims": claims[:12],
        "risks": risks[:8],
    }


def _compact_for_match(text: str) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _evidence_is_supported(evidence: str, source_text: str) -> bool:
    normalized_evidence = _compact_for_match(evidence)
    if not normalized_evidence:
        return False
    normalized_source = _compact_for_match(source_text)
    if normalized_evidence in normalized_source:
        return True
    evidence_tokens = [
        token
        for token in re.split(r"[|/；;，,。:\s]+", str(evidence or ""))
        if len(_compact_for_match(token)) >= 2
    ]
    if not evidence_tokens:
        return False
    supported_tokens = [
        token
        for token in evidence_tokens
        if _compact_for_match(token) in normalized_source
    ]
    return len(supported_tokens) >= max(1, min(2, len(evidence_tokens)))


def _needs_strong_evidence(text: str) -> bool:
    return bool(
        re.search(
            r"(最高|第一|第1|头名|领跑|最多|最强|唯一|全部|全场|包揽|碾压)",
            str(text or ""),
        )
    )


def verify_match_day_highlights(
    highlights: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    verified_highlights = []
    rejected_items = []
    for item in highlights.get("highlights") or []:
        title = str(item.get("title") or "").strip()
        detail = str(item.get("detail") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        item_text = f"{title} {detail}"
        supported = _evidence_is_supported(evidence, source_text)
        if supported and (evidence or not _needs_strong_evidence(item_text)):
            verified_highlights.append(item)
        else:
            rejected_items.append(
                {
                    "kind": "highlight",
                    "text": item_text.strip(),
                    "evidence": evidence,
                    "reason": "证据为空或无法在原始数据中找到。",
                }
            )

    verified_claims = []
    for item in highlights.get("claims") or []:
        text = str(item.get("text") or "").strip()
        evidence = str(item.get("evidence") or "").strip()
        supported = _evidence_is_supported(evidence, source_text)
        if supported and (evidence or not _needs_strong_evidence(text)):
            verified_claims.append(item)
        else:
            rejected_items.append(
                {
                    "kind": "claim",
                    "text": text,
                    "evidence": evidence,
                    "reason": "证据为空或无法在原始数据中找到。",
                }
            )

    risks = list(highlights.get("risks") or [])
    risks.extend(
        f"已剔除{item['kind']}：{item['text']}（{item['reason']}）"
        for item in rejected_items[:8]
    )
    return {
        "highlights": verified_highlights[:6],
        "claims": verified_claims[:10],
        "risks": risks[:12],
        "verification": {
            "accepted_highlights": len(verified_highlights),
            "accepted_claims": len(verified_claims),
            "rejected": len(rejected_items),
            "rejected_items": rejected_items[:12],
        },
    }


def build_match_day_report_prompt(
    *,
    original_user_prompt: str,
    highlights: dict[str, Any],
) -> str:
    highlights_json = json.dumps(highlights, ensure_ascii=False, indent=2)
    return f"""{original_user_prompt}

上面是原始真实比赛数据。下面是第一阶段提炼出的结构化要点，请优先基于这些已提炼要点生成最终日报；如果要点和原始数据冲突，以原始数据为准。

结构化要点：
{highlights_json}

请输出最终 Markdown 日报正文。不要输出 JSON，不要输出代码块。不得加入结构化要点之外且无法从原始数据支持的事实。"""


def run_match_day_report_workflow(
    *,
    played_on: str,
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
        job_type="match_day_report_pipeline",
        scope_type="played_on",
        scope_key=played_on,
        model=configured_model,
        created_by=created_by,
        created_at=started_at,
        metadata={"workflow": "match_day_report_v1", **(metadata or {})},
    )
    add_ai_job_step(
        job_id=job_id,
        step_order=1,
        step_name="build_context",
        status="succeeded",
        started_at=started_at,
        finished_at=now_label(),
        input_summary=f"played_on={played_on}",
        output_summary=summarize_ai_prompt_for_job(user_prompt),
    )

    highlights_prompt = MATCH_DAY_HIGHLIGHTS_USER_PROMPT.format(
        data_prompt=user_prompt
    )
    highlights_started_at = now_label()
    try:
        highlights_text, model = generate_text_from_settings(
            load_ai_settings=load_ai_settings,
            default_model=default_model,
            missing_config_message=missing_config_message,
            system_prompt=MATCH_DAY_HIGHLIGHTS_SYSTEM_PROMPT,
            user_prompt=highlights_prompt,
        )
        highlights = normalize_match_day_highlights(
            extract_json_object(highlights_text)
        )
    except Exception as exc:
        error_message = str(exc)
        add_ai_job_step(
            job_id=job_id,
            step_order=2,
            step_name="extract_highlights",
            status="failed",
            started_at=highlights_started_at,
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
    add_ai_job_step(
        job_id=job_id,
        step_order=2,
        step_name="extract_highlights",
        status="succeeded",
        started_at=highlights_started_at,
        finished_at=now_label(),
        input_summary=f"model={model}",
        output_summary=summarize_ai_prompt_for_job(
            json.dumps(highlights, ensure_ascii=False)
        ),
        metadata={"highlights": highlights},
    )

    verified_highlights = verify_match_day_highlights(highlights, user_prompt)
    verification = verified_highlights.get("verification") or {}
    add_ai_job_step(
        job_id=job_id,
        step_order=3,
        step_name="verify_highlights",
        status="succeeded",
        started_at=now_label(),
        finished_at=now_label(),
        input_summary=(
            f"highlights={len(highlights.get('highlights') or [])}; "
            f"claims={len(highlights.get('claims') or [])}"
        ),
        output_summary=(
            f"通过亮点 {verification.get('accepted_highlights', 0)} 条；"
            f"通过结论 {verification.get('accepted_claims', 0)} 条；"
            f"剔除 {verification.get('rejected', 0)} 条"
        ),
        metadata={"verification": verification},
    )

    report_prompt = build_match_day_report_prompt(
        original_user_prompt=user_prompt,
        highlights=verified_highlights,
    )
    report_started_at = now_label()
    try:
        report_text, model = generate_text_from_settings(
            load_ai_settings=load_ai_settings,
            default_model=default_model,
            missing_config_message=missing_config_message,
            system_prompt=system_prompt,
            user_prompt=report_prompt,
        )
    except Exception as exc:
        error_message = str(exc)
        add_ai_job_step(
            job_id=job_id,
            step_order=4,
            step_name="write_report",
            status="failed",
            started_at=report_started_at,
            finished_at=now_label(),
            input_summary=f"model={model}",
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
        step_order=4,
        step_name="write_report",
        status="succeeded",
        started_at=report_started_at,
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
