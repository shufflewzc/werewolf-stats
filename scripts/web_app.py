#!/usr/bin/env python3

from __future__ import annotations

import base64
from copy import deepcopy
import hashlib
import hmac
import json
import math
import mimetypes
import os
import re
import secrets
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from email.parser import BytesParser
from email.policy import default as default_email_policy
from html import escape
from http import cookies
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode

from wsgiref.simple_server import make_server

sys.modules.setdefault("web_app", sys.modules[__name__])

from generate_stats import (
    build_player_details,
    build_player_rows,
    build_team_rows,
    format_pct,
    get_match_competition_name,
    list_competitions,
    list_seasons as stats_list_seasons,
    safe_rate,
)
from competition_meta import (
    build_city_code,
    build_season_code,
    build_series_context_from_competition,
    canonicalize_match_ids,
    format_datetime_local_label,
    get_season_entry,
    get_season_entries_for_series,
    get_season_status,
    get_series_entries_by_slug,
    get_series_entry_by_competition,
    infer_region_name_from_competition,
    infer_series_name_from_competition,
    list_seasons,
    load_season_catalog,
    load_series_catalog,
    normalize_season_catalog_entry,
    normalize_series_catalog_entry,
    parse_china_datetime,
    save_season_catalog,
    save_series_catalog,
    season_status_label,
)
from sqlite_store import (
    DB_PATH,
    delete_session,
    delete_sessions_for_username,
    load_session_username,
    load_membership_requests,
    load_meta_value,
    load_users,
    save_session,
    save_matches as persist_matches,
    save_membership_requests,
    save_meta_value,
    save_repository_data,
    save_users,
)
from validate_data import validate_repository
from web_authz import (
    ADMIN_USERNAME,
    DEFAULT_EVENT_MANAGER_PERMISSION_KEYS,
    EVENT_SCOPE_PERMISSION_KEYS,
    PERMISSION_DESCRIPTIONS,
    PERMISSION_GROUPS,
    PERMISSION_LABELS,
    SERIES_MANAGEMENT_PERMISSION_KEYS,
    build_manager_scope_key,
    get_all_permission_keys,
    get_user_manager_scope_keys,
    get_user_permission_labels,
    is_admin_user,
    normalize_permission_keys,
    user_has_any_permission,
    user_has_permission,
)
from web_config import (
    ACCOUNT_ROLE_OPTIONS,
    CAMP_OPTIONS,
    CHINA_MAINLAND_CITY_OPTIONS,
    CHINA_MAINLAND_LOCATION_OPTIONS,
    CHINA_MAINLAND_LOCATION_OPTIONS_JSON,
    CHINA_MAINLAND_PROVINCE_OPTIONS,
    CITY_TO_PROVINCE,
    DEFAULT_PROVINCE_NAME,
    DEFAULT_REGION_NAME,
    DIRECT_CONTROLLED_MUNICIPALITIES,
    GENDER_OPTIONS,
    RESULT_OPTIONS,
    STAGE_OPTIONS,
    STANCE_OPTIONS,
    WINNING_CAMP_OPTIONS,
)

from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
PLAYER_ASSETS_DIR = ASSETS_DIR / "players"
PLAYER_UPLOAD_DIR = PLAYER_ASSETS_DIR / "uploads"
TEAM_ASSETS_DIR = ASSETS_DIR / "teams"
TEAM_UPLOAD_DIR = TEAM_ASSETS_DIR / "uploads"
DEFAULT_PLAYER_PHOTO = "assets/players/default-player.svg"
DEFAULT_TEAM_LOGO = "assets/teams/default-team.svg"
SESSION_COOKIE = "werewolf_session"
SESSION_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24 * 30
HOST = os.getenv("HOST", "")
PORT = int(os.getenv("PORT", "8000"))
VALIDATED_DATA_CACHE_TTL_SECONDS = float(
    os.getenv("VALIDATED_DATA_CACHE_TTL_SECONDS", "5")
)
AI_DAILY_BRIEF_SETTINGS_KEY = "ai_daily_brief_settings"
AI_DAILY_BRIEF_REPORT_KEY_PREFIX = "ai_daily_brief_report:"
AI_SEASON_SUMMARY_KEY_PREFIX = "ai_season_summary:"
AI_PLAYER_SEASON_SUMMARY_KEY_PREFIX = "ai_player_season_summary:"
AI_TEAM_SEASON_SUMMARY_KEY_PREFIX = "ai_team_season_summary:"
AI_PROMPT_TEMPLATES_KEY = "ai_prompt_templates"
DEFAULT_AI_DAILY_BRIEF_MODEL = os.getenv("AI_DAILY_BRIEF_MODEL", "gpt-4.1-mini")
CAPTCHA_CHALLENGES: dict[str, dict[str, str]] = {}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
SLUG_SANITIZE_PATTERN = re.compile(r"[^a-z0-9_-]+")
MATCH_ID_PATTERN = re.compile(r"^[a-z0-9]{1,6}-[a-z0-9]{1,8}-\d{6}-\d{2}$")
ALIAS_SPLIT_PATTERN = re.compile(r"[\n,，、]+")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
VALIDATED_DATA_CACHE_LOCK = threading.RLock()
VALIDATED_DATA_CACHE: dict[str, Any] = {
    "db_mtime_ns": None,
    "cached_at": 0.0,
    "data": None,
}

DEFAULT_MATCH_DAY_SYSTEM_PROMPT = (
    "你是一名狼人杀赛事内容编辑。"
    "请把输入的真实比赛数据整理成适合站内发布的中文日报，禁止虚构。"
)
DEFAULT_MATCH_DAY_USER_PROMPT = """请基于下面的真实比赛数据，为 {played_on} 生成一份中文赛事日报。
要求：
1. 只能基于给定数据写，不要编造未提供的事实。
2. 输出 Markdown 格式中文，可使用二级或三级标题、无序列表、加粗，不要输出代码块。
3. 结构按“## 今日总览 + ## 今日亮点 + ## 结语”组织，其中亮点部分写 3 到 6 条列表。
4. 可以提炼当天的强势战队、亮眼队员、关键比赛和积分走势。
5. 语气像赛事官号日报，简洁但有信息量。

当天共有 {series_count} 个系列赛、{match_count} 场比赛。

战队日榜：
{team_board}

队员日榜：
{player_board}

比赛明细：
{match_details}
"""
DEFAULT_SEASON_SUMMARY_SYSTEM_PROMPT = (
    "你是一名狼人杀赛事内容编辑。"
    "请把输入的真实赛季数据整理成适合站内发布的中文赛季总结，禁止虚构。"
)
DEFAULT_SEASON_SUMMARY_USER_PROMPT = """请基于下面的真实赛季数据，为 {competition_name} 的 {season_name} 输出一份中文赛季总结。
要求：
1. 只能依据给定数据总结，不要编造队伍故事、场外信息或未提供的事件。
2. 输出 Markdown 格式中文，可使用二级或三级标题、无序列表、加粗，不要输出代码块。
3. 结构按“## 赛季总览 + ## 重点总结 + ## 收尾”组织，其中重点总结部分写 4 到 8 条列表。
4. 可以总结赛季走势、强势战队、亮眼选手、阶段变化和 MVP 亮点。
5. 语气像官方赛季回顾，简洁、准确、有概括力。

赛季基础信息：赛事 {competition_name}；赛季 {season_name}；已录入比赛 {match_count} 场；参赛战队 {team_count} 支；参赛队员 {player_count} 名。

战队积分榜：
{team_board}

个人积分榜：
{player_board}

MVP 榜：
{mvp_board}

赛段摘要：
{stage_summary}

比赛日分布：
{match_day_distribution}
"""
DEFAULT_PLAYER_SEASON_SUMMARY_SYSTEM_PROMPT = (
    "你是一名狼人杀赛事内容编辑。"
    "请把输入的真实选手赛季数据整理成适合站内发布的中文个人赛季总结，禁止虚构。"
)
AI_COMPLETION_MAX_RETRIES = 10
AI_COMPLETION_RETRY_DELAY_SECONDS = 1.0
DEFAULT_TEAM_SEASON_SUMMARY_SYSTEM_PROMPT = (
    "你是一名狼人杀赛事内容编辑。"
    "请把输入的真实战队赛季数据整理成适合站内发布的中文战队赛季总结，禁止虚构。"
)
DEFAULT_PLAYER_SEASON_SUMMARY_USER_PROMPT = """请基于下面的真实选手赛季数据，为 {player_name} 输出一份中文个人赛季总结。
要求：
1. 只能依据给定数据总结，不要编造人物故事、场外信息或未提供的比赛细节。
2. 输出 Markdown 格式中文，可使用二级或三级标题、无序列表、加粗，不要输出代码块。
3. 结构按“## 赛季定位 + ## 表现总结 + ## 收尾点评”组织，其中表现总结部分写 3 到 6 条列表。
4. 可以总结这名选手的赛季定位、战绩走势、角色分布、关键场次和相对排名。
5. 语气像官方选手观察，简洁、准确、有概括力。

选手基础信息：姓名 {player_name}；战队 {team_name}；赛事 {competition_name}；赛季 {season_name}；赛季排名 第 {rank} 名；出场 {games_played} 场；战绩 {record}；总胜率 {overall_win_rate}；好人胜率 {villagers_win_rate}；狼人胜率 {werewolves_win_rate}；总积分 {points_total}；场均得分 {average_points}。

站边信息：
{stance_summary}

角色分布：
{role_summary}

选手所在赛季积分榜参考：
{season_player_board}

战队积分榜参考：
{season_team_board}

最近比赛记录：
{recent_matches}
"""
DEFAULT_TEAM_SEASON_SUMMARY_USER_PROMPT = """请基于下面的真实战队赛季数据，为 {team_name} 输出一份中文战队赛季总结。
要求：
1. 只能依据给定数据总结，不要编造队伍故事、队员关系、场外信息或未提供的比赛细节。
2. 输出 Markdown 格式中文，可使用二级或三级标题、无序列表、加粗，不要输出代码块。
3. 结构按“## 战队定位 + ## 赛季表现 + ## 收尾点评”组织，其中赛季表现部分写 3 到 6 条列表。
4. 可以总结这支战队的赛季定位、队内核心贡献、比赛走势、关键场次和在积分榜中的位置。
5. 语气像官方战队观察，简洁、准确、有概括力。

战队基础信息：名称 {team_name}；赛事 {competition_name}；赛季 {season_name}；积分排名 第 {rank} 名；参赛队员 {player_count} 名；出场 {matches_represented} 场；总积分 {points_total}；场均积分 {points_per_match}；胜率 {win_rate}；站边成功率 {stance_rate}。

当前赛季战队积分榜参考：
{season_team_board}

战队队员赛季数据：
{roster_board}

最近比赛记录：
{recent_matches}
"""


@dataclass
class UploadedFile:
    filename: str
    content_type: str
    data: bytes


@dataclass
class RequestContext:
    method: str
    path: str
    query: dict[str, list[str]]
    form: dict[str, list[str]]
    files: dict[str, list[UploadedFile]]
    current_user: dict[str, Any] | None
    now_label: str


def china_now() -> datetime:
    return datetime.now(CHINA_TZ)


def china_now_label() -> str:
    return china_now().strftime("%Y-%m-%d %H:%M:%S 中国时间")


def china_today_label() -> str:
    return china_now().strftime("%Y-%m-%d")


def normalize_openai_compatible_base_url(base_url: str) -> str:
    normalized = str(base_url or "").strip().rstrip("/")
    lowered = normalized.lower()
    if lowered.endswith("/chat/completions"):
        return normalized
    if lowered.endswith("/v1"):
        return normalized + "/chat/completions"
    return normalized + "/v1/chat/completions"


def load_ai_daily_brief_settings() -> dict[str, str]:
    raw_value = load_meta_value(AI_DAILY_BRIEF_SETTINGS_KEY) or ""
    if not raw_value.strip():
        return {
            "base_url": "",
            "api_key": "",
            "model": DEFAULT_AI_DAILY_BRIEF_MODEL,
        }
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {
            "base_url": "",
            "api_key": "",
            "model": DEFAULT_AI_DAILY_BRIEF_MODEL,
        }
    return {
        "base_url": str(parsed.get("base_url") or "").strip(),
        "api_key": str(parsed.get("api_key") or "").strip(),
        "model": str(parsed.get("model") or DEFAULT_AI_DAILY_BRIEF_MODEL).strip()
        or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }


def save_ai_daily_brief_settings(
    base_url: str,
    api_key: str,
    model: str,
    preserve_existing_api_key: bool = True,
) -> None:
    existing_settings = load_ai_daily_brief_settings()
    normalized_api_key = str(api_key or "").strip()
    if preserve_existing_api_key and not normalized_api_key:
        normalized_api_key = existing_settings.get("api_key", "")
    payload = {
        "base_url": str(base_url or "").strip(),
        "api_key": normalized_api_key,
        "model": str(model or "").strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    save_meta_value(AI_DAILY_BRIEF_SETTINGS_KEY, json.dumps(payload, ensure_ascii=False))


def load_ai_prompt_templates() -> dict[str, str]:
    raw_value = load_meta_value(AI_PROMPT_TEMPLATES_KEY) or ""
    default_payload = {
        "match_day_system_prompt": DEFAULT_MATCH_DAY_SYSTEM_PROMPT,
        "match_day_user_prompt": DEFAULT_MATCH_DAY_USER_PROMPT,
        "season_summary_system_prompt": DEFAULT_SEASON_SUMMARY_SYSTEM_PROMPT,
        "season_summary_user_prompt": DEFAULT_SEASON_SUMMARY_USER_PROMPT,
        "player_season_summary_system_prompt": DEFAULT_PLAYER_SEASON_SUMMARY_SYSTEM_PROMPT,
        "player_season_summary_user_prompt": DEFAULT_PLAYER_SEASON_SUMMARY_USER_PROMPT,
        "team_season_summary_system_prompt": DEFAULT_TEAM_SEASON_SUMMARY_SYSTEM_PROMPT,
        "team_season_summary_user_prompt": DEFAULT_TEAM_SEASON_SUMMARY_USER_PROMPT,
    }
    if not raw_value.strip():
        return default_payload
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return default_payload
    return {
        key: str(parsed.get(key) or default_value).strip() or default_value
        for key, default_value in default_payload.items()
    }


def save_ai_prompt_templates(
    match_day_system_prompt: str,
    match_day_user_prompt: str,
    season_summary_system_prompt: str,
    season_summary_user_prompt: str,
    player_season_summary_system_prompt: str,
    player_season_summary_user_prompt: str,
    team_season_summary_system_prompt: str,
    team_season_summary_user_prompt: str,
) -> None:
    payload = {
        "match_day_system_prompt": str(match_day_system_prompt or "").strip()
        or DEFAULT_MATCH_DAY_SYSTEM_PROMPT,
        "match_day_user_prompt": str(match_day_user_prompt or "").strip()
        or DEFAULT_MATCH_DAY_USER_PROMPT,
        "season_summary_system_prompt": str(season_summary_system_prompt or "").strip()
        or DEFAULT_SEASON_SUMMARY_SYSTEM_PROMPT,
        "season_summary_user_prompt": str(season_summary_user_prompt or "").strip()
        or DEFAULT_SEASON_SUMMARY_USER_PROMPT,
        "player_season_summary_system_prompt": str(player_season_summary_system_prompt or "").strip()
        or DEFAULT_PLAYER_SEASON_SUMMARY_SYSTEM_PROMPT,
        "player_season_summary_user_prompt": str(player_season_summary_user_prompt or "").strip()
        or DEFAULT_PLAYER_SEASON_SUMMARY_USER_PROMPT,
        "team_season_summary_system_prompt": str(team_season_summary_system_prompt or "").strip()
        or DEFAULT_TEAM_SEASON_SUMMARY_SYSTEM_PROMPT,
        "team_season_summary_user_prompt": str(team_season_summary_user_prompt or "").strip()
        or DEFAULT_TEAM_SEASON_SUMMARY_USER_PROMPT,
    }
    save_meta_value(AI_PROMPT_TEMPLATES_KEY, json.dumps(payload, ensure_ascii=False))


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


def mask_api_key(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    if len(normalized) <= 8:
        return "*" * len(normalized)
    return normalized[:4] + "*" * (len(normalized) - 8) + normalized[-4:]


def load_ai_match_day_report(played_on: str) -> dict[str, str] | None:
    raw_value = load_meta_value(AI_DAILY_BRIEF_REPORT_KEY_PREFIX + played_on) or ""
    if not raw_value.strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
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


def save_ai_match_day_report(
    played_on: str,
    content: str,
    model: str,
    generated_at: str | None = None,
) -> None:
    payload = {
        "content": str(content or "").strip(),
        "generated_at": str(generated_at or china_now_label()).strip(),
        "model": str(model or "").strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    save_meta_value(
        AI_DAILY_BRIEF_REPORT_KEY_PREFIX + played_on,
        json.dumps(payload, ensure_ascii=False),
    )


def load_ai_season_summary(
    competition_name: str,
    season_name: str,
) -> dict[str, str] | None:
    raw_value = load_meta_value(
        AI_SEASON_SUMMARY_KEY_PREFIX + competition_name + ":" + season_name
    ) or ""
    if not raw_value.strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
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


def save_ai_season_summary(
    competition_name: str,
    season_name: str,
    content: str,
    model: str,
    generated_at: str | None = None,
) -> None:
    payload = {
        "content": str(content or "").strip(),
        "generated_at": str(generated_at or china_now_label()).strip(),
        "model": str(model or "").strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    save_meta_value(
        AI_SEASON_SUMMARY_KEY_PREFIX + competition_name + ":" + season_name,
        json.dumps(payload, ensure_ascii=False),
    )


def load_ai_player_season_summary(
    player_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, str] | None:
    raw_value = load_meta_value(
        AI_PLAYER_SEASON_SUMMARY_KEY_PREFIX
        + player_id
        + ":"
        + competition_name
        + ":"
        + season_name
    ) or ""
    if not raw_value.strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
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


def save_ai_player_season_summary(
    player_id: str,
    competition_name: str,
    season_name: str,
    content: str,
    model: str,
    generated_at: str | None = None,
) -> None:
    payload = {
        "content": str(content or "").strip(),
        "generated_at": str(generated_at or china_now_label()).strip(),
        "model": str(model or "").strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    save_meta_value(
        AI_PLAYER_SEASON_SUMMARY_KEY_PREFIX
        + player_id
        + ":"
        + competition_name
        + ":"
        + season_name,
        json.dumps(payload, ensure_ascii=False),
    )


def load_ai_team_season_summary(
    team_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, str] | None:
    raw_value = load_meta_value(
        AI_TEAM_SEASON_SUMMARY_KEY_PREFIX
        + team_id
        + ":"
        + competition_name
        + ":"
        + season_name
    ) or ""
    if not raw_value.strip():
        return None
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
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


def save_ai_team_season_summary(
    team_id: str,
    competition_name: str,
    season_name: str,
    content: str,
    model: str,
    generated_at: str | None = None,
) -> None:
    payload = {
        "content": str(content or "").strip(),
        "generated_at": str(generated_at or china_now_label()).strip(),
        "model": str(model or "").strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
    }
    save_meta_value(
        AI_TEAM_SEASON_SUMMARY_KEY_PREFIX
        + team_id
        + ":"
        + competition_name
        + ":"
        + season_name,
        json.dumps(payload, ensure_ascii=False),
    )


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
    timeout_seconds: int = 90,
) -> str:
    endpoint = normalize_openai_compatible_base_url(base_url)
    payload = {
        "model": model.strip() or DEFAULT_AI_DAILY_BRIEF_MODEL,
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
    for attempt in range(1, AI_COMPLETION_MAX_RETRIES + 1):
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

        if attempt < AI_COMPLETION_MAX_RETRIES:
            time.sleep(AI_COMPLETION_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise last_error
    raise ValueError("AI 接口请求失败，请稍后重试。")


def _is_safe_markdown_href(href: str) -> bool:
    normalized = str(href or "").strip().lower()
    return normalized.startswith(("http://", "https://", "/"))


def render_markdown_inline(text: str) -> str:
    raw_text = str(text or "")
    placeholders: dict[str, str] = {}

    def store_placeholder(html: str) -> str:
        token = f"@@HTML{len(placeholders)}@@"
        placeholders[token] = html
        return token

    def replace_code(match: re.Match[str]) -> str:
        return store_placeholder(f"<code>{escape(match.group(1))}</code>")

    def replace_link(match: re.Match[str]) -> str:
        label = match.group(1)
        href = match.group(2).strip()
        if not _is_safe_markdown_href(href):
            return match.group(0)
        return store_placeholder(
            f'<a href="{escape(href, quote=True)}" target="_blank" rel="noopener noreferrer">{escape(label)}</a>'
        )

    processed = re.sub(r"`([^`\n]+)`", replace_code, raw_text)
    processed = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", replace_link, processed)
    rendered = escape(processed)
    rendered = re.sub(r"(\*\*|__)(.+?)\1", r"<strong>\2</strong>", rendered)
    rendered = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", rendered)
    rendered = re.sub(r"(?<!_)_([^_\n]+)_(?!_)", r"<em>\1</em>", rendered)
    for token, html in placeholders.items():
        rendered = rendered.replace(token, html)
    return rendered


def render_markdown_html(content: str) -> str:
    normalized = str(content or "").replace("\r\n", "\n").strip()
    if not normalized:
        return '<div class="text-secondary">AI 日报暂时没有可展示的正文。</div>'

    lines = normalized.split("\n")
    blocks: list[str] = []
    index = 0
    total_lines = len(lines)

    while index < total_lines:
        line = lines[index]
        stripped = line.strip()
        if not stripped:
            index += 1
            continue

        if stripped.startswith("```"):
            code_lines: list[str] = []
            index += 1
            while index < total_lines and not lines[index].strip().startswith("```"):
                code_lines.append(lines[index])
                index += 1
            if index < total_lines:
                index += 1
            blocks.append(f"<pre><code>{escape(chr(10).join(code_lines))}</code></pre>")
            continue

        heading_match = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if heading_match:
            level = len(heading_match.group(1))
            blocks.append(
                f"<h{level}>{render_markdown_inline(heading_match.group(2).strip())}</h{level}>"
            )
            index += 1
            continue

        if re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", stripped):
            blocks.append("<hr>")
            index += 1
            continue

        if stripped.startswith(">"):
            quote_lines: list[str] = []
            while index < total_lines:
                current = lines[index].strip()
                if not current.startswith(">"):
                    break
                quote_lines.append(current[1:].lstrip())
                index += 1
            quote_html = "<br>".join(render_markdown_inline(item) for item in quote_lines)
            blocks.append(f"<blockquote><p>{quote_html}</p></blockquote>")
            continue

        unordered_match = re.match(r"^[-*]\s+(.+)$", stripped)
        ordered_match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if unordered_match or ordered_match:
            list_tag = "ul" if unordered_match else "ol"
            items: list[str] = []
            pattern = r"^[-*]\s+(.+)$" if list_tag == "ul" else r"^\d+\.\s+(.+)$"
            while index < total_lines:
                current = lines[index].strip()
                if not current:
                    look_ahead = index + 1
                    while look_ahead < total_lines and not lines[look_ahead].strip():
                        look_ahead += 1
                    if look_ahead >= total_lines:
                        index = look_ahead
                        break
                    if re.match(pattern, lines[look_ahead].strip()):
                        index = look_ahead
                        continue
                    break
                match = re.match(pattern, current)
                if not match:
                    break
                items.append(f"<li>{render_markdown_inline(match.group(1).strip())}</li>")
                index += 1
            blocks.append(f"<{list_tag}>{''.join(items)}</{list_tag}>")
            continue

        paragraph_lines = [line.strip()]
        index += 1
        while index < total_lines:
            current = lines[index]
            current_stripped = current.strip()
            if not current_stripped:
                index += 1
                break
            if (
                current_stripped.startswith(("```", ">", "#"))
                or re.match(r"^[-*]\s+.+$", current_stripped)
                or re.match(r"^\d+\.\s+.+$", current_stripped)
                or re.fullmatch(r"(-{3,}|\*{3,}|_{3,})", current_stripped)
            ):
                break
            paragraph_lines.append(current.strip())
            index += 1
        paragraph_html = "<br>".join(render_markdown_inline(item) for item in paragraph_lines)
        blocks.append(f"<p>{paragraph_html}</p>")

    return "".join(blocks) or '<div class="text-secondary">AI 日报暂时没有可展示的正文。</div>'


def render_ai_daily_brief_html(content: str) -> str:
    return render_markdown_html(content)


def get_database_mtime_ns() -> int | None:
    try:
        return DB_PATH.stat().st_mtime_ns
    except FileNotFoundError:
        return None


def invalidate_validated_data_cache() -> None:
    with VALIDATED_DATA_CACHE_LOCK:
        VALIDATED_DATA_CACHE["db_mtime_ns"] = None
        VALIDATED_DATA_CACHE["cached_at"] = 0.0
        VALIDATED_DATA_CACHE["data"] = None


def get_cached_validated_data() -> dict[str, Any] | None:
    current_mtime_ns = get_database_mtime_ns()
    if current_mtime_ns is None:
        return None
    with VALIDATED_DATA_CACHE_LOCK:
        cached_data = VALIDATED_DATA_CACHE["data"]
        if cached_data is None:
            return None
        if VALIDATED_DATA_CACHE["db_mtime_ns"] != current_mtime_ns:
            return None
        if (
            VALIDATED_DATA_CACHE_TTL_SECONDS > 0
            and time.monotonic() - VALIDATED_DATA_CACHE["cached_at"]
            > VALIDATED_DATA_CACHE_TTL_SECONDS
        ):
            return None
        return deepcopy(cached_data)


def set_cached_validated_data(data: dict[str, Any]) -> None:
    current_mtime_ns = get_database_mtime_ns()
    with VALIDATED_DATA_CACHE_LOCK:
        VALIDATED_DATA_CACHE["db_mtime_ns"] = current_mtime_ns
        VALIDATED_DATA_CACHE["cached_at"] = time.monotonic()
        VALIDATED_DATA_CACHE["data"] = deepcopy(data)


def to_chinese_camp(value: str) -> str:
    return CAMP_OPTIONS.get(value, value)


def normalize_stance_result(entry: dict[str, Any]) -> str:
    value = str(entry.get("stance_result") or "").strip()
    if value in STANCE_OPTIONS:
        return value
    legacy_pick = str(entry.get("stance_pick") or "none").strip()
    if not legacy_pick or legacy_pick == "none":
        return "none"
    return "correct" if entry.get("stance_correct") else "incorrect"


MATCH_SCORE_MODEL_STANDARD = "standard"
MATCH_SCORE_MODEL_JINGCHENG_DAILY = "jingcheng_daily"
MATCH_SCORE_MODEL_OPTIONS = {
    MATCH_SCORE_MODEL_STANDARD: "通用总分录入",
    MATCH_SCORE_MODEL_JINGCHENG_DAILY: "京城大师赛日报积分模型",
}
MATCH_SCORE_COMPONENT_FIELDS = [
    ("result_points", "胜负分"),
    ("vote_points", "投票分"),
    ("behavior_points", "行为分"),
    ("special_points", "特殊分"),
    ("adjustment_points", "附加/罚分"),
]


def normalize_match_score_model(value: str | None) -> str:
    normalized = str(value or "").strip()
    if normalized in MATCH_SCORE_MODEL_OPTIONS:
        return normalized
    return MATCH_SCORE_MODEL_STANDARD


def uses_structured_score_model(value: str | None) -> bool:
    return normalize_match_score_model(value) == MATCH_SCORE_MODEL_JINGCHENG_DAILY


def build_empty_score_breakdown() -> dict[str, float]:
    return {field_name: 0.0 for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS}


def parse_float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_score_breakdown(entry: dict[str, Any] | None) -> dict[str, float]:
    current = entry or {}
    return {
        field_name: parse_float_value(current.get(field_name), 0.0)
        for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
    }


def calculate_score_breakdown_total(entry: dict[str, Any] | None) -> float:
    return round(sum(normalize_score_breakdown(entry).values()), 2)


def get_match_score_model_label(value: str | None) -> str:
    normalized = normalize_match_score_model(value)
    return MATCH_SCORE_MODEL_OPTIONS.get(normalized, MATCH_SCORE_MODEL_OPTIONS[MATCH_SCORE_MODEL_STANDARD])


def is_placeholder_match(match: dict[str, Any]) -> bool:
    return str(match.get("format") or "").strip() == "待补录"


def is_match_counted_as_played(match: dict[str, Any]) -> bool:
    if is_placeholder_match(match):
        return False
    return bool(match.get("players"))


def parse_match_day(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def sort_match_days_by_relevance(days: list[str], today_label: str | None = None) -> list[str]:
    today_value = parse_match_day(today_label or china_today_label())
    if today_value is None:
        return sorted(days, reverse=True)

    def sort_key(day: str) -> tuple[int, int, str]:
        parsed_day = parse_match_day(day)
        if parsed_day is None:
            return (3, 10**9, day)
        delta_days = (parsed_day.date() - today_value.date()).days
        if delta_days == 0:
            return (0, 0, day)
        if delta_days > 0:
            return (1, delta_days, day)
        return (2, abs(delta_days), day)

    return sorted(days, key=sort_key)


def get_nearest_match_day_label(days: list[str], today_label: str | None = None) -> str:
    ordered_days = sort_match_days_by_relevance(days, today_label)
    return ordered_days[0] if ordered_days else "待更新"


def competition_latest_day_sort_key(row: dict[str, Any]) -> tuple[int, str, str]:
    latest_played_on = str(row.get("latest_played_on") or "").strip()
    ordered_days = sort_match_days_by_relevance([latest_played_on], china_today_label())
    preferred_day = ordered_days[0] if ordered_days else ""
    if not preferred_day:
        return (3, 10**9, str(row.get("competition_name") or ""))
    today_value = parse_match_day(china_today_label())
    parsed_day = parse_match_day(preferred_day)
    if today_value is None or parsed_day is None:
        return (3, 10**9, str(row.get("competition_name") or ""))
    delta_days = (parsed_day.date() - today_value.date()).days
    if delta_days == 0:
        return (0, 0, str(row.get("competition_name") or ""))
    if delta_days > 0:
        return (1, delta_days, str(row.get("competition_name") or ""))
    return (2, abs(delta_days), str(row.get("competition_name") or ""))


def get_scheduled_match_day_label(
    matches: list[dict[str, Any]],
    today_label: str | None = None,
) -> str:
    return get_nearest_match_day_label(
        [
            str(match.get("played_on") or "").strip()
            for match in matches
            if str(match.get("played_on") or "").strip()
        ],
        today_label,
    )


def parse_cookies(environ: dict[str, Any]) -> cookies.SimpleCookie[str]:
    jar = cookies.SimpleCookie()
    if environ.get("HTTP_COOKIE"):
        jar.load(environ["HTTP_COOKIE"])
    return jar


def get_request_data(
    environ: dict[str, Any]
) -> tuple[dict[str, list[str]], dict[str, list[str]], dict[str, list[UploadedFile]]]:
    query = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    form: dict[str, list[str]] = {}
    files: dict[str, list[UploadedFile]] = {}

    if environ.get("REQUEST_METHOD", "GET").upper() == "POST":
        content_type = environ.get("CONTENT_TYPE", "")
        size = int(environ.get("CONTENT_LENGTH") or 0)
        raw_body = environ["wsgi.input"].read(size)
        if content_type.startswith("multipart/form-data"):
            message = BytesParser(policy=default_email_policy).parsebytes(
                b"Content-Type: "
                + content_type.encode("utf-8")
                + b"\r\nMIME-Version: 1.0\r\n\r\n"
                + raw_body
            )
            for part in message.iter_parts():
                field_name = part.get_param("name", header="content-disposition")
                if not field_name:
                    continue
                filename = part.get_filename()
                payload = part.get_payload(decode=True) or b""
                if filename:
                    files.setdefault(field_name, []).append(
                        UploadedFile(
                            filename=filename,
                            content_type=part.get_content_type(),
                            data=payload,
                        )
                    )
                else:
                    charset = part.get_content_charset() or "utf-8"
                    form.setdefault(field_name, []).append(
                        payload.decode(charset, errors="replace")
                    )
        else:
            raw = raw_body.decode("utf-8")
            form = parse_qs(raw, keep_blank_values=True)

    return query, form, files


def get_current_user(environ: dict[str, Any]) -> dict[str, Any] | None:
    jar = parse_cookies(environ)
    token = jar.get(SESSION_COOKIE)
    if token is None:
        return None

    username = load_session_username(token.value)
    if not username:
        return None

    for user in load_users():
        if user["username"] == username and user.get("active"):
            return user
    return None


def verify_password(password: str, user: dict[str, Any]) -> bool:
    salt = base64.b64decode(user["password_salt"])
    expected = base64.b64decode(user["password_hash"])
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return hmac.compare_digest(candidate, expected)


def hash_password(password: str) -> tuple[str, str]:
    salt = secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 200000)
    return base64.b64encode(salt).decode("utf-8"), base64.b64encode(password_hash).decode("utf-8")


def normalize_slug_fragment(value: str, fallback: str) -> str:
    normalized = SLUG_SANITIZE_PATTERN.sub("-", value.strip().lower().replace(".", "-"))
    normalized = normalized.strip("-_")
    return normalized or fallback


def build_unique_slug(existing_ids: set[str], prefix: str, source: str, fallback: str) -> str:
    base = f"{prefix}-{normalize_slug_fragment(source, fallback)}"
    candidate = base
    counter = 2
    while candidate in existing_ids:
        candidate = f"{base}-{counter}"
        counter += 1
    return candidate


def list_region_names(catalog: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    region_names: list[str] = []
    for entry in catalog:
        region_name = entry["region_name"]
        if region_name in seen:
            continue
        seen.add(region_name)
        region_names.append(region_name)
    return region_names


def list_series_rows_for_region(
    competition_rows: list[dict[str, Any]],
    region_name: str | None,
) -> list[dict[str, Any]]:
    if not region_name:
        return competition_rows
    series_index: dict[str, dict[str, Any]] = {}
    for row in competition_rows:
        if row["region_name"] != region_name:
            continue
        existing = series_index.get(row["series_slug"])
        if not existing:
            series_index[row["series_slug"]] = {
                "series_slug": row["series_slug"],
                "series_name": row["series_name"],
                "series_code": row["series_code"],
                "region_name": row["region_name"],
                "competition_count": 1,
                "match_count": row["match_count"],
                "team_count": row["team_count"],
                "player_count": row["player_count"],
                "latest_played_on": row["latest_played_on"],
                "seasons": list(row["seasons"]),
                "summary": row["summary"],
            }
            continue
        existing["competition_count"] += 1
        existing["match_count"] += row["match_count"]
        existing["team_count"] = max(existing["team_count"], row["team_count"])
        existing["player_count"] = max(existing["player_count"], row["player_count"])
        existing["latest_played_on"] = get_nearest_match_day_label(
            [existing["latest_played_on"], row["latest_played_on"]],
            china_today_label(),
        )
        existing["summary"] = existing["summary"] or row["summary"]
        combined_seasons = {*existing["seasons"], *row["seasons"]}
        existing["seasons"] = sorted(combined_seasons, reverse=True)

    return sorted(
        series_index.values(),
        key=lambda item: (competition_latest_day_sort_key(item), item["series_name"]),
    )


def build_competition_catalog_rows(
    data: dict[str, Any],
    catalog: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    stats_by_competition = {
        row["competition_name"]: row for row in build_competition_rows(data)
    }
    rows: list[dict[str, Any]] = []
    for entry in catalog:
        stats = stats_by_competition.get(entry["competition_name"], {})
        row = {
            "competition_name": entry["competition_name"],
            "region_name": entry["region_name"],
            "series_name": entry["series_name"],
            "series_code": entry["series_code"],
            "series_slug": entry["series_slug"],
            "summary": entry["summary"],
            "page_badge": entry.get("page_badge", ""),
            "hero_title": entry.get("hero_title", ""),
            "hero_intro": entry.get("hero_intro", ""),
            "hero_note": entry.get("hero_note", ""),
            "active": entry["active"],
            "match_count": int(stats.get("match_count", 0)),
            "team_count": int(stats.get("team_count", 0)),
            "player_count": int(stats.get("player_count", 0)),
            "latest_played_on": str(stats.get("latest_played_on", "")),
            "seasons": list(stats.get("seasons", [])),
        }
        if row["active"] or row["match_count"] > 0:
            rows.append(row)

    return sorted(
        rows,
        key=lambda item: (
            item["region_name"] != DEFAULT_REGION_NAME,
            item["region_name"],
            item["series_name"],
            item["competition_name"],
            item["latest_played_on"],
        ),
    )


def build_filtered_data(
    data: dict[str, Any],
    competition_names: set[str],
) -> dict[str, Any]:
    filtered_matches = [
        match
        for match in data["matches"]
        if get_match_competition_name(match) in competition_names
    ]
    return {
        "teams": data["teams"],
        "players": data["players"],
        "matches": filtered_matches,
        "_competition_names": sorted(competition_names),
    }


def build_captcha() -> tuple[str, str]:
    left = secrets.randbelow(9) + 1
    right = secrets.randbelow(9) + 1
    token = secrets.token_urlsafe(18)
    CAPTCHA_CHALLENGES[token] = {
        "prompt": f"{left} + {right} = ?",
        "answer": str(left + right),
    }
    return token, CAPTCHA_CHALLENGES[token]["prompt"]


def consume_captcha(token: str, answer: str) -> bool:
    challenge = CAPTCHA_CHALLENGES.pop(token, None)
    if not challenge:
        return False
    return challenge["answer"] == answer.strip()


def normalize_user_province(province_name: str) -> str:
    normalized = province_name.strip()
    if normalized in CHINA_MAINLAND_PROVINCE_OPTIONS:
        return normalized
    return ""


def normalize_user_region(region_name: str) -> str:
    normalized = region_name.strip()
    if normalized in CHINA_MAINLAND_CITY_OPTIONS:
        return normalized
    for city_name in CHINA_MAINLAND_CITY_OPTIONS:
        if city_name.endswith(("市", "地区", "盟", "自治州")):
            short_name = re.sub(r"(市|地区|盟|自治州)$", "", city_name)
            if normalized == short_name:
                return city_name
    return ""


def compact_region_name(region_name: str) -> str:
    normalized = normalize_user_region(region_name)
    if not normalized:
        normalized = region_name.strip()
    return re.sub(r"(市|地区|盟|自治州)$", "", normalized)


def normalize_user_location(
    province_name: str,
    region_name: str,
) -> tuple[str, str]:
    normalized_province = normalize_user_province(province_name)
    normalized_region = normalize_user_region(region_name)
    if normalized_region and not normalized_province:
        normalized_province = CITY_TO_PROVINCE.get(normalized_region, "")
    if (
        normalized_province
        and normalized_region
        and normalized_region not in CHINA_MAINLAND_LOCATION_OPTIONS.get(normalized_province, [])
    ):
        normalized_province = CITY_TO_PROVINCE.get(normalized_region, "")
    return normalized_province, normalized_region


def get_user_region_label(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    province_name, region_name = normalize_user_location(
        str(user.get("province_name") or ""),
        str(user.get("region_name") or ""),
    )
    if not region_name:
        return None
    if province_name in DIRECT_CONTROLLED_MUNICIPALITIES and province_name == region_name:
        return province_name
    if province_name:
        return f"{province_name} {region_name}"
    return region_name


def get_user_preferred_region(user: dict[str, Any] | None) -> str | None:
    if not user:
        return None
    _, region_name = normalize_user_location(
        str(user.get("province_name") or ""),
        str(user.get("region_name") or ""),
    )
    compact_name = compact_region_name(region_name)
    return compact_name or None


def normalize_user_gender(gender: str) -> str:
    normalized = gender.strip()
    if normalized in GENDER_OPTIONS:
        return normalized
    return ""


def can_manage_series_entry(
    user: dict[str, Any] | None,
    series_entry: dict[str, Any] | None,
) -> bool:
    if is_admin_user(user):
        return True
    if not series_entry or not user_has_any_permission(user, SERIES_MANAGEMENT_PERMISSION_KEYS):
        return False
    return build_manager_scope_key(
        str(series_entry.get("region_name") or ""),
        str(series_entry.get("series_slug") or ""),
    ) in get_user_manager_scope_keys(user)


def can_manage_competition_with_permissions(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
    permission_keys: list[str] | tuple[str, ...] | set[str],
) -> bool:
    if is_admin_user(user):
        return True
    if not user_has_any_permission(user, permission_keys):
        return False
    series_entry = get_series_entry_by_competition(
        load_series_catalog(data),
        competition_name,
    )
    if not series_entry:
        return False
    return build_manager_scope_key(
        str(series_entry.get("region_name") or ""),
        str(series_entry.get("series_slug") or ""),
    ) in get_user_manager_scope_keys(user)


def can_manage_competition(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
) -> bool:
    return can_manage_competition_with_permissions(
        user,
        data,
        competition_name,
        EVENT_SCOPE_PERMISSION_KEYS,
    )


def can_manage_competition_catalog(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
) -> bool:
    return can_manage_competition_with_permissions(
        user,
        data,
        competition_name,
        {"competition_catalog_manage"},
    )


def can_manage_competition_seasons(
    user: dict[str, Any] | None,
    data: dict[str, Any],
    competition_name: str,
) -> bool:
    return can_manage_competition_with_permissions(
        user,
        data,
        competition_name,
        {"competition_season_manage"},
    )


def can_manage_matches(
    user: dict[str, Any] | None,
    data: dict[str, Any] | None = None,
    competition_name: str | None = None,
) -> bool:
    if is_admin_user(user):
        return True
    if not user_has_permission(user, "match_manage"):
        return False
    if not competition_name:
        return bool(get_user_manager_scope_keys(user))
    current_data = data or load_validated_data()
    return can_manage_competition_with_permissions(
        user,
        current_data,
        competition_name,
        {"match_manage"},
    )


def can_access_series_management(user: dict[str, Any] | None) -> bool:
    if is_admin_user(user):
        return True
    return bool(get_user_manager_scope_keys(user)) and user_has_any_permission(
        user,
        SERIES_MANAGEMENT_PERMISSION_KEYS,
    )


def get_manager_scope_labels(
    user: dict[str, Any] | None,
    data: dict[str, Any] | None = None,
) -> list[str]:
    if not user:
        return []
    current_data = data or load_validated_data()
    labels: list[str] = []
    catalog = load_series_catalog(current_data)
    for scope_key in get_user_manager_scope_keys(user):
        region_name, _, series_slug = scope_key.partition("::")
        matched_entries = [
            entry
            for entry in catalog
            if entry["region_name"] == region_name and entry["series_slug"] == series_slug
        ]
        if matched_entries:
            labels.append(f"{region_name} · {matched_entries[0]['series_name']}")
        else:
            labels.append(scope_key)
    return labels


def build_manager_scope_options(
    current_user: dict[str, Any] | None,
    selected_scope_keys: list[str],
) -> str:
    data = load_validated_data()
    catalog = sorted(
        load_series_catalog(data),
        key=lambda item: (item["region_name"], item["series_name"], item["competition_name"]),
    )
    if not catalog:
        return '<div class="small text-secondary">请先创建地区系列赛目录，再给赛事负责人分配负责范围。</div>'
    cards = []
    selected_set = set(selected_scope_keys)
    for entry in catalog:
        scope_key = build_manager_scope_key(entry["region_name"], entry["series_slug"])
        checked = " checked" if scope_key in selected_set else ""
        disabled = ""
        cards.append(
            f"""
            <label class="team-link-card shadow-sm p-3 h-100 d-block">
              <input class="form-check-input me-2" type="checkbox" name="manager_scope_key" value="{escape(scope_key)}"{checked}{disabled}>
              <span class="fw-semibold">{escape(entry['region_name'])} · {escape(entry['series_name'])}</span>
              <span class="d-block small text-secondary mt-2">{escape(entry['competition_name'])}</span>
            </label>
            """
        )
    card_columns = "".join(
        f'<div class="col-12 col-lg-6">{card}</div>' for card in cards
    )
    return f'<div class="row g-3">{card_columns}</div>'


def build_permission_options(selected_permission_keys: list[str]) -> str:
    selected_set = set(normalize_permission_keys(selected_permission_keys))
    sections: list[str] = []
    for group in PERMISSION_GROUPS:
        cards: list[str] = []
        for permission_key in group["keys"]:
            checked = " checked" if permission_key in selected_set else ""
            cards.append(
                f"""
                <label class="team-link-card shadow-sm p-3 h-100 d-block">
                  <input class="form-check-input me-2" type="checkbox" name="permission_key" value="{escape(permission_key)}"{checked}>
                  <span class="fw-semibold">{escape(PERMISSION_LABELS[permission_key])}</span>
                  <span class="d-block small text-secondary mt-2">{escape(PERMISSION_DESCRIPTIONS[permission_key])}</span>
                </label>
                """
            )
        cards_html = "".join(f'<div class="col-12 col-lg-6">{card}</div>' for card in cards)
        sections.append(
            f"""
            <div class="mb-4">
              <h3 class="h6 mb-2">{escape(group['title'])}</h3>
              <p class="small text-secondary mb-3">{escape(group['copy'])}</p>
              <div class="row g-3">{cards_html}</div>
            </div>
            """
        )
    return "".join(sections)


def account_role_label(user: dict[str, Any]) -> str:
    if is_admin_user(user):
        return ACCOUNT_ROLE_OPTIONS["admin"]
    return ACCOUNT_ROLE_OPTIONS.get(user.get("role") or "member", ACCOUNT_ROLE_OPTIONS["member"])


def revoke_user_sessions(username: str) -> None:
    delete_sessions_for_username(username)


def start_response_html(start_response, status: str, body: str, headers: list[tuple[str, str]] | None = None):
    extra_headers = headers or []
    payload = body.encode("utf-8")
    start_response(
        status,
        [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))] + extra_headers,
    )
    return [payload]


def start_response_json(
    start_response,
    status: str,
    payload: Any,
    headers: list[tuple[str, str]] | None = None,
):
    extra_headers = headers or []
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        status,
        [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))] + extra_headers,
    )
    return [body]


def redirect(start_response, location: str, headers: list[tuple[str, str]] | None = None):
    extra_headers = headers or []
    start_response("302 Found", [("Location", location)] + extra_headers)
    return [b""]


def form_value(form: dict[str, list[str]], key: str, default: str = "") -> str:
    values = form.get(key)
    if not values:
        return default
    return values[0]


def file_value(files: dict[str, list[UploadedFile]], key: str) -> UploadedFile | None:
    values = files.get(key)
    if not values:
        return None
    return values[0]


def option_tags(options: dict[str, str], current: str) -> str:
    tags = []
    for value, label in options.items():
        selected = " selected" if value == current else ""
        tags.append(f'<option value="{escape(value)}"{selected}>{escape(label)}</option>')
    return "".join(tags)


def build_region_picker(
    province_name: str,
    region_name: str,
    picker_id: str,
    helper_text: str = "",
) -> str:
    normalized_province, normalized_region = normalize_user_location(
        province_name,
        region_name,
    )
    selected_province = normalized_province or DEFAULT_PROVINCE_NAME
    selected_region = normalized_region
    picker_slug = normalize_slug_fragment(picker_id, "region-picker")
    helper_html = (
        f'<div class="small text-secondary mt-2">{escape(helper_text)}</div>'
        if helper_text
        else ""
    )
    return f"""
    <div class="region-picker" data-region-map='{escape(CHINA_MAINLAND_LOCATION_OPTIONS_JSON)}'>
      <div class="row g-3">
        <div class="col-12 col-md-6">
          <label class="form-label" for="{picker_slug}-province">省份</label>
          <select class="form-select" id="{picker_slug}-province" name="province_name" data-province-select>
            {option_tags({province: province for province in CHINA_MAINLAND_PROVINCE_OPTIONS}, selected_province)}
          </select>
        </div>
        <div class="col-12 col-md-6">
          <label class="form-label" for="{picker_slug}-city">城市</label>
          <select class="form-select" id="{picker_slug}-city" name="region_name" data-city-select data-selected="{escape(selected_region)}"></select>
        </div>
      </div>
      {helper_html}
    </div>
    <script>
      (function() {{
        const scope = document.currentScript.previousElementSibling;
        if (!scope) return;
        const regionMap = JSON.parse(scope.getAttribute("data-region-map") || "{{}}");
        const provinceSelect = scope.querySelector("[data-province-select]");
        const citySelect = scope.querySelector("[data-city-select]");
        if (!provinceSelect || !citySelect) return;

        function renderCities(selectedCity) {{
          const cities = regionMap[provinceSelect.value] || [];
          citySelect.innerHTML = cities.map((city) => {{
            const selected = city === selectedCity ? " selected" : "";
            return `<option value="${{city}}"${{selected}}>${{city}}</option>`;
          }}).join("");
          if (!citySelect.value && cities.length) {{
            citySelect.value = cities[0];
          }}
        }}

        renderCities(citySelect.getAttribute("data-selected") || "");
        provinceSelect.addEventListener("change", function() {{
          renderCities("");
        }});
      }})();
    </script>
    """


def is_management_path(path: str) -> bool:
    if path in {
        "/accounts",
        "/permissions",
        "/profile",
        "/bindings",
        "/team-center",
        "/team-admin",
        "/series-manage",
        "/matches/new",
    }:
        return True
    if path.startswith("/matches/") and path.endswith("/edit"):
        return True
    if path.startswith("/players/") and path.endswith("/edit"):
        return True
    return False


def build_nav_link(label: str, href: str, active: bool = False) -> str:
    return (
        f'<a class="nav-link nav-pill px-0{" is-active" if active else ""}" '
        f'href="{escape(href)}">{escape(label)}</a>'
    )


def layout(title: str, body: str, ctx: RequestContext, alert: str = "") -> str:
    is_admin_layout = is_management_path(ctx.path)
    body_class = "app-admin" if is_admin_layout else "app-public"
    user_html = ""
    nav_links = []
    admin_nav_links: list[str] = []
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        region_label = get_user_region_label(ctx.current_user)
        user_html = f"""
        <div class="account-actions d-flex flex-wrap align-items-center gap-3">
          <span class="small text-secondary">当前登录：{escape(display_name)} · {escape(role_label)}{' · ' + escape(region_label) if region_label else ''}</span>
          {'' if is_admin_layout else '<a class="btn btn-outline-dark btn-sm" href="/profile">进入控制台</a>'}
          <form method="post" action="/logout" class="m-0">
            <button type="submit" class="btn btn-outline-dark btn-sm">退出登录</button>
          </form>
        </div>
        """
        nav_links = [
            build_nav_link("首页", "/dashboard", ctx.path == "/dashboard"),
            build_nav_link("比赛页面", "/competitions", ctx.path == "/competitions"),
            build_nav_link("门派", "/guilds", ctx.path == "/guilds"),
        ]
        admin_nav_links = [
            build_nav_link("控制台总览", "/profile", ctx.path == "/profile"),
            build_nav_link("战队认领", "/team-center", ctx.path == "/team-center"),
        ]
        if can_manage_matches(ctx.current_user):
            admin_nav_links.append(
                build_nav_link(
                    "比赛管理",
                    "/matches/new",
                    ctx.path == "/matches/new"
                    or (ctx.path.startswith("/matches/") and ctx.path.endswith("/edit")),
                )
            )
        if can_access_series_management(ctx.current_user):
            admin_nav_links.append(
                build_nav_link(
                    "系列赛管理",
                    "/series-manage",
                    ctx.path == "/series-manage",
                )
            )
        if is_admin_user(ctx.current_user):
            admin_nav_links.append(
                build_nav_link("账号管理", "/accounts", ctx.path == "/accounts")
            )
            admin_nav_links.append(
                build_nav_link("权限控制", "/permissions", ctx.path == "/permissions")
            )
            admin_nav_links.append(
                build_nav_link("战队管理", "/team-admin", ctx.path == "/team-admin")
            )
        if is_admin_layout:
            nav_links = admin_nav_links
    else:
        nav_links = [
            build_nav_link("首页", "/dashboard", ctx.path == "/dashboard"),
            build_nav_link("比赛页面", "/competitions", ctx.path == "/competitions"),
            build_nav_link("门派", "/guilds", ctx.path == "/guilds"),
        ]
        user_html = """
        <div class="account-actions d-flex flex-wrap align-items-center gap-2">
          <a class="btn btn-outline-dark btn-sm" href="/login">登录</a>
          <a class="btn btn-dark btn-sm" href="/register">注册</a>
        </div>
        """

    alert_html = ""
    if alert:
        alert_html = f'<div class="alert alert-warning border-0 shadow-sm">{escape(alert)}</div>'

    brand_kicker = "Control Console" if is_admin_layout else "League Site"
    brand_title = "一颗小草后台管理台" if is_admin_layout else "一颗小草赛事数据中心"
    brand_copy = (
        "录入、审核、权限分配与赛事维护"
        if is_admin_layout
        else f"当前时间：{escape(ctx.now_label)}"
    )
    admin_return_link = (
        '<a class="admin-return-link" href="/dashboard">返回公开首页</a>'
        if is_admin_layout
        else ""
    )
    admin_status = ""
    if is_admin_layout:
        current_scope = get_user_region_label(ctx.current_user) or "未绑定地区"
        admin_status = f"""
        <div class="admin-console-strip">
          <div class="admin-console-copy">
            <span class="admin-console-label">Workspace</span>
            <strong>{escape(title)}</strong>
            <span>{escape(current_scope)}</span>
          </div>
          {admin_return_link}
        </div>
        """

    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#edf8f4">
    <title>{escape(title)}</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Manrope:wght@500;600;700;800&family=Noto+Sans+SC:wght@400;500;600;700&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css">
    <style>
      :root {{
        --bg: #eef6fb;
        --bg-alt: #fbfdff;
        --surface: rgba(255, 255, 255, 0.72);
        --surface-strong: rgba(255, 255, 255, 0.94);
        --ink: #16324a;
        --muted: #678093;
        --accent: #77bce8;
        --accent-dark: #3b7fb1;
        --accent-soft: rgba(119, 188, 232, 0.14);
        --sky-soft: rgba(190, 224, 255, 0.32);
        --sun-soft: rgba(255, 255, 255, 0.58);
        --line: rgba(15, 23, 42, 0.08);
        --line-strong: rgba(15, 23, 42, 0.12);
        --shadow: 0 1rem 2.8rem rgba(94, 131, 160, 0.12);
        --shadow-soft: 0 0.65rem 1.6rem rgba(94, 131, 160, 0.08);
      }}
      * {{
        box-sizing: border-box;
      }}
      html {{
        scroll-behavior: smooth;
      }}
      body {{
        min-height: 100vh;
        color: var(--ink);
        font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
        background:
          radial-gradient(circle at top left, rgba(198, 224, 255, 0.42), transparent 28%),
          radial-gradient(circle at top right, rgba(216, 233, 255, 0.48), transparent 24%),
          radial-gradient(circle at bottom right, rgba(208, 225, 247, 0.28), transparent 30%),
          linear-gradient(180deg, var(--bg-alt) 0%, var(--bg) 100%);
      }}
      body::before {{
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background:
          linear-gradient(135deg, rgba(255, 255, 255, 0.46), transparent 42%),
          radial-gradient(circle at 20% 20%, rgba(233, 243, 255, 0.4), transparent 26%);
        opacity: 0.8;
      }}
      body::after {{
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background-image: linear-gradient(rgba(255, 255, 255, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(255, 255, 255, 0.05) 1px, transparent 1px);
        background-size: 26px 26px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.14), transparent 72%);
        opacity: 0.18;
      }}
      .shell {{
        max-width: 1380px;
      }}
      a {{
        color: var(--accent-dark);
      }}
      a:hover {{
        color: var(--accent);
      }}
      .topbar,
      .panel,
      .stat-card,
      .form-panel,
      .team-link-card,
      .table-responsive {{
        border: 1px solid rgba(255, 255, 255, 0.82);
        box-shadow: var(--shadow-soft);
        backdrop-filter: blur(22px);
        -webkit-backdrop-filter: blur(22px);
      }}
      .topbar,
      .panel,
      .form-panel {{
        background: var(--surface);
        border-radius: 18px;
      }}
      .topbar {{
        position: sticky;
        top: 0.75rem;
        z-index: 40;
        background:
          radial-gradient(circle at top right, rgba(210, 230, 255, 0.36), transparent 24%),
          linear-gradient(135deg, rgba(255, 255, 255, 0.92), rgba(245, 249, 255, 0.94));
      }}
      .topbar.mb-4,
      .hero.mb-4,
      .panel.mb-4,
      .form-panel.mb-4 {{
        margin-bottom: 1rem !important;
      }}
      .brand-kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.32rem 0.72rem;
        margin-bottom: 0.5rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.82);
        color: var(--accent-dark);
        font-size: 0.7rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }}
      .brand-kicker::before {{
        content: "";
        width: 0.55rem;
        height: 0.55rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #ffffff, #a9d4ff 55%, var(--accent));
        box-shadow: 0 0 0 0.24rem rgba(119, 188, 232, 0.14);
      }}
      .brand-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.08rem, 1.8vw, 1.32rem);
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .topbar-actions {{
        justify-content: flex-end;
      }}
      .primary-nav {{
        row-gap: 0.45rem;
      }}
      .hero {{
        position: relative;
        overflow: hidden;
        isolation: isolate;
        background:
          linear-gradient(135deg, rgba(255, 255, 255, 0.86), rgba(245, 249, 255, 0.82) 42%, rgba(235, 244, 255, 0.8)),
          linear-gradient(180deg, rgba(255, 255, 255, 0.62), rgba(255, 255, 255, 0.3));
        color: var(--ink);
        border: 1px solid rgba(255, 255, 255, 0.84);
        border-radius: 20px;
        box-shadow: var(--shadow);
        padding: 1rem 1.1rem !important;
      }}
      .hero::before {{
        content: "";
        position: absolute;
        right: -10%;
        bottom: -24%;
        width: min(30vw, 300px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(154, 203, 255, 0.42), rgba(154, 203, 255, 0));
        z-index: -1;
        opacity: 0.78;
      }}
      .hero::after {{
        content: "";
        position: absolute;
        left: -10%;
        top: -20%;
        width: min(24vw, 220px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0));
        z-index: -1;
        opacity: 0.68;
      }}
      .hero-layout {{
        display: grid;
        grid-template-columns: minmax(0, 1.72fr) minmax(220px, 0.72fr);
        gap: 0.65rem;
        align-items: start;
      }}
      .eyebrow {{
        display: inline-flex;
        align-items: center;
        gap: 0.55rem;
        font-size: 0.76rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        letter-spacing: 0.18em;
        text-transform: uppercase;
        color: #3b7fb1;
      }}
      .eyebrow::before {{
        content: "";
        width: 0.8rem;
        height: 1px;
        background: currentColor;
      }}
      .hero-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.6rem, 2.9vw, 3rem);
        line-height: 1;
        letter-spacing: -0.06em;
      }}
      .hero-copy {{
        max-width: 64ch;
        color: rgba(17, 24, 39, 0.74);
        font-size: clamp(0.88rem, 0.98vw, 0.96rem);
        line-height: 1.45;
      }}
      .hero-switchers {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.38rem;
      }}
      .hero-kpis {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.55rem;
        margin-top: 0.8rem;
      }}
      .hero-pill {{
        padding: 0.62rem 0.72rem;
        border-radius: 14px;
        background: rgba(255, 255, 255, 0.5);
        border: 1px solid rgba(255, 255, 255, 0.88);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
      }}
      .hero-pill span {{
        display: block;
        font-size: 0.72rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
      }}
      .hero-pill strong {{
        display: block;
        margin-top: 0.24rem;
        font-size: clamp(0.98rem, 1.4vw, 1.16rem);
        line-height: 1.1;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .hero-pill small {{
        display: block;
        margin-top: 0.16rem;
        color: var(--muted);
        font-size: 0.74rem;
      }}
      .hero-stage-card {{
        position: relative;
        min-height: 100%;
        padding: 0.9rem;
        border-radius: 18px;
        max-width: 340px;
        width: 100%;
        justify-self: end;
        overflow: hidden;
        color: #f8fbff;
        background:
          radial-gradient(circle at top right, rgba(116, 190, 255, 0.32), transparent 28%),
          linear-gradient(160deg, rgba(16, 23, 40, 0.88), rgba(25, 52, 109, 0.78) 62%, rgba(18, 25, 38, 0.88));
        box-shadow: 0 1.8rem 4rem rgba(16, 23, 40, 0.22);
      }}
      .hero-stage-card::before {{
        content: "";
        position: absolute;
        inset: 1px;
        border-radius: inherit;
        border: 1px solid rgba(255, 255, 255, 0.08);
        pointer-events: none;
      }}
      .hero-stage-card::after {{
        content: "";
        position: absolute;
        top: -35%;
        right: -12%;
        width: 70%;
        height: 62%;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.26), rgba(255, 255, 255, 0));
        pointer-events: none;
      }}
      .official-mark {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.4rem 0.8rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.1);
        color: rgba(255, 255, 255, 0.9);
        font-size: 0.74rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .official-mark::before {{
        content: "";
        width: 0.55rem;
        height: 0.55rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #ffffff, #7cc2ff);
      }}
      .hero-stage-label {{
        margin-top: 0.55rem;
        font-size: 0.76rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(244, 247, 255, 0.66);
      }}
      .hero-stage-title {{
        margin-top: 0.42rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.28rem, 1.95vw, 1.9rem);
        font-weight: 800;
        line-height: 1.02;
        letter-spacing: -0.05em;
      }}
      .hero-stage-note {{
        margin-top: 0.42rem;
        color: rgba(244, 247, 255, 0.74);
        line-height: 1.35;
        font-size: 0.82rem;
      }}
      .hero-stage-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.5rem;
        margin-top: 0.72rem;
      }}
      .hero-stage-metric {{
        padding: 0.62rem 0.68rem;
        border-radius: 13px;
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.1);
      }}
      .hero-stage-metric span {{
        display: block;
        font-size: 0.74rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: rgba(244, 247, 255, 0.6);
      }}
      .hero-stage-metric strong {{
        display: block;
        margin-top: 0.28rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1rem;
        font-weight: 800;
        line-height: 1.08;
        letter-spacing: -0.04em;
      }}
      .hero-stage-metric small {{
        display: block;
        margin-top: 0.18rem;
        color: rgba(244, 247, 255, 0.62);
        font-size: 0.76rem;
      }}
      .section-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.05rem, 1.8vw, 1.36rem);
        letter-spacing: -0.04em;
      }}
      .section-copy {{
        color: var(--muted);
        max-width: 68ch;
        font-size: 0.86rem;
        line-height: 1.38;
      }}
      .editorial-copy {{
        max-width: none;
        color: rgba(17, 24, 39, 0.9);
        font-size: 0.94rem;
        line-height: 1.72;
      }}
      .editorial-copy p {{
        margin-bottom: 0.7rem;
      }}
      .editorial-copy p:last-child {{
        margin-bottom: 0;
      }}
      .editorial-copy h1,
      .editorial-copy h2,
      .editorial-copy h3,
      .editorial-copy h4,
      .editorial-copy h5,
      .editorial-copy h6 {{
        margin: 1.1rem 0 0.65rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        letter-spacing: -0.04em;
        line-height: 1.3;
      }}
      .editorial-copy h1:first-child,
      .editorial-copy h2:first-child,
      .editorial-copy h3:first-child,
      .editorial-copy h4:first-child,
      .editorial-copy h5:first-child,
      .editorial-copy h6:first-child {{
        margin-top: 0;
      }}
      .editorial-copy ul,
      .editorial-copy ol {{
        padding-left: 1.4rem;
        margin: 0 0 1rem;
      }}
      .editorial-copy li {{
        margin-bottom: 0.35rem;
      }}
      .editorial-copy blockquote {{
        margin: 0 0 1rem;
        padding: 0.85rem 1rem;
        border-left: 4px solid rgba(176, 94, 53, 0.35);
        background: rgba(176, 94, 53, 0.06);
        border-radius: 0 14px 14px 0;
      }}
      .editorial-copy blockquote p {{
        margin-bottom: 0;
      }}
      .editorial-copy code {{
        padding: 0.12rem 0.35rem;
        border-radius: 0.35rem;
        background: rgba(15, 23, 42, 0.08);
        font-size: 0.92em;
      }}
      .editorial-copy pre {{
        margin: 0 0 1rem;
        padding: 1rem;
        border-radius: 1rem;
        background: rgba(15, 23, 42, 0.92);
        color: rgba(248, 250, 252, 0.96);
        overflow-x: auto;
      }}
      .editorial-copy pre code {{
        padding: 0;
        background: transparent;
        color: inherit;
      }}
      .editorial-copy a {{
        color: var(--accent-dark);
        text-decoration-thickness: 0.08em;
      }}
      .editorial-copy hr {{
        margin: 1.25rem 0;
        border: 0;
        border-top: 1px solid rgba(15, 23, 42, 0.12);
      }}
      .card-kicker {{
        font-size: 0.74rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #3b7fb1;
        font-weight: 700;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
      }}
      .stat-card {{
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(245, 252, 251, 0.88));
        border-radius: 14px;
        padding: 0.75rem !important;
      }}
      .stat-label {{
        font-size: 0.76rem;
        letter-spacing: 0.14em;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        text-transform: uppercase;
        color: var(--muted);
      }}
      .stat-value {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.2rem, 1.9vw, 1.65rem);
        line-height: 1;
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .team-link-card {{
        display: block;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(244, 251, 250, 0.86));
        border-radius: 14px;
        padding: 0.8rem !important;
        color: inherit;
        text-decoration: none;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      }}
      .team-link-card:hover {{
        transform: translateY(-2px);
        border-color: rgba(119, 188, 232, 0.22);
        box-shadow: 0 0.8rem 1.8rem rgba(102, 147, 176, 0.12);
      }}
      .table-responsive {{
        overflow: auto;
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.88), rgba(245, 251, 252, 0.82));
      }}
      .table {{
        --bs-table-bg: transparent;
        --bs-table-border-color: var(--line);
        margin-bottom: 0;
      }}
      .table thead th {{
        white-space: nowrap;
        font-size: 0.74rem;
        letter-spacing: 0.14em;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        text-transform: uppercase;
        color: var(--muted);
        background: rgba(246, 248, 252, 0.86);
        padding-top: 0.58rem;
        padding-bottom: 0.58rem;
      }}
      .table tbody td {{
        padding-top: 0.5rem;
        padding-bottom: 0.5rem;
        font-size: 0.88rem;
      }}
      .panel,
      .form-panel {{
        padding: 0.9rem 1rem !important;
      }}
      .panel > :last-child,
      .form-panel > :last-child,
      .hero > :last-child {{
        margin-bottom: 0 !important;
      }}
      .panel p,
      .form-panel p,
      .hero p {{
        margin-bottom: 0.45rem;
      }}
      .panel h2,
      .panel h3,
      .form-panel h2,
      .form-panel h3 {{
        margin-bottom: 0.35rem;
      }}
      .table tbody tr {{
        transition: background-color 0.18s ease;
      }}
      .table tbody tr:hover {{
        background: rgba(218, 235, 255, 0.48);
      }}
      .table.is-mobile-stack td::before {{
        content: attr(data-label);
        display: none;
      }}
      .schedule-calendar-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
        gap: 0.72rem;
      }}
      .schedule-calendar-month {{
        padding: 0.75rem;
        border-radius: 14px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(246, 249, 255, 0.82));
        border: 1px solid var(--line);
        box-shadow: var(--shadow-soft);
      }}
      .schedule-calendar-month-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: -0.03em;
        margin-bottom: 0.7rem;
      }}
      .schedule-calendar-weekdays,
      .schedule-calendar-days {{
        display: grid;
        grid-template-columns: repeat(7, minmax(0, 1fr));
        gap: 0.35rem;
      }}
      .schedule-calendar-weekday {{
        text-align: center;
        font-size: 0.72rem;
        color: var(--muted);
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        padding-bottom: 0.15rem;
      }}
      .schedule-calendar-day {{
        min-height: 54px;
        border-radius: 12px;
        border: 1px solid rgba(15, 23, 42, 0.06);
        background: rgba(255, 255, 255, 0.52);
        padding: 0.35rem;
      }}
      .schedule-calendar-day.is-outside {{
        opacity: 0.28;
      }}
      .schedule-calendar-day.has-match {{
        background: linear-gradient(160deg, rgba(45, 127, 249, 0.16), rgba(152, 205, 255, 0.26));
        border-color: rgba(45, 127, 249, 0.18);
      }}
      .schedule-calendar-day-link {{
        display: flex;
        flex-direction: column;
        gap: 0.2rem;
        width: 100%;
        min-height: 100%;
        color: inherit;
        text-decoration: none;
      }}
      .schedule-calendar-day-no {{
        display: block;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.92rem;
        font-weight: 800;
        line-height: 1;
      }}
      .schedule-calendar-day-count {{
        display: inline-flex;
        align-self: flex-start;
        margin-top: auto;
        font-size: 0.68rem;
        color: var(--accent-dark);
        background: rgba(255, 255, 255, 0.7);
        border-radius: 999px;
        padding: 0.16rem 0.45rem;
        border: 1px solid rgba(45, 127, 249, 0.12);
      }}
      .small-muted {{
        color: var(--muted);
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 0.22rem 0.58rem;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.88), rgba(226, 239, 255, 0.82));
        color: var(--accent-dark);
        font-size: 0.76rem;
        font-weight: 600;
        border: 1px solid rgba(119, 188, 232, 0.14);
      }}
      .hero .chip {{
        background: rgba(255, 255, 255, 0.5);
        border-color: rgba(255, 255, 255, 0.82);
      }}
      .form-panel {{
        border-radius: 18px;
      }}
      .form-label {{
        font-size: 0.82rem;
        font-weight: 600;
        color: var(--muted);
      }}
      .form-control,
      .form-select {{
        border-radius: 12px;
        border-color: rgba(17, 24, 39, 0.08);
        background: rgba(255, 255, 255, 0.86);
        color: var(--ink);
        padding: 0.52rem 0.74rem;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
      }}
      .form-control:focus,
      .form-select:focus {{
        border-color: rgba(45, 127, 249, 0.36);
        box-shadow: 0 0 0 0.25rem rgba(45, 127, 249, 0.12);
        background: #ffffff;
      }}
      textarea.form-control {{
        min-height: 96px;
      }}
      .player-photo-frame {{
        width: min(100%, 220px);
        aspect-ratio: 1 / 1;
        border-radius: 18px;
        overflow: hidden;
        background:
          radial-gradient(circle at top, rgba(168, 208, 255, 0.3), transparent 42%),
          linear-gradient(160deg, rgba(255, 255, 255, 0.98), rgba(235, 241, 252, 0.92));
        border: 1px solid rgba(255, 255, 255, 0.84);
        box-shadow: var(--shadow);
      }}
      .panel .player-photo-frame {{
        border-color: rgba(45, 127, 249, 0.1);
        box-shadow: var(--shadow-soft);
      }}
      .player-photo {{
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }}
      .nav-link {{
        color: var(--ink);
        font-weight: 600;
        text-decoration: none;
      }}
      .nav-link:hover {{
        color: var(--accent-dark);
      }}
      .nav-pill {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.1rem;
        padding: 0.38rem 0.72rem !important;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.56);
        border: 1px solid rgba(255, 255, 255, 0.78);
        transition: transform 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
      }}
      .nav-pill:hover {{
        transform: translateY(-1px);
        background: rgba(255, 255, 255, 0.78);
        border-color: rgba(119, 188, 232, 0.14);
      }}
      .nav-pill.is-active {{
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(226, 239, 255, 0.94));
        border-color: rgba(119, 188, 232, 0.16);
        color: var(--accent-dark);
        box-shadow: 0 0.8rem 1.7rem rgba(102, 147, 176, 0.08);
      }}
      .switcher-chip {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2rem;
        padding: 0.34rem 0.7rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.82);
        background: rgba(255, 255, 255, 0.56);
        color: var(--ink);
        text-decoration: none;
        font-size: 0.8rem;
        font-weight: 600;
        transition: transform 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
      }}
      .switcher-chip:hover {{
        transform: translateY(-1px);
        background: rgba(255, 255, 255, 0.84);
        box-shadow: 0 0.9rem 1.8rem rgba(15, 23, 42, 0.08);
      }}
      .switcher-chip.is-active {{
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(228, 240, 255, 0.94));
        color: var(--accent-dark);
        border-color: rgba(119, 188, 232, 0.14);
      }}
      .btn {{
        border-radius: 999px;
        font-weight: 700;
        letter-spacing: -0.01em;
        padding: 0.42rem 0.82rem;
        transition: transform 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
      }}
      .btn:hover {{
        transform: translateY(-1px);
      }}
      .btn-sm {{
        padding: 0.34rem 0.7rem;
      }}
      .btn-dark {{
        background: linear-gradient(135deg, #9bd0ff, var(--accent-dark));
        border-color: transparent;
        color: #ffffff;
        box-shadow: 0 0.9rem 1.9rem rgba(119, 188, 232, 0.22);
      }}
      .btn-dark:hover,
      .btn-dark:focus {{
        color: #ffffff;
        background: linear-gradient(135deg, #82bfff, #2f78ad);
        border-color: transparent;
        box-shadow: 0 1.05rem 2.1rem rgba(119, 188, 232, 0.24);
      }}
      .btn-outline-dark {{
        background: rgba(255, 255, 255, 0.62);
        border-color: rgba(255, 255, 255, 0.84);
        color: var(--ink);
      }}
      .btn-outline-dark:hover,
      .btn-outline-dark:focus {{
        color: var(--accent-dark);
        background: rgba(255, 255, 255, 0.86);
        border-color: rgba(119, 188, 232, 0.18);
      }}
      .btn-light {{
        background: rgba(255, 255, 255, 0.72);
        border-color: rgba(255, 255, 255, 0.82);
        color: var(--ink);
      }}
      .btn-light:hover,
      .btn-light:focus {{
        color: var(--accent-dark);
        background: rgba(255, 255, 255, 0.92);
        border-color: rgba(119, 188, 232, 0.14);
      }}
      .alert {{
        border-radius: 14px;
        border: 1px solid rgba(255, 204, 102, 0.3);
        background: linear-gradient(135deg, rgba(255, 252, 243, 0.96), rgba(255, 247, 228, 0.94));
        color: #7a5b14;
        box-shadow: var(--shadow-soft);
      }}
      .p-4,
      .p-lg-4,
      .p-md-5 {{
        padding: 1rem !important;
      }}
      .p-3 {{
        padding: 0.8rem !important;
      }}
      .py-3 {{
        padding-top: 0.8rem !important;
        padding-bottom: 0.8rem !important;
      }}
      .px-4,
      .px-lg-4 {{
        padding-left: 1rem !important;
        padding-right: 1rem !important;
      }}
      .mb-4 {{
        margin-bottom: 0.75rem !important;
      }}
      .mb-3 {{
        margin-bottom: 0.55rem !important;
      }}
      .mb-2 {{
        margin-bottom: 0.35rem !important;
      }}
      .mt-5 {{
        margin-top: 0.9rem !important;
      }}
      .mt-4 {{
        margin-top: 0.7rem !important;
      }}
      .mt-3 {{
        margin-top: 0.5rem !important;
      }}
      .pt-1 {{
        padding-top: 0.12rem !important;
      }}
      .gap-4 {{
        gap: 0.8rem !important;
      }}
      .gap-3 {{
        gap: 0.55rem !important;
      }}
      .gap-2 {{
        gap: 0.42rem !important;
      }}
      .row.g-3 {{
        --bs-gutter-x: 0.65rem;
        --bs-gutter-y: 0.65rem;
      }}
      .row.g-4 {{
        --bs-gutter-x: 0.8rem;
        --bs-gutter-y: 0.8rem;
      }}
      .link-dark,
      .link-dark:focus,
      .link-underline-opacity-0 {{
        color: var(--ink) !important;
      }}
      .link-dark:hover,
      .link-underline-opacity-75-hover:hover {{
        color: var(--accent-dark) !important;
      }}
      .dashboard-home {{
        display: grid;
        gap: 1rem;
      }}
      .dashboard-hero {{
        position: relative;
        overflow: hidden;
        padding: 1.3rem !important;
        border-radius: 24px;
        border: 1px solid rgba(142, 191, 236, 0.24);
        background:
          radial-gradient(circle at top left, rgba(188, 220, 255, 0.38), transparent 28%),
          radial-gradient(circle at 85% 18%, rgba(244, 222, 208, 0.2), transparent 20%),
          linear-gradient(145deg, #fafdff 0%, #f2f8ff 54%, #edf4ff 100%);
        box-shadow: 0 1.3rem 3rem rgba(105, 149, 177, 0.16);
        color: #18324a;
      }}
      .dashboard-hero::before {{
        content: "";
        position: absolute;
        inset: auto -8% -26% auto;
        width: min(32vw, 340px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(151, 197, 255, 0.34), rgba(151, 197, 255, 0));
        pointer-events: none;
      }}
      .dashboard-hero::after {{
        content: "";
        position: absolute;
        inset: 0;
        pointer-events: none;
        background-image: linear-gradient(rgba(91, 136, 163, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(91, 136, 163, 0.05) 1px, transparent 1px);
        background-size: 24px 24px;
        mask-image: linear-gradient(180deg, rgba(0, 0, 0, 0.38), transparent 75%);
        opacity: 0.22;
      }}
      .dashboard-hero .hero-layout {{
        grid-template-columns: minmax(0, 1.48fr) minmax(300px, 0.9fr);
        gap: 0.9rem;
      }}
      .dashboard-hero .eyebrow {{
        color: #3b7fb1;
      }}
      .dashboard-hero .eyebrow::before {{
        background: currentColor;
      }}
      .dashboard-hero .hero-title {{
        color: #17324d;
        font-size: clamp(2rem, 4.2vw, 4.1rem);
        line-height: 0.95;
        text-wrap: balance;
      }}
      .dashboard-hero .hero-copy {{
        max-width: 58ch;
        color: rgba(60, 91, 117, 0.78);
        font-size: 0.96rem;
        line-height: 1.62;
      }}
      .dashboard-status-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
        margin-top: 0.8rem;
      }}
      .dashboard-status-chip {{
        display: inline-flex;
        align-items: center;
        gap: 0.42rem;
        padding: 0.38rem 0.72rem;
        border-radius: 999px;
        border: 1px solid rgba(142, 191, 236, 0.16);
        background: rgba(255, 255, 255, 0.7);
        color: #35516e;
        font-size: 0.78rem;
        font-weight: 600;
      }}
      .dashboard-status-chip strong {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.82rem;
        letter-spacing: -0.03em;
      }}
      .dashboard-filter-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.72rem;
        margin-top: 0.95rem;
      }}
      .dashboard-filter-block {{
        min-height: 100%;
        padding: 0.82rem 0.88rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.66);
        border: 1px solid rgba(142, 191, 236, 0.12);
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.36);
      }}
      .dashboard-filter-label {{
        margin-bottom: 0.55rem;
        color: rgba(72, 113, 158, 0.78);
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }}
      .dashboard-filter-block .hero-switchers {{
        gap: 0.48rem;
      }}
      .dashboard-home .dashboard-filter-block .switcher-chip {{
        min-height: 2.1rem;
        background: rgba(255, 255, 255, 0.82);
        border-color: rgba(142, 191, 236, 0.12);
        color: #35516e;
      }}
      .dashboard-home .dashboard-filter-block .switcher-chip:hover {{
        background: rgba(255, 255, 255, 0.98);
        color: #17324d;
        box-shadow: none;
      }}
      .dashboard-home .dashboard-filter-block .switcher-chip.is-active {{
        background: linear-gradient(135deg, rgba(201, 226, 255, 0.96), rgba(230, 239, 255, 0.98));
        border-color: rgba(142, 191, 236, 0.22);
        color: #356d9c;
        box-shadow: 0 0.8rem 1.7rem rgba(118, 168, 195, 0.12);
      }}
      .dashboard-home .dashboard-filter-block form {{
        margin: 0;
      }}
      .dashboard-home .dashboard-filter-block label {{
        color: rgba(72, 113, 158, 0.84) !important;
      }}
      .dashboard-home .dashboard-filter-block .form-select {{
        min-width: 100% !important;
        background: rgba(255, 255, 255, 0.92);
        border-color: rgba(142, 191, 236, 0.14);
        color: #17324d;
      }}
      .dashboard-home .dashboard-filter-block .form-select:focus {{
        background: #ffffff;
        border-color: rgba(142, 191, 236, 0.22);
        box-shadow: 0 0 0 0.22rem rgba(142, 191, 236, 0.14);
      }}
      .dashboard-hero-side {{
        display: grid;
        gap: 0.72rem;
      }}
      .dashboard-spotlight-card,
      .dashboard-brief-card {{
        position: relative;
        overflow: hidden;
        border-radius: 20px;
        border: 1px solid rgba(142, 191, 236, 0.14);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.84), rgba(247, 252, 255, 0.72));
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.4);
      }}
      .dashboard-spotlight-card {{
        padding: 1rem;
      }}
      .dashboard-spotlight-card::after {{
        content: "";
        position: absolute;
        top: -20%;
        right: -18%;
        width: 56%;
        height: 56%;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(192, 216, 255, 0.22), rgba(192, 216, 255, 0));
        pointer-events: none;
      }}
      .dashboard-panel-kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        color: rgba(72, 113, 158, 0.78);
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }}
      .dashboard-panel-kicker::before {{
        content: "";
        width: 0.52rem;
        height: 0.52rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #b8d8ff, #93cfff);
      }}
      .dashboard-spotlight-title {{
        margin-top: 0.6rem;
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.28rem, 2vw, 1.9rem);
        font-weight: 800;
        letter-spacing: -0.05em;
        line-height: 1.02;
      }}
      .dashboard-spotlight-copy {{
        margin-top: 0.48rem;
        color: rgba(76, 102, 125, 0.76);
        font-size: 0.85rem;
        line-height: 1.48;
      }}
      .dashboard-spotlight-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.55rem;
        margin-top: 0.8rem;
      }}
      .dashboard-spotlight-metric {{
        padding: 0.72rem;
        border-radius: 16px;
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(142, 191, 236, 0.12);
      }}
      .dashboard-spotlight-metric span {{
        display: block;
        color: rgba(72, 113, 158, 0.68);
        font-size: 0.7rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }}
      .dashboard-spotlight-metric strong {{
        display: block;
        margin-top: 0.28rem;
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1rem;
        font-weight: 800;
        line-height: 1.12;
        letter-spacing: -0.04em;
      }}
      .dashboard-spotlight-metric small {{
        display: block;
        margin-top: 0.14rem;
        color: rgba(76, 102, 125, 0.62);
        font-size: 0.74rem;
      }}
      .dashboard-brief-card {{
        padding: 0.9rem;
      }}
      .dashboard-brief-list {{
        display: grid;
        gap: 0.58rem;
        margin-top: 0.78rem;
      }}
      .dashboard-brief-item {{
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        gap: 0.62rem;
        align-items: center;
      }}
      .dashboard-rank-badge {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2rem;
        height: 2rem;
        border-radius: 14px;
        background: linear-gradient(135deg, rgba(195, 223, 255, 0.9), rgba(226, 236, 255, 0.92));
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.84rem;
        font-weight: 800;
      }}
      .dashboard-brief-name {{
        color: #17324d;
        font-size: 0.9rem;
        font-weight: 700;
      }}
      .dashboard-brief-meta {{
        color: rgba(98, 121, 143, 0.72);
        font-size: 0.76rem;
      }}
      .dashboard-brief-value {{
        color: #3b7fb1;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.96rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        text-align: right;
      }}
      .dashboard-brief-value small {{
        display: block;
        color: rgba(98, 121, 143, 0.6);
        font-size: 0.68rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
      }}
      .dashboard-metrics-grid {{
        display: grid;
        grid-template-columns: repeat(4, minmax(0, 1fr));
        gap: 0.8rem;
      }}
      .dashboard-metric-card {{
        position: relative;
        min-height: 100%;
        padding: 1rem;
        border-radius: 20px;
        border: 1px solid rgba(17, 24, 39, 0.06);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(246, 249, 255, 0.88));
        box-shadow: 0 1rem 2.2rem rgba(15, 23, 42, 0.08);
      }}
      .dashboard-metric-card::before {{
        content: "";
        position: absolute;
        inset: 0 auto auto 0;
        width: 100%;
        height: 4px;
        border-radius: 20px 20px 0 0;
        background: linear-gradient(90deg, #72b7ef, #a4cff8, #f1c8af);
        opacity: 0.88;
      }}
      .dashboard-metric-label {{
        color: #667085;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.16em;
        text-transform: uppercase;
      }}
      .dashboard-metric-value {{
        margin-top: 0.46rem;
        color: #0f172a;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.6rem, 2.6vw, 2.4rem);
        font-weight: 800;
        letter-spacing: -0.06em;
        line-height: 0.94;
      }}
      .dashboard-metric-copy {{
        margin-top: 0.36rem;
        color: #64748b;
        font-size: 0.82rem;
        line-height: 1.45;
      }}
      .dashboard-grid {{
        display: grid;
        grid-template-columns: minmax(0, 1.55fr) minmax(280px, 0.82fr);
        gap: 0.9rem;
      }}
      .dashboard-section-panel {{
        padding: 1rem !important;
        border-radius: 22px;
      }}
      .dashboard-section-head {{
        display: flex;
        flex-wrap: wrap;
        align-items: end;
        justify-content: space-between;
        gap: 0.8rem;
        margin-bottom: 0.9rem;
      }}
      .dashboard-section-copy {{
        max-width: 62ch;
        color: var(--muted);
        font-size: 0.88rem;
        line-height: 1.48;
      }}
      .dashboard-feature-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.85rem;
      }}
      .dashboard-feature-card {{
        position: relative;
        overflow: hidden;
        min-height: 100%;
        padding: 1rem;
        border-radius: 22px;
        background:
          radial-gradient(circle at top right, rgba(190, 221, 255, 0.18), transparent 24%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 251, 250, 0.94));
        border: 1px solid rgba(17, 24, 39, 0.06);
        box-shadow: 0 1rem 2.2rem rgba(15, 23, 42, 0.08);
      }}
      .dashboard-feature-card::after {{
        content: "";
        position: absolute;
        right: -16%;
        bottom: -28%;
        width: 46%;
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(151, 197, 255, 0.16), rgba(151, 197, 255, 0));
        pointer-events: none;
      }}
      .dashboard-feature-top {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.6rem;
      }}
      .dashboard-feature-tag {{
        display: inline-flex;
        align-items: center;
        padding: 0.28rem 0.6rem;
        border-radius: 999px;
        background: rgba(190, 221, 255, 0.16);
        color: #3b7fb1;
        font-size: 0.72rem;
        font-weight: 700;
      }}
      .dashboard-feature-title {{
        margin-top: 0.85rem;
        color: #0f172a;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.2rem, 1.8vw, 1.7rem);
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .dashboard-feature-copy {{
        margin-top: 0.38rem;
        color: #475569;
        font-size: 0.86rem;
        line-height: 1.5;
      }}
      .dashboard-feature-stats {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.55rem;
        margin-top: 0.85rem;
      }}
      .dashboard-feature-stat {{
        padding: 0.62rem 0.68rem;
        border-radius: 15px;
        background: rgba(255, 255, 255, 0.78);
        border: 1px solid rgba(17, 24, 39, 0.06);
      }}
      .dashboard-feature-stat span {{
        display: block;
        color: #64748b;
        font-size: 0.7rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .dashboard-feature-stat strong {{
        display: block;
        margin-top: 0.26rem;
        color: #111827;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.98rem;
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .dashboard-feature-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.52rem;
        margin-top: 0.95rem;
      }}
      .dashboard-side-panel {{
        padding: 1rem !important;
        border-radius: 22px;
      }}
      .dashboard-ranking-list {{
        display: grid;
        gap: 0.68rem;
        margin-top: 0.9rem;
      }}
      .dashboard-ranking-item {{
        display: grid;
        grid-template-columns: auto minmax(0, 1fr) auto;
        gap: 0.7rem;
        align-items: center;
        padding: 0.78rem 0.82rem;
        border-radius: 18px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(246, 249, 255, 0.82));
        border: 1px solid rgba(17, 24, 39, 0.05);
        color: inherit;
        text-decoration: none;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
      }}
      .dashboard-ranking-item:hover {{
        transform: translateY(-1px);
        box-shadow: 0 0.9rem 1.8rem rgba(15, 23, 42, 0.08);
        border-color: rgba(29, 78, 216, 0.12);
      }}
      .dashboard-ranking-index {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 2.2rem;
        height: 2.2rem;
        border-radius: 16px;
        background: linear-gradient(135deg, #0f172a, #1d4ed8);
        color: #ffffff;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.84rem;
        font-weight: 800;
      }}
      .dashboard-ranking-name {{
        color: #0f172a;
        font-size: 0.92rem;
        font-weight: 700;
      }}
      .dashboard-ranking-meta {{
        color: #64748b;
        font-size: 0.76rem;
        line-height: 1.4;
      }}
      .dashboard-ranking-score {{
        text-align: right;
        color: #0f172a;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 0.98rem;
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .dashboard-ranking-score small {{
        display: block;
        color: #64748b;
        font-size: 0.68rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
      }}
      .dashboard-day-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.85rem;
      }}
      .dashboard-day-card {{
        display: block;
        min-height: 100%;
        padding: 1rem;
        border-radius: 22px;
        background:
          radial-gradient(circle at top right, rgba(198, 224, 255, 0.18), transparent 22%),
          linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(246, 252, 251, 0.9));
        border: 1px solid rgba(17, 24, 39, 0.06);
        box-shadow: 0 1rem 2.2rem rgba(15, 23, 42, 0.08);
        color: inherit;
        text-decoration: none;
        transition: transform 0.18s ease, box-shadow 0.18s ease, border-color 0.18s ease;
      }}
      .dashboard-day-card:hover {{
        transform: translateY(-2px);
        box-shadow: 0 1.1rem 2.3rem rgba(102, 147, 176, 0.1);
        border-color: rgba(142, 191, 236, 0.24);
      }}
      .dashboard-day-top {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
      }}
      .dashboard-day-kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.4rem;
        color: #3b7fb1;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.14em;
        text-transform: uppercase;
      }}
      .dashboard-day-kicker::before {{
        content: "";
        width: 0.5rem;
        height: 0.5rem;
        border-radius: 50%;
        background: linear-gradient(135deg, #bfdcff, #9bd0ff);
      }}
      .dashboard-day-count {{
        padding: 0.28rem 0.58rem;
        border-radius: 999px;
        background: rgba(198, 224, 255, 0.28);
        color: #3b7fb1;
        font-size: 0.74rem;
        font-weight: 700;
      }}
      .dashboard-day-title {{
        margin-top: 0.92rem;
        color: #0f172a;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.28rem, 1.9vw, 1.86rem);
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .dashboard-day-copy {{
        margin-top: 0.32rem;
        color: #64748b;
        font-size: 0.84rem;
        line-height: 1.48;
      }}
      .dashboard-day-tags {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.42rem;
        margin-top: 0.78rem;
      }}
      .dashboard-day-tag {{
        display: inline-flex;
        align-items: center;
        padding: 0.26rem 0.55rem;
        border-radius: 999px;
        background: rgba(15, 23, 42, 0.05);
        color: #334155;
        font-size: 0.74rem;
        font-weight: 600;
      }}
      .player-showcase-grid {{
        display: grid;
        grid-template-columns: minmax(0, 1.3fr) minmax(320px, 0.9fr);
        gap: 0.9rem;
      }}
      .player-showcase-card,
      .player-insight-card,
      .player-role-card,
      .player-match-card,
      .player-season-card,
      .player-competition-card {{
        position: relative;
        overflow: hidden;
        border-radius: 22px;
        border: 1px solid rgba(17, 24, 39, 0.06);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(245, 250, 255, 0.9));
        box-shadow: 0 1rem 2.2rem rgba(15, 23, 42, 0.08);
      }}
      .player-showcase-card,
      .player-insight-card {{
        padding: 1rem;
      }}
      .player-showcase-card::after,
      .player-insight-card::after {{
        content: "";
        position: absolute;
        right: -12%;
        bottom: -20%;
        width: 42%;
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(153, 201, 255, 0.18), rgba(153, 201, 255, 0));
        pointer-events: none;
      }}
      .player-masthead {{
        display: flex;
        align-items: flex-start;
        gap: 0.9rem;
      }}
      .player-masthead-copy {{
        min-width: 0;
        flex: 1;
      }}
      .player-masthead-meta {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.42rem;
        margin-top: 0.78rem;
      }}
      .player-headline {{
        margin-top: 0.3rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.4rem, 2.4vw, 2.2rem);
        font-weight: 800;
        letter-spacing: -0.05em;
        color: #17324d;
      }}
      .player-subtitle {{
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.55;
      }}
      .player-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.34rem 0.68rem;
        border-radius: 999px;
        background: rgba(226, 239, 255, 0.72);
        color: #356d9c;
        font-size: 0.76rem;
        font-weight: 700;
      }}
      .player-kpi-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.72rem;
        margin-top: 1rem;
      }}
      .player-kpi-card {{
        padding: 0.78rem 0.82rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(17, 24, 39, 0.06);
      }}
      .player-kpi-label {{
        color: #64748b;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .player-kpi-value {{
        margin-top: 0.34rem;
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.25rem, 1.9vw, 1.7rem);
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .player-kpi-copy {{
        margin-top: 0.18rem;
        color: #6b7f93;
        font-size: 0.76rem;
        line-height: 1.4;
      }}
      .player-insight-card {{
        display: grid;
        gap: 0.7rem;
      }}
      .player-skill-row {{
        display: grid;
        gap: 0.32rem;
      }}
      .player-skill-head {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
      }}
      .player-skill-head strong {{
        color: #17324d;
        font-size: 0.88rem;
      }}
      .player-skill-head span {{
        color: #64748b;
        font-size: 0.76rem;
      }}
      .player-skill-track {{
        position: relative;
        height: 0.55rem;
        border-radius: 999px;
        background: rgba(217, 230, 243, 0.9);
        overflow: hidden;
      }}
      .player-skill-fill {{
        position: absolute;
        inset: 0 auto 0 0;
        border-radius: inherit;
        background: linear-gradient(90deg, #88bffd, #63d4c7);
      }}
      .player-note-grid {{
        display: grid;
        gap: 0.62rem;
      }}
      .player-note-item {{
        padding: 0.78rem 0.82rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid rgba(17, 24, 39, 0.06);
      }}
      .player-note-label {{
        color: #64748b;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }}
      .player-note-value {{
        margin-top: 0.2rem;
        color: #17324d;
        font-weight: 700;
        line-height: 1.5;
      }}
      .player-roles-grid,
      .player-season-grid,
      .player-competition-grid,
      .player-match-grid {{
        display: grid;
        gap: 0.8rem;
      }}
      .player-roles-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .player-season-grid,
      .player-competition-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .player-role-card,
      .player-season-card,
      .player-competition-card,
      .player-match-card {{
        padding: 0.9rem;
      }}
      .player-role-top,
      .player-season-top,
      .player-competition-top,
      .player-match-top {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.7rem;
      }}
      .player-role-name,
      .player-season-name,
      .player-competition-name,
      .player-match-name {{
        color: #17324d;
        font-size: 0.98rem;
        font-weight: 800;
        line-height: 1.3;
      }}
      .player-role-meta,
      .player-season-meta,
      .player-competition-meta,
      .player-match-meta {{
        color: #64748b;
        font-size: 0.78rem;
        line-height: 1.45;
      }}
      .player-role-count,
      .player-season-points,
      .player-competition-points,
      .player-match-points {{
        color: #3b7fb1;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        white-space: nowrap;
      }}
      .player-role-track {{
        margin-top: 0.75rem;
        height: 0.52rem;
        border-radius: 999px;
        background: rgba(217, 230, 243, 0.9);
        overflow: hidden;
      }}
      .player-role-fill {{
        height: 100%;
        border-radius: inherit;
        background: linear-gradient(90deg, #9fc4ff, #74d2c8);
      }}
      .player-role-share {{
        margin-top: 0.42rem;
        color: #64748b;
        font-size: 0.76rem;
      }}
      .player-season-stats,
      .player-competition-stats,
      .player-match-tags {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.4rem;
        margin-top: 0.75rem;
      }}
      .player-stat-pill {{
        display: inline-flex;
        align-items: center;
        padding: 0.24rem 0.52rem;
        border-radius: 999px;
        background: rgba(226, 239, 255, 0.7);
        color: #356d9c;
        font-size: 0.74rem;
        font-weight: 700;
      }}
      .player-match-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .player-match-card {{
        display: grid;
        gap: 0.72rem;
      }}
      .player-match-result {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-width: 4.6rem;
        padding: 0.34rem 0.62rem;
        border-radius: 999px;
        background: rgba(234, 179, 8, 0.12);
        color: #a16207;
        font-size: 0.76rem;
        font-weight: 700;
      }}
      .player-match-result.is-win {{
        background: rgba(34, 197, 94, 0.12);
        color: #15803d;
      }}
      .player-match-result.is-loss {{
        background: rgba(239, 68, 68, 0.1);
        color: #b91c1c;
      }}
      .player-match-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
      }}
      .team-showcase-grid {{
        display: grid;
        grid-template-columns: minmax(0, 1.26fr) minmax(320px, 0.94fr);
        gap: 0.9rem;
      }}
      .team-showcase-card,
      .team-insight-card,
      .team-roster-card,
      .team-match-card {{
        position: relative;
        overflow: hidden;
        border-radius: 22px;
        border: 1px solid rgba(17, 24, 39, 0.06);
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.96), rgba(245, 250, 255, 0.9));
        box-shadow: 0 1rem 2.2rem rgba(15, 23, 42, 0.08);
      }}
      .team-showcase-card,
      .team-insight-card {{
        padding: 1rem;
      }}
      .team-showcase-card::after,
      .team-insight-card::after {{
        content: "";
        position: absolute;
        right: -12%;
        bottom: -22%;
        width: 42%;
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(153, 201, 255, 0.18), rgba(153, 201, 255, 0));
        pointer-events: none;
      }}
      .team-headline {{
        margin-top: 0.3rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.42rem, 2.45vw, 2.2rem);
        font-weight: 800;
        letter-spacing: -0.05em;
        color: #17324d;
      }}
      .team-subtitle {{
        color: #64748b;
        font-size: 0.9rem;
        line-height: 1.55;
      }}
      .team-badge-row,
      .team-insight-tags,
      .team-roster-tags {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.42rem;
      }}
      .team-badge {{
        display: inline-flex;
        align-items: center;
        gap: 0.35rem;
        padding: 0.34rem 0.68rem;
        border-radius: 999px;
        background: rgba(226, 239, 255, 0.72);
        color: #356d9c;
        font-size: 0.76rem;
        font-weight: 700;
      }}
      .team-kpi-grid {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.72rem;
        margin-top: 1rem;
      }}
      .team-kpi-card {{
        padding: 0.78rem 0.82rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.74);
        border: 1px solid rgba(17, 24, 39, 0.06);
      }}
      .team-kpi-label {{
        color: #64748b;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .team-kpi-value {{
        margin-top: 0.34rem;
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.2rem, 1.85vw, 1.64rem);
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .team-kpi-copy {{
        margin-top: 0.18rem;
        color: #6b7f93;
        font-size: 0.76rem;
        line-height: 1.4;
      }}
      .team-insight-card {{
        display: grid;
        gap: 0.7rem;
      }}
      .team-meter-row {{
        display: grid;
        gap: 0.32rem;
      }}
      .team-meter-head {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 0.7rem;
      }}
      .team-meter-head strong {{
        color: #17324d;
        font-size: 0.88rem;
      }}
      .team-meter-head span {{
        color: #64748b;
        font-size: 0.76rem;
      }}
      .team-meter-track {{
        position: relative;
        height: 0.55rem;
        border-radius: 999px;
        background: rgba(217, 230, 243, 0.9);
        overflow: hidden;
      }}
      .team-meter-fill {{
        position: absolute;
        inset: 0 auto 0 0;
        border-radius: inherit;
        background: linear-gradient(90deg, #88bffd, #63d4c7);
      }}
      .team-note-grid,
      .team-roster-grid,
      .team-match-grid {{
        display: grid;
        gap: 0.8rem;
      }}
      .team-note-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .team-note-item {{
        padding: 0.78rem 0.82rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, 0.76);
        border: 1px solid rgba(17, 24, 39, 0.06);
      }}
      .team-note-label {{
        color: #64748b;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.1em;
        text-transform: uppercase;
      }}
      .team-note-value {{
        margin-top: 0.2rem;
        color: #17324d;
        font-weight: 700;
        line-height: 1.5;
      }}
      .team-roster-grid {{
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }}
      .team-match-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
      .team-roster-card,
      .team-match-card {{
        padding: 0.9rem;
      }}
      .team-roster-card {{
        display: grid;
        gap: 0.72rem;
      }}
      .team-roster-top,
      .team-match-top {{
        display: flex;
        align-items: flex-start;
        justify-content: space-between;
        gap: 0.7rem;
      }}
      .team-roster-name,
      .team-match-name {{
        color: #17324d;
        font-size: 0.98rem;
        font-weight: 800;
        line-height: 1.3;
      }}
      .team-roster-meta,
      .team-match-meta {{
        color: #64748b;
        font-size: 0.78rem;
        line-height: 1.45;
      }}
      .team-roster-value,
      .team-match-value {{
        color: #3b7fb1;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: -0.04em;
        white-space: nowrap;
      }}
      .team-match-card {{
        display: grid;
        gap: 0.72rem;
      }}
      .team-scoreboard {{
        display: flex;
        align-items: baseline;
        gap: 0.5rem;
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
      }}
      .team-scoreboard strong {{
        font-size: 1.16rem;
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .team-scoreboard span {{
        color: #64748b;
        font-size: 0.78rem;
      }}
      .team-match-actions {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.45rem;
      }}
      .compact-list-wrap {{
        overflow: visible;
        border: 0;
        border-radius: 0;
        background: transparent;
        box-shadow: none;
        backdrop-filter: none;
        -webkit-backdrop-filter: none;
      }}
      .compact-scope-block + .compact-scope-block {{
        margin-top: 1rem;
        padding-top: 1rem;
        border-top: 1px solid rgba(15, 23, 42, 0.08);
      }}
      .admin-console-strip {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        justify-content: space-between;
        gap: 0.75rem;
        margin-bottom: 0.95rem;
        padding: 0.95rem 1rem;
        border-radius: 20px;
        border: 1px solid rgba(125, 166, 210, 0.18);
        background:
          radial-gradient(circle at top right, rgba(165, 214, 255, 0.28), transparent 24%),
          linear-gradient(135deg, rgba(244, 251, 255, 0.98), rgba(236, 245, 255, 0.95));
        box-shadow: 0 1rem 2.2rem rgba(117, 145, 179, 0.16);
      }}
      .admin-console-copy {{
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: 0.55rem;
        color: #5f7288;
      }}
      .admin-console-copy strong {{
        color: #17324d;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: -0.03em;
      }}
      .admin-console-label {{
        display: inline-flex;
        align-items: center;
        padding: 0.3rem 0.6rem;
        border-radius: 999px;
        background: rgba(113, 197, 188, 0.18);
        color: #0f766e;
        font-size: 0.72rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: 0.12em;
        text-transform: uppercase;
      }}
      .admin-return-link {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.2rem;
        padding: 0.42rem 0.86rem;
        border-radius: 999px;
        border: 1px solid rgba(125, 166, 210, 0.18);
        background: rgba(255, 255, 255, 0.72);
        color: #17324d;
        text-decoration: none;
        font-weight: 700;
      }}
      .admin-return-link:hover {{
        color: #0f5cc6;
        background: rgba(255, 255, 255, 0.96);
      }}
      body.app-admin {{
        background:
          radial-gradient(circle at top left, rgba(152, 230, 223, 0.22), transparent 28%),
          radial-gradient(circle at top right, rgba(176, 220, 255, 0.28), transparent 24%),
          radial-gradient(circle at bottom right, rgba(196, 234, 255, 0.22), transparent 24%),
          linear-gradient(180deg, #f5fbff 0%, #edf6fb 100%);
        color: #19324a;
      }}
      body.app-admin::before {{
        background:
          linear-gradient(135deg, rgba(255, 255, 255, 0.46), transparent 42%),
          radial-gradient(circle at 20% 20%, rgba(150, 219, 214, 0.22), transparent 24%);
      }}
      body.app-admin::after {{
        background-image: linear-gradient(rgba(148, 163, 184, 0.05) 1px, transparent 1px),
          linear-gradient(90deg, rgba(148, 163, 184, 0.05) 1px, transparent 1px);
        opacity: 0.16;
      }}
      body.app-admin .topbar,
      body.app-admin .panel,
      body.app-admin .form-panel,
      body.app-admin .table-responsive,
      body.app-admin .team-link-card,
      body.app-admin .stat-card {{
        border-color: rgba(125, 166, 210, 0.14);
        box-shadow: 0 1rem 2.4rem rgba(126, 151, 180, 0.12);
        backdrop-filter: blur(18px);
        -webkit-backdrop-filter: blur(18px);
      }}
      body.app-admin .topbar,
      body.app-admin .panel,
      body.app-admin .form-panel {{
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.86), rgba(247, 251, 255, 0.8));
      }}
      body.app-admin .topbar {{
        background:
          radial-gradient(circle at top right, rgba(178, 224, 255, 0.28), transparent 22%),
          linear-gradient(135deg, rgba(255, 255, 255, 0.94), rgba(242, 249, 255, 0.9));
      }}
      body.app-admin .brand-kicker {{
        background: rgba(113, 197, 188, 0.14);
        color: #0f766e;
      }}
      body.app-admin .brand-title,
      body.app-admin .nav-link,
      body.app-admin .section-title,
      body.app-admin .dashboard-metric-value,
      body.app-admin .dashboard-ranking-name,
      body.app-admin .dashboard-feature-title,
      body.app-admin .dashboard-day-title {{
        color: #17324d;
      }}
      body.app-admin .small,
      body.app-admin .small-muted,
      body.app-admin .section-copy,
      body.app-admin .dashboard-section-copy,
      body.app-admin .dashboard-feature-copy,
      body.app-admin .dashboard-day-copy,
      body.app-admin .dashboard-ranking-meta,
      body.app-admin .form-label,
      body.app-admin .text-secondary {{
        color: #6f869b !important;
      }}
      body.app-admin .nav-pill {{
        background: rgba(255, 255, 255, 0.74);
        border-color: rgba(125, 166, 210, 0.16);
        color: #35516e;
      }}
      body.app-admin .nav-pill:hover {{
        background: rgba(255, 255, 255, 0.96);
        border-color: rgba(84, 156, 231, 0.22);
      }}
      body.app-admin .nav-pill.is-active {{
        background: linear-gradient(135deg, rgba(136, 219, 209, 0.82), rgba(173, 220, 255, 0.92));
        border-color: rgba(105, 184, 203, 0.26);
        color: #0f4c81;
      }}
      body.app-admin .hero {{
        background:
          radial-gradient(circle at top right, rgba(170, 225, 255, 0.34), transparent 24%),
          radial-gradient(circle at left bottom, rgba(160, 231, 222, 0.24), transparent 24%),
          linear-gradient(145deg, rgba(248, 252, 255, 0.96), rgba(239, 248, 255, 0.92));
        border-color: rgba(125, 166, 210, 0.14);
        color: #17324d;
      }}
      body.app-admin .hero-copy,
      body.app-admin .hero p,
      body.app-admin .opacity-75 {{
        color: rgba(47, 82, 112, 0.78) !important;
      }}
      body.app-admin .chip,
      body.app-admin .hero .chip {{
        background: rgba(173, 220, 255, 0.28);
        border-color: rgba(125, 166, 210, 0.16);
        color: #0f5cc6;
      }}
      body.app-admin .team-link-card,
      body.app-admin .stat-card,
      body.app-admin .dashboard-feature-card,
      body.app-admin .dashboard-day-card,
      body.app-admin .dashboard-ranking-item,
      body.app-admin .dashboard-metric-card {{
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(244, 250, 255, 0.88));
        border-color: rgba(125, 166, 210, 0.12);
      }}
      body.app-admin .dashboard-feature-tag,
      body.app-admin .dashboard-day-tag,
      body.app-admin .dashboard-day-count {{
        background: rgba(173, 220, 255, 0.28);
        color: #0f5cc6;
      }}
      body.app-admin .dashboard-ranking-index,
      body.app-admin .dashboard-rank-badge {{
        background: linear-gradient(135deg, #86ddd2, #6daeff);
      }}
      body.app-admin .dashboard-ranking-score,
      body.app-admin .dashboard-brief-value {{
        color: #d97706;
      }}
      body.app-admin .form-control,
      body.app-admin .form-select {{
        background: rgba(255, 255, 255, 0.92);
        border-color: rgba(125, 166, 210, 0.16);
        color: #17324d;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8);
      }}
      body.app-admin .form-control:focus,
      body.app-admin .form-select:focus {{
        background: #ffffff;
        border-color: rgba(84, 156, 231, 0.26);
        box-shadow: 0 0 0 0.24rem rgba(84, 156, 231, 0.14);
        color: #0f2740;
      }}
      body.app-admin .btn-outline-dark,
      body.app-admin .btn-light {{
        background: rgba(255, 255, 255, 0.84);
        border-color: rgba(125, 166, 210, 0.16);
        color: #35516e;
      }}
      body.app-admin .btn-outline-dark:hover,
      body.app-admin .btn-light:hover {{
        background: rgba(255, 255, 255, 1);
        color: #0f5cc6;
      }}
      body.app-admin .table {{
        color: #19324a;
      }}
      body.app-admin .table thead th {{
        background: rgba(230, 243, 255, 0.9);
        color: #3b6a93;
      }}
      body.app-admin .table tbody tr:hover {{
        background: rgba(173, 220, 255, 0.18);
      }}
      body.app-admin .alert {{
        border-color: rgba(251, 191, 36, 0.2);
        background: linear-gradient(135deg, rgba(255, 250, 235, 0.96), rgba(255, 244, 214, 0.92));
        color: #9a6700;
      }}
      @media (max-width: 991.98px) {{
        .dashboard-hero .hero-layout,
        .dashboard-grid,
        .player-showcase-grid,
        .team-showcase-grid {{
          grid-template-columns: 1fr;
        }}
        .dashboard-metrics-grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .dashboard-day-grid,
        .dashboard-feature-grid {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .hero-layout {{
          grid-template-columns: 1fr;
        }}
        .topbar,
        .panel,
        .form-panel,
        .hero {{
          border-radius: 16px;
        }}
        .topbar {{
          position: relative;
          top: 0;
        }}
        .topbar-actions {{
          justify-content: flex-start;
        }}
      }}
      @media (max-width: 767.98px) {{
        .dashboard-hero {{
          padding: 1rem !important;
        }}
        .dashboard-filter-grid,
        .dashboard-feature-grid,
        .dashboard-day-grid,
        .player-roles-grid,
        .player-season-grid,
        .player-competition-grid,
        .player-match-grid,
        .team-roster-grid,
        .team-match-grid {{
          grid-template-columns: 1fr;
        }}
        .dashboard-metrics-grid {{
          grid-template-columns: 1fr 1fr;
          gap: 0.7rem;
        }}
        .dashboard-feature-stats,
        .dashboard-spotlight-grid {{
          grid-template-columns: 1fr 1fr;
        }}
        .container-fluid {{
          padding-left: 1rem !important;
          padding-right: 1rem !important;
        }}
        .primary-nav,
        .account-actions {{
          width: 100%;
        }}
        .primary-nav .nav-pill {{
          flex: 1 1 calc(50% - 0.5rem);
        }}
        .account-actions {{
          justify-content: flex-start;
          gap: 0.75rem;
        }}
        .account-actions .small {{
          width: 100%;
        }}
        .hero {{
          border-radius: 18px;
          padding: 0.85rem !important;
        }}
        .hero-title {{
          font-size: clamp(1.45rem, 9vw, 2.1rem);
        }}
        .hero-kpis {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .hero-stage-grid {{
          grid-template-columns: 1fr 1fr;
        }}
        .player-kpi-grid {{
          grid-template-columns: 1fr 1fr;
        }}
        .team-kpi-grid,
        .team-note-grid {{
          grid-template-columns: 1fr 1fr;
        }}
        .section-title {{
          font-size: clamp(1rem, 4.8vw, 1.24rem);
        }}
        .panel,
        .form-panel {{
          padding: 0.8rem !important;
        }}
        .schedule-calendar-grid {{
          grid-template-columns: 1fr;
          gap: 0.75rem;
        }}
        .schedule-calendar-month {{
          padding: 0.75rem;
        }}
        .schedule-calendar-weekdays,
        .schedule-calendar-days {{
          gap: 0.25rem;
        }}
        .schedule-calendar-day {{
          min-height: 48px;
          padding: 0.3rem;
          border-radius: 12px;
        }}
        .schedule-calendar-day-no {{
          font-size: 0.82rem;
        }}
        .schedule-calendar-day-count {{
          font-size: 0.62rem;
          padding: 0.12rem 0.34rem;
        }}
        .table-responsive {{
          overflow: visible;
          background: transparent;
          border: 0;
          box-shadow: none;
          backdrop-filter: none;
          -webkit-backdrop-filter: none;
        }}
        .table-responsive .table {{
          min-width: 0;
        }}
        .table.is-mobile-stack thead {{
          display: none;
        }}
        .table.is-mobile-stack tbody {{
          display: grid;
          gap: 0.55rem;
        }}
        .table.is-mobile-stack tbody tr {{
          display: block;
          border: 1px solid var(--line);
          border-radius: 14px;
          background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(246, 249, 255, 0.84));
          box-shadow: var(--shadow-soft);
          padding: 0.42rem 0.62rem;
        }}
        .table.is-mobile-stack tbody td {{
          display: grid;
          grid-template-columns: minmax(5.2rem, max-content) minmax(0, 1fr);
          gap: 0.55rem;
          align-items: start;
          white-space: normal;
          word-break: break-word;
          border: 0;
          padding: 0.28rem 0;
          font-size: 0.86rem;
        }}
        .table.is-mobile-stack tbody td::before {{
          display: block;
          color: var(--muted);
          font-size: 0.72rem;
          font-family: "Manrope", "Noto Sans SC", sans-serif;
          font-weight: 700;
          letter-spacing: 0.08em;
          text-transform: uppercase;
        }}
        .table.is-mobile-stack tbody td:empty {{
          display: none;
        }}
      }}
      @media (max-width: 575.98px) {{
        .dashboard-metrics-grid,
        .dashboard-feature-stats,
        .dashboard-spotlight-grid {{
          grid-template-columns: 1fr;
        }}
        .player-kpi-grid {{
          grid-template-columns: 1fr;
        }}
        .team-kpi-grid,
        .team-note-grid {{
          grid-template-columns: 1fr;
        }}
        .hero-kpis,
        .hero-stage-grid {{
          grid-template-columns: 1fr;
        }}
        .nav-pill {{
          flex: 1 1 100%;
        }}
      }}
    </style>
  </head>
  <body class="{body_class}">
    <div class="container-fluid px-2 px-md-3 px-xl-3 py-2">
      <div class="shell mx-auto">
        <div class="topbar shadow-sm px-3 py-2 py-lg-2 mb-4">
          <div class="d-flex flex-column flex-xl-row justify-content-between gap-2 align-items-xl-center">
            <div>
              <div class="brand-kicker">{brand_kicker}</div>
              <div class="brand-title">{brand_title}</div>
              <div class="small text-secondary">{brand_copy}</div>
            </div>
            <div class="topbar-actions d-flex flex-wrap align-items-center gap-2 gap-xl-3">
              <nav class="primary-nav d-flex flex-wrap gap-2">{''.join(nav_links)}</nav>
              {user_html}
            </div>
          </div>
        </div>
        {admin_status}
        {alert_html}
        {body}
      </div>
    </div>
    <script>
      (function () {{
        function applyMobileTableCards() {{
          const isMobile = window.matchMedia("(max-width: 767.98px)").matches;
          document.querySelectorAll(".table-responsive .table").forEach((table) => {{
            const headers = Array.from(table.querySelectorAll("thead th")).map((cell) => (cell.textContent || "").trim());
            const bodyRows = table.querySelectorAll("tbody tr");
            bodyRows.forEach((row) => {{
              Array.from(row.children).forEach((cell, index) => {{
                if (!(cell instanceof HTMLElement)) return;
                const label = headers[index] || "";
                if (label) {{
                  cell.setAttribute("data-label", label);
                }} else {{
                  cell.removeAttribute("data-label");
                }}
              }});
            }});
            table.classList.toggle("is-mobile-stack", isMobile && headers.length > 0);
          }});
        }}
        window.addEventListener("resize", applyMobileTableCards);
        window.addEventListener("DOMContentLoaded", applyMobileTableCards);
        applyMobileTableCards();
      }})();
    </script>
  </body>
</html>
"""


def load_validated_data() -> dict[str, Any]:
    cached_data = get_cached_validated_data()
    if cached_data is not None:
        return cached_data
    errors, data = validate_repository()
    if errors:
        invalidate_validated_data_cache()
        raise ValueError("\n".join(errors))
    set_cached_validated_data(data)
    return data


def save_matches(matches: list[dict[str, Any]]) -> list[str]:
    invalidate_validated_data_cache()
    _, backup_data = validate_repository()
    backup_matches = backup_data.get("matches", [])
    normalized_matches, _ = canonicalize_match_ids(matches)
    try:
        persist_matches(normalized_matches)
        errors, _ = validate_repository()
        if errors:
            persist_matches(backup_matches)
            invalidate_validated_data_cache()
            return errors
        invalidate_validated_data_cache()
        return []
    except Exception:
        if backup_matches:
            persist_matches(backup_matches)
        invalidate_validated_data_cache()
        raise


def save_repository_state(data: dict[str, Any], users: list[dict[str, Any]]) -> list[str]:
    invalidate_validated_data_cache()
    backup_errors, backup_data = validate_repository()
    if backup_errors:
        return backup_errors
    backup_users = load_users()
    try:
        save_repository_data(data, users)
        errors, _ = validate_repository()
        if errors:
            save_repository_data(backup_data, backup_users)
            invalidate_validated_data_cache()
            return errors
        invalidate_validated_data_cache()
        return []
    except Exception:
        save_repository_data(backup_data, backup_users)
        invalidate_validated_data_cache()
        raise


def get_user_player(data: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any] | None:
    if not user or not user.get("player_id"):
        return None
    for player in data["players"]:
        if player["player_id"] == user["player_id"]:
            return player
    return None


def get_user_bound_player_ids(user: dict[str, Any] | None) -> list[str]:
    if not user:
        return []
    ordered_ids: list[str] = []
    for player_id in [user.get("player_id"), *(user.get("linked_player_ids") or [])]:
        normalized = str(player_id or "").strip()
        if normalized and normalized not in ordered_ids:
            ordered_ids.append(normalized)
    return ordered_ids


def get_user_by_player_id(users: list[dict[str, Any]], player_id: str) -> dict[str, Any] | None:
    normalized_player_id = player_id.strip()
    for user in users:
        if normalized_player_id in get_user_bound_player_ids(user):
            return user
    return None


def get_user_badge_label(user: dict[str, Any] | None) -> str:
    if not user:
        return "未绑定账号"
    return user["username"]


def get_user_display_name_label(user: dict[str, Any] | None) -> str:
    if not user:
        return "无"
    return str(user.get("display_name") or user["username"])


def ensure_player_asset_dirs() -> None:
    PLAYER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def ensure_team_asset_dirs() -> None:
    TEAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def public_asset_url(path: str) -> str:
    normalized = path.strip().lstrip("/")
    if path.strip().startswith(("http://", "https://")):
        return path.strip()
    return "/" + normalized if normalized else "/" + DEFAULT_PLAYER_PHOTO


def safe_asset_path(path: str) -> Path | None:
    normalized = path.strip().lstrip("/")
    if not normalized:
        return None
    candidate = (ROOT / normalized).resolve()
    assets_root = ASSETS_DIR.resolve()
    if candidate == assets_root or assets_root in candidate.parents:
        return candidate
    return None


def resolve_player_photo_path(photo: str) -> str:
    candidate = safe_asset_path(photo)
    if candidate and candidate.is_file():
        return photo.strip().lstrip("/")
    return DEFAULT_PLAYER_PHOTO


def parse_aliases_text(raw: str) -> list[str]:
    seen: list[str] = []
    for item in ALIAS_SPLIT_PATTERN.split(raw.strip()):
        name = item.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


def parse_username_list_text(raw: str) -> list[str]:
    seen: list[str] = []
    for item in ALIAS_SPLIT_PATTERN.split(raw.strip()):
        username = item.strip()
        if username and username not in seen:
            seen.append(username)
    return seen


def can_manage_player(ctx: RequestContext, player_id: str) -> bool:
    if not ctx.current_user:
        return False
    if is_admin_user(ctx.current_user):
        return True
    return ctx.current_user.get("player_id") == player_id


def can_manage_team(ctx: RequestContext, team: dict[str, Any] | None, player: dict[str, Any] | None) -> bool:
    if not ctx.current_user or not team:
        return False
    if is_admin_user(ctx.current_user):
        return True
    if user_has_permission(ctx.current_user, "team_manage"):
        return True
    try:
        data = load_validated_data()
    except Exception:
        return is_team_captain(team, player)
    return user_is_team_captain(data, ctx.current_user, team)


def is_team_captain_user(data: dict[str, Any], user: dict[str, Any] | None) -> bool:
    return any(
        is_team_captain(team, player)
        for player, team in get_user_team_identities(data, user)
    )


def get_user_captained_team_ids(data: dict[str, Any], user: dict[str, Any] | None) -> set[str]:
    return {
        team["team_id"]
        for player, team in get_user_team_identities(data, user)
        if is_team_captain(team, player)
    }


def can_manage_player_bindings(
    data: dict[str, Any],
    acting_user: dict[str, Any] | None,
    target_user: dict[str, Any] | None = None,
    source_player: dict[str, Any] | None = None,
) -> bool:
    if not acting_user:
        return False
    if target_user and acting_user["username"] == target_user["username"]:
        return True
    return bool(
        is_admin_user(acting_user)
        or user_has_permission(acting_user, "player_binding_manage")
    )


def build_placeholder_player(
    player_id: str,
    team_id: str,
    competition_name: str,
    season_name: str,
    display_name: str = "",
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "display_name": display_name.strip() or player_id,
        "team_id": team_id,
        "photo": DEFAULT_PLAYER_PHOTO,
        "aliases": [],
        "active": True,
        "joined_on": china_today_label(),
        "notes": (
            f"比赛录入时自动创建的赛季队员档案：{competition_name} · {season_name}。"
            " 后续可由账号绑定到该赛季档案。"
        ),
    }


def build_placeholder_team(
    team_id: str,
    team_name: str,
    competition_name: str,
    season_name: str,
) -> dict[str, Any]:
    normalized_name = team_name.strip()
    short_name = normalized_name[:12] if normalized_name else "赛季战队"
    return {
        "team_id": team_id,
        "name": normalized_name or team_id,
        "short_name": short_name,
        "logo": DEFAULT_TEAM_LOGO,
        "active": True,
        "founded_on": china_today_label(),
        "competition_name": competition_name,
        "season_name": season_name,
        "guild_id": "",
        "captain_player_id": None,
        "stage_groups": [],
        "members": [],
        "notes": f"比赛录入时自动创建的赛季战队档案：{competition_name} / {season_name}。",
    }


def normalize_team_stage_groups(team: dict[str, Any] | None) -> list[dict[str, str]]:
    normalized_rows: list[dict[str, str]] = []
    seen_stages: set[str] = set()
    if not team:
        return normalized_rows
    for item in team.get("stage_groups", []) or []:
        if not isinstance(item, dict):
            continue
        stage = str(item.get("stage") or "").strip()
        group_label = str(item.get("group_label") or "").strip()
        if stage not in STAGE_OPTIONS or not group_label or stage in seen_stages:
            continue
        seen_stages.add(stage)
        normalized_rows.append({"stage": stage, "group_label": group_label})
    return normalized_rows


def get_team_stage_group_map(team: dict[str, Any] | None) -> dict[str, str]:
    return {
        item["stage"]: item["group_label"]
        for item in normalize_team_stage_groups(team)
    }


def find_team_by_name_in_scope(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    team_name: str,
) -> dict[str, Any] | None:
    normalized_team_name = team_name.strip()
    if not normalized_team_name:
        return None
    for team in data["teams"]:
        if (
            str(team.get("name") or "").strip() == normalized_team_name
            and str(team.get("competition_name") or "").strip() == competition_name.strip()
            and str(team.get("season_name") or "").strip() == season_name.strip()
        ):
            return team
    return None


def find_player_by_name_in_scope(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    player_name: str,
    team_name: str = "",
) -> dict[str, Any] | None:
    normalized_player_name = player_name.strip()
    normalized_team_name = team_name.strip()
    if not normalized_player_name:
        return None
    team_lookup_by_id = {team["team_id"]: team for team in data["teams"]}
    for player in data["players"]:
        if str(player.get("display_name") or "").strip() != normalized_player_name:
            continue
        player_team = team_lookup_by_id.get(player.get("team_id"))
        if not player_team:
            continue
        if (
            str(player_team.get("competition_name") or "").strip() != competition_name.strip()
            or str(player_team.get("season_name") or "").strip() != season_name.strip()
        ):
            continue
        if normalized_team_name and str(player_team.get("name") or "").strip() != normalized_team_name:
            continue
        return player
    return None


def resolve_match_award_player_ids(match: dict[str, Any]) -> None:
    participant_name_map = {
        str(participant.get("player_name") or "").strip(): str(participant.get("player_id") or "").strip()
        for participant in match.get("players", [])
        if str(participant.get("player_name") or "").strip() and str(participant.get("player_id") or "").strip()
    }
    match["mvp_player_id"] = participant_name_map.get(str(match.get("mvp_player_name") or "").strip(), "")
    match["svp_player_id"] = participant_name_map.get(str(match.get("svp_player_name") or "").strip(), "")
    match["scapegoat_player_id"] = participant_name_map.get(str(match.get("scapegoat_player_name") or "").strip(), "")


def resolve_match_entities(
    data: dict[str, Any],
    matches: list[dict[str, Any]],
) -> list[str]:
    existing_player_ids = {player["player_id"] for player in data["players"]}
    errors: list[str] = []
    for match in matches:
        competition_name = get_match_competition_name(match)
        season_name = str(match.get("season") or "").strip()
        for entry in match.get("players", []):
            player_name = str(
                entry.get("player_name")
                or entry.get("display_name")
                or entry.get("player_id")
                or ""
            ).strip()
            team_name = str(entry.get("team_name") or entry.get("team_id") or "").strip()
            if not player_name and not team_name:
                continue
            if not team_name:
                errors.append(f"{player_name or '某位选手'} 缺少战队名称。")
                continue
            team = find_team_by_name_in_scope(data, competition_name, season_name, team_name)
            if not team:
                placeholder_team_id = build_team_serial(data, competition_name, season_name, data["teams"])
                team = build_placeholder_team(
                    placeholder_team_id,
                    team_name,
                    competition_name,
                    season_name,
                )
                data["teams"].append(team)
            entry["team_id"] = team["team_id"]
            entry["team_name"] = team["name"]
            if not player_name:
                errors.append(f"{team_name} 有一行缺少队员姓名。")
                continue
            player = find_player_by_name_in_scope(
                data,
                competition_name,
                season_name,
                player_name,
                team["name"],
            )
            if not player:
                player_id = build_unique_slug(existing_player_ids, "player", player_name, "player")
                player = build_placeholder_player(
                    player_id,
                    team["team_id"],
                    competition_name,
                    season_name,
                    display_name=player_name,
                )
                data["players"].append(player)
                existing_player_ids.add(player_id)
            entry["player_id"] = player["player_id"]
            entry["player_name"] = player["display_name"]
            if entry["player_id"] not in team["members"]:
                team["members"].append(entry["player_id"])
        resolve_match_award_player_ids(match)
    return errors


def ensure_placeholder_players_for_matches(
    data: dict[str, Any],
    matches: list[dict[str, Any]],
) -> list[str]:
    existing_player_ids = {player["player_id"] for player in data["players"]}
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    created_player_ids: list[str] = []
    for match in matches:
        competition_name = get_match_competition_name(match)
        season_name = str(match.get("season") or "").strip() or "未命名赛季"
        for entry in match.get("players", []):
            player_id = str(entry.get("player_id") or "").strip()
            team_id = str(entry.get("team_id") or "").strip()
            if not player_id or player_id in existing_player_ids:
                continue
            team = team_lookup.get(team_id)
            if not team:
                continue
            data["players"].append(
                build_placeholder_player(
                    player_id,
                    team_id,
                    competition_name,
                    season_name,
                )
            )
            if player_id not in team["members"]:
                team["members"].append(player_id)
            existing_player_ids.add(player_id)
            created_player_ids.append(player_id)
    return created_player_ids


def ensure_placeholder_users_for_player_ids(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    player_ids: list[str],
) -> list[dict[str, Any]]:
    return list(users)


def merge_placeholder_users_for_registration(
    users: list[dict[str, Any]],
    display_name: str,
    new_user: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    return [*users, new_user], []


def append_alert_query(path: str, alert: str) -> str:
    if not path or not alert:
        return path
    separator = "&" if "?" in path else "?"
    return f"{path}{separator}{urlencode({'alert': alert})}"


def replace_match_path_id(path: str, old_match_id: str, new_match_id: str) -> str:
    normalized_path = path.strip()
    if not normalized_path or not old_match_id or not new_match_id:
        return normalized_path
    old_prefix = f"/matches/{old_match_id}"
    if not normalized_path.startswith(old_prefix):
        return normalized_path
    return f"/matches/{new_match_id}{normalized_path[len(old_prefix):]}"


def build_bound_player_summary(
    data: dict[str, Any],
    user: dict[str, Any],
) -> dict[str, Any] | None:
    bound_player_ids = get_user_bound_player_ids(user)
    if not bound_player_ids:
        return None
    bound_set = set(bound_player_ids)
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    wins = 0
    losses = 0
    points_total = 0.0
    stance_calls = 0
    correct_stances = 0
    incorrect_stances = 0
    history: list[dict[str, Any]] = []
    competition_stats: dict[str, dict[str, Any]] = {}
    seasons: set[str] = set()
    team_names: list[str] = []
    roles: dict[str, int] = {}

    for match in sorted(
        data["matches"],
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    ):
        competition_name = get_match_competition_name(match)
        for entry in match["players"]:
            if entry["player_id"] not in bound_set:
                continue
            team_name = team_lookup.get(entry["team_id"], {}).get("name", entry["team_id"])
            stance_result = normalize_stance_result(entry)
            if team_name not in team_names:
                team_names.append(team_name)
            wins += 1 if entry["result"] == "win" else 0
            losses += 1 if entry["result"] == "loss" else 0
            points_total += float(entry["points_earned"])
            if stance_result != "none":
                stance_calls += 1
                if stance_result == "correct":
                    correct_stances += 1
                elif stance_result == "incorrect":
                    incorrect_stances += 1
            seasons.add(str(match.get("season") or "").strip())
            roles[entry["role"]] = roles.get(entry["role"], 0) + 1

            competition_row = competition_stats.setdefault(
                competition_name,
                {
                    "competition_name": competition_name,
                    "games_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "points_total": 0.0,
                    "team_names": [],
                },
            )
            competition_row["games_played"] += 1
            competition_row["wins"] += 1 if entry["result"] == "win" else 0
            competition_row["losses"] += 1 if entry["result"] == "loss" else 0
            competition_row["points_total"] += float(entry["points_earned"])
            if team_name not in competition_row["team_names"]:
                competition_row["team_names"].append(team_name)

            history.append(
                {
                    "player_id": entry["player_id"],
                    "match_id": match["match_id"],
                    "competition_name": competition_name,
                    "season": match["season"],
                    "played_on": match["played_on"],
                    "stage_label": STAGE_OPTIONS.get(match["stage"], match["stage"]),
                    "round": match["round"],
                    "game_no": match["game_no"],
                    "team_name": team_name,
                    "role": entry["role"],
                    "camp_label": to_chinese_camp(entry["camp"]),
                    "result_label": RESULT_OPTIONS.get(entry["result"], entry["result"]),
                    "stance_result_label": STANCE_OPTIONS.get(stance_result, stance_result),
                    "points_earned": float(entry["points_earned"]),
                }
            )

    games_played = wins + losses
    average_points = round(points_total / games_played, 2) if games_played else 0.0
    competition_rows = [
        {
            **item,
            "record": f"{item['wins']}-{item['losses']}",
            "team_names": "、".join(item["team_names"]) or "未分配战队",
            "average_points": round(item["points_total"] / item["games_played"], 2)
            if item["games_played"]
            else 0.0,
        }
        for item in competition_stats.values()
    ]
    competition_rows.sort(
        key=lambda item: (-item["points_total"], -item["games_played"], item["competition_name"])
    )
    role_rows = [
        {"role": role, "games": games}
        for role, games in sorted(roles.items(), key=lambda item: (-item[1], item[0]))
    ]
    return {
        "bound_player_ids": bound_player_ids,
        "games_played": games_played,
        "record": f"{wins}-{losses}",
        "win_rate": format_pct(wins / games_played) if games_played else "0.0%",
        "stance_rate": format_pct(correct_stances / stance_calls) if stance_calls else "0.0%",
        "points_total": f"{points_total:.2f}",
        "average_points": f"{average_points:.2f}",
        "correct_stances": correct_stances,
        "incorrect_stances": incorrect_stances,
        "stance_calls": stance_calls,
        "team_names": team_names,
        "seasons": sorted(item for item in seasons if item),
        "roles": role_rows,
        "history": history[:20],
        "competition_rows": competition_rows,
    }


def get_player_binding_scopes(
    data: dict[str, Any],
    player_id: str,
) -> list[dict[str, str]]:
    scopes: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for match in data["matches"]:
        if not any(entry["player_id"] == player_id for entry in match["players"]):
            continue
        competition_name = get_match_competition_name(match)
        season_name = str(match.get("season") or "").strip() or "未命名赛季"
        scope_key = (competition_name, season_name)
        if scope_key in seen:
            continue
        seen.add(scope_key)
        scopes.append(
            {
                "competition_name": competition_name,
                "season_name": season_name,
                "scope_label": f"{competition_name} / {season_name}",
            }
        )
    scopes.sort(key=lambda item: (item["competition_name"], item["season_name"]))
    return scopes


def get_player_binding_scope_labels(
    data: dict[str, Any],
    player_id: str,
) -> list[str]:
    return [item["scope_label"] for item in get_player_binding_scopes(data, player_id)]


def find_season_binding_conflict(
    data: dict[str, Any],
    user: dict[str, Any],
    candidate_player_id: str,
) -> tuple[str, list[str]] | None:
    candidate_scope_labels = set(get_player_binding_scope_labels(data, candidate_player_id))
    if not candidate_scope_labels:
        return None
    for bound_player_id in get_user_bound_player_ids(user):
        if bound_player_id == candidate_player_id:
            continue
        bound_scope_labels = set(get_player_binding_scope_labels(data, bound_player_id))
        overlap = sorted(candidate_scope_labels & bound_scope_labels)
        if overlap:
            return bound_player_id, overlap
    return None


def build_player_binding_candidates(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    target_user: dict[str, Any],
) -> list[dict[str, Any]]:
    target_bound_ids = set(get_user_bound_player_ids(target_user))
    candidates: list[dict[str, Any]] = []
    for player in data["players"]:
        player_id = player["player_id"]
        owner = get_user_by_player_id(users, player_id)
        if owner and owner["username"] != target_user["username"]:
            continue
        scope_labels = get_player_binding_scope_labels(data, player_id)
        competition_names = sorted({item.split(" / ", 1)[0] for item in scope_labels})
        season_names = sorted(
            {
                item.split(" / ", 1)[1]
                for item in scope_labels
                if " / " in item
            }
        )
        games_played = sum(
            1
            for match in data["matches"]
            for entry in match["players"]
            if entry["player_id"] == player_id
        )
        if games_played <= 0:
            continue
        candidates.append(
            {
                "player_id": player_id,
                "display_name": player["display_name"],
                "team_name": get_team_by_id(data, player["team_id"])["name"]
                if get_team_by_id(data, player["team_id"])
                else player["team_id"],
                "games_played": games_played,
                "competitions": "、".join(competition_names) or "未分类赛事",
                "seasons": "、".join(item for item in season_names if item) or "未命名赛季",
                "scope_labels": "、".join(scope_labels) or "未命名赛季",
                "already_bound": player_id in target_bound_ids,
                "owner_username": owner["username"] if owner else "",
            }
        )
    candidates.sort(
        key=lambda item: (
            item["already_bound"],
            -item["games_played"],
            item["team_name"],
            item["player_id"],
        )
    )
    return candidates


def validate_uploaded_photo(upload: UploadedFile | None) -> str:
    if upload is None or not upload.filename:
        return ""
    extension = Path(upload.filename).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        return "照片文件格式仅支持 PNG、JPG、JPEG、WEBP、GIF 或 SVG。"
    if len(upload.data) > MAX_UPLOAD_BYTES:
        return "照片文件不能超过 5 MB。"
    if not upload.data:
        return "上传的照片文件为空，请重新选择。"
    return ""


def save_uploaded_player_photo(player_id: str, upload: UploadedFile | None) -> str | None:
    if upload is None or not upload.filename:
        return None
    ensure_player_asset_dirs()
    extension = Path(upload.filename).suffix.lower()
    filename = f"{player_id}-{secrets.token_hex(6)}{extension}"
    target = PLAYER_UPLOAD_DIR / filename
    target.write_bytes(upload.data)
    return str(target.relative_to(ROOT)).replace("\\", "/")


def save_uploaded_user_photo(username: str, upload: UploadedFile | None) -> str | None:
    if upload is None or not upload.filename:
        return None
    ensure_player_asset_dirs()
    extension = Path(upload.filename).suffix.lower()
    filename = f"user-{username}-{secrets.token_hex(6)}{extension}"
    target = PLAYER_UPLOAD_DIR / filename
    target.write_bytes(upload.data)
    return str(target.relative_to(ROOT)).replace("\\", "/")


def save_uploaded_team_logo(team_id: str, upload: UploadedFile | None) -> str | None:
    if upload is None or not upload.filename:
        return None
    ensure_team_asset_dirs()
    extension = Path(upload.filename).suffix.lower()
    filename = f"{team_id}-{secrets.token_hex(6)}{extension}"
    target = TEAM_UPLOAD_DIR / filename
    target.write_bytes(upload.data)
    return str(target.relative_to(ROOT)).replace("\\", "/")


def build_player_photo_html(photo_path: str, display_name: str, extra_class: str = "") -> str:
    return (
        f'<div class="player-photo-frame mx-auto {escape(extra_class)}">'
        f'<img class="player-photo" src="{escape(public_asset_url(resolve_player_photo_path(photo_path)))}" alt="{escape(display_name)} 照片">'
        "</div>"
    )


def build_team_logo_html(logo_path: str, team_name: str, extra_class: str = "") -> str:
    if logo_path.strip().startswith(("http://", "https://")):
        return (
            f'<div class="player-photo-frame mx-auto {escape(extra_class)}">'
            f'<img class="player-photo" src="{escape(logo_path.strip())}" alt="{escape(team_name)} 队标">'
            "</div>"
        )
    candidate = safe_asset_path(logo_path)
    if candidate and candidate.is_file():
        return (
            f'<div class="player-photo-frame mx-auto {escape(extra_class)}">'
            f'<img class="player-photo" src="{escape(public_asset_url(logo_path))}" alt="{escape(team_name)} 队标">'
            "</div>"
        )

    initials = "".join(part[0] for part in re.findall(r"[A-Za-z0-9]+|[\u4e00-\u9fff]", team_name)[:2]) or "队"
    return (
        f'<div class="player-photo-frame mx-auto d-flex align-items-center justify-content-center {escape(extra_class)}" '
        'style="background: linear-gradient(135deg, rgba(90, 167, 255, 0.18), rgba(23, 92, 211, 0.2));">'
        f'<span style="font-family: Manrope, Noto Sans SC, sans-serif; font-size: 2.2rem; font-weight: 800; color: #175cd3;">{escape(initials.upper())}</span>'
        "</div>"
        )


def get_team_by_id(data: dict[str, Any], team_id: str) -> dict[str, Any] | None:
    for team in data["teams"]:
        if team["team_id"] == team_id:
            return team
    return None


def get_guild_by_id(data: dict[str, Any], guild_id: str) -> dict[str, Any] | None:
    for guild in data.get("guilds", []):
        if guild["guild_id"] == guild_id:
            return guild
    return None


def get_team_scope(team: dict[str, Any] | None) -> tuple[str, str]:
    if not team:
        return "", ""
    return (
        str(team.get("competition_name") or "").strip(),
        str(team.get("season_name") or "").strip(),
    )


def team_scope_label(team: dict[str, Any] | None) -> str:
    competition_name, season_name = get_team_scope(team)
    return " / ".join(item for item in [competition_name, season_name] if item) or "未分配赛季"


def team_matches_scope(
    team: dict[str, Any] | None,
    competition_name: str,
    season_name: str,
) -> bool:
    team_competition_name, team_season_name = get_team_scope(team)
    return (
        team_competition_name == competition_name.strip()
        and team_season_name == season_name.strip()
    )


def get_user_team_identities(
    data: dict[str, Any],
    user: dict[str, Any] | None,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    identities: list[tuple[dict[str, Any], dict[str, Any]]] = []
    if not user:
        return identities
    seen_pairs: set[tuple[str, str]] = set()
    player_lookup = {player["player_id"]: player for player in data["players"]}
    for player_id in get_user_bound_player_ids(user):
        player = player_lookup.get(player_id)
        team = get_team_by_id(data, player["team_id"]) if player else None
        if not player or not team:
            continue
        pair = (player["player_id"], team["team_id"])
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        identities.append((player, team))
    return identities


def get_user_team_for_scope(
    data: dict[str, Any],
    user: dict[str, Any] | None,
    competition_name: str,
    season_name: str,
) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    for player, team in get_user_team_identities(data, user):
        if team_matches_scope(team, competition_name, season_name):
            return player, team
    return None, None


def get_user_captained_team_for_scope(
    data: dict[str, Any],
    user: dict[str, Any] | None,
    competition_name: str,
    season_name: str,
) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    for player, team in get_user_team_identities(data, user):
        if team_matches_scope(team, competition_name, season_name) and is_team_captain(team, player):
            return player, team
    return None, None


def user_has_team_identity_in_scope(
    data: dict[str, Any],
    user: dict[str, Any] | None,
    competition_name: str,
    season_name: str,
) -> bool:
    player, team = get_user_team_for_scope(data, user, competition_name, season_name)
    return bool(player and team)


def user_is_team_captain(data: dict[str, Any], user: dict[str, Any] | None, team: dict[str, Any] | None) -> bool:
    if not user or not team:
        return False
    if is_admin_user(user):
        return True
    team_id = team["team_id"]
    for player, identity_team in get_user_team_identities(data, user):
        if identity_team["team_id"] == team_id and is_team_captain(team, player):
            return True
    return False


def can_manage_guild(user: dict[str, Any] | None, guild: dict[str, Any] | None) -> bool:
    if not user or not guild:
        return False
    if is_admin_user(user):
        return True
    if user_has_permission(user, "guild_manage"):
        return True
    if guild.get("leader_username") == user["username"]:
        return True
    return user["username"] in guild.get("manager_usernames", [])


def build_team_serial(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    teams: list[dict[str, Any]],
) -> str:
    context = build_series_context_from_competition(
        competition_name,
        load_series_catalog(data),
    )
    series_code = str(context.get("series_code") or "").strip() or "series"
    city_code = build_city_code(competition_name)
    season_code = build_season_code(season_name)
    prefix = f"{series_code}-{city_code}-{season_code}-"
    used_numbers = {
        int(match.group(1))
        for team in teams
        for match in [re.match(re.escape(prefix) + r"(\d{3})$", str(team.get("team_id") or ""))]
        if match
    }
    next_number = 1
    while next_number in used_numbers:
        next_number += 1
    return f"{prefix}{next_number:03d}"


def get_team_for_player(data: dict[str, Any], player: dict[str, Any] | None) -> dict[str, Any] | None:
    if not player:
        return None
    return get_team_by_id(data, player["team_id"])


def get_team_captain_id(team: dict[str, Any]) -> str | None:
    captain_player_id = str(team.get("captain_player_id") or "").strip()
    return captain_player_id or None


def is_team_captain(team: dict[str, Any] | None, player: dict[str, Any] | None) -> bool:
    if not team or not player:
        return False
    return get_team_captain_id(team) == player["player_id"]


def remove_member_from_team(team: dict[str, Any], player_id: str) -> None:
    team["members"] = [member_id for member_id in team["members"] if member_id != player_id]
    if get_team_captain_id(team) == player_id:
        team["captain_player_id"] = None


def get_team_member_removal_error(
    data: dict[str, Any],
    team: dict[str, Any] | None,
    acting_player: dict[str, Any] | None,
    member_player_id: str,
) -> str:
    from web.features.team_center import get_team_member_removal_error as impl

    return impl(data, team, acting_player, member_player_id)



def user_has_match_history(data: dict[str, Any], player_id: str) -> bool:
    for match in data["matches"]:
        if any(entry["player_id"] == player_id for entry in match["players"]):
            return True
    return False


def get_selected_region(
    ctx: RequestContext,
    region_names: list[str],
    default_region: str | None = None,
) -> str | None:
    selected = form_value(ctx.query, "region").strip()
    if selected and selected in region_names:
        return selected
    if default_region and default_region in region_names:
        return default_region
    if DEFAULT_REGION_NAME in region_names:
        return DEFAULT_REGION_NAME
    return region_names[0] if region_names else None


def get_selected_series_slug(
    ctx: RequestContext,
    series_slugs: list[str],
    default_series_slug: str | None = None,
) -> str | None:
    selected = form_value(ctx.query, "series").strip()
    if selected and selected in series_slugs:
        return selected
    if default_series_slug and default_series_slug in series_slugs:
        return default_series_slug
    return None


def get_selected_competition(
    ctx: RequestContext, competition_names: list[str]
) -> str | None:
    selected = form_value(ctx.query, "competition").strip()
    if selected and selected in competition_names:
        return selected
    return None


def get_selected_season(ctx: RequestContext, season_names: list[str]) -> str | None:
    selected = form_value(ctx.query, "season").strip()
    if selected and selected in season_names:
        return selected
    if season_names:
        return season_names[0]
    return None


def build_team_scope_value(competition_name: str, season_name: str) -> str:
    return f"{competition_name}\n{season_name}"


def parse_team_scope_value(value: str) -> tuple[str, str]:
    competition_name, _, season_name = value.partition("\n")
    return competition_name.strip(), season_name.strip()


def list_team_scopes(
    data: dict[str, Any],
    allowed_statuses: set[str] | None = None,
) -> list[dict[str, str]]:
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)
    effective_statuses = allowed_statuses or {"ongoing"}
    scopes: list[dict[str, str]] = []
    for season_entry in season_catalog:
        season_status = get_season_status(season_entry)
        if season_status not in effective_statuses:
            continue
        for competition_entry in series_catalog:
            if competition_entry["series_slug"] != season_entry["series_slug"]:
                continue
            competition_name = competition_entry["competition_name"]
            season_name = season_entry["season_name"]
            scopes.append(
                {
                    "value": build_team_scope_value(competition_name, season_name),
                    "competition_name": competition_name,
                    "season_name": season_name,
                    "status": season_status,
                    "label": (
                        f"{competition_entry['series_name']} · {competition_name} · {season_name}"
                    ),
                }
            )
    scopes.sort(key=lambda item: (item["competition_name"], item["season_name"]))
    return scopes


def list_ongoing_team_scopes(data: dict[str, Any]) -> list[dict[str, str]]:
    return list_team_scopes(data, {"ongoing"})


def build_scope_query(
    competition_name: str | None = None,
    season_name: str | None = None,
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if region_name:
        params["region"] = region_name
    if series_slug:
        params["series"] = series_slug
    if competition_name:
        params["competition"] = competition_name
    if season_name:
        params["season"] = season_name
    return urlencode(params)


def build_scoped_path(
    base_path: str,
    competition_name: str | None = None,
    season_name: str | None = None,
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    query = build_scope_query(
        competition_name,
        season_name,
        region_name,
        series_slug,
    )
    if not query:
        return base_path
    return f"{base_path}?{query}"


def build_competition_switcher(
    base_path: str,
    competition_names: list[str],
    selected_competition: str | None,
    tone: str = "dark",
    all_label: str = "全部赛事",
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    if not competition_names:
        return ""

    links = [
        (
            all_label,
            build_scoped_path(base_path, None, None, region_name, series_slug),
            selected_competition is None,
        )
    ]
    for competition_name in competition_names:
        links.append(
            (
                competition_name,
                build_scoped_path(
                    base_path,
                    competition_name,
                    None,
                    region_name,
                    series_slug,
                ),
                selected_competition == competition_name,
            )
        )

    if tone == "light":
        return "".join(
            (
                f'<a class="switcher-chip{" is-active" if is_active else ""}" '
                f'href="{escape(href)}">{escape(label)}</a>'
            )
            for label, href, is_active in links
        )

    return "".join(
        (
            f'<a class="btn {"btn-dark" if is_active else "btn-outline-dark"} btn-sm" '
            f'href="{escape(href)}">{escape(label)}</a>'
        )
        for label, href, is_active in links
    )


def build_season_switcher(
    base_path: str,
    competition_name: str | None,
    season_names: list[str],
    selected_season: str | None,
    tone: str = "dark",
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    if not competition_name or not season_names:
        return ""
    options_html = []
    for season_name in season_names:
        selected_attr = " selected" if selected_season == season_name else ""
        options_html.append(
            f'<option value="{escape(season_name)}"{selected_attr}>{escape(season_name)}</option>'
        )
    return f"""
    <form method="get" action="{escape(base_path)}" class="d-flex flex-wrap align-items-center gap-2">
      {f'<input type="hidden" name="region" value="{escape(region_name)}">' if region_name else ''}
      {f'<input type="hidden" name="series" value="{escape(series_slug)}">' if series_slug else ''}
      <input type="hidden" name="competition" value="{escape(competition_name)}">
      <label class="small text-secondary fw-semibold mb-0">赛季</label>
      <select class="form-select" name="season" onchange="this.form.submit()" style="min-width: 220px;">
        {''.join(options_html)}
      </select>
      <noscript><button class="btn btn-dark btn-sm" type="submit">切换</button></noscript>
    </form>
    """


def build_region_switcher(
    base_path: str,
    region_names: list[str],
    selected_region: str | None,
    selected_series_slug: str | None = None,
    tone: str = "light",
) -> str:
    if not region_names:
        return ""

    links = [
        (
            region_name,
            build_scoped_path(base_path, None, None, region_name, selected_series_slug),
            selected_region == region_name,
        )
        for region_name in region_names
    ]

    if tone == "light":
        return "".join(
            (
                f'<a class="switcher-chip{" is-active" if is_active else ""}" '
                f'href="{escape(href)}">{escape(label)}</a>'
            )
            for label, href, is_active in links
        )

    return "".join(
        (
            f'<a class="btn {"btn-dark" if is_active else "btn-outline-dark"} btn-sm" '
            f'href="{escape(href)}">{escape(label)}</a>'
        )
        for label, href, is_active in links
    )


def build_series_switcher(
    base_path: str,
    series_rows: list[dict[str, Any]],
    selected_region: str | None,
    selected_series_slug: str | None,
    tone: str = "light",
    all_label: str = "全部系列赛",
) -> str:
    if not series_rows:
        return ""

    links = [
        (
            all_label,
            build_scoped_path(base_path, None, None, selected_region, None),
            selected_series_slug is None,
        )
    ]
    for row in series_rows:
        links.append(
            (
                row["series_name"],
                build_scoped_path(
                    base_path,
                    None,
                    None,
                    selected_region,
                    row["series_slug"],
                ),
                selected_series_slug == row["series_slug"],
            )
        )

    if tone == "light":
        return "".join(
            (
                f'<a class="switcher-chip{" is-active" if is_active else ""}" '
                f'href="{escape(href)}">{escape(label)}</a>'
            )
            for label, href, is_active in links
        )

    return "".join(
        (
            f'<a class="btn {"btn-dark" if is_active else "btn-outline-dark"} btn-sm" '
            f'href="{escape(href)}">{escape(label)}</a>'
        )
        for label, href, is_active in links
    )


def build_series_topic_path(
    series_slug: str,
    season_name: str | None = None,
    next_path: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if season_name:
        params["season"] = season_name
    if next_path:
        params["next"] = next_path
    query = urlencode(params)
    return f"/series/{quote(series_slug)}?{query}" if query else f"/series/{quote(series_slug)}"


def build_series_manage_path(
    competition_name: str | None = None,
    next_path: str | None = None,
    season_name: str | None = None,
    edit_mode: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if competition_name:
        params["competition_name"] = competition_name
    if next_path:
        params["next"] = next_path
    if season_name:
        params["season_name"] = season_name
    if edit_mode:
        params["edit"] = edit_mode
    query = urlencode(params)
    return f"/series-manage?{query}" if query else "/series-manage"


def build_series_season_switcher(
    series_slug: str,
    season_names: list[str],
    selected_season: str | None,
    tone: str = "light",
) -> str:
    if not season_names:
        return ""
    options_html = []
    for season_name in season_names:
        selected_attr = " selected" if selected_season == season_name else ""
        options_html.append(
            f'<option value="{escape(season_name)}"{selected_attr}>{escape(season_name)}</option>'
        )
    return f"""
    <form method="get" action="{escape(build_series_topic_path(series_slug))}" class="d-flex flex-wrap align-items-center gap-2">
      <label class="small text-secondary fw-semibold mb-0">赛季</label>
      <select class="form-select" name="season" onchange="this.form.submit()" style="min-width: 220px;">
        {''.join(options_html)}
      </select>
      <noscript><button class="btn btn-dark btn-sm" type="submit">切换</button></noscript>
    </form>
    """


def match_in_scope(
    match: dict[str, Any],
    competition_name: str | None = None,
    season_name: str | None = None,
) -> bool:
    if competition_name and get_match_competition_name(match) != competition_name:
        return False
    if season_name and (match.get("season") or "").strip() != season_name:
        return False
    return True


def resolve_team_player_ids(
    data: dict[str, Any],
    team_id: str,
    selected_competition: str | None = None,
    selected_season: str | None = None,
) -> list[str]:
    seen: list[str] = []
    for match in sorted(
        data["matches"],
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    ):
        if not match_in_scope(match, selected_competition, selected_season):
            continue
        for entry in match["players"]:
            if entry["team_id"] == team_id and entry["player_id"] not in seen:
                seen.append(entry["player_id"])
    for player in data["players"]:
        if player.get("team_id") == team_id and player["player_id"] not in seen:
            seen.append(player["player_id"])

    if seen:
        return seen

    team = get_team_by_id(data, team_id)
    return list(team.get("members", [])) if team else []


def resolve_catalog_scope(ctx: RequestContext, data: dict[str, Any]) -> dict[str, Any]:
    catalog = load_series_catalog(data)
    competition_rows = build_competition_catalog_rows(data, catalog)
    competition_names = [row["competition_name"] for row in competition_rows]
    selected_competition = get_selected_competition(ctx, competition_names)
    selected_entry = next(
        (row for row in competition_rows if row["competition_name"] == selected_competition),
        None,
    )
    region_names = list_region_names(catalog)
    preferred_region = get_user_preferred_region(ctx.current_user)
    selected_region = (
        selected_entry["region_name"]
        if selected_entry
        else get_selected_region(
            ctx,
            region_names,
            preferred_region or DEFAULT_REGION_NAME,
        )
    )
    region_rows = [
        row for row in competition_rows if row["region_name"] == selected_region
    ]
    series_rows = list_series_rows_for_region(competition_rows, selected_region)
    series_slugs = [row["series_slug"] for row in series_rows]
    selected_series_slug = (
        selected_entry["series_slug"]
        if selected_entry
        else get_selected_series_slug(ctx, series_slugs)
    )
    filtered_rows = [
        row
        for row in region_rows
        if not selected_series_slug or row["series_slug"] == selected_series_slug
    ]
    return {
        "catalog": catalog,
        "competition_rows": competition_rows,
        "competition_names": competition_names,
        "selected_competition": selected_competition,
        "selected_entry": selected_entry,
        "region_names": region_names,
        "selected_region": selected_region,
        "region_rows": region_rows,
        "series_rows": series_rows,
        "selected_series_slug": selected_series_slug,
        "filtered_rows": filtered_rows,
    }


def build_competition_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)

    rows = []
    competition_names = set(list_competitions(data)) | {
        entry["competition_name"] for entry in series_catalog
    }
    for competition_name in sorted(competition_names):
        matches = [
            match
            for match in data["matches"]
            if get_match_competition_name(match) == competition_name
        ]
        played_matches = [match for match in matches if is_match_counted_as_played(match)]
        series_context = build_series_context_from_competition(competition_name, series_catalog)
        season_entries = get_season_entries_for_series(
            season_catalog,
            series_context["series_slug"],
            include_non_ongoing=True,
            competition_name=competition_name,
        )
        team_ids = sorted(
            {
                entry["team_id"]
                for match in matches
                for entry in match["players"]
            }
            | {
                team["team_id"]
                for team in data["teams"]
                if str(team.get("competition_name") or "").strip() == competition_name
            }
        )
        player_ids = sorted(
            {
                entry["player_id"]
                for match in matches
                for entry in match["players"]
            }
        )
        seasons = []
        seen_seasons: set[str] = set()
        for season_entry in season_entries:
            season_name = season_entry["season_name"]
            if season_name in seen_seasons:
                continue
            seen_seasons.add(season_name)
            seasons.append(season_name)
        for season_name in stats_list_seasons({"matches": matches}, competition_name):
            if season_name in seen_seasons:
                continue
            seen_seasons.add(season_name)
            seasons.append(season_name)
        rows.append(
            {
                "competition_name": competition_name,
                "match_count": len(matches),
                "team_count": len(team_ids),
                "player_count": len(player_ids),
                "latest_played_on": get_scheduled_match_day_label(matches, china_today_label()),
                "seasons": seasons,
            }
        )
    return rows


def _legacy_get_competitions_page_impl(ctx: RequestContext, alert: str = "") -> str:
    from web.features.competitions import get_competitions_page as impl

    return impl(ctx, alert)


def build_dashboard_frontend_page(ctx: RequestContext) -> str:
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        account_html = f"""
        <div class="shell-account">
          <span class="shell-account-label">{escape(display_name)} · {escape(role_label)}</span>
          <a class="shell-button shell-button-secondary" href="/profile">控制台</a>
          <form method="post" action="/logout" class="shell-inline-form">
            <button type="submit" class="shell-button shell-button-secondary">退出</button>
          </form>
        </div>
        """
    else:
        account_html = """
        <div class="shell-account">
          <a class="shell-button shell-button-secondary" href="/login">登录</a>
          <a class="shell-button shell-button-primary" href="/register">注册</a>
        </div>
        """

    bootstrap = json.dumps(
        {
            "apiEndpoint": "/api/dashboard",
            "alert": form_value(ctx.query, "alert").strip(),
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="zh-CN">
  <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="theme-color" content="#dceef7">
    <title>首页</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700;800&family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/assets/dashboard-app.css">
  </head>
  <body class="dashboard-app-shell">
    <div class="shell-backdrop"></div>
    <header class="shell-header">
      <div class="shell-brand">
        <a class="shell-brand-link" href="/dashboard">一颗小草赛事数据中心</a>
        <span class="shell-brand-copy">League Site · Frontend App</span>
      </div>
      <nav class="shell-nav" aria-label="主导航">
        <a class="shell-nav-link is-active" href="/dashboard">首页</a>
        <a class="shell-nav-link" href="/competitions">比赛页面</a>
        <a class="shell-nav-link" href="/guilds">门派</a>
      </nav>
      {account_html}
    </header>
    <main id="dashboard-app" class="dashboard-app-root" aria-live="polite">
      <section class="dashboard-loading-shell">
        <div class="dashboard-loading-kicker">Loading Dashboard</div>
        <h1>正在加载赛事首页</h1>
        <p>前端会通过独立接口拉取数据并渲染页面。</p>
      </section>
    </main>
    <script>window.__WEREWOLF_DASHBOARD_BOOTSTRAP__ = {bootstrap};</script>
    <script src="/assets/dashboard-app.js" defer></script>
  </body>
</html>
"""


def _serialize_dashboard_team_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "team_id": row["team_id"],
        "name": row["name"],
        "short_name": row["short_name"],
        "logo": row["logo"],
        "matches_represented": int(row["matches_represented"]),
        "points_total": f'{float(row["points_earned_total"]):.2f}',
        "win_rate": format_pct(float(row["win_rate"])),
        "stance_rate": format_pct(float(row["stance_rate"])),
        "href": f'/teams/{quote(row["team_id"])}',
    }


def _serialize_dashboard_player_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "rank": int(row["rank"]),
        "player_id": row["player_id"],
        "display_name": row["display_name"],
        "team_name": row["team_name"],
        "photo": row["photo"],
        "games_played": int(row["games_played"]),
        "points_total": f'{float(row["points_earned_total"]):.2f}',
        "win_rate": format_pct(float(row["win_rate"])),
        "stance_rate": format_pct(float(row["stance_rate"])),
        "href": f'/players/{quote(row["player_id"])}',
    }


def build_dashboard_api_payload(ctx: RequestContext) -> dict[str, Any]:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_catalog = scope["competition_rows"]
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    scoped_competition_rows = filtered_rows or region_rows
    scoped_competition_names = {
        row["competition_name"] for row in scoped_competition_rows
    }
    stats_data = (
        build_filtered_data(data, scoped_competition_names)
        if not selected_competition and scoped_competition_names
        else data
    )
    player_rows = build_player_rows(stats_data, selected_competition, selected_season)
    team_rows = build_team_rows(stats_data, selected_competition, selected_season)
    visible_player_rows = [row for row in player_rows if row["games_played"] > 0]
    visible_team_rows = [row for row in team_rows if row["matches_represented"] > 0]
    displayed_player_rows = visible_player_rows or player_rows
    displayed_team_rows = visible_team_rows or team_rows
    scope_label = " / ".join(
        item
        for item in [
            selected_region or DEFAULT_REGION_NAME,
            selected_entry["series_name"] if selected_entry else None,
            selected_competition,
            selected_season,
        ]
        if item
    ) or f"{DEFAULT_REGION_NAME}赛区汇总"
    active_team_count = len(visible_team_rows) if selected_competition else max(
        (row["team_count"] for row in scoped_competition_rows),
        default=0,
    )
    active_player_count = (
        len(visible_player_rows)
        if selected_competition
        else max((row["player_count"] for row in scoped_competition_rows), default=0)
    )
    active_match_count = sum(
        1
        for match in stats_data["matches"]
        if (
            match_in_scope(match, selected_competition, selected_season)
            if selected_competition
            else (
                get_match_competition_name(match) in scoped_competition_names
                and (
                    not selected_season
                    or (match.get("season") or "").strip() == selected_season
                )
            )
        )
    )
    featured_competition = min(
        scoped_competition_rows or competition_catalog,
        key=competition_latest_day_sort_key,
        default=None,
    )
    selected_series_row = next(
        (row for row in series_rows if row["series_slug"] == selected_series_slug),
        None,
    )
    featured_label = selected_competition or (
        selected_series_row["series_name"]
        if selected_series_row
        else (featured_competition["competition_name"] if featured_competition else "等待录入赛事")
    )
    scheduled_match_day = get_nearest_match_day_label(
        [
            match["played_on"]
            for match in stats_data["matches"]
            if (
                match_in_scope(match, selected_competition, selected_season)
                if selected_competition
                else get_match_competition_name(match) in scoped_competition_names
            )
        ],
        china_today_label(),
    )
    latest_played_on = scheduled_match_day
    featured_seasons = selected_season or (
        " / ".join((selected_series_row or featured_competition or {}).get("seasons", [])[:2])
        if (selected_series_row or featured_competition)
        and (selected_series_row or featured_competition).get("seasons")
        else "赛季待录入"
    )
    dashboard_scope_label = selected_competition or featured_label
    latest_match_day_href = build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    scope_summary_line = (
        f"{selected_region or DEFAULT_REGION_NAME}赛区"
        + (
            f" · {selected_series_row['series_name']}"
            if selected_series_row
            else ""
        )
        + (f" · {selected_competition}" if selected_competition else "")
        + (f" · {selected_season}" if selected_season else "")
    )
    summary_description = (
        f"当前正在查看 {scope_summary_line} 的实时统计。"
        "先锁定赛区和系列赛，再决定是否下钻到单个赛事赛季。"
    )

    top_team = _serialize_dashboard_team_row(displayed_team_rows[0]) if displayed_team_rows else None
    top_player = _serialize_dashboard_player_row(displayed_player_rows[0]) if displayed_player_rows else None

    competition_source_rows = filtered_rows or region_rows or competition_catalog
    region_options = [
        {
            "label": region_name,
            "href": build_scoped_path("/dashboard", None, None, region_name, selected_series_slug),
            "active": selected_region == region_name,
        }
        for region_name in scope["region_names"]
    ]
    series_options = [
        {
            "label": "全部系列赛",
            "href": build_scoped_path("/dashboard", None, None, selected_region, None),
            "active": selected_series_slug is None,
        }
    ] + [
        {
            "label": row["series_name"],
            "href": build_scoped_path("/dashboard", None, None, selected_region, row["series_slug"]),
            "active": selected_series_slug == row["series_slug"],
        }
        for row in series_rows
    ]
    competition_options = [
        {
            "label": "全部赛事",
            "href": build_scoped_path("/dashboard", None, None, selected_region, selected_series_slug),
            "active": selected_competition is None,
        }
    ] + [
        {
            "label": row["competition_name"],
            "href": build_scoped_path(
                "/dashboard",
                row["competition_name"],
                None,
                selected_region,
                selected_series_slug,
            ),
            "active": selected_competition == row["competition_name"],
        }
        for row in competition_source_rows
    ]
    season_options = [
        {
            "label": season_name,
            "href": build_scoped_path(
                "/dashboard",
                selected_competition,
                season_name,
                selected_region,
                selected_series_slug,
            ),
            "selected": selected_season == season_name,
        }
        for season_name in season_names
    ]

    dashboard_series_rows = [
        row
        for row in series_rows
        if not selected_series_slug or row["series_slug"] == selected_series_slug
    ]
    series_cards: list[dict[str, Any]] = []
    for row in dashboard_series_rows:
        regional_competitions = [
            item
            for item in region_rows
            if item["series_slug"] == row["series_slug"]
        ]
        primary_competition = regional_competitions[0] if regional_competitions else None
        competition_path = (
            build_scoped_path(
                "/competitions",
                primary_competition["competition_name"],
                None,
                selected_region,
                row["series_slug"],
            )
            if primary_competition
            else build_scoped_path("/competitions", None, None, selected_region, row["series_slug"])
        )
        series_cards.append(
            {
                "series_slug": row["series_slug"],
                "series_name": row["series_name"],
                "region_name": selected_region or DEFAULT_REGION_NAME,
                "seasons": list(row["seasons"]),
                "latest_played_on": row["latest_played_on"] or "待更新",
                "team_count": int(row["team_count"]),
                "player_count": int(row["player_count"]),
                "match_count": int(row["match_count"]),
                "summary": row["summary"],
                "topic_href": build_series_topic_path(row["series_slug"]),
                "competition_href": competition_path,
            }
        )

    relevant_days: list[str] = []
    for played_on in list_match_days(data):
        has_match = any(
            (
                str(match.get("played_on") or "").strip() == played_on
                and (
                    get_match_competition_name(match) in scoped_competition_names
                    if not selected_competition
                    else match_in_scope(match, selected_competition, selected_season)
                )
            )
            for match in data["matches"]
        )
        if has_match:
            relevant_days.append(played_on)
    relevant_days = sort_match_days_by_relevance(relevant_days, china_today_label())
    latest_played_on = relevant_days[0] if relevant_days else scheduled_match_day
    if relevant_days:
        latest_match_day_href = build_match_day_path(
            relevant_days[0],
            build_scoped_path(
                "/dashboard",
                selected_competition,
                selected_season,
                selected_region,
                selected_series_slug,
            ),
        )

    match_days: list[dict[str, Any]] = []
    for played_on in relevant_days[:6]:
        day_matches = [
            match
            for match in data["matches"]
            if (
                str(match.get("played_on") or "").strip() == played_on
                and (
                    get_match_competition_name(match) in scoped_competition_names
                    if not selected_competition
                    else match_in_scope(match, selected_competition, selected_season)
                )
            )
        ]
        if not day_matches:
            continue
        day_competitions = sorted({get_match_competition_name(match) for match in day_matches})
        match_days.append(
            {
                "played_on": played_on,
                "match_count": len(day_matches),
                "competition_names": day_competitions,
                "href": build_match_day_path(
                    played_on,
                    build_scoped_path(
                        "/dashboard",
                        selected_competition,
                        selected_season,
                        selected_region,
                        selected_series_slug,
                    ),
                ),
            }
        )

    legacy_href = build_scoped_path(
        "/dashboard/legacy",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    return {
        "generated_at": ctx.now_label,
        "legacy_href": legacy_href,
        "scope": {
            "label": scope_label,
            "dashboard_label": dashboard_scope_label,
            "summary_line": scope_summary_line,
            "description": summary_description,
            "selected_region": selected_region,
            "selected_series_slug": selected_series_slug,
            "selected_competition": selected_competition,
            "selected_season": selected_season,
            "filters": {
                "regions": region_options,
                "series": series_options,
                "competitions": competition_options,
                "seasons": season_options,
            },
        },
        "hero": {
            "featured_label": featured_label,
            "featured_seasons": featured_seasons,
            "latest_played_on": latest_played_on or "待录入",
            "latest_match_day_href": latest_match_day_href,
            "competitions_href": "/competitions",
            "top_team": top_team,
            "top_player": top_player,
        },
        "metrics": [
            {
                "label": "收录战队",
                "value": str(active_team_count),
                "copy": f"{scope_label} 口径下有成绩的战队数量。",
            },
            {
                "label": "出场队员",
                "value": str(active_player_count),
                "copy": "当前视角里已经出场并生成统计的选手数量。",
            },
            {
                "label": "比赛场次",
                "value": str(active_match_count),
                "copy": "包含已录入比分、阵营和个人表现的有效对局。",
            },
            {
                "label": "最近比赛日",
                "value": latest_played_on or "待录入",
                "copy": f"{featured_seasons} · 继续往下可以查看当天总览。",
            },
        ],
        "series_cards": series_cards,
        "top_teams": [_serialize_dashboard_team_row(row) for row in displayed_team_rows[:5]],
        "top_players": [_serialize_dashboard_player_row(row) for row in displayed_player_rows[:5]],
        "match_days": match_days,
    }


def handle_dashboard_api(ctx: RequestContext, start_response):
    if ctx.method != "GET":
        return start_response_json(
            start_response,
            "405 Method Not Allowed",
            {"error": "dashboard api only supports GET"},
            headers=[("Allow", "GET")],
        )
    return start_response_json(
        start_response,
        "200 OK",
        build_dashboard_api_payload(ctx),
    )


def get_dashboard_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_catalog = scope["competition_rows"]
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    scoped_competition_rows = filtered_rows or region_rows
    scoped_competition_names = {
        row["competition_name"] for row in scoped_competition_rows
    }
    stats_data = (
        build_filtered_data(data, scoped_competition_names)
        if not selected_competition and scoped_competition_names
        else data
    )
    player_rows = build_player_rows(stats_data, selected_competition, selected_season)
    team_rows = build_team_rows(stats_data, selected_competition, selected_season)
    visible_player_rows = [row for row in player_rows if row["games_played"] > 0]
    visible_team_rows = [row for row in team_rows if row["matches_represented"] > 0]
    displayed_player_rows = visible_player_rows or player_rows
    displayed_team_rows = visible_team_rows or team_rows
    scope_label = " / ".join(
        item
        for item in [
            selected_region or DEFAULT_REGION_NAME,
            selected_entry["series_name"] if selected_entry else None,
            selected_competition,
            selected_season,
        ]
        if item
    ) or f"{DEFAULT_REGION_NAME}赛区汇总"
    region_switcher = build_region_switcher(
        "/dashboard",
        scope["region_names"],
        selected_region,
        selected_series_slug,
    )
    series_switcher = build_series_switcher(
        "/dashboard",
        series_rows,
        selected_region,
        selected_series_slug,
    )
    competition_switcher = build_competition_switcher(
        "/dashboard",
        [row["competition_name"] for row in (filtered_rows or region_rows or competition_catalog)],
        selected_competition,
        tone="light",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher = build_season_switcher(
        "/dashboard",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    active_team_count = len(visible_team_rows) if selected_competition else max(
        (row["team_count"] for row in scoped_competition_rows),
        default=0,
    )
    active_player_count = (
        len(visible_player_rows)
        if selected_competition
        else max((row["player_count"] for row in scoped_competition_rows), default=0)
    )
    active_match_count = sum(
        1
        for match in stats_data["matches"]
        if (
            match_in_scope(match, selected_competition, selected_season)
            if selected_competition
            else (
                get_match_competition_name(match) in scoped_competition_names
                and (
                    not selected_season
                    or (match.get("season") or "").strip() == selected_season
                )
            )
        )
    )
    featured_competition = min(
        scoped_competition_rows or competition_catalog,
        key=competition_latest_day_sort_key,
        default=None,
    )
    selected_series_row = next(
        (row for row in series_rows if row["series_slug"] == selected_series_slug),
        None,
    )
    featured_label = selected_competition or (
        selected_series_row["series_name"]
        if selected_series_row
        else (featured_competition["competition_name"] if featured_competition else "等待录入赛事")
    )
    scheduled_match_day = get_nearest_match_day_label(
        [
            match["played_on"]
            for match in stats_data["matches"]
            if (
                match_in_scope(match, selected_competition, selected_season)
                if selected_competition
                else get_match_competition_name(match) in scoped_competition_names
            )
        ],
        china_today_label(),
    )
    latest_played_on = scheduled_match_day
    featured_seasons = selected_season or (
        " / ".join((selected_series_row or featured_competition or {}).get("seasons", [])[:2])
        if (selected_series_row or featured_competition)
        and (selected_series_row or featured_competition).get("seasons")
        else "赛季待录入"
    )
    region_switcher_html = (
        f'<div class="hero-switchers">{region_switcher}</div>' if region_switcher else ""
    )
    series_switcher_html = (
        f'<div class="hero-switchers">{series_switcher}</div>' if series_switcher else ""
    )
    competition_switcher_html = (
        f'<div class="hero-switchers">{competition_switcher}</div>'
        if competition_switcher
        else ""
    )
    season_switcher_html = (
        f'<div class="hero-switchers">{season_switcher}</div>' if season_switcher else ""
    )
    dashboard_scope_label = selected_competition or featured_label
    latest_match_day_path = build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    scope_summary_line = (
        f"{escape(selected_region or DEFAULT_REGION_NAME)}赛区"
        + (
            f" · {escape(selected_series_row['series_name'])}"
            if selected_series_row
            else ""
        )
        + (f" · {escape(selected_competition)}" if selected_competition else "")
        + (f" · {escape(selected_season)}" if selected_season else "")
    )
    summary_description = (
        f"当前正在查看 {scope_summary_line} 的实时统计。"
        "先锁定赛区和系列赛，再决定是否下钻到单个赛事赛季。"
    )
    top_team = displayed_team_rows[0] if displayed_team_rows else None
    top_player = displayed_player_rows[0] if displayed_player_rows else None

    metrics_cards = f"""
    <section class="dashboard-metrics-grid">
      <article class="dashboard-metric-card">
        <div class="dashboard-metric-label">收录战队</div>
        <div class="dashboard-metric-value">{active_team_count}</div>
        <div class="dashboard-metric-copy">{escape(scope_label)} 口径下有成绩的战队数量。</div>
      </article>
      <article class="dashboard-metric-card">
        <div class="dashboard-metric-label">出场队员</div>
        <div class="dashboard-metric-value">{active_player_count}</div>
        <div class="dashboard-metric-copy">当前视角里已经出场并生成统计的选手数量。</div>
      </article>
      <article class="dashboard-metric-card">
        <div class="dashboard-metric-label">比赛场次</div>
        <div class="dashboard-metric-value">{active_match_count}</div>
        <div class="dashboard-metric-copy">包含已录入比分、阵营和个人表现的有效对局。</div>
      </article>
      <article class="dashboard-metric-card">
        <div class="dashboard-metric-label">最近比赛日</div>
        <div class="dashboard-metric-value">{escape(latest_played_on)}</div>
        <div class="dashboard-metric-copy">{escape(featured_seasons)} · 继续往下可以查看当天总览。</div>
      </article>
    </section>
    """

    series_cards = []
    dashboard_series_rows = [
        row
        for row in series_rows
        if not selected_series_slug or row["series_slug"] == selected_series_slug
    ]
    for row in dashboard_series_rows:
        regional_competitions = [
            item
            for item in region_rows
            if item["series_slug"] == row["series_slug"]
        ]
        primary_competition = regional_competitions[0] if regional_competitions else None
        topic_path = build_series_topic_path(row["series_slug"])
        competition_path = (
            build_scoped_path(
                "/competitions",
                primary_competition["competition_name"],
                None,
                selected_region,
                row["series_slug"],
            )
            if primary_competition
            else build_scoped_path("/competitions", None, None, selected_region, row["series_slug"])
        )
        series_cards.append(
            f"""
            <article class="dashboard-feature-card">
              <div class="dashboard-feature-top">
                <div class="card-kicker">{escape(selected_region or DEFAULT_REGION_NAME)} · Series Topic</div>
                <span class="dashboard-feature-tag">专题页 + 地区站点</span>
              </div>
              <h2 class="dashboard-feature-title">{escape(row['series_name'])}</h2>
              <p class="dashboard-feature-copy">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '未设置'} · 下一个比赛日 {escape(row['latest_played_on'] or '待更新')}。先看专题，再按地区进入具体赛事。</p>
              <div class="dashboard-feature-stats">
                <div class="dashboard-feature-stat">
                  <span>战队</span>
                  <strong>{row['team_count']} 支</strong>
                </div>
                <div class="dashboard-feature-stat">
                  <span>队员</span>
                  <strong>{row['player_count']} 名</strong>
                </div>
                <div class="dashboard-feature-stat">
                  <span>对局</span>
                  <strong>{row['match_count']} 场</strong>
                </div>
              </div>
              <div class="dashboard-feature-actions">
                <a class="btn btn-dark" href="{escape(topic_path)}">查看系列专题</a>
                <a class="btn btn-outline-dark" href="{escape(competition_path)}">进入地区赛事页</a>
              </div>
            </article>
            """
        )

    relevant_days = []
    for played_on in list_match_days(data):
        has_match = any(
            (
                str(match.get("played_on") or "").strip() == played_on
                and (
                    get_match_competition_name(match) in scoped_competition_names
                    if not selected_competition
                    else match_in_scope(match, selected_competition, selected_season)
                )
            )
            for match in data["matches"]
        )
        if has_match:
            relevant_days.append(played_on)
    relevant_days = sort_match_days_by_relevance(relevant_days, china_today_label())
    latest_played_on = relevant_days[0] if relevant_days else scheduled_match_day
    if relevant_days:
        latest_match_day_path = build_match_day_path(
            relevant_days[0],
            build_scoped_path(
                "/dashboard",
                selected_competition,
                selected_season,
                selected_region,
                selected_series_slug,
            ),
        )

    recent_day_cards = []
    for played_on in relevant_days[:6]:
        day_matches = [
            match
            for match in data["matches"]
            if (
                str(match.get("played_on") or "").strip() == played_on
                and (
                    get_match_competition_name(match) in scoped_competition_names
                    if not selected_competition
                    else match_in_scope(match, selected_competition, selected_season)
                )
            )
        ]
        if not day_matches:
            continue
        day_competitions = sorted({get_match_competition_name(match) for match in day_matches})
        recent_day_cards.append(
            f"""
            <a class="dashboard-day-card" href="{escape(build_match_day_path(played_on, build_scoped_path('/dashboard', selected_competition, selected_season, selected_region, selected_series_slug)))}">
              <div class="dashboard-day-top">
                <div class="dashboard-day-kicker">Match Day</div>
                <div class="dashboard-day-count">{len(day_matches)} 场</div>
              </div>
              <h2 class="dashboard-day-title">{escape(played_on)}</h2>
              <p class="dashboard-day-copy">覆盖 {len(day_competitions)} 个系列赛，可以直接进入当天总览继续看单场详情。</p>
              <div class="dashboard-day-tags">
                {''.join(f'<span class="dashboard-day-tag">{escape(name)}</span>' for name in day_competitions[:3])}
                {('<span class="dashboard-day-tag">更多赛事</span>' if len(day_competitions) > 3 else '')}
              </div>
            </a>
            """
        )

    top_team_items = []
    for row in displayed_team_rows[:3]:
        top_team_items.append(
            f"""
            <a class="dashboard-ranking-item" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">
              <span class="dashboard-ranking-index">{row['rank']:02d}</span>
              <div>
                <div class="dashboard-ranking-name">{escape(row['name'])}</div>
                <div class="dashboard-ranking-meta">胜率 {format_pct(row['win_rate'])} · 对局 {row['matches_represented']} 场</div>
              </div>
              <div class="dashboard-ranking-score">{row['points_earned_total']:.2f}<small>总积分</small></div>
            </a>
            """
        )

    top_player_items = []
    for row in displayed_player_rows[:3]:
        top_player_items.append(
            f"""
            <a class="dashboard-ranking-item" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">
              <span class="dashboard-ranking-index">{row['rank']:02d}</span>
              <div>
                <div class="dashboard-ranking-name">{escape(row['display_name'])}</div>
                <div class="dashboard-ranking-meta">胜率 {format_pct(row['win_rate'])} · 出场 {row['games_played']} 次</div>
              </div>
              <div class="dashboard-ranking-score">{row['points_earned_total']:.2f}<small>总积分</small></div>
            </a>
            """
        )

    body = f"""
    <div class="dashboard-home">
      <section class="dashboard-hero hero shadow-lg">
        <div class="hero-layout">
          <div>
            <div class="eyebrow mb-3">Match Control Room</div>
            <h1 class="hero-title mb-3">{escape(selected_region or DEFAULT_REGION_NAME)}赛区<br>赛事指挥台</h1>
            <p class="hero-copy mb-0">{summary_description}</p>
            <div class="dashboard-status-row">
              <span class="dashboard-status-chip"><strong>当前焦点</strong>{escape(dashboard_scope_label)}</span>
              <span class="dashboard-status-chip"><strong>数据时间</strong>{escape(ctx.now_label)}</span>
              <span class="dashboard-status-chip"><strong>比赛日</strong>{escape(latest_played_on)}</span>
            </div>
            <div class="dashboard-filter-grid">
              <div class="dashboard-filter-block">
                <div class="dashboard-filter-label">赛区视角</div>
                {region_switcher_html or '<div class="small text-secondary">暂无赛区数据</div>'}
              </div>
              <div class="dashboard-filter-block">
                <div class="dashboard-filter-label">系列赛筛选</div>
                {series_switcher_html or '<div class="small text-secondary">暂无系列赛目录</div>'}
              </div>
              <div class="dashboard-filter-block">
                <div class="dashboard-filter-label">赛事入口</div>
                {competition_switcher_html or '<div class="small text-secondary">当前还没有可切换赛事</div>'}
              </div>
              <div class="dashboard-filter-block">
                <div class="dashboard-filter-label">赛季切换</div>
                {season_switcher_html or '<div class="small text-secondary">先选择赛事后再切换赛季</div>'}
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2 mt-4">
              <a class="btn btn-light" href="{escape(latest_match_day_path)}">打开比赛日时间线</a>
              <a class="btn btn-outline-dark" href="/competitions">打开全部赛事</a>
            </div>
          </div>
          <div class="dashboard-hero-side">
            <section class="dashboard-spotlight-card">
              <div class="dashboard-panel-kicker">Featured Scope</div>
              <div class="dashboard-spotlight-title">{escape(featured_label)}</div>
              <p class="dashboard-spotlight-copy">当前仪表盘会优先展示这个视角下最值得继续查看的范围，你可以先看榜单，再进入某个系列赛或某一天的比赛记录。</p>
              <div class="dashboard-spotlight-grid">
                <div class="dashboard-spotlight-metric">
                  <span>赛季范围</span>
                  <strong>{escape(featured_seasons)}</strong>
                  <small>优先展示最近活跃数据</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>对局规模</span>
                  <strong>{active_match_count} 场</strong>
                  <small>{escape(scope_label)}</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>头名战队</span>
                  <strong>{escape(top_team['name']) if top_team else '等待录入'}</strong>
                  <small>{f"{top_team['points_earned_total']:.2f} 分" if top_team else '暂无战绩'}</small>
                </div>
                <div class="dashboard-spotlight-metric">
                  <span>头名选手</span>
                  <strong>{escape(top_player['display_name']) if top_player else '等待录入'}</strong>
                  <small>{f"{top_player['points_earned_total']:.2f} 分" if top_player else '暂无战绩'}</small>
                </div>
              </div>
            </section>
            <section class="dashboard-brief-card">
              <div class="dashboard-panel-kicker">Quick Brief</div>
              <div class="dashboard-brief-list">
                <div class="dashboard-brief-item">
                  <span class="dashboard-rank-badge">T</span>
                  <div>
                    <div class="dashboard-brief-name">{escape(top_team['name']) if top_team else '暂无战队头名'}</div>
                    <div class="dashboard-brief-meta">{f"胜率 {format_pct(top_team['win_rate'])} · 对局 {top_team['matches_represented']} 场" if top_team else '当前口径下还没有有效战绩'}</div>
                  </div>
                  <div class="dashboard-brief-value">{f"{top_team['points_earned_total']:.2f}" if top_team else '--'}<small>team</small></div>
                </div>
                <div class="dashboard-brief-item">
                  <span class="dashboard-rank-badge">P</span>
                  <div>
                    <div class="dashboard-brief-name">{escape(top_player['display_name']) if top_player else '暂无选手头名'}</div>
                    <div class="dashboard-brief-meta">{f"胜率 {format_pct(top_player['win_rate'])} · 出场 {top_player['games_played']} 次" if top_player else '当前口径下还没有有效战绩'}</div>
                  </div>
                  <div class="dashboard-brief-value">{f"{top_player['points_earned_total']:.2f}" if top_player else '--'}<small>player</small></div>
                </div>
              </div>
            </section>
          </div>
        </div>
      </section>
      {metrics_cards}
      <section class="dashboard-grid">
        <section class="panel dashboard-section-panel shadow-sm">
          <div class="dashboard-section-head">
            <div>
              <h2 class="section-title mb-2">系列赛专题入口</h2>
              <p class="dashboard-section-copy mb-0">首页先把“值得点进去的专题”摆出来。你可以先看系列赛品牌页，再根据需要落到某个地区赛事站点。</p>
            </div>
            <a class="btn btn-outline-dark" href="/competitions">进入全部赛事</a>
          </div>
          <div class="dashboard-feature-grid">
            {''.join(series_cards) or '<div class="alert alert-secondary mb-0">当前地区还没有系列赛，请先创建系列赛目录。</div>'}
          </div>
        </section>
        <aside class="panel dashboard-side-panel shadow-sm">
          <div class="dashboard-section-head">
            <div>
              <h2 class="section-title mb-2">即时榜单</h2>
              <p class="dashboard-section-copy mb-0">首页不放大表格，先给你当前口径下最能代表走势的头部名单。</p>
            </div>
          </div>
          <div class="dashboard-panel-kicker">Top Teams</div>
          <div class="dashboard-ranking-list">
            {''.join(top_team_items) or '<div class="alert alert-secondary mb-0">当前没有可展示的战队榜单。</div>'}
          </div>
          <div class="dashboard-panel-kicker mt-4">Top Players</div>
          <div class="dashboard-ranking-list">
            {''.join(top_player_items) or '<div class="alert alert-secondary mb-0">当前没有可展示的选手榜单。</div>'}
          </div>
        </aside>
      </section>
      <section class="panel dashboard-section-panel shadow-sm">
        <div class="dashboard-section-head">
          <div>
            <h2 class="section-title mb-2">最近比赛日</h2>
            <p class="dashboard-section-copy mb-0">把有比赛的日期做成时间卡片，方便从“今天发生了什么”这个入口快速下钻，而不是先读一堆说明文字。</p>
          </div>
        </div>
        <div class="dashboard-day-grid">
          {''.join(recent_day_cards) or '<div class="alert alert-secondary mb-0">当前统计范围还没有比赛日数据。</div>'}
        </div>
      </section>
    </div>
    """
    return layout("首页", body, ctx, alert=alert)


def _legacy_get_series_page_impl(ctx: RequestContext, series_slug: str) -> str:
    from web.features.competitions import get_series_page as impl

    return impl(ctx, series_slug)


def validate_series_catalog_form(
    series_name: str,
    region_name: str,
    competition_name: str,
) -> str:
    if not series_name.strip():
        return "系列赛名称不能为空。"
    if not region_name.strip():
        return "地区名称不能为空。"
    if not competition_name.strip():
        return "地区赛事页名称不能为空。"
    return ""


def validate_season_catalog_form(
    series_slug: str,
    season_name: str,
    start_at: str,
    end_at: str,
) -> str:
    if not series_slug.strip():
        return "请先选择要管理的系列赛。"
    if not season_name.strip():
        return "赛季名称不能为空。"
    normalized_start = parse_china_datetime(start_at)
    normalized_end = parse_china_datetime(end_at)
    if not normalized_start or not normalized_end:
        return "请为赛季填写有效的起止时间。"
    if normalized_start > normalized_end:
        return "赛季开始时间不能晚于结束时间。"
    return ""


def _legacy_get_series_manage_page_impl(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    from web.features.series_manage import get_series_manage_page as impl

    return impl(ctx, alert, form_values)


def _legacy_handle_series_manage_impl(ctx: RequestContext, start_response):
    from web.features.series_manage import handle_series_manage as impl

    return impl(ctx, start_response)


def get_series_manage_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    from web.features.series_manage import get_series_manage_page as impl

    return impl(ctx, alert, form_values)


def handle_series_manage(ctx: RequestContext, start_response):
    from web.features.series_manage import handle_series_manage as impl

    return impl(ctx, start_response)


def get_competitions_page(ctx: RequestContext, alert: str = "") -> str:
    from web.features.competitions import get_competitions_page as impl

    return impl(ctx, alert)


def get_series_page(ctx: RequestContext, series_slug: str) -> str:
    from web.features.competitions import get_series_page as impl

    return impl(ctx, series_slug)


def get_series_legacy_page(ctx: RequestContext, series_slug: str) -> str:
    from web.features.competitions import get_series_legacy_page as impl

    return impl(ctx, series_slug)


def get_match_day_page(ctx: RequestContext, played_on: str) -> str:
    from web.features.competitions import get_match_day_page as impl

    return impl(ctx, played_on)


def get_match_day_legacy_page(ctx: RequestContext, played_on: str) -> str:
    from web.features.competitions import get_match_day_legacy_page as impl

    return impl(ctx, played_on)


def handle_match_day(ctx: RequestContext, start_response, played_on: str):
    from web.features.competitions import handle_match_day as impl

    return impl(ctx, start_response, played_on)


def handle_match_day_api(ctx: RequestContext, start_response, played_on: str):
    from web.features.competitions import handle_match_day_api as impl

    return impl(ctx, start_response, played_on)


def get_teams_page(ctx: RequestContext) -> str:
    from web.features.competitions import get_teams_page as impl

    return impl(ctx)


def get_team_frontend_page(ctx: RequestContext, team_id: str) -> str:
    from web.features.team_page import build_team_frontend_page as impl

    return impl(ctx, team_id)


def get_team_legacy_page(ctx: RequestContext, team_id: str, alert: str = "") -> str:
    from web.features.team_page import get_team_legacy_page as impl

    return impl(ctx, team_id, alert)


def handle_team_api(ctx: RequestContext, start_response, team_id: str):
    from web.features.team_page import handle_team_api as impl

    return impl(ctx, start_response, team_id)


def get_player_frontend_page(ctx: RequestContext, player_id: str) -> str:
    from web.features.player_page import build_player_frontend_page as impl

    return impl(ctx, player_id)


def get_player_legacy_page(ctx: RequestContext, player_id: str, alert: str = "") -> str:
    from web.features.player_page import get_player_legacy_page as impl

    return impl(ctx, player_id, alert)


def handle_player_api(ctx: RequestContext, start_response, player_id: str):
    from web.features.player_page import handle_player_api as impl

    return impl(ctx, start_response, player_id)


def handle_competitions(ctx: RequestContext, start_response):
    from web.features.competitions import handle_competitions as impl

    return impl(ctx, start_response)


def handle_competitions_api(ctx: RequestContext, start_response):
    from web.features.competitions import handle_competitions_api as impl

    return impl(ctx, start_response)


def handle_series_api(ctx: RequestContext, start_response, series_slug: str):
    from web.features.competitions import handle_series_api as impl

    return impl(ctx, start_response, series_slug)


def summarize_team_match(team_id: str, match: dict[str, Any], team_lookup: dict[str, Any]) -> dict[str, Any]:
    from web.features.competitions import summarize_team_match as impl

    return impl(team_id, match, team_lookup)


def build_match_next_path(match: dict[str, Any]) -> str:
    from web.features.competitions import build_match_next_path as impl

    return impl(match)


def list_match_days(data: dict[str, Any]) -> list[str]:
    from web.features.competitions import list_match_days as impl

    return impl(data)


def build_match_day_path(played_on: str, next_path: str | None = None) -> str:
    from web.features.competitions import build_match_day_path as impl

    return impl(played_on, next_path)


def build_schedule_path(
    competition_name: str | None = None,
    season_name: str | None = None,
    next_path: str | None = None,
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    from web.features.competitions import build_schedule_path as impl

    return impl(competition_name, season_name, next_path, region_name, series_slug)


def is_valid_match_day(value: str) -> bool:
    from web.features.competitions import is_valid_match_day as impl

    return impl(value)


def _legacy_get_teams_page_impl(ctx: RequestContext) -> str:
    return _legacy_get_competitions_page_impl(ctx)


def _legacy_handle_competitions_impl(ctx: RequestContext, start_response):
    from web.features.competitions import handle_competitions as impl

    return impl(ctx, start_response)


def _legacy_summarize_team_match_impl(team_id: str, match: dict[str, Any], team_lookup: dict[str, Any]) -> dict[str, Any]:
    team_score = 0.0
    opponents: dict[str, float] = {}
    for participant in match["players"]:
        if participant["team_id"] == team_id:
            team_score += float(participant["points_earned"])
        else:
            opponents.setdefault(participant["team_id"], 0.0)
            opponents[participant["team_id"]] += float(participant["points_earned"])

    opponent_names = "、".join(team_lookup[opponent_id]["name"] for opponent_id in opponents)
    opponent_score = sum(opponents.values())
    return {
        "match_id": match["match_id"],
        "competition_name": get_match_competition_name(match),
        "season": match["season"],
        "stage": STAGE_OPTIONS.get(match["stage"], match["stage"]),
        "round": match["round"],
        "game_no": match["game_no"],
        "played_on": match["played_on"],
        "table_label": match["table_label"],
        "format": match["format"],
        "duration_minutes": match["duration_minutes"],
        "winning_camp": CAMP_OPTIONS.get(match["winning_camp"], match["winning_camp"]),
        "team_score": round(team_score, 2),
        "opponent_score": round(opponent_score, 2),
        "opponents": opponent_names or "无",
        "notes": match["notes"],
    }


def _legacy_build_match_next_path_impl(match: dict[str, Any]) -> str:
    return build_scoped_path(
        "/competitions",
        get_match_competition_name(match),
        (match.get("season") or "").strip() or None,
    )


def _legacy_list_match_days_impl(data: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(match.get("played_on") or "").strip()
            for match in data["matches"]
            if str(match.get("played_on") or "").strip()
        },
        reverse=True,
    )


def _legacy_build_match_day_path_impl(played_on: str, next_path: str | None = None) -> str:
    base_path = f"/days/{played_on}"
    if not next_path:
        return base_path
    return f"{base_path}?{urlencode({'next': next_path})}"


def _legacy_build_schedule_path_impl(
    competition_name: str | None = None,
    season_name: str | None = None,
    next_path: str | None = None,
    region_name: str | None = None,
    series_slug: str | None = None,
) -> str:
    params: dict[str, str] = {}
    if region_name:
        params["region"] = region_name
    if series_slug:
        params["series"] = series_slug
    if competition_name:
        params["competition"] = competition_name
    if season_name:
        params["season"] = season_name
    if next_path:
        params["next"] = next_path
    query = urlencode(params)
    return f"/schedule?{query}" if query else "/schedule"


def _legacy_is_valid_match_day_impl(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _legacy_get_match_day_page_impl(ctx: RequestContext, played_on: str) -> str:
    from web.features.competitions import get_match_day_page as impl

    return impl(ctx, played_on)


def get_schedule_page(ctx: RequestContext) -> str:
    from web.features.competitions import get_schedule_page as impl

    return impl(ctx)


def get_schedule_legacy_page(ctx: RequestContext) -> str:
    from web.features.competitions import get_schedule_legacy_page as impl

    return impl(ctx)


def handle_schedule_api(ctx: RequestContext, start_response):
    from web.features.competitions import handle_schedule_api as impl

    return impl(ctx, start_response)


def get_match_page(ctx: RequestContext, match_id: str) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)
    alert = form_value(ctx.query, "alert").strip()
    if alert == "placeholder-created":
        alert = "本场比赛涉及未绑定账号的选手，系统已自动创建对应赛季档案，可稍后在绑定页完成绑定。"

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = (match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
    score_model = normalize_match_score_model(match.get("score_model"))
    score_model_label = get_match_score_model_label(score_model)
    show_score_breakdown = uses_structured_score_model(score_model)
    participant_by_id = {
        str(participant.get("player_id") or "").strip(): participant
        for participant in match["players"]
        if str(participant.get("player_id") or "").strip()
    }

    def render_award_player(player_id: str, empty_label: str) -> str:
        if not player_id:
            return f'<div class="small text-secondary">{escape(empty_label)}</div>'
        participant = participant_by_id.get(player_id)
        player = player_lookup.get(player_id)
        display_name = player["display_name"] if player else player_id
        detail_path = build_scoped_path(
            f"/players/{player_id}",
            competition_name,
            season_name,
            selected_region,
            selected_series_slug,
        )
        meta_parts = []
        if participant:
            seat = participant.get("seat")
            role = str(participant.get("role") or "").strip()
            team_name = team_lookup.get(participant.get("team_id"), {}).get(
                "name",
                str(participant.get("team_id") or "").strip(),
            )
            if seat:
                meta_parts.append(f"{seat}号")
            if role:
                meta_parts.append(role)
            if team_name:
                meta_parts.append(team_name)
        meta_html = ""
        if meta_parts:
            meta_html = f'<div class="small-muted mt-2">{" · ".join(escape(part) for part in meta_parts)}</div>'
        return (
            f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover '
            f'fw-semibold fs-4" href="{escape(detail_path)}">{escape(display_name)}</a>'
            f"{meta_html}"
        )

    team_scores: dict[str, float] = {}
    for participant in match["players"]:
        team_scores.setdefault(participant["team_id"], 0.0)
        team_scores[participant["team_id"]] += float(participant["points_earned"])

    score_rows = [
        (
            team_id,
            team_lookup.get(team_id, {}).get("name", team_id),
            round(score, 2),
        )
        for team_id, score in sorted(
            team_scores.items(),
            key=lambda item: (-item[1], team_lookup.get(item[0], {}).get("name", item[0])),
        )
    ]
    scoreboard_html = "".join(
        f"""
        <div class="col-12 col-md-6">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">战队积分</div>
            <div class="stat-value mt-2">{score:.2f}</div>
            <div class="small-muted mt-2">{escape(team_name)}</div>
          </div>
        </div>
        """
        for _, team_name, score in score_rows
    )
    winning_camp = str(match.get("winning_camp") or "").strip()
    awards_html = f"""
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">MVP</div>
            <div class="mt-2">{render_award_player(str(match.get('mvp_player_id') or '').strip(), '暂未设置 MVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">SVP</div>
            <div class="mt-2">{render_award_player(str(match.get('svp_player_id') or '').strip(), '暂未设置 SVP')}</div>
          </div>
        </div>
        <div class="col-12 col-md-4">
          <div class="stat-card h-100 p-4 shadow-sm border-0">
            <div class="stat-label">背锅</div>
            <div class="mt-2">{
                '<div class="small text-secondary">好人胜利局不设背锅。</div>'
                if winning_camp == 'villagers'
                else render_award_player(str(match.get('scapegoat_player_id') or '').strip(), '暂未设置背锅选手')
            }</div>
          </div>
        </div>
    """

    participant_rows = []
    for participant in sorted(match["players"], key=lambda item: item["seat"]):
        player = player_lookup.get(participant["player_id"])
        team = team_lookup.get(participant["team_id"])
        player_name = player["display_name"] if player else participant["player_id"]
        team_name = team["name"] if team else participant["team_id"]
        stance_result = normalize_stance_result(participant)
        score_breakdown = normalize_score_breakdown(participant)
        breakdown_cells = ""
        if show_score_breakdown:
            breakdown_cells = "".join(
                f"<td>{score_breakdown[field_name]:.2f}</td>"
                for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
            )
        participant_rows.append(
            f"""
            <tr>
              <td>{participant['seat']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + participant['player_id'], competition_name, season_name))}">{escape(player_name)}</a></td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name))}">{escape(team_name)}</a></td>
              <td>{escape(participant['role'])}</td>
              <td>{escape(to_chinese_camp(participant['camp']))}</td>
              <td>{escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
              {breakdown_cells}
              <td>{escape(STANCE_OPTIONS.get(stance_result, stance_result))}</td>
              <td>{float(participant['points_earned']):.2f}</td>
              <td>{escape(participant['notes'] or '无')}</td>
            </tr>
            """
        )

    breakdown_header_html = ""
    if show_score_breakdown:
        breakdown_header_html = "".join(
            f"<th>{escape(field_label)}</th>"
            for _, field_label in MATCH_SCORE_COMPONENT_FIELDS
        )

    edit_button = ""
    if can_manage_matches(ctx.current_user, data, competition_name):
        edit_button = (
            f'<a class="btn btn-dark" href="/matches/{escape(match_id)}/edit?next='
            f'{quote(build_scoped_path("/matches/" + match_id, competition_name, season_name))}">编辑比赛</a>'
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛详情页</div>
          <h1 class="hero-title mb-3">{escape(competition_name)} · {escape(season_name)}</h1>
          <p class="hero-copy mb-0">这里展示单场比赛的完整信息，包括比赛编号、阶段、参赛分组以及所有上场成员的个人明细。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">编号 {escape(match['match_id'])}</span>
            <span class="chip">{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</span>
            <span class="chip">第 {match['round']} 轮</span>
            <span class="chip">计分模型 {escape(score_model_label)}</span>
            <a class="switcher-chip" href="{escape(build_match_day_path(match['played_on'], build_scoped_path('/matches/' + match_id, competition_name, season_name)))}">{escape(match['played_on'])}</a>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
            {edit_button}
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Match Detail</div>
          <div class="hero-stage-label">Match Overview</div>
          <div class="hero-stage-title">{escape(match['match_id'])}</div>
          <div class="hero-stage-note">比赛详情页会固定当前系列赛和赛季口径，方便从战队页、队员页和赛事页继续回看单场内容。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>房间</span>
              <strong>{escape(match['table_label'])}</strong>
              <small>{escape(match['format'])}</small>
            </div>
            <div class="hero-stage-metric">
              <span>时长</span>
              <strong>{match['duration_minutes']} 分钟</strong>
              <small>完整比赛耗时</small>
            </div>
            <div class="hero-stage-metric">
              <span>胜利阵营</span>
              <strong>{escape(to_chinese_camp(match['winning_camp']))}</strong>
              <small>本局最终结果</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛分组</span>
              <strong>{escape(str(match.get('group_label') or '未设置'))}</strong>
              <small>本场所属分组</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">本局奖项</h2>
          <p class="section-copy mb-0">这里记录每场比赛的 MVP、SVP 和背锅选手；好人胜利局不会设置背锅。</p>
        </div>
      </div>
      <div class="row g-3">{awards_html}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队比分</h2>
          <p class="section-copy mb-0">按本场所有上场成员的得分累计展示，方便快速查看单场战队表现。</p>
        </div>
      </div>
      <div class="row g-3">{scoreboard_html}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">上场成员明细</h2>
          <p class="section-copy mb-0">点击队员或战队名称，可以继续跳转到对应的详情页，并保持当前系列赛与赛季口径。{escape('当前使用京城日报积分模型，已展开分项积分。' if show_score_breakdown else '')}</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>座位</th>
              <th>队员</th>
              <th>战队</th>
              <th>角色</th>
              <th>阵营</th>
              <th>结果</th>
              {breakdown_header_html}
              <th>站边</th>
              <th>得分</th>
              <th>备注</th>
            </tr>
          </thead>
          <tbody>
            {''.join(participant_rows)}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-2">比赛备注</h2>
      <p class="section-copy mb-0">{escape(match['notes'] or '暂无备注。')}</p>
    </section>
    """
    return layout(f"{match['match_id']} 详情", body, ctx, alert=alert)


def format_dimension_metric_value(value: Any) -> str:
    if isinstance(value, bool):
        return "是" if value else "否"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.2f}".rstrip("0").rstrip(".")
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"


def get_player_dimension_history(
    data: dict[str, Any],
    player_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in data.get("season_player_dimension_stats", [])
        if row.get("player_id") == player_id
        and (not competition_name or row.get("competition_name") == competition_name)
        and (not season_name or row.get("season_name") == season_name)
    ]
    rows.sort(
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("seat") or 0),
            str(item.get("team_id") or ""),
        ),
        reverse=True,
    )
    return rows


def get_team_dimension_history(
    data: dict[str, Any],
    team_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> list[dict[str, Any]]:
    rows = [
        row
        for row in data.get("season_team_dimension_stats", [])
        if row.get("team_id") == team_id
        and (not competition_name or row.get("competition_name") == competition_name)
        and (not season_name or row.get("season_name") == season_name)
    ]
    rows.sort(
        key=lambda item: (
            str(item.get("played_on") or ""),
            int(item.get("seat") or 0),
            str(item.get("team_id") or ""),
        ),
        reverse=True,
    )
    return rows


def summarize_dimension_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for row in rows:
        for key, value in row.items():
            if key in {"competition_name", "season_name", "played_on", "player_id", "team_id", "seat"}:
                continue
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                summary[key] = float(summary.get(key, 0.0)) + float(value)
    return summary


def build_dimension_season_options(
    rows: list[dict[str, Any]],
) -> list[str]:
    seasons = sorted(
        {
            str(row.get("season_name") or "").strip()
            for row in rows
            if str(row.get("season_name") or "").strip()
        },
        reverse=True,
    )
    return seasons


def build_dimension_radar_chart(
    title: str,
    metrics: list[dict[str, Any]],
) -> str:
    center_x = 126
    center_y = 118
    radius = 78

    def axis_point(index: int, ratio: float) -> tuple[float, float]:
        angle = -math.pi / 2 + index * math.pi / 3
        return (
            center_x + radius * ratio * math.cos(angle),
            center_y + radius * ratio * math.sin(angle),
        )

    grid_polygons = []
    for level in (0.25, 0.5, 0.75, 1.0):
        points = " ".join(
            f"{x:.2f},{y:.2f}"
            for index in range(6)
            for x, y in [axis_point(index, level)]
        )
        grid_polygons.append(
            f'<polygon points="{points}" fill="none" stroke="rgba(45, 127, 249, {0.12 + level * 0.12:.2f})" stroke-width="1"></polygon>'
        )

    axis_lines = []
    labels = []
    metric_rows = []
    data_points = []
    for index, item in enumerate(metrics):
        outer_x, outer_y = axis_point(index, 1.0)
        value_x, value_y = axis_point(index, float(item["ratio"]))
        label_x, label_y = axis_point(index, 1.24)
        label_anchor = "middle"
        if label_x < center_x - 8:
            label_anchor = "end"
        elif label_x > center_x + 8:
            label_anchor = "start"
        axis_lines.append(
            f'<line x1="{center_x}" y1="{center_y}" x2="{outer_x:.2f}" y2="{outer_y:.2f}" stroke="rgba(15, 23, 42, 0.18)" stroke-width="1"></line>'
        )
        labels.append(
            f'<text x="{label_x:.2f}" y="{label_y:.2f}" text-anchor="{label_anchor}" font-size="11" fill="#475467">{escape(str(item["label"]))}</text>'
        )
        metric_rows.append(
            f'<div class="col-6 col-xl-4"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">{escape(str(item["label"]))}</div><div class="fw-semibold mt-2">{escape(str(item["display"]))}</div></div></div>'
        )
        data_points.append(f"{value_x:.2f},{value_y:.2f}")

    polygon_points = " ".join(data_points)
    return f"""
    <div class="row g-4 align-items-center mb-4">
      <div class="col-12 col-xl-5">
        <div class="panel h-100 shadow-sm p-3">
          <div class="small text-secondary mb-3">{escape(title)}</div>
          <svg viewBox="0 0 252 236" width="100%" role="img" aria-label="{escape(title)}">
            {''.join(grid_polygons)}
            {''.join(axis_lines)}
            <polygon points="{polygon_points}" fill="rgba(45, 127, 249, 0.20)" stroke="#2d7ff9" stroke-width="2"></polygon>
            {''.join(f'<circle cx="{point.split(",")[0]}" cy="{point.split(",")[1]}" r="3.2" fill="#175cd3"></circle>' for point in data_points)}
            {''.join(labels)}
            <circle cx="{center_x}" cy="{center_y}" r="2.6" fill="#175cd3"></circle>
          </svg>
        </div>
      </div>
      <div class="col-12 col-xl-7">
        <div class="row g-3">
          {''.join(metric_rows)}
        </div>
      </div>
    </div>
    """


def build_dimension_season_switcher(
    base_path: str,
    competition_name: str | None,
    selected_page_season: str | None,
    available_seasons: list[str],
    selected_dimension_season: str,
) -> str:
    if len(available_seasons) <= 1:
        return ""
    options_html = "".join(
        f'<option value="{escape(item)}"{" selected" if item == selected_dimension_season else ""}>{escape(item)}</option>'
        for item in available_seasons
    )
    hidden_fields = []
    if competition_name:
        hidden_fields.append(f'<input type="hidden" name="competition" value="{escape(competition_name)}">')
    if selected_page_season:
        hidden_fields.append(f'<input type="hidden" name="season" value="{escape(selected_page_season)}">')
    return f"""
    <form method="get" action="{escape(base_path)}" class="row g-3 align-items-end mb-4">
      {''.join(hidden_fields)}
      <div class="col-12 col-lg-4">
        <label class="form-label mb-2">维度数据赛季</label>
        <select class="form-select" name="dimension_season" onchange="this.form.submit()">
          {options_html}
        </select>
      </div>
    </form>
    """


def build_empty_dimension_panel(title: str, description: str) -> str:
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">{escape(title)}</h2>
          <p class="section-copy mb-0">{escape(description)}</p>
        </div>
      </div>
      <div class="alert alert-secondary mb-0">当前还没有导入对应赛季的维度数据。</div>
    </section>
    """


def build_player_dimension_panel(
    ctx: RequestContext,
    data: dict[str, Any],
    player_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> str:
    if not competition_name:
        return ""
    all_rows = get_player_dimension_history(data, player_id, competition_name, None)
    if not all_rows:
        return build_empty_dimension_panel(
            "赛季维度补充数据",
            "这部分来自比赛日报 Excel 的赛季维度补充数据。导入后，这里会显示分赛季汇总和六边形画像。",
        )
    available_seasons = build_dimension_season_options(all_rows)
    requested_dimension_season = form_value(ctx.query, "dimension_season").strip()
    selected_dimension_season = (
        requested_dimension_season
        if requested_dimension_season in available_seasons
        else (season_name if season_name in available_seasons else (available_seasons[0] if available_seasons else ""))
    )
    if not selected_dimension_season:
        return ""
    history = [
        row
        for row in all_rows
        if str(row.get("season_name") or "").strip() == selected_dimension_season
    ]
    if not history:
        return ""
    season_summaries = {
        item: summarize_dimension_rows(
            [row for row in all_rows if str(row.get("season_name") or "").strip() == item]
        )
        for item in available_seasons
    }
    summary = season_summaries[selected_dimension_season]
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    latest = history[0]
    current_team_name = (
        team_lookup.get(latest.get("team_id"), {}).get("name")
        or str(latest.get("team_name") or "").strip()
        or "未知战队"
    )
    avg_points_by_season = {
        item: safe_rate(
            season_summaries[item].get("daily_points", 0.0),
            season_summaries[item].get("games_played", 0.0),
        )
        for item in available_seasons
    }
    max_avg_points = max(avg_points_by_season.values(), default=0.0) or 1.0
    radar_html = build_dimension_radar_chart(
        f"{selected_dimension_season} 赛季维度六边形",
        [
            {
                "label": "总胜率",
                "ratio": safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0)),
                "display": format_pct(safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0))),
            },
            {
                "label": "好人胜率",
                "ratio": safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0)),
                "display": format_pct(safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0))),
            },
            {
                "label": "狼人胜率",
                "ratio": safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0)),
                "display": format_pct(safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0))),
            },
            {
                "label": "场均积分",
                "ratio": min(avg_points_by_season[selected_dimension_season] / max_avg_points, 1.0),
                "display": format_dimension_metric_value(avg_points_by_season[selected_dimension_season]),
            },
            {
                "label": "投狼率",
                "ratio": safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0)),
                "display": format_pct(safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0))),
            },
            {
                "label": "MVP率",
                "ratio": safe_rate(summary.get("mvp_count", 0.0), summary.get("games_played", 0.0)),
                "display": format_pct(safe_rate(summary.get("mvp_count", 0.0), summary.get("games_played", 0.0))),
            },
        ],
    )
    season_switcher_html = build_dimension_season_switcher(
        f"/players/{player_id}",
        competition_name,
        season_name,
        available_seasons,
        selected_dimension_season,
    )
    history_rows = "".join(
        f"""
        <tr>
          <td>{escape(str(item.get('played_on') or ''))}</td>
          <td>{format_dimension_metric_value(item.get('seat', 0))}</td>
          <td>{escape(team_lookup.get(item.get('team_id'), {}).get('name', current_team_name))}</td>
          <td>{format_dimension_metric_value(item.get('daily_points', 0))}</td>
          <td>{format_dimension_metric_value(item.get('games_played', 0))}</td>
          <td>{format_dimension_metric_value(item.get('wins', 0))}</td>
          <td>{format_dimension_metric_value(item.get('vote_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('vote_wolf_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('mvp_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('svp_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('scapegoat_count', 0))}</td>
        </tr>
        """
        for item in history
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">赛季维度补充数据</h2>
          <p class="section-copy mb-0">这部分来自比赛日报 Excel 的赛季维度补充数据。可单独切换赛季查看，并在下方用六边形图看当前赛季的维度画像。</p>
        </div>
        <span class="chip">{escape(selected_dimension_season)}</span>
      </div>
      {season_switcher_html}
      <div class="row g-3 mb-4">
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">当前战队</div><div class="stat-value mt-2">{escape(current_team_name)}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">赛季总维度积分</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('daily_points', 0))}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">局数 / 胜场</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('games_played', 0))} / {format_dimension_metric_value(summary.get('wins', 0))}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">MVP / SVP / 背锅</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('mvp_count', 0))} / {format_dimension_metric_value(summary.get('svp_count', 0))} / {format_dimension_metric_value(summary.get('scapegoat_count', 0))}</div></div></div>
      </div>
      {radar_html}
      <div class="table-responsive">
        <table class="table align-middle">
          <thead><tr><th>日期</th><th>座位</th><th>战队</th><th>当日积分</th><th>局数</th><th>胜场</th><th>投票</th><th>投狼</th><th>MVP</th><th>SVP</th><th>背锅</th></tr></thead>
          <tbody>{history_rows}</tbody>
        </table>
      </div>
    </section>
    """


def build_team_dimension_panel(
    ctx: RequestContext,
    data: dict[str, Any],
    team_id: str,
    competition_name: str | None,
    season_name: str | None,
) -> str:
    if not competition_name:
        return ""
    all_rows = get_team_dimension_history(data, team_id, competition_name, None)
    if not all_rows:
        return build_empty_dimension_panel(
            "战队赛季维度补充数据",
            "这部分来自比赛日报 Excel 的战队维度补充数据。导入后，这里会显示分赛季汇总和六边形画像。",
        )
    available_seasons = build_dimension_season_options(all_rows)
    requested_dimension_season = form_value(ctx.query, "dimension_season").strip()
    selected_dimension_season = (
        requested_dimension_season
        if requested_dimension_season in available_seasons
        else (season_name if season_name in available_seasons else (available_seasons[0] if available_seasons else ""))
    )
    if not selected_dimension_season:
        return ""
    history = [
        row
        for row in all_rows
        if str(row.get("season_name") or "").strip() == selected_dimension_season
    ]
    if not history:
        return ""
    season_summaries = {
        item: summarize_dimension_rows(
            [row for row in all_rows if str(row.get("season_name") or "").strip() == item]
        )
        for item in available_seasons
    }
    summary = season_summaries[selected_dimension_season]
    avg_points_by_season = {
        item: safe_rate(
            season_summaries[item].get("daily_points", 0.0),
            season_summaries[item].get("games_played", 0.0),
        )
        for item in available_seasons
    }
    max_avg_points = max(avg_points_by_season.values(), default=0.0) or 1.0
    latest = history[0]
    radar_html = build_dimension_radar_chart(
        f"{selected_dimension_season} 战队维度六边形",
        [
            {
                "label": "总胜率",
                "ratio": safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0)),
                "display": format_pct(safe_rate(summary.get("wins", 0.0), summary.get("games_played", 0.0))),
            },
            {
                "label": "好人胜率",
                "ratio": safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0)),
                "display": format_pct(safe_rate(summary.get("villager_wins", 0.0), summary.get("villager_games", 0.0))),
            },
            {
                "label": "狼人胜率",
                "ratio": safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0)),
                "display": format_pct(safe_rate(summary.get("werewolf_wins", 0.0), summary.get("werewolf_games", 0.0))),
            },
            {
                "label": "场均积分",
                "ratio": min(avg_points_by_season[selected_dimension_season] / max_avg_points, 1.0),
                "display": format_dimension_metric_value(avg_points_by_season[selected_dimension_season]),
            },
            {
                "label": "投狼率",
                "ratio": safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0)),
                "display": format_pct(safe_rate(summary.get("vote_wolf_count", 0.0), summary.get("vote_count", 0.0))),
            },
            {
                "label": "首日投对率",
                "ratio": safe_rate(
                    summary.get("first_vote_correct", 0.0),
                    float(summary.get("first_vote_correct", 0.0)) + float(summary.get("first_vote_incorrect", 0.0)),
                ),
                "display": format_pct(
                    safe_rate(
                        summary.get("first_vote_correct", 0.0),
                        float(summary.get("first_vote_correct", 0.0)) + float(summary.get("first_vote_incorrect", 0.0)),
                    )
                ),
            },
        ],
    )
    season_switcher_html = build_dimension_season_switcher(
        f"/teams/{team_id}",
        competition_name,
        season_name,
        available_seasons,
        selected_dimension_season,
    )
    history_rows = "".join(
        f"""
        <tr>
          <td>{escape(str(item.get('played_on') or ''))}</td>
          <td>{format_dimension_metric_value(item.get('seat', 0))}</td>
          <td>{format_dimension_metric_value(item.get('daily_points', 0))}</td>
          <td>{format_dimension_metric_value(item.get('games_played', 0))}</td>
          <td>{format_dimension_metric_value(item.get('wins', 0))}</td>
          <td>{format_dimension_metric_value(item.get('villager_points', 0))}</td>
          <td>{format_dimension_metric_value(item.get('werewolf_points', 0))}</td>
          <td>{format_dimension_metric_value(item.get('first_vote_correct', 0))}</td>
          <td>{format_dimension_metric_value(item.get('first_vote_incorrect', 0))}</td>
          <td>{format_dimension_metric_value(item.get('mvp_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('svp_count', 0))}</td>
          <td>{format_dimension_metric_value(item.get('scapegoat_count', 0))}</td>
        </tr>
        """
        for item in history
    )
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队赛季维度补充数据</h2>
          <p class="section-copy mb-0">这部分来自比赛日报 Excel 的战队维度补充数据。可单独切换赛季查看，并在下方用六边形图看当前赛季的战队画像。</p>
        </div>
        <span class="chip">{escape(selected_dimension_season)}</span>
      </div>
      {season_switcher_html}
      <div class="row g-3 mb-4">
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">赛季总维度积分</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('daily_points', 0))}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">局数 / 胜场</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('games_played', 0))} / {format_dimension_metric_value(summary.get('wins', 0))}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">好人得分 / 狼人得分</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('villager_points', 0))} / {format_dimension_metric_value(summary.get('werewolf_points', 0))}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">首日投对 / 投错</div><div class="stat-value mt-2">{format_dimension_metric_value(summary.get('first_vote_correct', 0))} / {format_dimension_metric_value(summary.get('first_vote_incorrect', 0))}</div></div></div>
      </div>
      {radar_html}
      <div class="table-responsive">
        <table class="table align-middle">
          <thead><tr><th>日期</th><th>座位</th><th>当日积分</th><th>局数</th><th>胜场</th><th>好人得分</th><th>狼人得分</th><th>首日投对</th><th>首日投错</th><th>MVP</th><th>SVP</th><th>背锅</th></tr></thead>
          <tbody>{history_rows}</tbody>
        </table>
      </div>
    </section>
    """


def get_team_page(ctx: RequestContext, team_id: str, alert: str = "") -> str:
    data = load_validated_data()
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team = team_lookup.get(team_id)
    if not team:
        return layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx)
    current_player = get_user_player(data, ctx.current_user)
    can_manage_team_profile = can_manage_team(ctx, team, current_player)
    can_delete_team = bool(ctx.current_user and is_admin_user(ctx.current_user))
    team_competition_name, team_season_name = get_team_scope(team)
    team_status = get_team_season_status(data, team)
    team_status_label = get_team_season_status_label(team_status)
    can_edit_team_page = can_manage_team_profile and team_status in {"ongoing", "upcoming", "unknown"}
    guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
    stage_group_map = get_team_stage_group_map(team)
    team_logo_html = build_team_logo_html(team["logo"], team["name"])
    captain_player = player_lookup.get(get_team_captain_id(team) or "")
    captain_label = captain_player["display_name"] if captain_player else ""
    is_unclaimed = not captain_player
    scope_player, scope_team = get_user_team_for_scope(
        data,
        ctx.current_user,
        team_competition_name,
        team_season_name,
    )
    has_scope_claim_conflict = bool(scope_player and scope_team and scope_team["team_id"] != team_id)
    has_same_team_identity = bool(scope_player and scope_team and scope_team["team_id"] == team_id)
    current_claim_request = (
        next(
            (
                item
                for item in load_membership_requests()
                if ctx.current_user
                and item.get("username") == ctx.current_user["username"]
                and item.get("request_type") == "team_claim"
            ),
            None,
        )
        if ctx.current_user
        else None
    )
    current_team_path = build_scoped_path(
        f"/teams/{team_id}",
        form_value(ctx.query, "competition").strip() or team_competition_name or None,
        form_value(ctx.query, "season").strip() or team_season_name or None,
    )
    requested_competition = form_value(ctx.query, "competition").strip()
    requested_season = form_value(ctx.query, "season").strip()
    claim_panel = ""
    if is_unclaimed and team_status != "completed":
        claim_copy = "战队名称和成员由赛季档案维护。认领后，你可以编辑战队队标、简称、介绍和赛段分组信息。"
        claim_action_html = ""
        if not ctx.current_user:
            claim_action_html = f'<a class="btn btn-dark" href="/login?next={quote(current_team_path)}">登录后申请认领</a>'
        elif has_scope_claim_conflict:
            claim_copy = "当前账号在这个赛事赛季里已经绑定了其他战队身份，不能重复认领新的战队。"
            claim_action_html = '<span class="chip">当前账号已绑定其他战队</span>'
        elif current_claim_request:
            claim_copy = "你当前已经有一条待处理的战队认领申请，处理完成前不能再提交新的申请。"
            claim_action_html = '<a class="btn btn-outline-dark" href="/team-center">前往认领中心查看</a>'
        else:
            if has_same_team_identity:
                claim_copy = "当前账号已经绑定了这支战队的赛季参赛身份。认领通过后会直接把这个赛季身份设为负责人，不会再额外创建队员。"
            claim_action_html = f"""
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="request_team_claim">
              <input type="hidden" name="team_id" value="{escape(team_id)}">
              <input type="hidden" name="next" value="{escape(current_team_path)}">
              <button type="submit" class="btn btn-dark">申请认领</button>
            </form>
            """
        claim_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
            <div>
              <h2 class="section-title mb-2">认领这支战队</h2>
              <p class="section-copy mb-0">{escape(claim_copy)}</p>
            </div>
            {claim_action_html}
          </div>
        </section>
        """
    stage_group_summary = (
        " / ".join(
            f"{stage_label} {escape(stage_group_map.get(stage_key, ''))}"
            for stage_key, stage_label in STAGE_OPTIONS.items()
            if stage_group_map.get(stage_key)
        )
        or "暂未设置"
    )
    stage_group_inputs_html = "".join(
        f"""
        <div class="col-12 col-md-6 col-xl-4">
          <label class="form-label">{escape(stage_label)}</label>
          <input class="form-control" name="stage_group_{escape(stage_key)}" value="{escape(stage_group_map.get(stage_key, ''))}" placeholder="例如 A组 / 淘汰组 / 种子组">
        </div>
        """
        for stage_key, stage_label in STAGE_OPTIONS.items()
    )
    team_manage_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队维护</h2>
          <p class="section-copy mb-0">这里只保留维护操作。战队展示信息已经合并到上方巡礼区域。</p>
        </div>
      </div>
      <div class="form-panel p-3 p-lg-4">
        {(
          f'''
          <form method="post" action="/teams/{escape(team_id)}/logo" enctype="multipart/form-data" class="mb-4">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <div class="row g-3 align-items-end">
              <div class="col-12 col-lg-8">
                <input class="form-control" name="logo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
              </div>
              <div class="col-12 col-lg-4 d-flex gap-2">
                <button type="submit" class="btn btn-dark">更新队标</button>
              </div>
            </div>
          </form>
          '''
          if can_edit_team_page
          else ''
        )}
        {(
          f'''
          <form method="post" action="/team-center" class="mb-4">
            <input type="hidden" name="action" value="delete_team">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <button type="submit" class="btn btn-outline-danger">管理员删除战队</button>
          </form>
          '''
          if can_delete_team
          else ''
        )}
        {(
          f'''
          <form method="post" action="/team-center">
            <input type="hidden" name="action" value="update_team_profile">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <div class="row g-3">
              <div class="col-12 col-lg-4">
                <label class="form-label">战队简称</label>
                <input class="form-control" name="short_name" value="{escape(team.get('short_name') or '')}" maxlength="24">
              </div>
              <div class="col-12">
                <label class="form-label">战队介绍</label>
                <textarea class="form-control" name="notes" rows="4">{escape(team.get('notes') or '')}</textarea>
              </div>
            </div>
            <button type="submit" class="btn btn-dark mt-4">保存战队资料</button>
          </form>
          '''
          if can_edit_team_page
          else (
            '<div class="small text-secondary">当前赛季已结束，战队资料已锁定。</div>'
            if team_status == "completed"
            else '<div class="small text-secondary">只有管理员、具备战队管理权限的账号或已认领该战队的负责人可以编辑战队资料。</div>'
          )
        )}
        {(
          f'''
          <form method="post" action="/team-center" class="mt-3">
            <input type="hidden" name="action" value="unbind_team_claim">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <input type="hidden" name="next" value="{escape(current_team_path)}">
            <button type="submit" class="btn btn-outline-danger">解除当前认领</button>
            <div class="small text-secondary mt-2">只会解除负责人身份，不会删除战队档案，也不会移除赛季成员记录。</div>
          </form>
          '''
          if can_manage_team_profile and not is_unclaimed
          else ''
        )}
        <div class="small text-secondary mt-4">
          <strong>赛段分组：</strong>
          {stage_group_summary}
        </div>
        {(
          f'''
          <form method="post" action="/team-center" class="mt-3">
            <input type="hidden" name="action" value="update_team_stage_groups">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <div class="row g-3">
              {stage_group_inputs_html}
            </div>
            <button type="submit" class="btn btn-outline-dark mt-3">保存赛段分组</button>
          </form>
          '''
          if can_edit_team_page
          else ''
        )}
      </div>
    </section>
    """

    team_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if any(entry["team_id"] == team_id for entry in match["players"])
    ]
    team_competition_names = []
    for match in team_matches:
        competition_name = get_match_competition_name(match)
        if competition_name not in team_competition_names:
            team_competition_names.append(competition_name)
    if team_competition_name and team_competition_name not in team_competition_names:
        team_competition_names.append(team_competition_name)

    selected_competition = (
        form_value(ctx.query, "competition").strip()
        or team_competition_name
        or get_selected_competition(ctx, team_competition_names)
    )
    season_names = [team_season_name] if team_season_name else (
        list_seasons(
            {
                "matches": [
                    match
                    for match in team_matches
                    if get_match_competition_name(match) == selected_competition
                ]
            },
            selected_competition,
        )
        if selected_competition
        else []
    )
    selected_season = team_season_name or get_selected_season(ctx, season_names)
    team_dimension_panel = build_team_dimension_panel(
        ctx,
        data,
        team_id,
        selected_competition,
        selected_season,
    )
    competition_switcher = build_competition_switcher(
        f"/teams/{team_id}",
        team_competition_names,
        selected_competition,
        tone="light",
        all_label="比赛总览",
    )
    season_switcher = ""
    competition_groups: dict[str, list[dict[str, Any]]] = {}
    for match in team_matches:
        competition_name = get_match_competition_name(match)
        competition_groups.setdefault(competition_name, []).append(
            summarize_team_match(team_id, match, team_lookup)
        )
    team_match_player_score_section = build_team_match_player_score_section(
        ctx,
        data,
        team_id,
        player_lookup,
        team_lookup,
        selected_competition,
        selected_season or "",
    )

    if not selected_competition:
        competition_cards = []
        for competition_name in team_competition_names:
            competition_team_stats = {
                row["team_id"]: row for row in build_team_rows(data, competition_name)
            }.get(team_id)
            matches = competition_groups.get(competition_name, [])
            if not competition_team_stats:
                continue
            competition_cards.append(
                f"""
                <div class="col-12 col-md-6">
                  <a class="team-link-card shadow-sm p-4 h-100" href="/teams/{escape(team_id)}?{urlencode({'competition': competition_name})}">
                    <div class="small text-secondary mb-2">比赛入口</div>
                    <h2 class="h4 mb-2">{escape(competition_name)}</h2>
                    <div class="small-muted mb-3">赛季 {escape('、'.join(list_seasons({'matches': team_matches}, competition_name, include_non_ongoing=True)) or '未设置')} · 对局 {competition_team_stats['matches_represented']} 场 · 队员 {competition_team_stats['player_count']} 名</div>
                    <div class="row g-3">
                      <div class="col-6"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(competition_team_stats['win_rate'])}</div></div>
                      <div class="col-6"><div class="small text-secondary">总积分</div><div class="fw-semibold">{competition_team_stats['points_earned_total']:.2f}</div></div>
                    </div>
                  </a>
                </div>
                """
            )

        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="hero-layout">
            <div>
              <div class="eyebrow mb-3">战队比赛总览</div>
              <h1 class="display-6 fw-semibold mb-2">{escape(team['name'])}</h1>
              <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
              <p class="mb-2 opacity-75">简称：{escape(team.get('short_name') or '未设置')}</p>
              <p class="mb-2 opacity-75">负责人：{escape(captain_label or '暂未认领')}</p>
              <p class="mb-2 opacity-75">赛段分组：{stage_group_summary}</p>
              <p class="mb-0 opacity-75">{escape(team['notes'])}</p>
              <div class="d-flex flex-wrap gap-2 mt-3">
                {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
              </div>
              <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
            </div>
            <div class="ms-lg-auto">
              {team_logo_html}
            </div>
          </div>
        </section>
        {claim_panel}
        {team_manage_panel if (can_edit_team_page or can_delete_team or can_manage_team_profile) else ''}
        {team_dimension_panel}
        {team_match_player_score_section}
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">请选择系列赛</h2>
              <p class="section-copy mb-0">战队战绩和排名只在单个系列赛的具体赛季里统计。先选系列赛，再继续切换赛季查看这支战队的队员和战绩。</p>
            </div>
            <a class="btn btn-outline-dark" href="/competitions">返回比赛列表</a>
          </div>
          <div class="row g-3 g-lg-4">{''.join(competition_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">这支战队暂时还没有比赛数据。</div></div>'}</div>
        </section>
        """
        return layout(f"{team['name']} 页面", body, ctx, alert=alert)

    player_rows = {
        row["player_id"]: row
        for row in build_player_rows(data, selected_competition, selected_season)
    }
    team_rows = {
        row["team_id"]: row for row in build_team_rows(data, selected_competition, selected_season)
    }
    roster_player_ids = resolve_team_player_ids(
        data, team_id, selected_competition, selected_season
    )
    roster_count = len(roster_player_ids)
    team_stats = team_rows.get(
        team_id,
        {
            "team_id": team_id,
            "win_rate": 0.0,
            "stance_rate": 0.0,
            "points_earned_total": 0.0,
            "player_count": roster_count,
            "matches_represented": 0,
        },
    )
    players = []
    for player_id in roster_player_ids:
        player = player_lookup.get(player_id)
        player_stats = player_rows.get(player_id)
        if not player:
            continue
        players.append(
            {
                **player,
                "win_rate": format_pct(player_stats["win_rate"]) if player_stats else "0.0%",
                "stance_rate": format_pct(player_stats["stance_rate"]) if player_stats else "0.0%",
                "points_total": f"{player_stats['points_earned_total']:.2f}" if player_stats else "0.00",
                "games_played": player_stats["games_played"] if player_stats else 0,
                "average_points": player_stats["average_points"] if player_stats else 0.0,
                "has_stats": bool(player_stats),
            }
        )
    players.sort(
        key=lambda item: (
            0 if item["has_stats"] else 1,
            -float(item["points_total"]),
            -item["games_played"],
            item["display_name"],
        )
    )
    ai_team_season_summary = (
        load_ai_team_season_summary(team_id, selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_team_summary_actions = ""
    ai_team_summary_admin_editor = ""
    if selected_competition and selected_season:
        if ai_configured and (not ai_team_season_summary or is_admin_user(ctx.current_user)):
            ai_team_summary_actions = f"""
            <form method="post" action="/teams/{escape(team_id)}" class="m-0">
              <input type="hidden" name="action" value="generate_ai_team_season_summary">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season)}">
              <button type="submit" class="btn btn-dark">{'重生成 AI 战队赛季总结' if ai_team_season_summary else '生成 AI 战队赛季总结'}</button>
            </form>
            """
        elif not ai_configured and is_admin_user(ctx.current_user):
            ai_team_summary_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
        if ai_team_season_summary and is_admin_user(ctx.current_user):
            ai_team_summary_admin_editor = f"""
            <div class="form-panel p-3 p-lg-4 mt-4">
              <h3 class="h5 mb-2">管理员编辑总结</h3>
              <p class="section-copy mb-3">可以直接修改当前总结正文。保存后会立即覆盖展示内容。</p>
              <form method="post" action="/teams/{escape(team_id)}">
                <input type="hidden" name="action" value="save_ai_team_season_summary">
                <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
                <input type="hidden" name="season_name" value="{escape(selected_season)}">
                <div class="mb-3">
                  <textarea class="form-control" name="summary_content" rows="12">{escape(ai_team_season_summary.get('content') or '')}</textarea>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
                </div>
              </form>
            </div>
            """
    ai_team_summary_panel = ""
    if selected_season:
        ai_team_summary_panel = (
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">AI 战队赛季总结</h2>
                  <p class="section-copy mb-0">基于当前战队在这个赛事赛季下的真实战绩、队员数据和比赛记录生成总结。首次生成对所有访客开放；生成后仅管理员可重生成或编辑。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_team_summary_actions}</div>
              </div>
              <div class="small text-secondary mb-3">生成时间 {escape(ai_team_season_summary.get('generated_at') or '未生成')} · 模型 {escape(ai_team_season_summary.get('model') or ai_settings.get('model') or DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
              <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_team_season_summary.get('content') or '')}</div>
              {ai_team_summary_admin_editor}
            </section>
            """
            if ai_team_season_summary
            else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 战队赛季总结</h2>
                  <p class="section-copy mb-0">{escape('当前赛季还没有生成 AI 总结，首次生成对所有访客开放。' if ai_configured else '当前还没有配置 AI 接口。配置后即可在这里生成战队赛季总结。')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_team_summary_actions}</div>
              </div>
            </section>
            """
        )

    team_short_label = str(team.get("short_name") or team["name"]).strip() or team["name"]
    team_record = f"{team_stats.get('wins', 0)}-{team_stats.get('losses', 0)}"
    team_points_total = f"{float(team_stats.get('points_earned_total', 0.0)):.2f}"
    team_points_per_match = f"{float(team_stats.get('points_per_match', 0.0)):.2f}"
    team_win_display = format_pct(team_stats.get("win_rate", 0.0))
    team_rank_copy = (
        f"当前赛季积分榜第 {team_stats.get('points_rank', '-')} 名 · 战绩 {team_record}"
        if team_stats.get("matches_represented")
        else "当前赛季还没有形成有效积分排名"
    )
    team_win_width = max(0.0, min(100.0, float(team_stats.get("win_rate", 0.0)) * 100.0))
    team_point_speed_width = max(
        0.0,
        min(100.0, float(team_stats.get("points_per_match", 0.0)) / 12.0 * 100.0),
    )
    scoped_match_summaries = [
        summarize_team_match(team_id, match, team_lookup)
        for match in team_matches
        if get_match_competition_name(match) == selected_competition
        and (not selected_season or str(match.get("season") or "").strip() == selected_season)
    ]
    roster_cards_html = "".join(
        f"""
        <a class="team-roster-card text-decoration-none" href="{escape(build_scoped_path('/players/' + player['player_id'], selected_competition, selected_season))}">
          <div class="team-roster-top">
            <div>
              <div class="team-roster-name">{escape(player["display_name"])}</div>
              <div class="team-roster-meta">{escape('赛季主力轮换' if player["has_stats"] else '赛季档案已创建，等待补录数据')}</div>
            </div>
            <div class="team-roster-value">{escape(player["points_total"])} 分</div>
          </div>
          <div class="team-roster-tags">
            {'<span class="player-stat-pill">负责人</span>' if captain_player and captain_player.get("player_id") == player["player_id"] else ''}
            <span class="player-stat-pill">出场 {player["games_played"]}</span>
            <span class="player-stat-pill">胜率 {escape(player["win_rate"])}</span>
            <span class="player-stat-pill">场均 {player["average_points"]:.2f}</span>
          </div>
        </a>
        """
        for player in players[:6]
    ) or """
        <article class="team-roster-card">
          <div class="team-roster-name">暂无赛季阵容数据</div>
          <div class="team-roster-meta mt-2">当前统计口径下，这支战队还没有参赛队员数据。</div>
        </article>
    """
    recent_match_cards: list[str] = []
    for item in scoped_match_summaries[:4]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/teams/' + team_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/teams/" + team_id, selected_competition, selected_season),
        )
        match_row = next(
            (
                match
                for match in team_matches
                if match["match_id"] == item["match_id"]
            ),
            None,
        )
        team_result_value = next(
            (
                str(entry.get("result") or "").strip()
                for entry in (match_row or {}).get("players", [])
                if str(entry.get("team_id") or "").strip() == team_id
                and str(entry.get("result") or "").strip()
            ),
            "",
        )
        team_result_label = (
            RESULT_OPTIONS.get(team_result_value, "")
            or (
                "胜利"
                if item["team_score"] > item["opponent_score"]
                else ("失利" if item["team_score"] < item["opponent_score"] else "战平")
            )
        )
        team_award_labels = [
            label
            for label, award_player_id in [
                ("MVP", str((match_row or {}).get("mvp_player_id") or "").strip()),
                ("SVP", str((match_row or {}).get("svp_player_id") or "").strip()),
                ("背锅", str((match_row or {}).get("scapegoat_player_id") or "").strip()),
            ]
            if award_player_id
            and any(
                str(entry.get("team_id") or "").strip() == team_id
                and str(entry.get("player_id") or "").strip() == award_player_id
                for entry in (match_row or {}).get("players", [])
            )
        ]
        team_award_pills = "".join(
            f'<span class="player-stat-pill">{escape(label)}</span>'
            for label in team_award_labels
        ) or '<span class="player-stat-pill">无特殊奖励</span>'
        team_player_score_pills = "".join(
            f'<span class="player-stat-pill">{escape(player_lookup.get(str(entry.get("player_id") or "").strip(), {}).get("display_name", str(entry.get("player_name") or entry.get("player_id") or "未命名队员")))} {float(entry.get("points_earned") or 0.0):.2f}</span>'
            for entry in sorted(
                [
                    participant
                    for participant in (match_row or {}).get("players", [])
                    if str(participant.get("team_id") or "").strip() == team_id
                ],
                key=lambda participant: (
                    -float(participant.get("points_earned") or 0.0),
                    int(participant.get("seat") or 0),
                ),
            )
        ) or '<span class="player-stat-pill">暂无队员得分</span>'
        recent_match_cards.append(
            f"""
            <article class="team-match-card">
              <div class="team-match-top">
                <div>
                  <div class="team-match-name">第 {item["round"]} 轮 · {escape(item["played_on"])}</div>
                  <div class="team-match-meta">{escape(selected_season or item["season"])} · {escape(team_result_label)}</div>
                </div>
                <div class="team-match-value">{item["team_score"]:.2f}</div>
              </div>
              <div class="team-scoreboard">
                <strong>{item["team_score"]:.2f}</strong>
                <span>{escape(team_short_label)} 本队得分</span>
              </div>
              <div class="team-insight-tags">
                {team_player_score_pills}
              </div>
              <div class="team-insight-tags">
                <span class="player-stat-pill">{escape(team_result_label)}</span>
                {team_award_pills}
              </div>
              <div class="team-match-actions">
                <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">比赛详情</a>
                <a class="btn btn-sm btn-light border" href="{escape(day_path)}">当日赛程</a>
              </div>
            </article>
            """
        )
    recent_match_cards_html = "".join(recent_match_cards) or """
        <article class="team-match-card">
          <div class="team-match-name">暂无近期比赛</div>
          <div class="team-match-meta mt-2">当前统计口径下，这支战队还没有可展示的赛季比赛记录。</div>
        </article>
    """

    competition_sections = []
    for competition_name, matches in competition_groups.items():
        if competition_name != selected_competition:
            continue
        scoped_matches = [
            item
            for item in matches
            if not selected_season or item["season"] == selected_season
        ]
        seasons = sorted({item["season"] for item in scoped_matches}, reverse=True)
        rows = []
        for item in sorted(
            scoped_matches,
            key=lambda row: (row["played_on"], row["round"], row["game_no"]),
        ):
            match_detail_path = (
                f"/matches/{item['match_id']}?next="
                f"{quote(build_scoped_path('/teams/' + team_id, selected_competition, selected_season))}"
            )
            day_path = build_match_day_path(
                item["played_on"],
                build_scoped_path("/teams/" + team_id, selected_competition, selected_season),
            )
            manage_actions = (
                f'<a class="btn btn-sm btn-outline-dark" href="/matches/{escape(item["match_id"])}/edit?next={quote(build_scoped_path("/teams/" + team_id, selected_competition, selected_season))}">编辑比赛</a>'
                if can_edit_team_page and can_manage_matches(ctx.current_user, data, selected_competition)
                else ""
            )
            rows.append(
                f"""
                <tr>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(item['match_id'])}</a></td>
                  <td>{escape(item['season'])}</td>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(item['played_on'])}</a></td>
                  <td>{escape(item['stage'])}</td>
                  <td>第 {item['round']} 轮</td>
                  <td>{escape(item['table_label'])}</td>
                  <td>{escape(item['format'])}</td>
                  <td>{escape(item['winning_camp'])}</td>
                  <td>{item['team_score']:.2f}</td>
                  <td>{item['opponent_score']:.2f}</td>
                  <td>{item['duration_minutes']} 分钟</td>
                  <td>
                    <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">详情</a>
                    {manage_actions}
                  </td>
                </tr>
                """
            )
        competition_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">{escape(competition_name)}</h2>
                  <p class="section-copy mb-0">当前赛季：{escape(selected_season or '全部赛季')}。这里展示 {escape(team['name'])} 在该系列赛当前赛季中的全部比赛。</p>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>赛季</th>
                      <th>日期</th>
                      <th>阶段</th>
                      <th>轮次</th>
                      <th>房间</th>
                      <th>板型</th>
                      <th>胜利阵营</th>
                      <th>{escape(team['short_name'])} 得分</th>
                      <th>对手得分</th>
                      <th>时长</th>
                      <th>操作</th>
                    </tr>
                  </thead>
                  <tbody>
                    {''.join(rows)}
                  </tbody>
                </table>
              </div>
            </section>
            """
        )

    guild_options_html = "".join(
        f'<option value="{escape(item["guild_id"])}">{escape(item["name"])}</option>'
        for item in sorted(data.get("guilds", []), key=lambda row: row["name"])
    )
    guild_panel = ""
    if guild:
        guild_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">关联门派</h2>
          <p class="section-copy mb-3">这支战队已经加入门派，门派页会统一汇总它在不同赛事与赛季中的荣誉和公开成绩。</p>
          <a class="btn btn-outline-dark" href="/guilds/{escape(guild['guild_id'])}">{escape(guild['name'])}</a>
        </section>
        """
    elif can_edit_team_page and guild_options_html:
        guild_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <h2 class="section-title mb-2">申请加入门派</h2>
          <p class="section-copy mb-4">当前赛季战队还没有门派归属。管理员、具备战队管理权限的账号或已认领该战队的负责人可以从这里向某个门派提交加入申请，等待门主或门派管理员审核。</p>
          <form method="post" action="/guilds">
            <input type="hidden" name="action" value="request_team_guild_join">
            <input type="hidden" name="team_id" value="{escape(team_id)}">
            <div class="mb-4">
              <label class="form-label">选择门派</label>
              <select class="form-select" name="guild_id">{guild_options_html}</select>
            </div>
            <button type="submit" class="btn btn-dark">提交申请</button>
          </form>
        </section>
        """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">战队巡礼</div>
          <h1 class="display-6 fw-semibold mb-2">{escape(team['name'])}</h1>
          <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
          <p class="mb-2 opacity-75">简称：{escape(team.get('short_name') or '未设置')}</p>
          <p class="mb-2 opacity-75">负责人：{escape(captain_label or '暂未认领')}</p>
          <p class="mb-2 opacity-75">赛段分组：{stage_group_summary}</p>
          <p class="mb-0 opacity-75">{escape(team['notes'])}</p>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <span class="chip">{escape(team_status_label)}</span>
            <span class="chip">{'待认领' if is_unclaimed else f'负责人：{escape(captain_label)}'}</span>
            {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">关联门派：{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
          {f'<div class="d-flex flex-wrap gap-2 mt-3">{season_switcher}</div>' if season_switcher else ''}
          <div class="d-flex flex-wrap gap-3 mt-3">
            <span class="chip">{escape(selected_season or '当前赛季')}</span>
            <span class="chip">胜率 {format_pct(team_stats['win_rate'])}</span>
            <span class="chip">总积分 {team_stats['points_earned_total']:.2f}</span>
            <span class="chip">队员 {roster_count} 名</span>
          </div>
        </div>
        <div class="ms-lg-auto">
          {team_logo_html}
        </div>
      </div>
    </section>
    {claim_panel}
    {(
      '<div class="alert alert-secondary mb-4">当前战队所属赛季已结束，战队资料和门派申请入口已关闭，页面仅保留公开展示。</div>'
      if team_status == "completed"
      else ''
    )}
    {ai_team_summary_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队赛季主页</h2>
          <p class="section-copy mb-0">把这个赛季最该先看的信息收在一屏里：战绩、阵容、状态和最近比赛走势。</p>
        </div>
      </div>
      <div class="team-showcase-grid">
        <article class="team-showcase-card">
          <div class="eyebrow">Team Dossier</div>
          <div class="team-headline">{escape(team['name'])}</div>
          <div class="team-subtitle">{escape(selected_competition or team_scope_label(team))} · {escape(selected_season or '当前赛季')} · {escape(team_rank_copy)}</div>
          <div class="team-badge-row mt-3">
            <span class="team-badge">{escape(team_status_label)}</span>
            <span class="team-badge">队员 {roster_count} 名</span>
            <span class="team-badge">出赛 {team_stats.get('matches_represented', 0)} 场</span>
            <span class="team-badge">总积分 {team_points_total}</span>
          </div>
          <div class="team-kpi-grid">
            <div class="team-kpi-card">
              <div class="team-kpi-label">Season Record</div>
              <div class="team-kpi-value">{team_record}</div>
              <div class="team-kpi-copy">当前赛季累计胜负走势</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Win Rate</div>
              <div class="team-kpi-value">{team_win_display}</div>
              <div class="team-kpi-copy">按赛季全部出场计算</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Points Total</div>
              <div class="team-kpi-value">{team_points_total}</div>
              <div class="team-kpi-copy">赛季累计积分沉淀</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Points Per Match</div>
              <div class="team-kpi-value">{team_points_per_match}</div>
              <div class="team-kpi-copy">每场比赛的稳定产出</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Matches Played</div>
              <div class="team-kpi-value">{team_stats.get('matches_represented', 0)}</div>
              <div class="team-kpi-copy">当前赛季有效出赛场次</div>
            </div>
            <div class="team-kpi-card">
              <div class="team-kpi-label">Roster Active</div>
              <div class="team-kpi-value">{team_stats.get('player_count', roster_count)}</div>
              <div class="team-kpi-copy">当前赛季已上场队员数</div>
            </div>
          </div>
        </article>
        <aside class="team-insight-card">
          <div>
            <h3 class="section-title mb-2">赛季观察</h3>
            <p class="section-copy mb-0">先看这支队伍现在是稳扎稳打、靠积分效率拉开，还是靠判断和阵容深度取胜。</p>
          </div>
          <div class="team-meter-row">
            <div class="team-meter-head">
              <strong>胜率表现</strong>
              <span>{team_win_display}</span>
            </div>
            <div class="team-meter-track"><div class="team-meter-fill" style="width: {team_win_width:.1f}%"></div></div>
          </div>
          <div class="team-meter-row">
            <div class="team-meter-head">
              <strong>积分效率</strong>
              <span>场均 {team_points_per_match}</span>
            </div>
            <div class="team-meter-track"><div class="team-meter-fill" style="width: {team_point_speed_width:.1f}%"></div></div>
          </div>
          <div class="team-note-grid">
            <div class="team-note-item">
              <div class="team-note-label">Captain</div>
              <div class="team-note-value">{escape(captain_label or '暂未认领')}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Guild</div>
              <div class="team-note-value">{escape(guild['name'] if guild else '未加入门派')}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Stage Group</div>
              <div class="team-note-value">{stage_group_summary}</div>
            </div>
            <div class="team-note-item">
              <div class="team-note-label">Notes</div>
              <div class="team-note-value">{escape(team.get('notes') or '暂无战队备注')}</div>
            </div>
          </div>
        </aside>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">赛季阵容</h2>
          <p class="section-copy mb-3">先展示当前赛季最主要的轮换成员，方便从战队页直接下钻到队员档案。</p>
          <div class="team-roster-grid">{roster_cards_html}</div>
        </div>
        <div class="col-12 col-xl-6">
          <h2 class="section-title mb-2">最近比赛</h2>
          <p class="section-copy mb-3">把最近几场的比分和比赛详情提上来，不用先翻到底部的大表。</p>
          <div class="team-match-grid">{recent_match_cards_html}</div>
        </div>
      </div>
    </section>
    {guild_panel}
    {team_dimension_panel}
    {team_match_player_score_section}
    {team_manage_panel if (can_edit_team_page or can_delete_team or can_manage_team_profile) else ''}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">完整比赛明细</h2>
          <p class="section-copy mb-0">下面继续保留完整赛季比赛表，方便你核对每一场的板型、得分和操作入口。</p>
        </div>
      </div>
    </section>
    {''.join(competition_sections) if competition_sections else '<div class="alert alert-secondary">该战队在当前统计口径下暂时没有比赛记录。</div>'}
    """
    return layout(f"{team['name']} 页面", body, ctx, alert=alert)


def get_team_season_status(data: dict[str, Any], team: dict[str, Any]) -> str:
    competition_name, season_name = get_team_scope(team)
    if not competition_name or not season_name:
        return "unknown"
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)
    try:
        series_slug = build_series_context_from_competition(
            competition_name,
            series_catalog,
        )["series_slug"]
    except Exception:
        return "unknown"
    season_entry = get_season_entry(
        season_catalog,
        series_slug,
        season_name,
        competition_name=competition_name,
    )
    if not season_entry:
        return "unknown"
    return get_season_status(season_entry)


def get_team_season_status_rank(status: str) -> int:
    return {"ongoing": 0, "upcoming": 1, "completed": 2, "unknown": 3}.get(status, 3)


def get_team_season_status_label(status: str) -> str:
    return {
        "ongoing": "进行中",
        "upcoming": "未开始",
        "completed": "已结束",
        "unknown": "未配置",
    }.get(status, "未配置")


def build_team_match_player_score_section(
    ctx: RequestContext,
    data: dict[str, Any],
    team_id: str,
    player_lookup: dict[str, dict[str, Any]],
    team_lookup: dict[str, dict[str, Any]],
    selected_competition: str = "",
    selected_season: str = "",
) -> str:
    completed_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (
                get_match_competition_name(item),
                str(item.get("season") or "").strip(),
                item["played_on"],
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
            reverse=True,
        )
        if is_match_counted_as_played(match)
        and any(str(entry.get("team_id") or "").strip() == team_id for entry in match["players"])
        and (not selected_competition or get_match_competition_name(match) == selected_competition)
        and (not selected_season or str(match.get("season") or "").strip() == selected_season)
    ]
    if not completed_matches:
        return f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">战队比赛队员成绩</h2>
              <p class="section-copy mb-0">这里只展示已完成补录的比赛，进行中的赛季会优先展示。</p>
            </div>
          </div>
          <div class="alert alert-secondary mb-0">当前筛选口径下，这支战队还没有已完成补录的比赛成绩。</div>
        </section>
        """

    grouped_matches: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for match in completed_matches:
        scope_key = (
            get_match_competition_name(match),
            str(match.get("season") or "").strip(),
        )
        grouped_matches.setdefault(scope_key, []).append(match)

    def scope_sort_key(item: tuple[tuple[str, str], list[dict[str, Any]]]) -> tuple[int, int, int, str, str]:
        (competition_name, season_name), matches = item
        status = get_team_season_status(
            data,
            {
                "competition_name": competition_name,
                "season_name": season_name,
            },
        )
        latest_played_on = max(
            (str(match.get("played_on") or "").strip() for match in matches),
            default="",
        )
        latest_match_day = parse_match_day(latest_played_on)
        return (
            get_team_season_status_rank(status),
            0 if (competition_name, season_name) == (selected_competition, selected_season) else 1,
            -(latest_match_day.toordinal() if latest_match_day else 0),
            competition_name,
            season_name,
        )

    scope_sections: list[str] = []
    for (competition_name, season_name), matches in sorted(
        grouped_matches.items(),
        key=scope_sort_key,
        reverse=False,
    ):
        status = get_team_season_status(
            data,
            {
                "competition_name": competition_name,
                "season_name": season_name,
            },
        )
        scope_path = build_scoped_path(
            f"/teams/{team_id}",
            competition_name,
            season_name,
        )
        match_rows_html: list[str] = []
        for match_index, match in enumerate(sorted(
            matches,
            key=lambda item: (
                item["played_on"],
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
            reverse=True,
        )):
            summary = summarize_team_match(team_id, match, team_lookup)
            participant_rows: list[str] = []
            for participant in sorted(
                [
                    entry
                    for entry in match["players"]
                    if str(entry.get("team_id") or "").strip() == team_id
                ],
                key=lambda entry: (
                    int(entry.get("seat") or 0),
                    str(entry.get("player_id") or ""),
                ),
            ):
                player_id = str(participant.get("player_id") or "").strip()
                player = player_lookup.get(player_id)
                player_name = (
                    str(player.get("display_name") or "").strip()
                    if player
                    else str(participant.get("player_name") or player_id or "未命名队员").strip()
                )
                stance_result = normalize_stance_result(participant)
                participant_rows.append(
                    f"""
                    <tr>
                      <td>{int(participant.get('seat') or 0)}</td>
                      <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + player_id, competition_name, season_name))}">{escape(player_name)}</a></td>
                      <td>{escape(str(participant.get('role') or '未填写'))}</td>
                      <td>{escape(to_chinese_camp(str(participant.get('camp') or '')) or '未填写')}</td>
                      <td>{escape(RESULT_OPTIONS.get(str(participant.get('result') or ''), str(participant.get('result') or '未填写')))}</td>
                      <td>{escape(STANCE_OPTIONS.get(stance_result, stance_result))}</td>
                      <td>{float(participant.get('points_earned') or 0.0):.2f}</td>
                    </tr>
                    """
                )
            team_page_path = build_scoped_path(
                f"/teams/{team_id}",
                competition_name,
                season_name,
            )
            match_detail_path = (
                f"/matches/{match['match_id']}?next="
                f"{quote(team_page_path)}"
            )
            item_classes = "py-2"
            if match_index > 0:
                item_classes += " border-top"
            match_rows_html.append(
                f"""
                <li class="{item_classes} list-unstyled">
                  <div class="d-flex flex-column flex-xl-row justify-content-between align-items-xl-center gap-2 mb-2">
                    <div>
                      <div class="fw-semibold">{escape(summary['match_id'])}</div>
                      <div class="small text-secondary">{escape(summary['played_on'])} · {escape(summary['stage'])} · 第 {summary['round']} 轮 · {escape(summary['table_label'])}</div>
                    </div>
                    <div class="d-flex flex-wrap gap-2">
                      <span class="chip">{escape(summary['winning_camp'])}</span>
                      <span class="chip">本队 {summary['team_score']:.2f}</span>
                      <span class="chip">另一方 {summary['opponent_score']:.2f}</span>
                      <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">比赛详情</a>
                    </div>
                  </div>
                  <div class="table-responsive compact-list-wrap">
                    <table class="table table-sm align-middle mb-0">
                      <thead>
                        <tr>
                          <th>座位</th>
                          <th>队员</th>
                          <th>角色</th>
                          <th>阵营</th>
                          <th>结果</th>
                          <th>站边</th>
                          <th>得分</th>
                        </tr>
                      </thead>
                      <tbody>{''.join(participant_rows) or '<tr><td colspan="7" class="text-secondary">当前还没有这支战队的队员成绩明细。</td></tr>'}</tbody>
                    </table>
                  </div>
                </li>
                """
            )
        scope_sections.append(
            f"""
            <div class="compact-scope-block">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-2">
                <div>
                  <h3 class="h5 mb-2">{escape(competition_name)} · {escape(season_name or '未命名赛季')}</h3>
                  <p class="section-copy mb-0">{escape(get_team_season_status_label(status))} · 已完成补录 {len(matches)} 场比赛。</p>
                </div>
                <a class="btn btn-outline-dark" href="{escape(scope_path)}">切换到这个赛季</a>
              </div>
              <ul class="list-unstyled mb-0">{''.join(match_rows_html)}</ul>
            </div>
            """
        )

    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队比赛队员成绩</h2>
          <p class="section-copy mb-0">这里只展示已完成补录的比赛，按赛季状态排序，进行中的赛季优先展示。</p>
        </div>
      </div>
      <div>{''.join(scope_sections)}</div>
    </section>
    """


def build_ai_team_season_summary_prompt(
    team: dict[str, Any],
    competition_name: str,
    season_name: str,
    team_row: dict[str, Any],
    roster_rows: list[dict[str, Any]],
    season_team_rows: list[dict[str, Any]],
    recent_matches: list[dict[str, Any]],
) -> str:
    prompt_templates = load_ai_prompt_templates()
    roster_lines = [
        f"- {row['display_name']} | 出场 {row['games_played']} | 战绩 {row['record']} | "
        f"总积分 {float(row['points_earned_total']):.2f} | 场均 {float(row['average_points']):.2f} | 胜率 {format_pct(row['win_rate'])}"
        for row in roster_rows[:12]
    ]
    team_board_lines = [
        f"- 第{row.get('points_rank', '-')}名 {row['name']} | 场次 {row['matches_represented']} | "
        f"上场队员 {row['player_count']} | 总积分 {float(row['points_earned_total']):.2f} | 胜率 {format_pct(row['win_rate'])}"
        for row in season_team_rows[:10]
    ]
    recent_match_lines = [
        f"- {item['played_on']} | {competition_name} / {season_name} | {item['stage']} | 第 {item['round']} 轮 | "
        f"对手 {item['opponents']} | 台次 {item['table_label']} | 胜利阵营 {item['winning_camp']} | "
        f"本队 {float(item['team_score']):.2f} : 对手 {float(item['opponent_score']):.2f}"
        for item in recent_matches[:12]
    ]
    return render_ai_prompt_template(
        prompt_templates["team_season_summary_user_prompt"],
        {
            "team_name": team.get("name") or team.get("team_id") or "未知战队",
            "competition_name": competition_name,
            "season_name": season_name,
            "rank": team_row.get("points_rank", "-"),
            "player_count": team_row.get("player_count", 0),
            "matches_represented": team_row.get("matches_represented", 0),
            "points_total": f"{float(team_row.get('points_earned_total', 0.0)):.2f}",
            "points_per_match": f"{float(team_row.get('points_per_match', 0.0)):.2f}",
            "win_rate": format_pct(team_row.get("win_rate", 0.0)),
            "stance_rate": format_pct(team_row.get("stance_rate", 0.0)),
            "season_team_board": "\n".join(team_board_lines) if team_board_lines else "- 当前赛季暂无战队积分榜数据",
            "roster_board": "\n".join(roster_lines) if roster_lines else "- 当前赛季暂无队员战绩数据",
            "recent_matches": "\n".join(recent_match_lines) if recent_match_lines else "- 当前赛季暂无比赛明细",
        },
        "战队赛季总结用户提示词模板",
    )


def generate_ai_team_season_summary(
    team: dict[str, Any],
    competition_name: str,
    season_name: str,
    team_row: dict[str, Any],
    roster_rows: list[dict[str, Any]],
    season_team_rows: list[dict[str, Any]],
    recent_matches: list[dict[str, Any]],
) -> tuple[str, str]:
    settings = load_ai_daily_brief_settings()
    prompt_templates = load_ai_prompt_templates()
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or DEFAULT_AI_DAILY_BRIEF_MODEL).strip() or DEFAULT_AI_DAILY_BRIEF_MODEL
    if not base_url or not api_key:
        raise ValueError("AI 战队赛季总结尚未配置 Base URL 或 API Key。")
    report_text = request_openai_compatible_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=prompt_templates["team_season_summary_system_prompt"],
        user_prompt=build_ai_team_season_summary_prompt(
            team,
            competition_name,
            season_name,
            team_row,
            roster_rows,
            season_team_rows,
            recent_matches,
        ),
    )
    return report_text, model


def build_guild_honor_rows(data: dict[str, Any], guild_id: str) -> list[dict[str, str]]:
    guild = get_guild_by_id(data, guild_id)
    if not guild:
        return []
    honors: list[dict[str, str]] = []
    for item in guild.get("honors", []) or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        team_name = str(item.get("team_name") or "").strip()
        scope = str(item.get("scope") or "").strip()
        if not title or not team_name or not scope:
            continue
        honors.append({"title": title, "team_name": team_name, "scope": scope})
    honors.sort(key=lambda item: (item["scope"], item["title"], item["team_name"]), reverse=True)
    return honors


def get_guilds_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    from web.features.guilds import get_guilds_page as impl

    return impl(ctx, alert, form_values)



def get_guild_page(ctx: RequestContext, guild_id: str, alert: str = "") -> str:
    from web.features.guilds import get_guild_page as impl

    return impl(ctx, guild_id, alert)



def handle_guilds(ctx: RequestContext, start_response):
    from web.features.guilds import handle_guilds as impl

    return impl(ctx, start_response)


def handle_guilds_api(ctx: RequestContext, start_response):
    from web.features.guilds import handle_guilds_api as impl

    return impl(ctx, start_response)


def get_guild_frontend_page(ctx: RequestContext, guild_id: str) -> str:
    from web.features.guilds import build_guild_frontend_page as impl

    return impl(ctx, guild_id)


def get_guild_legacy_page(ctx: RequestContext, guild_id: str, alert: str = "") -> str:
    from web.features.guilds import get_guild_legacy_page as impl

    return impl(ctx, guild_id, alert)


def handle_guild_api(ctx: RequestContext, start_response, guild_id: str):
    from web.features.guilds import handle_guild_api as impl

    return impl(ctx, start_response, guild_id)


def handle_guild_page(ctx: RequestContext, start_response, guild_id: str):
    from web.features.guilds import handle_guild_page as impl

    return impl(ctx, start_response, guild_id)


def build_ai_player_season_summary_prompt(
    player_name: str,
    competition_name: str,
    season_name: str,
    detail: dict[str, Any],
    player_row: dict[str, Any],
    season_player_rows: list[dict[str, Any]],
    season_team_rows: list[dict[str, Any]],
) -> str:
    prompt_templates = load_ai_prompt_templates()
    role_lines = [
        f"- {item['role']}：{item['games']} 局"
        for item in detail.get("roles", [])
    ]
    recent_match_lines = [
        f"- {item['played_on']} | {item['competition_name']} / {item['season']} | {item['stage_label']} | "
        f"第 {item['round']} 轮 | 角色 {item['role']} | 阵营 {item['camp_label']} | "
        f"结果 {item['result_label']} | 站边 {item['stance_result_label']} | 积分 {float(item['points_earned']):.2f}"
        for item in detail.get("history", [])[:12]
    ]
    player_board_lines = [
        f"- 第{row['rank']}名 {row['display_name']} | {row['team_name']} | 出场 {row['games_played']} | "
        f"战绩 {row['record']} | 总积分 {float(row['points_earned_total']):.2f} | 场均 {float(row['average_points']):.2f}"
        for row in season_player_rows[:10]
    ]
    team_board_lines = [
        f"- 第{row.get('points_rank', '-')}名 {row['name']} | 场次 {row['matches_represented']} | "
        f"总积分 {float(row['points_earned_total']):.2f} | 胜率 {format_pct(row['win_rate'])}"
        for row in season_team_rows[:8]
    ]
    return render_ai_prompt_template(
        prompt_templates["player_season_summary_user_prompt"],
        {
            "player_name": player_name,
            "team_name": detail.get("team_name") or player_row.get("team_name") or "未知战队",
            "competition_name": competition_name,
            "season_name": season_name,
            "rank": player_row.get("rank", "-"),
            "games_played": player_row.get("games_played", 0),
            "record": detail.get("record") or player_row.get("record") or "0-0",
            "overall_win_rate": detail.get("overall_win_rate") or format_pct(player_row.get("win_rate", 0.0)),
            "villagers_win_rate": detail.get("villagers_win_rate") or format_pct(player_row.get("villagers_win_rate", 0.0)),
            "werewolves_win_rate": detail.get("werewolves_win_rate") or format_pct(player_row.get("werewolves_win_rate", 0.0)),
            "points_total": detail.get("points_total") or f"{float(player_row.get('points_earned_total', 0.0)):.2f}",
            "average_points": detail.get("average_points") or f"{float(player_row.get('average_points', 0.0)):.2f}",
            "stance_summary": (
                f"站对边 {detail.get('correct_stances', 0)} 次；"
                f"站错边 {detail.get('incorrect_stances', 0)} 次；"
                f"总判断 {detail.get('stance_calls', 0)} 次；"
                f"站边成功率 {detail.get('stance_rate') or format_pct(player_row.get('stance_rate', 0.0))}"
            ),
            "role_summary": "\n".join(role_lines) if role_lines else "- 暂无角色分布数据",
            "season_player_board": "\n".join(player_board_lines) if player_board_lines else "- 当前赛季暂无个人积分榜数据",
            "season_team_board": "\n".join(team_board_lines) if team_board_lines else "- 当前赛季暂无战队积分榜数据",
            "recent_matches": "\n".join(recent_match_lines) if recent_match_lines else "- 当前赛季暂无比赛明细",
        },
        "选手赛季总结用户提示词模板",
    )


def generate_ai_player_season_summary(
    player_name: str,
    competition_name: str,
    season_name: str,
    detail: dict[str, Any],
    player_row: dict[str, Any],
    season_player_rows: list[dict[str, Any]],
    season_team_rows: list[dict[str, Any]],
) -> tuple[str, str]:
    settings = load_ai_daily_brief_settings()
    prompt_templates = load_ai_prompt_templates()
    base_url = str(settings.get("base_url") or "").strip()
    api_key = str(settings.get("api_key") or "").strip()
    model = str(settings.get("model") or DEFAULT_AI_DAILY_BRIEF_MODEL).strip() or DEFAULT_AI_DAILY_BRIEF_MODEL
    if not base_url or not api_key:
        raise ValueError("AI 选手赛季总结尚未配置 Base URL 或 API Key。")
    report_text = request_openai_compatible_completion(
        base_url=base_url,
        api_key=api_key,
        model=model,
        system_prompt=prompt_templates["player_season_summary_system_prompt"],
        user_prompt=build_ai_player_season_summary_prompt(
            player_name,
            competition_name,
            season_name,
            detail,
            player_row,
            season_player_rows,
            season_team_rows,
        ),
    )
    return report_text, model


def handle_team_page(ctx: RequestContext, start_response, team_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_team_frontend_page(ctx, team_id))

    action = form_value(ctx.form, "action").strip()
    competition_name = form_value(ctx.form, "competition_name").strip()
    season_name = form_value(ctx.form, "season_name").strip()
    redirect_path = build_scoped_path(
        f"/teams/{team_id}",
        competition_name or None,
        season_name or None,
    )

    if not competition_name or not season_name:
        return redirect(
            start_response,
            append_alert_query(redirect_path, "请先切换到具体赛事和赛季，再生成 AI 战队赛季总结。"),
        )

    existing_summary = load_ai_team_season_summary(
        team_id,
        competition_name,
        season_name,
    )
    if action == "save_ai_team_season_summary":
        admin_guard = require_admin(ctx, start_response)
        if admin_guard is not None:
            return admin_guard
        summary_content = form_value(ctx.form, "summary_content").strip()
        if not summary_content:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "总结正文不能为空。"),
            )
        save_ai_team_season_summary(
            team_id,
            competition_name,
            season_name,
            summary_content,
            "管理员手动编辑",
        )
        return redirect(
            start_response,
            append_alert_query(redirect_path, "AI 战队赛季总结已保存。"),
        )

    if action != "generate_ai_team_season_summary":
        return redirect(
            start_response,
            append_alert_query(redirect_path, "未识别的操作。"),
        )

    if existing_summary and not is_admin_user(ctx.current_user):
        return redirect(
            start_response,
            append_alert_query(redirect_path, "当前总结已生成，只有管理员可以重生成。"),
        )

    data = load_validated_data()
    team_lookup = {item["team_id"]: item for item in data["teams"]}
    team = team_lookup.get(team_id)
    if not team:
        return start_response_html(
            start_response,
            "404 Not Found",
            layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx),
        )

    season_matches = [
        match
        for match in data["matches"]
        if any(str(entry.get("team_id") or "").strip() == team_id for entry in match["players"])
        and get_match_competition_name(match) == competition_name
        and str(match.get("season") or "").strip() == season_name
    ]
    if not season_matches:
        return redirect(
            start_response,
            append_alert_query(redirect_path, "当前战队在这个赛季下还没有可用于总结的比赛数据。"),
        )

    season_team_rows = [
        row
        for row in build_team_rows(data, competition_name, season_name)
        if row["matches_represented"] > 0
    ]
    season_team_rows.sort(
        key=lambda row: (
            row.get("points_rank", 9999),
            -row["points_earned_total"],
            row["name"],
        )
    )
    team_row = next((row for row in season_team_rows if row["team_id"] == team_id), None)
    if not team_row or not team_row.get("matches_represented"):
        return redirect(
            start_response,
            append_alert_query(redirect_path, "当前战队在这个赛季下还没有可用于总结的战绩数据。"),
        )

    season_player_rows = [
        row
        for row in build_player_rows(data, competition_name, season_name)
        if row["games_played"] > 0
    ]
    roster_player_ids = set(resolve_team_player_ids(data, team_id, competition_name, season_name))
    roster_rows = [row for row in season_player_rows if row["player_id"] in roster_player_ids]
    roster_rows.sort(
        key=lambda row: (
            row.get("rank", 9999),
            -row["points_earned_total"],
            row["display_name"],
        )
    )
    recent_matches = [
        summarize_team_match(team_id, match, team_lookup)
        for match in sorted(
            season_matches,
            key=lambda item: (
                item["played_on"],
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
            reverse=True,
        )
    ]
    try:
        report_text, model = generate_ai_team_season_summary(
            team,
            competition_name,
            season_name,
            team_row,
            roster_rows,
            season_team_rows,
            recent_matches,
        )
        save_ai_team_season_summary(
            team_id,
            competition_name,
            season_name,
            report_text,
            model,
        )
    except ValueError as exc:
        return redirect(
            start_response,
            append_alert_query(redirect_path, str(exc)),
        )

    return redirect(
        start_response,
        append_alert_query(redirect_path, "AI 战队赛季总结已生成。"),
    )


def get_player_page(ctx: RequestContext, player_id: str, alert: str = "") -> str:
    data = load_validated_data()
    users = load_users()
    player_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if any(entry["player_id"] == player_id for entry in match["players"])
    ]
    player_competition_names = []
    for match in player_matches:
        competition_name = get_match_competition_name(match)
        if competition_name not in player_competition_names:
            player_competition_names.append(competition_name)

    selected_competition = get_selected_competition(ctx, player_competition_names)
    season_names = (
        list_seasons(
            {
                "matches": [
                    match
                    for match in player_matches
                    if get_match_competition_name(match) == selected_competition
                ]
            },
            selected_competition,
        )
        if selected_competition
        else []
    )
    selected_season = get_selected_season(ctx, season_names)
    competition_switcher = build_competition_switcher(
        f"/players/{player_id}", player_competition_names, selected_competition, tone="light"
    )
    season_switcher = build_season_switcher(
        f"/players/{player_id}",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
    )
    player_rows = build_player_rows(data, selected_competition, selected_season)
    row_lookup = {row["player_id"]: row for row in player_rows}
    player_details = build_player_details(
        data, player_rows, selected_competition, selected_season
    )
    detail = player_details.get(player_id)
    if not detail:
        return layout("未找到队员", '<div class="alert alert-danger">没有找到对应的队员。</div>', ctx)

    players = {player["player_id"]: player for player in data["players"]}
    player = players[player_id]
    owner_user = get_user_by_player_id(users, player_id)
    player_row = row_lookup[player_id]
    team_id = player_row["team_id"]
    aliases = "、".join(detail["aliases"]) if detail["aliases"] else "无"
    photo_html = build_player_photo_html(detail["photo"], detail["display_name"])
    manage_buttons: list[str] = []
    if ctx.current_user and ctx.current_user.get("player_id") == player_id:
        manage_buttons.append('<a class="btn btn-light text-dark shadow-sm" href="/profile">编辑我的资料</a>')
    elif can_manage_player(ctx, player_id):
        manage_buttons.append(
            f'<a class="btn btn-light text-dark shadow-sm" '
            f'href="/players/{escape(player_id)}/edit?{urlencode({"next": build_scoped_path("/players/" + player_id, selected_competition, selected_season)})}">编辑队员资料</a>'
        )
    if ctx.current_user and can_manage_player_bindings(data, ctx.current_user, owner_user, player):
        binding_query = {"player_id": player_id}
        if owner_user:
            binding_query["username"] = owner_user["username"]
        manage_buttons.append(
            f'<a class="btn btn-outline-light text-dark shadow-sm" href="/bindings?{urlencode(binding_query)}">管理赛事绑定</a>'
        )
    manage_button_row = (
        f'<div class="d-flex flex-wrap gap-2 mt-3">{"".join(manage_buttons)}</div>' if manage_buttons else ""
    )
    season_chip = f'<span class="chip">{escape(selected_season)}</span>' if selected_season else ""
    player_team_path = build_scoped_path("/teams/" + team_id, selected_competition, selected_season)
    overall_win_width = max(0.0, min(100.0, float(player_row.get("win_rate", 0.0)) * 100.0))
    villagers_win_width = max(0.0, min(100.0, float(player_row.get("villagers_win_rate", 0.0)) * 100.0))
    werewolves_win_width = max(0.0, min(100.0, float(player_row.get("werewolves_win_rate", 0.0)) * 100.0))
    role_total = sum(item["games"] for item in detail["roles"])

    role_cards_html = "".join(
        f"""
        <article class="player-role-card">
          <div class="player-role-top">
            <div>
              <div class="player-role-name">{escape(item["role"])}</div>
              <div class="player-role-meta">当前口径下共登场 {item["games"]} 局</div>
            </div>
            <div class="player-role-count">{item["games"]} 局</div>
          </div>
          <div class="player-role-track">
            <div class="player-role-fill" style="width: {safe_rate(item['games'], role_total) * 100:.1f}%"></div>
          </div>
          <div class="player-role-share">角色占比 {format_pct(safe_rate(item["games"], role_total))}</div>
        </article>
        """
        for item in detail["roles"][:6]
    ) or """
        <article class="player-role-card">
          <div class="player-role-name">暂无角色记录</div>
          <div class="player-role-meta mt-2">当前筛选范围内还没有可展示的角色分布数据。</div>
        </article>
    """

    season_cards_html = "".join(
        f"""
        <article class="player-season-card">
          <div class="player-season-top">
            <div>
              <div class="player-season-name">{escape(item["season_name"])}</div>
              <div class="player-season-meta">{escape(item["competition_name"])}</div>
            </div>
            <div class="player-season-points">{escape(item["points_total"])} 分</div>
          </div>
          <div class="player-season-stats">
            <span class="player-stat-pill">出场 {item["games_played"]}</span>
            <span class="player-stat-pill">战绩 {escape(item["record"])}</span>
            <span class="player-stat-pill">总胜率 {escape(item["overall_win_rate"])}</span>
            <span class="player-stat-pill">场均 {escape(item["average_points"])}</span>
          </div>
        </article>
        """
        for item in detail["season_stats"][:4]
    ) or """
        <article class="player-season-card">
          <div class="player-season-name">暂无赛季切片</div>
          <div class="player-season-meta mt-2">当前筛选范围内还没有形成可展示的小赛季统计。</div>
        </article>
    """

    recent_match_cards: list[str] = []
    for item in detail["history"][:4]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/players/' + player_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/players/" + player_id, selected_competition, selected_season),
        )
        result_class = ""
        if item["result_label"] == "胜利":
            result_class = " is-win"
        elif item["result_label"] == "失利":
            result_class = " is-loss"
        award_pills = "".join(
            f'<span class="player-stat-pill">{escape(label)}</span>'
            for label in item.get("award_labels", [])
        ) or '<span class="player-stat-pill">无特殊奖励</span>'
        recent_match_cards.append(
            f"""
            <article class="player-match-card">
              <div class="player-match-top">
                <div>
                  <div class="player-match-name">{escape(item["competition_name"])}</div>
                  <div class="player-match-meta">{escape(item["season"])} · {escape(item["stage_label"])} · 第 {item["round"]} 轮 · {escape(item["played_on"])}</div>
                </div>
                <span class="player-match-result{result_class}">{escape(item["result_label"])}</span>
              </div>
              <div class="player-match-tags">
                <span class="player-stat-pill">得分 {item["points_earned"]:.2f}</span>
                {award_pills}
              </div>
              <div class="player-match-actions">
                <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">比赛详情</a>
                <a class="btn btn-sm btn-light border" href="{escape(day_path)}">当日赛程</a>
              </div>
            </article>
            """
        )
    recent_match_cards_html = "".join(recent_match_cards) or """
        <article class="player-match-card">
          <div class="player-match-name">暂无近期比赛</div>
          <div class="player-match-meta mt-2">当前筛选范围内还没有可展示的对局记录。</div>
        </article>
    """

    history_rows = []
    for item in detail["history"]:
        match_detail_path = (
            f"/matches/{item['match_id']}?next="
            f"{quote(build_scoped_path('/players/' + player_id, selected_competition, selected_season))}"
        )
        day_path = build_match_day_path(
            item["played_on"],
            build_scoped_path("/players/" + player_id, selected_competition, selected_season),
        )
        history_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(item['played_on'])}</a></td>
              <td>{escape(item['season'])}</td>
              <td>{escape(item['stage_label'])}</td>
              <td>第 {item['round']} 轮</td>
              <td>{escape(item['role'])}</td>
              <td>{escape(item['camp_label'])}</td>
              <td>{escape(item['result_label'])}</td>
              <td>{escape(item['stance_result_label'])}</td>
              <td>{item['points_earned']:.2f}</td>
              <td>{escape(item['notes'] or '无')}</td>
              <td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看比赛</a></td>
            </tr>
            """
        )

    season_rows = []
    for item in detail["season_stats"]:
        season_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td>{escape(item['season_name'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['record'])}</td>
              <td>{escape(item['overall_win_rate'])}</td>
              <td>{escape(item['villagers_win_rate'])}</td>
              <td>{escape(item['werewolves_win_rate'])}</td>
              <td>{escape(item['points_total'])}</td>
              <td>{escape(item['average_points'])}</td>
            </tr>
            """
        )
    season_detail_section = (
        f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">完整赛季明细</h2>
          <p class="section-copy mb-0">这里保留完整表格，方便继续核对每个小赛季的胜率和积分口径。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>赛季</th>
              <th>出场</th>
              <th>战绩</th>
              <th>总胜率</th>
              <th>好人胜率</th>
              <th>狼人胜率</th>
              <th>总积分</th>
              <th>场均得分</th>
            </tr>
          </thead>
          <tbody>
            {''.join(season_rows) or '<tr><td colspan="9" class="text-secondary">当前统计口径下暂无赛季胜率数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    """
        if len(detail["season_stats"]) > 1
        else ""
    )
    competition_detail_section = ""
    player_dimension_panel = build_player_dimension_panel(
        ctx,
        data,
        player_id,
        selected_competition,
        selected_season,
    )
    ai_player_season_summary = (
        load_ai_player_season_summary(player_id, selected_competition, selected_season)
        if selected_competition and selected_season
        else None
    )
    ai_settings = load_ai_daily_brief_settings()
    ai_configured = bool(ai_settings.get("base_url") and ai_settings.get("api_key"))
    ai_player_summary_actions = ""
    ai_player_summary_admin_editor = ""
    if selected_competition and selected_season:
        if ai_configured and (not ai_player_season_summary or is_admin_user(ctx.current_user)):
            ai_player_summary_actions = f"""
            <form method="post" action="/players/{escape(player_id)}" class="m-0">
              <input type="hidden" name="action" value="generate_ai_player_season_summary">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season)}">
              <button type="submit" class="btn btn-dark">{'重生成 AI 选手赛季总结' if ai_player_season_summary else '生成 AI 选手赛季总结'}</button>
            </form>
            """
        elif not ai_configured and is_admin_user(ctx.current_user):
            ai_player_summary_actions = '<a class="btn btn-outline-dark" href="/accounts">前往账号管理配置 AI 接口</a>'
        if ai_player_season_summary and is_admin_user(ctx.current_user):
            ai_player_summary_admin_editor = f"""
            <div class="form-panel p-3 p-lg-4 mt-4">
              <h3 class="h5 mb-2">管理员编辑总结</h3>
              <p class="section-copy mb-3">可以直接修改当前总结正文。保存后会立即覆盖展示内容。</p>
              <form method="post" action="/players/{escape(player_id)}">
                <input type="hidden" name="action" value="save_ai_player_season_summary">
                <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
                <input type="hidden" name="season_name" value="{escape(selected_season)}">
                <div class="mb-3">
                  <textarea class="form-control" name="summary_content" rows="12">{escape(ai_player_season_summary.get('content') or '')}</textarea>
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-outline-dark">保存人工编辑</button>
                </div>
              </form>
            </div>
            """
    ai_player_summary_panel = ""
    if selected_season:
        ai_player_summary_panel = (
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">AI 选手赛季总结</h2>
                  <p class="section-copy mb-0">基于当前选手在这个赛事赛季下的真实战绩、角色分布和比赛记录生成总结。首次生成对所有访客开放；生成后仅管理员可重生成或编辑。</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_player_summary_actions}</div>
              </div>
              <div class="small text-secondary mb-3">生成时间 {escape(ai_player_season_summary.get('generated_at') or '未生成')} · 模型 {escape(ai_player_season_summary.get('model') or ai_settings.get('model') or DEFAULT_AI_DAILY_BRIEF_MODEL)}</div>
              <div class="editorial-copy mb-0">{render_ai_daily_brief_html(ai_player_season_summary.get('content') or '')}</div>
              {ai_player_summary_admin_editor}
            </section>
            """
            if ai_player_season_summary
            else f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3">
                <div>
                  <h2 class="section-title mb-2">AI 选手赛季总结</h2>
                  <p class="section-copy mb-0">{escape('当前赛季还没有生成 AI 总结，首次生成对所有访客开放。' if ai_configured else '当前还没有配置 AI 接口。配置后即可在这里生成选手赛季总结。')}</p>
                </div>
                <div class="d-flex flex-wrap gap-2">{ai_player_summary_actions}</div>
              </div>
            </section>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="row g-4 align-items-center">
        <div class="col-12 col-lg-4 col-xl-3">
          {photo_html}
        </div>
        <div class="col-12 col-lg-8 col-xl-9">
          <div class="eyebrow mb-3">队员个人页面</div>
          <h1 class="display-6 fw-semibold mb-3">{escape(detail['display_name'])}</h1>
          <p class="mb-2 opacity-75">{escape(detail['team_name'])} · 当前排名第 {detail['rank']} 名</p>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
          {f'<div class="d-flex flex-wrap gap-2 mt-3">{season_switcher}</div>' if season_switcher else ''}
          {manage_button_row}
          <div class="d-flex flex-wrap gap-3 mt-5 pt-1">
            {season_chip}
            <span class="chip">战绩 {escape(detail['record'])}</span>
            <span class="chip">总胜率 {escape(detail['overall_win_rate'])}</span>
            <span class="chip">好人胜率 {escape(detail['villagers_win_rate'])}</span>
            <span class="chip">狼人胜率 {escape(detail['werewolves_win_rate'])}</span>
            <span class="chip">总积分 {escape(detail['points_total'])}</span>
          </div>
        </div>
      </div>
    </section>
    {player_dimension_panel}
    {ai_player_summary_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">选手数据档案</h2>
          <p class="section-copy mb-0">先用一屏把这位选手的状态、特征和近期走势讲清楚，下面再接完整明细表。</p>
        </div>
      </div>
      <div class="player-showcase-grid">
        <article class="player-showcase-card">
          <div class="player-masthead">
            <div class="player-masthead-copy">
              <div class="eyebrow">Player Dossier</div>
              <div class="player-headline">{escape(detail['display_name'])}</div>
              <div class="player-subtitle">{escape(detail['team_name'])} · 当前排名第 {detail['rank']} 名 · 战绩 {escape(detail['record'])}</div>
              <div class="player-masthead-meta">
                <span class="player-badge">总出场 {detail['games_played']}</span>
                <span class="player-badge">总积分 {escape(detail['points_total'])}</span>
                <span class="player-badge">场均 {escape(detail['average_points'])}</span>
              </div>
            </div>
          </div>
          <div class="player-kpi-grid">
            <div class="player-kpi-card">
              <div class="player-kpi-label">Current Team</div>
              <div class="player-kpi-value"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(player_team_path)}">{escape(detail['team_name'])}</a></div>
              <div class="player-kpi-copy">按当前赛事筛选口径归属战队</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Total Games</div>
              <div class="player-kpi-value">{detail['games_played']}</div>
              <div class="player-kpi-copy">当前范围内已录入对局数</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Win Rate</div>
              <div class="player-kpi-value">{escape(detail['overall_win_rate'])}</div>
              <div class="player-kpi-copy">综合胜率表现</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Avg Points</div>
              <div class="player-kpi-value">{escape(detail['average_points'])}</div>
              <div class="player-kpi-copy">单局积分产出效率</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Points Total</div>
              <div class="player-kpi-value">{escape(detail['points_total'])}</div>
              <div class="player-kpi-copy">累计积分沉淀</div>
            </div>
            <div class="player-kpi-card">
              <div class="player-kpi-label">Stance Calls</div>
              <div class="player-kpi-value">{detail['correct_stances']} / {detail['stance_calls']}</div>
              <div class="player-kpi-copy">站边判断命中次数</div>
            </div>
          </div>
        </article>
        <aside class="player-insight-card">
          <div>
            <h3 class="section-title mb-2">核心能力观察</h3>
            <p class="section-copy mb-0">把几条最关键的指标抽出来，方便一眼看出这名选手更偏稳定型、进攻型还是阵营特化型。</p>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>综合胜率</strong>
              <span>{escape(detail['overall_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {overall_win_width:.1f}%"></div></div>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>好人胜率</strong>
              <span>{escape(detail['villagers_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {villagers_win_width:.1f}%"></div></div>
          </div>
          <div class="player-skill-row">
            <div class="player-skill-head">
              <strong>狼人胜率</strong>
              <span>{escape(detail['werewolves_win_rate'])}</span>
            </div>
            <div class="player-skill-track"><div class="player-skill-fill" style="width: {werewolves_win_width:.1f}%"></div></div>
          </div>
          <div class="player-note-grid">
            <div class="player-note-item">
              <div class="player-note-label">Aliases</div>
              <div class="player-note-value">{escape(aliases)}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Joined</div>
              <div class="player-note-value">{escape(detail['joined_on'])}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Profile Status</div>
              <div class="player-note-value">{escape('已配置头像资料' if detail['photo'] else '使用默认头像')}</div>
            </div>
            <div class="player-note-item">
              <div class="player-note-label">Notes</div>
              <div class="player-note-value">{escape(detail['notes'] or '暂无补充备注')}</div>
            </div>
          </div>
        </aside>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">角色画像</h2>
              <p class="section-copy mb-0">不是只显示几个标签，而是直接看出这个人最常站在哪些位置。</p>
            </div>
          </div>
          <div class="player-roles-grid">{role_cards_html}</div>
        </div>
        <div class="col-12 col-xl-6">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">最近四场</h2>
              <p class="section-copy mb-0">用最近对局做一个趋势窗口，刷新时不用先翻整张长表。</p>
            </div>
          </div>
          <div class="player-match-grid">{recent_match_cards_html}</div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">赛季切片</h2>
      <p class="section-copy mb-3">当前球员档案按赛季独立建档，所以这里只看这个赛季身份下的阶段表现，不做跨赛事合并。</p>
      <div class="player-season-grid">{season_cards_html}</div>
    </section>
    {season_detail_section}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">角色标签摘要</h2>
      <p class="section-copy mb-3">如果你只想快速扫一眼角色池，也可以直接看这组简洁标签。</p>
      <div class="d-flex flex-wrap gap-2">
        {"".join(f'<span class="chip">{escape(item["role"])} {item["games"]} 局</span>' for item in detail["roles"]) or '<span class="chip">暂无角色记录</span>'}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">全部比赛记录</h2>
          <p class="section-copy mb-0">完整对局明细继续保留在这里，方便你往下查到具体每一盘。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>日期</th>
              <th>赛季</th>
              <th>阶段</th>
              <th>轮次</th>
              <th>角色</th>
              <th>阵营</th>
              <th>结果</th>
              <th>站边</th>
              <th>得分</th>
              <th>备注</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {''.join(history_rows)}
          </tbody>
        </table>
      </div>
    </section>
    """
    return layout(f"{detail['display_name']} 页面", body, ctx, alert=alert)


def handle_player_page(ctx: RequestContext, start_response, player_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_player_frontend_page(ctx, player_id))

    action = form_value(ctx.form, "action").strip()
    competition_name = form_value(ctx.form, "competition_name").strip()
    season_name = form_value(ctx.form, "season_name").strip()
    redirect_path = build_scoped_path(
        f"/players/{player_id}",
        competition_name or None,
        season_name or None,
    )

    if not competition_name or not season_name:
        return redirect(
            start_response,
            append_alert_query(redirect_path, "请先切换到具体赛事和赛季，再生成 AI 选手赛季总结。"),
        )

    existing_summary = load_ai_player_season_summary(
        player_id,
        competition_name,
        season_name,
    )
    if action == "save_ai_player_season_summary":
        admin_guard = require_admin(ctx, start_response)
        if admin_guard is not None:
            return admin_guard
        summary_content = form_value(ctx.form, "summary_content").strip()
        if not summary_content:
            return redirect(
                start_response,
                append_alert_query(redirect_path, "总结正文不能为空。"),
            )
        save_ai_player_season_summary(
            player_id,
            competition_name,
            season_name,
            summary_content,
            "管理员手动编辑",
        )
        return redirect(
            start_response,
            append_alert_query(redirect_path, "AI 选手赛季总结已保存。"),
        )

    if action != "generate_ai_player_season_summary":
        return redirect(
            start_response,
            append_alert_query(redirect_path, "未识别的操作。"),
        )

    if existing_summary:
        if not is_admin_user(ctx.current_user):
            return redirect(
                start_response,
                append_alert_query(redirect_path, "当前总结已生成，只有管理员可以重生成。"),
            )

    data = load_validated_data()
    player_matches = [
        match
        for match in data["matches"]
        if any(entry["player_id"] == player_id for entry in match["players"])
        and get_match_competition_name(match) == competition_name
        and str(match.get("season") or "").strip() == season_name
    ]
    if not player_matches:
        return redirect(
            start_response,
            append_alert_query(redirect_path, "当前选手在这个赛季下还没有可用于总结的比赛数据。"),
        )

    season_player_rows = build_player_rows(data, competition_name, season_name)
    player_row = next((row for row in season_player_rows if row["player_id"] == player_id), None)
    if not player_row or not player_row.get("games_played"):
        return redirect(
            start_response,
            append_alert_query(redirect_path, "当前选手在这个赛季下还没有可用于总结的战绩数据。"),
        )

    player_details = build_player_details(data, season_player_rows, competition_name, season_name)
    detail = player_details.get(player_id)
    player = next((item for item in data["players"] if item["player_id"] == player_id), None)
    if not detail or not player:
        return redirect(
            start_response,
            append_alert_query(redirect_path, "没有找到对应的选手资料。"),
        )

    season_team_rows = [
        row
        for row in build_team_rows(data, competition_name, season_name)
        if row["matches_represented"] > 0
    ]
    season_team_rows.sort(
        key=lambda row: (
            row.get("points_rank", 9999),
            -row["points_earned_total"],
            row["name"],
        )
    )
    try:
        report_text, model = generate_ai_player_season_summary(
            player.get("display_name") or player_id,
            competition_name,
            season_name,
            detail,
            player_row,
            season_player_rows,
            season_team_rows,
        )
        save_ai_player_season_summary(
            player_id,
            competition_name,
            season_name,
            report_text,
            model,
        )
    except ValueError as exc:
        return redirect(
            start_response,
            append_alert_query(redirect_path, str(exc)),
        )

    return redirect(
        start_response,
        append_alert_query(redirect_path, "AI 选手赛季总结已生成。"),
    )


def build_player_edit_form(
    player: dict[str, Any],
    action_url: str,
    submit_label: str,
    account_display_name: str = "",
    account_province_name: str = DEFAULT_PROVINCE_NAME,
    account_region_name: str = "广州市",
    account_gender: str = "prefer_not_to_say",
    account_bio: str = "",
    username: str = "",
    password_note: str = "",
    show_account_fields: bool = False,
    player_section_copy: str = "可以修改队员名称、别名、备注，并上传新的队员照片。",
    photo_field_label: str = "上传照片",
    photo_help_text: str = "支持 PNG、JPG、JPEG、WEBP、GIF、SVG，大小不超过 5 MB。",
    photo_preview_path: str = "",
    photo_preview_name: str = "",
    photo_preview_path_label: str = "当前照片路径",
) -> str:
    aliases_value = "、".join(player.get("aliases", []))
    current_photo_path = photo_preview_path or str(player.get("photo") or DEFAULT_PLAYER_PHOTO)
    current_photo_name = photo_preview_name or str(player.get("display_name") or "")
    account_fields = ""
    if show_account_fields:
        account_fields = f"""
        <div class="col-12 col-xl-6">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h2 class="section-title mb-2">账号资料</h2>
            <p class="section-copy mb-4">这里可以维护登录账号本身的信息。{escape(password_note)}</p>
            <div class="mb-3">
              <label class="form-label">用户名</label>
              <input class="form-control" value="{escape(username)}" disabled>
            </div>
            <div class="mb-3">
              <label class="form-label">账号显示名称</label>
              <input class="form-control" name="account_display_name" value="{escape(account_display_name)}">
            </div>
            <div class="mb-3">
              <label class="form-label">所在地区</label>
              {build_region_picker(account_province_name, account_region_name, username or 'profile-account', '先选择省份，再选择城市。')}
            </div>
            <div class="mb-3">
              <label class="form-label">性别</label>
              <select class="form-select" name="gender">
                {option_tags(GENDER_OPTIONS, account_gender)}
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">自我介绍</label>
              <textarea class="form-control" name="bio" rows="4" placeholder="例如：擅长发言组织、偏好赛事数据复盘。">{escape(account_bio)}</textarea>
            </div>
            <div class="mb-3">
              <label class="form-label">新密码</label>
              <input class="form-control" name="password" type="password" autocomplete="new-password">
            </div>
            <div class="mb-0">
              <label class="form-label">确认新密码</label>
              <input class="form-control" name="password_confirm" type="password" autocomplete="new-password">
            </div>
          </div>
        </div>
        """

    return f"""
    <form method="post" action="{escape(action_url)}" enctype="multipart/form-data">
      <div class="row g-4">
        {account_fields}
        <div class="col-12 {'col-xl-6' if show_account_fields else 'col-xl-7'}">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h2 class="section-title mb-2">队员资料</h2>
            <p class="section-copy mb-4">{escape(player_section_copy)}</p>
            <div class="mb-3">
              <label class="form-label">队员名称</label>
              <input class="form-control" name="player_display_name" value="{escape(player['display_name'])}">
            </div>
            <div class="mb-3">
              <label class="form-label">别名</label>
              <input class="form-control" name="aliases" value="{escape(aliases_value)}" placeholder="多个别名可用 顿号、逗号 或换行分隔">
            </div>
            <div class="mb-3">
              <label class="form-label">备注</label>
              <textarea class="form-control" name="notes" rows="4">{escape(player['notes'])}</textarea>
            </div>
            <div class="mb-0">
              <label class="form-label">{escape(photo_field_label)}</label>
              <input class="form-control" name="photo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
              <div class="small text-secondary mt-2">{escape(photo_help_text)}</div>
            </div>
          </div>
        </div>
        <div class="col-12 {'col-xl-6' if show_account_fields else 'col-xl-5'}">
          <div class="panel h-100 shadow-sm p-3 p-lg-4">
            <h2 class="section-title mb-3">当前照片预览</h2>
            <div class="mb-3">{build_player_photo_html(current_photo_path, current_photo_name)}</div>
            <div class="mb-2"><strong>{escape(photo_preview_path_label)}：</strong>{escape(current_photo_path)}</div>
            <div class="mb-2"><strong>所属战队：</strong>{escape(player['team_id'])}</div>
            <div class="mb-0"><strong>入库日期：</strong>{escape(player['joined_on'])}</div>
          </div>
        </div>
      </div>
      <div class="d-flex flex-wrap gap-2 mt-4">
        <button type="submit" class="btn btn-dark">{escape(submit_label)}</button>
      </div>
    </form>
    """


def get_profile_page(
    ctx: RequestContext,
    alert: str = "",
    account_values: dict[str, str] | None = None,
    player_values: dict[str, Any] | None = None,
    guild_form_values: dict[str, str] | None = None,
) -> str:
    from web.features.profile import get_profile_page as impl

    return impl(ctx, alert, account_values, player_values, guild_form_values)



def build_profile_binding_summary(summary: dict[str, Any]) -> str:
    competition_rows = []
    for item in summary["competition_rows"][:8]:
        competition_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td>{escape(item['team_names'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['record'])}</td>
              <td>{item['points_total']:.2f}</td>
              <td>{item['average_points']:.2f}</td>
            </tr>
            """
        )
    bound_id_chips = "".join(
        f'<span class="chip">{escape(player_id)}</span>' for player_id in summary["bound_player_ids"]
    ) or '<span class="chip">暂无</span>'
    return f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">已绑定赛事数据</h2>
          <p class="section-copy mb-0">这里会把你当前账号已绑定的多个参赛ID聚合到同一份个人数据里。</p>
        </div>
        <a class="btn btn-outline-dark" href="/bindings">管理绑定关系</a>
      </div>
      <div class="d-flex flex-wrap gap-2 mb-4">{bound_id_chips}</div>
      <div class="row g-3">
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">总出场</div><div class="stat-value mt-2">{summary['games_played']}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">战绩</div><div class="stat-value mt-2">{escape(summary['record'])}</div></div></div>
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">总积分</div><div class="stat-value mt-2">{escape(summary['points_total'])}</div></div></div>
      </div>
      <div class="table-responsive mt-4">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>涉及战队</th>
              <th>出场</th>
              <th>战绩</th>
              <th>总积分</th>
              <th>场均得分</th>
            </tr>
          </thead>
          <tbody>{''.join(competition_rows) or '<tr><td colspan="6" class="text-secondary">当前还没有可聚合的比赛数据。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """


def get_player_bindings_page(
    ctx: RequestContext,
    alert: str = "",
    target_username: str = "",
    selected_player_id: str = "",
) -> str:
    from web.features.bindings import get_player_bindings_page as impl

    return impl(ctx, alert, target_username, selected_player_id)


def get_player_edit_page(
    ctx: RequestContext,
    player_id: str,
    alert: str = "",
    player_values: dict[str, Any] | None = None,
) -> str:
    data = load_validated_data()
    player = next((item for item in data["players"] if item["player_id"] == player_id), None)
    if not player:
        return layout("未找到队员", '<div class="alert alert-danger">没有找到对应的队员。</div>', ctx)

    users = load_users()
    owner_user = get_user_by_player_id(users, player_id)
    form_player = {**player, **(player_values or {})}
    next_path = form_value(ctx.query, "next").strip() or f"/players/{player_id}"
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">管理员资料编辑</div>
      <h1 class="display-6 fw-semibold mb-3">编辑队员资料</h1>
      <p class="mb-0 opacity-75">你正在编辑 {escape(player['display_name'])} 的公开档案与照片。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        <div class="col-12 col-lg-6">
          <div class="panel h-100 shadow-sm p-3">
            <div class="mb-2"><strong>队员编号：</strong>{escape(player['player_id'])}</div>
            <div class="mb-2"><strong>所属战队：</strong>{escape(player['team_id'])}</div>
            <div class="mb-2"><strong>绑定账号：</strong>{escape(get_user_badge_label(owner_user))}</div>
            <div class="mb-0"><strong>账号显示名称：</strong>{escape(get_user_display_name_label(owner_user))}</div>
          </div>
        </div>
        <div class="col-12 col-lg-6 d-flex justify-content-lg-end align-items-start">
          <a class="btn btn-outline-dark" href="{escape(next_path)}">返回队员页面</a>
        </div>
      </div>
    </section>
    {build_player_edit_form(form_player, f"/players/{player_id}/edit?{urlencode({'next': next_path})}", "保存队员资料")}
    """
    return layout(f"编辑 {player['display_name']}", body, ctx, alert=alert)


def get_match_by_id(matches: list[dict[str, Any]], match_id: str) -> dict[str, Any] | None:
    for match in matches:
        if match["match_id"] == match_id:
            return match
    return None


def register_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
    captcha_token: str | None = None,
    captcha_prompt: str | None = None,
) -> str:
    current_form = form_values or {
        "username": "",
        "display_name": "",
        "province_name": DEFAULT_PROVINCE_NAME,
        "region_name": "广州市",
        "gender": "prefer_not_to_say",
        "bio": "",
    }
    token = captcha_token or ""
    prompt = captcha_prompt or ""
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">公开注册入口</div>
      <h1 class="display-6 fw-semibold mb-3">注册新账号</h1>
      <p class="mb-0 opacity-75">注册完成后，你可以创建自己的战队，或以队员身份加入已有战队。</p>
    </section>
    <section class="form-panel shadow-sm p-3 p-lg-4 mx-auto" style="max-width: 620px;">
      <form method="post" action="/register">
        <input type="hidden" name="captcha_token" value="{escape(token)}">
        <div class="mb-3">
          <label class="form-label">用户名</label>
          <input class="form-control" name="username" value="{escape(current_form['username'])}" autocomplete="username">
        </div>
        <div class="mb-3">
          <label class="form-label">显示名称</label>
          <input class="form-control" name="display_name" value="{escape(current_form['display_name'])}">
        </div>
        <div class="mb-3">
          <label class="form-label">所在地区</label>
          {build_region_picker(current_form['province_name'], current_form['region_name'], 'register', '登录后首页会默认显示你所在城市对应的比赛入口。')}
        </div>
        <div class="mb-3">
          <label class="form-label">性别</label>
          <select class="form-select" name="gender">
            {option_tags(GENDER_OPTIONS, current_form['gender'])}
          </select>
        </div>
        <div class="mb-3">
          <label class="form-label">自我介绍</label>
          <textarea class="form-control" name="bio" rows="4" placeholder="简单介绍一下你自己、擅长位置或参赛风格。">{escape(current_form['bio'])}</textarea>
        </div>
        <div class="mb-3">
          <label class="form-label">密码</label>
          <input class="form-control" name="password" type="password" autocomplete="new-password">
        </div>
        <div class="mb-3">
          <label class="form-label">确认密码</label>
          <input class="form-control" name="password_confirm" type="password" autocomplete="new-password">
        </div>
        <div class="mb-4">
          <label class="form-label">简单验证码：{escape(prompt)}</label>
          <input class="form-control" name="captcha_answer" inputmode="numeric">
        </div>
        <div class="d-flex flex-wrap gap-2 align-items-center">
          <button class="btn btn-dark" type="submit">完成注册</button>
          <a class="btn btn-outline-dark" href="/login">返回登录</a>
        </div>
      </form>
    </section>
    """
    return layout("注册", body, ctx, alert=alert)


def get_team_center_page(
    ctx: RequestContext,
    alert: str = "",
    create_values: dict[str, str] | None = None,
    join_values: dict[str, str] | None = None,
) -> str:
    from web.features.team_center import get_team_center_page as impl

    return impl(ctx, alert, create_values, join_values)



def get_accounts_page(
    ctx: RequestContext, alert: str = "", form_values: dict[str, str] | None = None
) -> str:
    from web.features.admin import get_accounts_page as impl

    return impl(ctx, alert, form_values)


def validate_permission_assignment(
    permission_keys: list[str],
    manager_scope_keys: list[str] | None = None,
) -> str:
    normalized_permissions = normalize_permission_keys(permission_keys)
    if len(normalized_permissions) != len(
        [str(permission_key or "").strip() for permission_key in permission_keys if str(permission_key or "").strip()]
    ):
        return "存在未识别的权限项，请刷新页面后重试。"
    normalized_scope_keys = [
        str(scope_key or "").strip()
        for scope_key in (manager_scope_keys or [])
        if str(scope_key or "").strip()
    ]
    known_scope_keys = {
        build_manager_scope_key(entry["region_name"], entry["series_slug"])
        for entry in load_series_catalog(load_validated_data())
    }
    unknown_scope_keys = [
        scope_key for scope_key in normalized_scope_keys if scope_key not in known_scope_keys
    ]
    if unknown_scope_keys:
        return "所选赛事负责人范围不存在，请刷新页面后重新勾选。"
    if any(permission_key in EVENT_SCOPE_PERMISSION_KEYS for permission_key in normalized_permissions):
        if not normalized_scope_keys:
            return "勾选赛事权限后，至少需要分配一个“地区 + 系列赛”负责范围。"
    return ""


def get_permission_control_page(
    ctx: RequestContext,
    alert: str = "",
    selected_username: str = "",
    form_values: dict[str, Any] | None = None,
) -> str:
    from web.features.admin import get_permission_control_page as impl

    return impl(ctx, alert, selected_username, form_values)


def validate_account_form(
    username: str,
    display_name: str,
    password: str,
    existing_users: list[dict[str, Any]],
    role: str = "member",
    province_name: str = "",
    region_name: str = "",
    manager_scope_keys: list[str] | None = None,
) -> str:
    if not USERNAME_PATTERN.match(username):
        return "用户名只能使用 3 到 32 位英文、数字、点、下划线或短横线，并且需以英文或数字开头。"
    error = validate_account_update_form(
        display_name,
        password,
        role,
        province_name,
        region_name,
        manager_scope_keys=manager_scope_keys,
        password_required=True,
    )
    if error:
        return error
    if any(user["username"] == username for user in existing_users):
        return "该用户名已经存在。"
    return ""


def validate_account_update_form(
    display_name: str,
    password: str,
    role: str = "member",
    province_name: str = "",
    region_name: str = "",
    manager_scope_keys: list[str] | None = None,
    password_required: bool = False,
) -> str:
    if not display_name.strip():
        return "显示名称不能为空。"
    if role not in {"member", "event_manager", "admin"}:
        return "账号类型无效。"
    normalized_province, normalized_region = normalize_user_location(
        province_name,
        region_name,
    )
    if not normalized_province or not normalized_region:
        return "请先选择省份，再选择中国大陆城市作为所在地区。"
    if password_required and len(password) < 6:
        return "密码至少需要 6 位。"
    if password and len(password) < 6:
        return "密码至少需要 6 位。"
    if role == "event_manager":
        selected_scope_keys = [str(item or "").strip() for item in (manager_scope_keys or []) if str(item or "").strip()]
        if not selected_scope_keys:
            return "请至少为赛事负责人分配一个地区系列赛管理范围。"
        known_scope_keys = {
            build_manager_scope_key(entry["region_name"], entry["series_slug"])
            for entry in load_series_catalog(load_validated_data())
        }
        unknown_scope_keys = [
            scope_key for scope_key in selected_scope_keys if scope_key not in known_scope_keys
        ]
        if unknown_scope_keys:
            return "所选赛事负责人管理范围不存在，请刷新后重新选择。"
    return ""


def validate_registration_form(
    username: str,
    display_name: str,
    province_name: str,
    region_name: str,
    gender: str,
    bio: str,
    password: str,
    password_confirm: str,
    captcha_token: str,
    captcha_answer: str,
    existing_users: list[dict[str, Any]],
) -> str:
    account_error = validate_account_form(
        username,
        display_name,
        password,
        existing_users,
        province_name=province_name,
        region_name=region_name,
    )
    if account_error:
        return account_error
    if not normalize_user_gender(gender):
        return "请选择有效的性别选项。"
    if not bio.strip():
        return "请填写自我介绍。"
    if password != password_confirm:
        return "两次输入的密码不一致。"
    if not consume_captcha(captcha_token, captcha_answer):
        return "验证码不正确或已失效，请重新输入。"
    return ""


def validate_team_creation(
    team_name: str,
    short_name: str,
    competition_name: str,
    season_name: str,
    teams: list[dict[str, Any]],
) -> str:
    if not team_name.strip():
        return "战队名称不能为空。"
    if not short_name.strip():
        return "战队简称不能为空。"
    if not competition_name.strip() or not season_name.strip():
        return "请先选择当前战队所属的赛事和赛季。"
    if any(
        team["name"] == team_name
        and str(team.get("competition_name") or "").strip() == competition_name.strip()
        and str(team.get("season_name") or "").strip() == season_name.strip()
        for team in teams
    ):
        return "同一赛事赛季内已经存在同名战队。"
    if any(
        team["short_name"] == short_name
        and str(team.get("competition_name") or "").strip() == competition_name.strip()
        and str(team.get("season_name") or "").strip() == season_name.strip()
        for team in teams
    ):
        return "同一赛事赛季内已经存在相同简称的战队。"
    return ""


def validate_guild_creation(
    name: str,
    short_name: str,
    manager_usernames: list[str],
    guilds: list[dict[str, Any]],
    users: list[dict[str, Any]],
) -> str:
    if not name.strip():
        return "门派名称不能为空。"
    if not short_name.strip():
        return "门派简称不能为空。"
    if any(guild["name"] == name for guild in guilds):
        return "门派名称已经存在。"
    if any(guild["short_name"] == short_name for guild in guilds):
        return "门派简称已经存在。"
    known_usernames = {user["username"] for user in users}
    unknown_usernames = [username for username in manager_usernames if username not in known_usernames]
    if unknown_usernames:
        return f"以下门派管理员账号不存在：{'、'.join(unknown_usernames[:3])}"
    return ""


def validate_profile_update(
    account_display_name: str,
    province_name: str,
    region_name: str,
    gender: str,
    bio: str,
    password: str,
    password_confirm: str,
    player_display_name: str = "",
) -> str:
    if not account_display_name.strip():
        return "账号显示名称不能为空。"
    normalized_province, normalized_region = normalize_user_location(
        province_name,
        region_name,
    )
    if not normalized_province or not normalized_region:
        return "请先选择省份，再选择中国大陆城市作为所在地区。"
    if not normalize_user_gender(gender):
        return "请选择有效的性别选项。"
    if not bio.strip():
        return "请填写自我介绍。"
    if player_display_name and not player_display_name.strip():
        return "队员名称不能为空。"
    if password or password_confirm:
        if len(password) < 6:
            return "新密码至少需要 6 位。"
        if password != password_confirm:
            return "两次输入的新密码不一致。"
    return ""


def append_user_player_binding(
    users: list[dict[str, Any]], username: str, player_id: str | None
) -> list[dict[str, Any]]:
    updated_users = []
    for user in users:
        if user["username"] == username:
            normalized_player_id = str(player_id or "").strip()
            existing_bound_ids = get_user_bound_player_ids(user)
            linked_player_ids = [
                item for item in existing_bound_ids if item != normalized_player_id
            ]
            updated_users.append(
                {
                    **user,
                    "player_id": normalized_player_id or None,
                    "linked_player_ids": linked_player_ids,
                }
            )
        else:
            updated_users.append(user)
    return updated_users


def remove_user_player_binding(
    users: list[dict[str, Any]],
    username: str,
    player_id: str | None,
) -> list[dict[str, Any]]:
    normalized_player_id = str(player_id or "").strip()
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        remaining_ids = [
            item
            for item in get_user_bound_player_ids(user)
            if item and item != normalized_player_id
        ]
        next_primary = remaining_ids[0] if remaining_ids else None
        updated_users.append(
            {
                **user,
                "player_id": next_primary,
                "linked_player_ids": remaining_ids[1:] if remaining_ids else [],
            }
        )
    return updated_users


def set_user_primary_player_id(
    users: list[dict[str, Any]],
    username: str,
    player_id: str,
) -> list[dict[str, Any]]:
    normalized_player_id = player_id.strip()
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        if normalized_player_id not in get_user_bound_player_ids(user):
            updated_users.append(user)
            continue
        linked_player_ids = [
            item
            for item in get_user_bound_player_ids(user)
            if item != normalized_player_id
        ]
        updated_users.append(
            {
                **user,
                "player_id": normalized_player_id,
                "linked_player_ids": linked_player_ids,
            }
        )
    return updated_users


def add_user_linked_player_id(
    users: list[dict[str, Any]], username: str, player_id: str
) -> list[dict[str, Any]]:
    normalized_player_id = player_id.strip()
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        existing_bound_ids = get_user_bound_player_ids(user)
        current_primary = str(user.get("player_id") or "").strip()
        linked_player_ids = [
            item for item in existing_bound_ids if item and item != current_primary
        ]
        next_primary = current_primary or None
        if normalized_player_id and normalized_player_id not in existing_bound_ids:
            if not next_primary:
                next_primary = normalized_player_id
            else:
                linked_player_ids.append(normalized_player_id)
        updated_users.append(
            {
                **user,
                "player_id": next_primary,
                "linked_player_ids": linked_player_ids,
            }
        )
    return updated_users


def remove_user_linked_player_id(
    users: list[dict[str, Any]], username: str, player_id: str
) -> list[dict[str, Any]]:
    normalized_player_id = player_id.strip()
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        next_primary = user.get("player_id")
        if next_primary == normalized_player_id:
            next_primary = None
        linked_player_ids = [
            item for item in get_user_bound_player_ids(user) if item != normalized_player_id
        ]
        if next_primary and next_primary not in linked_player_ids:
            linked_player_ids.insert(0, next_primary)
        updated_users.append(
            {
                **user,
                "player_id": next_primary,
                "linked_player_ids": [
                    item
                    for item in linked_player_ids
                    if item != str(next_primary or "").strip()
                ],
            }
        )
    return updated_users


def parse_bool(value: str) -> bool:
    return value == "true"


def build_match_award_options(
    participants: list[dict[str, Any]],
    winning_camp: str = "",
    losing_only: bool = False,
) -> dict[str, str]:
    options: dict[str, str] = {}
    for participant in participants:
        player_id = str(participant.get("player_id") or "").strip()
        if not player_id:
            continue
        if losing_only and str(participant.get("camp") or "").strip() == winning_camp:
            continue
        seat = participant.get("seat")
        role = str(participant.get("role") or "").strip()
        label = f"{seat}号 · {player_id}"
        if role:
            label += f" · {role}"
        options[player_id] = label
    return options


def build_match_award_select(
    field_name: str,
    selected_value: str,
    participants: list[dict[str, Any]],
    placeholder_label: str,
    winning_camp: str = "",
    losing_only: bool = False,
) -> str:
    choices = build_match_award_options(
        participants,
        winning_camp=winning_camp,
        losing_only=losing_only,
    )
    option_items = [f'<option value="">{escape(placeholder_label)}</option>']
    for value, label in choices.items():
        selected = " selected" if value == selected_value else ""
        option_items.append(
            f'<option value="{escape(value)}"{selected}>{escape(label)}</option>'
        )
    return "".join(option_items)


def validate_match_awards(match: dict[str, Any]) -> str:
    participants = [
        participant
        for participant in match.get("players", [])
        if str(participant.get("player_id") or "").strip()
    ]
    participant_map = {
        str(participant["player_id"]).strip(): participant for participant in participants
    }
    participant_name_map = {
        str(participant.get("player_name") or "").strip(): str(participant.get("player_id") or "").strip()
        for participant in participants
        if str(participant.get("player_name") or "").strip() and str(participant.get("player_id") or "").strip()
    }

    def resolve_award_player_id(
        player_id_key: str,
        player_name_key: str,
        player_ref_key: str,
    ) -> str:
        explicit_player_id = str(match.get(player_id_key) or "").strip()
        if explicit_player_id:
            return explicit_player_id
        raw_ref = str(match.get(player_ref_key) or "").strip()
        if raw_ref.isdigit():
            ref_index = int(raw_ref)
            if 0 <= ref_index < len(match.get("players", [])):
                candidate_player_id = str(match["players"][ref_index].get("player_id") or "").strip()
                if candidate_player_id:
                    return candidate_player_id
        return participant_name_map.get(str(match.get(player_name_key) or "").strip(), "")

    mvp_player_id = resolve_award_player_id("mvp_player_id", "mvp_player_name", "mvp_player_ref")
    svp_player_id = resolve_award_player_id("svp_player_id", "svp_player_name", "svp_player_ref")
    scapegoat_player_id = resolve_award_player_id(
        "scapegoat_player_id",
        "scapegoat_player_name",
        "scapegoat_player_ref",
    )
    winning_camp = str(match.get("winning_camp") or "").strip()

    if mvp_player_id and mvp_player_id not in participant_map:
        return "MVP 必须从本场参赛选手中选择。"
    if svp_player_id and svp_player_id not in participant_map:
        return "SVP 必须从本场参赛选手中选择。"
    if mvp_player_id and svp_player_id and mvp_player_id == svp_player_id:
        return "MVP 和 SVP 不能选择同一位选手。"
    if not scapegoat_player_id:
        return ""
    if scapegoat_player_id not in participant_map:
        return "背锅选手必须从本场参赛选手中选择。"
    if winning_camp in {"villagers", "third_party", "draw"}:
        return "只有狼人胜利时才设置背锅选手。"
    if str(participant_map[scapegoat_player_id].get("camp") or "").strip() == winning_camp:
        return "背锅选手需要从失利阵营中选择。"
    return ""


def parse_match_form(form: dict[str, list[str]], existing_match: dict[str, Any]) -> dict[str, Any]:
    score_model = normalize_match_score_model(form_value(form, "score_model"))
    participants = []
    for index in range(len(existing_match["players"])):
        player_name = form_value(form, f"player_name_{index}").strip()
        team_name = form_value(form, f"team_name_{index}").strip()
        if not player_name and not team_name:
            continue
        score_breakdown = {
            field_name: parse_float_value(
                form_value(form, f"{field_name}_{index}", "0") or "0",
                0.0,
            )
            for field_name, _ in MATCH_SCORE_COMPONENT_FIELDS
        }
        points_earned = parse_float_value(
            form_value(form, f"points_earned_{index}", "0") or "0",
            0.0,
        )
        if uses_structured_score_model(score_model):
            points_earned = round(sum(score_breakdown.values()), 2)
        participants.append(
            {
                "player_id": "",
                "player_name": player_name,
                "team_id": "",
                "team_name": team_name,
                "seat": int(form_value(form, f"seat_{index}", "0") or "0"),
                "role": form_value(form, f"role_{index}"),
                "camp": form_value(form, f"camp_{index}"),
                "result": form_value(form, f"result_{index}"),
                "points_earned": points_earned,
                **score_breakdown,
                "stance_result": form_value(form, f"stance_result_{index}", "none"),
                "notes": form_value(form, f"notes_{index}"),
            }
        )

    return {
        "match_id": existing_match["match_id"],
        "competition_name": form_value(form, "competition_name").strip(),
        "season": form_value(form, "season").strip(),
        "stage": form_value(form, "stage"),
        "round": int(form_value(form, "round", "0") or "0"),
        "game_no": int(form_value(form, "game_no", "0") or "0"),
        "score_model": score_model,
        "played_on": form_value(form, "played_on").strip(),
        "group_label": form_value(form, "group_label").strip(),
        "table_label": form_value(form, "table_label").strip(),
        "format": form_value(form, "format").strip(),
        "duration_minutes": int(form_value(form, "duration_minutes", "0") or "0"),
        "winning_camp": form_value(form, "winning_camp"),
        "mvp_player_id": "",
        "svp_player_id": "",
        "scapegoat_player_id": "",
        "mvp_player_ref": form_value(form, "mvp_player_ref").strip(),
        "svp_player_ref": form_value(form, "svp_player_ref").strip(),
        "scapegoat_player_ref": form_value(form, "scapegoat_player_ref").strip(),
        "mvp_player_name": form_value(form, "mvp_player_name").strip(),
        "svp_player_name": form_value(form, "svp_player_name").strip(),
        "scapegoat_player_name": form_value(form, "scapegoat_player_name").strip(),
        "players": participants,
        "notes": form_value(form, "notes").strip(),
    }


def save_matches_with_placeholders(
    data: dict[str, Any],
    users: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> tuple[list[str], list[str]]:
    normalized_matches, _ = canonicalize_match_ids(matches)
    data["matches"] = normalized_matches
    created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
    users = ensure_placeholder_users_for_player_ids(data, users, created_player_ids)
    errors = save_repository_state(data, users)
    return errors, created_player_ids


def validate_match_competition_selection(
    data: dict[str, Any],
    competition_name: str,
) -> str:
    known_competitions = {
        entry["competition_name"] for entry in load_series_catalog(data)
    }
    if known_competitions and competition_name not in known_competitions:
        return "请先在系列赛管理中创建对应的地区赛事页，再录入比赛。"
    return ""


def validate_match_season_selection(
    data: dict[str, Any],
    competition_name: str,
    season_name: str,
    existing_season_name: str = "",
    include_non_ongoing: bool = False,
) -> str:
    if not season_name.strip():
        return "请选择赛季。"
    available_seasons = list_seasons(
        data,
        competition_name,
        include_non_ongoing=include_non_ongoing,
        selected_season=existing_season_name or season_name,
    )
    if season_name not in available_seasons:
        return "请选择该系列赛已配置的赛季。"
    return ""


def build_empty_match(competition_name: str = "", season_name: str = "") -> dict[str, Any]:
    return {
        "match_id": "pending-new-match",
        "competition_name": competition_name,
        "season": season_name,
        "stage": "regular_season",
        "round": 1,
        "game_no": 1,
        "score_model": MATCH_SCORE_MODEL_STANDARD,
        "played_on": china_today_label(),
        "group_label": "A组",
        "table_label": "1号房",
        "format": "经典十二人局",
        "duration_minutes": 60,
        "winning_camp": "villagers",
        "mvp_player_id": "",
        "svp_player_id": "",
        "scapegoat_player_id": "",
        "mvp_player_ref": "",
        "svp_player_ref": "",
        "scapegoat_player_ref": "",
        "mvp_player_name": "",
        "svp_player_name": "",
        "scapegoat_player_name": "",
        "notes": "",
        "players": [
            {
                "player_id": "",
                "player_name": "",
                "team_id": "",
                "team_name": "",
                "seat": seat,
                "role": "",
                "camp": "villagers",
                "result": "win",
                "points_earned": 0.0,
                **build_empty_score_breakdown(),
                "stance_result": "none",
                "notes": "",
            }
            for seat in range(1, 13)
        ],
    }


def build_match_competition_field(
    current_competition_name: str,
    current_user: dict[str, Any] | None = None,
) -> str:
    from web.features.matches import build_match_competition_field as impl

    return impl(current_competition_name, current_user)


def build_match_season_field(
    current_competition_name: str,
    current_season_name: str,
    include_non_ongoing: bool = False,
) -> str:
    from web.features.matches import build_match_season_field as impl

    return impl(
        current_competition_name,
        current_season_name,
        include_non_ongoing=include_non_ongoing,
    )


def render_match_form_page(
    ctx: RequestContext,
    current: dict[str, Any],
    action_url: str,
    page_title: str,
    heading: str,
    submit_label: str,
    next_path: str,
    match_code_hint: str,
    alert: str = "",
) -> str:
    from web.features.matches import render_match_form_page as impl

    return impl(
        ctx,
        current,
        action_url,
        page_title,
        heading,
        submit_label,
        next_path,
        match_code_hint,
        alert,
    )


def get_match_edit_page(
    ctx: RequestContext, match_id: str, alert: str = "", field_values: dict[str, Any] | None = None
) -> str:
    from web.features.matches import get_match_edit_page as impl

    return impl(ctx, match_id, alert, field_values)


def get_match_create_page(
    ctx: RequestContext,
    alert: str = "",
    field_values: dict[str, Any] | None = None,
) -> str:
    from web.features.matches import get_match_create_page as impl

    return impl(ctx, alert, field_values)


def login_page(ctx: RequestContext, alert: str = "") -> str:
    next_path = form_value(ctx.query, "next", "/dashboard")
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">中国时间登录入口</div>
      <h1 class="display-6 fw-semibold mb-3">登录狼人杀联赛管理台</h1>
      <p class="mb-0 opacity-75">登录后可以进入比赛页面选择战队，并编辑赛季比赛表格。</p>
    </section>
    <section class="form-panel shadow-sm p-3 p-lg-4 mx-auto" style="max-width: 560px;">
      <form method="post" action="/login?next={quote(next_path)}">
        <div class="mb-3">
          <label class="form-label">用户名</label>
          <input class="form-control" name="username" autocomplete="username">
        </div>
        <div class="mb-4">
          <label class="form-label">密码</label>
          <input class="form-control" name="password" type="password" autocomplete="current-password">
        </div>
        <div class="d-flex flex-wrap gap-2 align-items-center">
          <button class="btn btn-dark" type="submit">登录</button>
          <a class="btn btn-outline-dark" href="/register">注册新账号</a>
        </div>
      </form>
    </section>
    """
    return layout("登录", body, ctx, alert=alert)


def build_context(environ: dict[str, Any]) -> RequestContext:
    query, form, files = get_request_data(environ)
    return RequestContext(
        method=environ.get("REQUEST_METHOD", "GET").upper(),
        path=environ.get("PATH_INFO", "/"),
        query=query,
        form=form,
        files=files,
        current_user=get_current_user(environ),
        now_label=china_now_label(),
    )


def require_login(ctx: RequestContext, start_response):
    if ctx.current_user:
        return None
    next_path = ctx.path or "/dashboard"
    if ctx.query:
        next_path += "?" + urlencode({key: values[0] for key, values in ctx.query.items() if values})
    return redirect(start_response, "/login?next=" + quote(next_path))


def require_admin(ctx: RequestContext, start_response):
    if is_admin_user(ctx.current_user):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", '<div class="alert alert-danger">只有管理员可以访问账号管理页面。</div>', ctx),
    )


def require_match_manager(ctx: RequestContext, start_response):
    if can_manage_matches(ctx.current_user):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", '<div class="alert alert-danger">只有管理员或赛事负责人可以录入和编辑比赛结果。</div>', ctx),
    )


def require_series_manager(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return require_login(ctx, start_response)
    if can_access_series_management(ctx.current_user):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", '<div class="alert alert-danger">只有具备赛事页或赛季管理权限的账号才能访问系列赛管理页面。</div>', ctx),
    )


def require_competition_manager(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    competition_name: str,
    message: str,
):
    if can_manage_matches(ctx.current_user, data, competition_name):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", f'<div class="alert alert-danger">{escape(message)}</div>', ctx),
    )


def require_competition_catalog_manager(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    competition_name: str,
    message: str,
):
    if can_manage_competition_catalog(ctx.current_user, data, competition_name):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", f'<div class="alert alert-danger">{escape(message)}</div>', ctx),
    )


def require_competition_season_manager(
    ctx: RequestContext,
    start_response,
    data: dict[str, Any],
    competition_name: str,
    message: str,
):
    if can_manage_competition_seasons(ctx.current_user, data, competition_name):
        return None
    return start_response_html(
        start_response,
        "403 Forbidden",
        layout("没有权限", f'<div class="alert alert-danger">{escape(message)}</div>', ctx),
    )


def handle_register(ctx: RequestContext, start_response):
    if ctx.current_user:
        return redirect(start_response, "/dashboard")

    if ctx.method == "GET":
        captcha_token, captcha_prompt = build_captcha()
        return start_response_html(
            start_response,
            "200 OK",
            register_page(ctx, captcha_token=captcha_token, captcha_prompt=captcha_prompt),
        )

    users = load_users()
    username = form_value(ctx.form, "username").strip()
    display_name = form_value(ctx.form, "display_name").strip()
    province_name = form_value(ctx.form, "province_name").strip()
    region_name = form_value(ctx.form, "region_name").strip()
    gender = form_value(ctx.form, "gender").strip()
    bio = form_value(ctx.form, "bio").strip()
    password = form_value(ctx.form, "password")
    password_confirm = form_value(ctx.form, "password_confirm")
    captcha_token = form_value(ctx.form, "captcha_token")
    captcha_answer = form_value(ctx.form, "captcha_answer")
    error = validate_registration_form(
        username,
        display_name,
        province_name,
        region_name,
        gender,
        bio,
        password,
        password_confirm,
        captcha_token,
        captcha_answer,
        users,
    )
    if error:
        next_token, next_prompt = build_captcha()
        return start_response_html(
            start_response,
            "200 OK",
            register_page(
                ctx,
                alert=error,
                form_values={
                    "username": username,
                    "display_name": display_name,
                    "province_name": province_name or DEFAULT_PROVINCE_NAME,
                    "region_name": region_name or "广州市",
                    "gender": gender or "prefer_not_to_say",
                    "bio": bio,
                },
                captcha_token=next_token,
                captcha_prompt=next_prompt,
            ),
        )

    password_salt, password_hash = hash_password(password)
    normalized_province, normalized_region = normalize_user_location(
        province_name,
        region_name,
    )
    new_user = {
        "username": username,
        "display_name": display_name,
        "password_salt": password_salt,
        "password_hash": password_hash,
        "active": True,
        "player_id": None,
        "linked_player_ids": [],
        "manager_scope_keys": [],
        "permissions": [],
        "role": "member",
        "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
        "region_name": normalized_region or "广州市",
        "gender": normalize_user_gender(gender) or "prefer_not_to_say",
        "bio": bio,
        "photo": DEFAULT_PLAYER_PHOTO,
    }
    users, merged_player_ids = merge_placeholder_users_for_registration(users, display_name, new_user)
    save_users(users)
    success_message = "注册成功，请使用新账号登录。"
    return start_response_html(
        start_response,
        "200 OK",
        login_page(ctx, alert=success_message),
    )


def handle_login(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", login_page(ctx))

    username = form_value(ctx.form, "username").strip()
    password = form_value(ctx.form, "password")
    for user in load_users():
        if user["username"] == username and user.get("active") and verify_password(password, user):
            token = secrets.token_urlsafe(24)
            save_session(token, username)
            next_path = form_value(ctx.query, "next", "/dashboard")
            return redirect(
                start_response,
                next_path,
                headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; Max-Age={SESSION_COOKIE_MAX_AGE_SECONDS}; HttpOnly; SameSite=Lax")],
            )

    return start_response_html(start_response, "200 OK", login_page(ctx, alert="用户名或密码不正确。"))


def handle_logout(start_response, environ: dict[str, Any]):
    jar = parse_cookies(environ)
    token = jar.get(SESSION_COOKIE)
    if token is not None:
        delete_session(token.value)
    return redirect(
        start_response,
        "/login",
        headers=[("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")],
    )


def handle_accounts(ctx: RequestContext, start_response):
    from web.features.admin import handle_accounts as impl

    return impl(ctx, start_response)


def handle_permission_control(ctx: RequestContext, start_response):
    from web.features.admin import handle_permission_control as impl

    return impl(ctx, start_response)


def update_user_account_fields(
    users: list[dict[str, Any]],
    username: str,
    display_name: str,
    province_name: str,
    region_name: str,
    gender: str,
    bio: str,
    password: str,
    photo: str | None = None,
) -> list[dict[str, Any]]:
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue

        normalized_province, normalized_region = normalize_user_location(
            province_name,
            region_name,
        )
        next_user = {
            **user,
            "display_name": display_name,
            "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
            "region_name": normalized_region or "广州市",
            "gender": normalize_user_gender(gender) or "prefer_not_to_say",
            "bio": bio.strip(),
        }
        if password:
            password_salt, password_hash = hash_password(password)
            next_user["password_salt"] = password_salt
            next_user["password_hash"] = password_hash
        if photo:
            next_user["photo"] = photo
        updated_users.append(next_user)
    return updated_users


def handle_profile(ctx: RequestContext, start_response):
    from web.features.profile import handle_profile as impl

    return impl(ctx, start_response)



def handle_player_bindings(ctx: RequestContext, start_response):
    from web.features.bindings import handle_player_bindings as impl

    return impl(ctx, start_response)


def handle_player_edit(ctx: RequestContext, start_response, player_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_player_edit_page(ctx, player_id))

    data = load_validated_data()
    player = next((item for item in data["players"] if item["player_id"] == player_id), None)
    if not player:
        return start_response_html(
            start_response,
            "404 Not Found",
            layout("未找到队员", '<div class="alert alert-danger">没有找到对应的队员。</div>', ctx),
        )

    display_name = form_value(ctx.form, "player_display_name").strip()
    aliases_raw = form_value(ctx.form, "aliases")
    notes = form_value(ctx.form, "notes").strip()
    upload = file_value(ctx.files, "photo_file")
    error = validate_profile_update(
        "管理员",
        DEFAULT_PROVINCE_NAME,
        DEFAULT_REGION_NAME,
        "prefer_not_to_say",
        "管理员编辑队员资料。",
        "",
        "",
        display_name,
    )
    if not error:
        error = validate_uploaded_photo(upload)
    if error:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_edit_page(
                ctx,
                player_id,
                alert=error,
                player_values={
                    **player,
                    "display_name": display_name or player["display_name"],
                    "aliases": parse_aliases_text(aliases_raw),
                    "notes": notes,
                },
            ),
        )

    for item in data["players"]:
        if item["player_id"] != player_id:
            continue
        item["display_name"] = display_name
        item["aliases"] = parse_aliases_text(aliases_raw)
        item["notes"] = notes
        new_photo = save_uploaded_player_photo(player_id, upload)
        if new_photo:
            item["photo"] = new_photo
        break

    users = load_users()
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_edit_page(ctx, player_id, alert="保存失败：" + "；".join(errors[:3])),
        )
    next_path = form_value(ctx.query, "next").strip() or f"/players/{player_id}"
    return redirect(start_response, next_path)


def handle_team_logo_update(ctx: RequestContext, start_response, team_id: str):
    data = load_validated_data()
    team = get_team_by_id(data, team_id)
    if not team:
        return start_response_html(
            start_response,
            "404 Not Found",
            layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx),
        )

    current_player = get_user_player(data, ctx.current_user)
    if get_team_season_status(data, team) == "completed":
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert="当前战队所属赛季已结束，队标与战队资料不再允许修改。"),
        )
    if not can_manage_team(ctx, team, current_player):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、已认领该战队的负责人或管理员可以更新队标。</div>', ctx),
        )

    upload = file_value(ctx.files, "logo_file")
    error = validate_uploaded_photo(upload)
    if error:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert=error),
        )

    new_logo = save_uploaded_team_logo(team_id, upload)
    if not new_logo:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert="请先选择要上传的战队图标。"),
        )

    for item in data["teams"]:
        if item["team_id"] == team_id:
            item["logo"] = new_logo
            break

    users = load_users()
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert="保存失败：" + "；".join(errors[:3])),
        )
    next_path = form_value(ctx.form, "next").strip() or f"/teams/{team_id}"
    return redirect(start_response, next_path)


def serve_asset(start_response, path: str):
    asset_path = safe_asset_path(path)
    if not asset_path or not asset_path.is_file():
        fallback = safe_asset_path(DEFAULT_PLAYER_PHOTO)
        if not fallback or not fallback.is_file():
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"\xe8\xb5\x84\xe6\xba\x90\xe4\xb8\x8d\xe5\xad\x98\xe5\x9c\xa8"]
        asset_path = fallback

    payload = asset_path.read_bytes()
    content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
    start_response(
        "200 OK",
        [("Content-Type", content_type), ("Content-Length", str(len(payload)))],
    )
    return [payload]


def handle_team_center(ctx: RequestContext, start_response):
    from web.features.team_center import handle_team_center as impl

    return impl(ctx, start_response)


def handle_team_admin(ctx: RequestContext, start_response):
    from web.features.team_admin import handle_team_admin as impl

    return impl(ctx, start_response)



def handle_match_edit(ctx: RequestContext, start_response, match_id: str):
    from web.features.matches import handle_match_edit as impl

    return impl(ctx, start_response, match_id)


def get_match_frontend_page(ctx: RequestContext, match_id: str) -> str:
    from web.features.match_page import build_match_frontend_page as impl

    return impl(ctx, match_id)


def get_match_legacy_page(ctx: RequestContext, match_id: str) -> str:
    from web.features.match_page import get_match_legacy_page as impl

    return impl(ctx, match_id)


def handle_match_api(ctx: RequestContext, start_response, match_id: str):
    from web.features.match_page import handle_match_api as impl

    return impl(ctx, start_response, match_id)


def handle_match_create(ctx: RequestContext, start_response):
    from web.features.matches import handle_match_create as impl

    return impl(ctx, start_response)


def app(environ, start_response):
    try:
        ctx = build_context(environ)
        path = ctx.path

        if path == "/":
            return redirect(start_response, "/dashboard")
        if path.startswith("/assets/"):
            return serve_asset(start_response, path)
        if path == "/api/dashboard":
            return handle_dashboard_api(ctx, start_response)
        if path == "/api/competitions":
            return handle_competitions_api(ctx, start_response)
        if path == "/api/guilds":
            return handle_guilds_api(ctx, start_response)
        if path.startswith("/api/guilds/"):
            guild_id = path.split("/", 3)[3]
            return handle_guild_api(ctx, start_response, guild_id)
        if path.startswith("/api/players/"):
            player_id = path.split("/", 3)[3]
            return handle_player_api(ctx, start_response, player_id)
        if path.startswith("/api/teams/"):
            team_id = path.split("/", 3)[3]
            return handle_team_api(ctx, start_response, team_id)
        if path.startswith("/api/matches/"):
            match_id = path.split("/", 3)[3]
            return handle_match_api(ctx, start_response, match_id)
        if path.startswith("/api/series/"):
            series_slug = path.split("/", 3)[3]
            return handle_series_api(ctx, start_response, series_slug)
        if path.startswith("/api/days/"):
            played_on = path.split("/", 3)[3]
            return handle_match_day_api(ctx, start_response, played_on)
        if path == "/api/schedule":
            return handle_schedule_api(ctx, start_response)
        if path == "/login":
            return handle_login(ctx, start_response)
        if path == "/register":
            return handle_register(ctx, start_response)
        if path == "/logout":
            return handle_logout(start_response, environ)

        if path == "/dashboard":
            return start_response_html(start_response, "200 OK", build_dashboard_frontend_page(ctx))
        if path == "/dashboard/legacy":
            return start_response_html(start_response, "200 OK", get_dashboard_page(ctx))
        if path == "/competitions":
            return handle_competitions(ctx, start_response)
        if path == "/competitions/legacy":
            return start_response_html(start_response, "200 OK", get_competitions_page(ctx))
        if path == "/guilds":
            return handle_guilds(ctx, start_response)
        if path == "/guilds/legacy":
            return start_response_html(start_response, "200 OK", get_guilds_page(ctx))
        if path == "/schedule":
            return start_response_html(start_response, "200 OK", get_schedule_page(ctx))
        if path == "/schedule/legacy":
            return start_response_html(start_response, "200 OK", get_schedule_legacy_page(ctx))
        if path.startswith("/series/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "series" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_series_legacy_page(ctx, parts[1]),
                )
        if path.startswith("/series/"):
            parts = path.strip("/").split("/")
            if len(parts) == 2 and parts[0] == "series":
                return start_response_html(start_response, "200 OK", get_series_page(ctx, parts[1]))
        if path.startswith("/days/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "days" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_day_legacy_page(ctx, parts[1]),
                )
        if path.startswith("/days/"):
            played_on = path.split("/", 2)[2]
            return handle_match_day(ctx, start_response, played_on)
        if path.startswith("/guilds/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "guilds" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_guild_legacy_page(ctx, parts[1]),
                )
        if path.startswith("/guilds/"):
            guild_id = path.split("/", 2)[2]
            return handle_guild_page(ctx, start_response, guild_id)
        if path == "/teams":
            return start_response_html(start_response, "200 OK", get_teams_page(ctx))
        if path.startswith("/teams/") and path.endswith("/logo"):
            team_id = path.split("/")[2]
            guard = require_login(ctx, start_response)
            if guard is not None:
                return guard
            if ctx.method != "POST":
                return start_response_html(
                    start_response,
                    "405 Method Not Allowed",
                    layout("请求无效", '<div class="alert alert-danger">队标上传只支持提交操作。</div>', ctx),
                )
            return handle_team_logo_update(ctx, start_response, team_id)
        if path.startswith("/teams/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "teams" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_legacy_page(ctx, parts[1]),
                )
        if path == "/matches/new":
            guard = require_login(ctx, start_response)
            if guard is not None:
                return guard
            manager_guard = require_match_manager(ctx, start_response)
            if manager_guard is not None:
                return manager_guard
            return handle_match_create(ctx, start_response)
        if path.startswith("/matches/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "matches" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_match_legacy_page(ctx, parts[1]),
                )
        if path.startswith("/matches/") and path.endswith("/edit"):
            match_id = path.split("/")[2]
            guard = require_login(ctx, start_response)
            if guard is not None:
                return guard
            manager_guard = require_match_manager(ctx, start_response)
            if manager_guard is not None:
                return manager_guard
            return handle_match_edit(ctx, start_response, match_id)
        if path.startswith("/matches/"):
            match_id = path.split("/", 2)[2]
            return start_response_html(start_response, "200 OK", get_match_frontend_page(ctx, match_id))
        if path.startswith("/players/") and path.endswith("/edit"):
            player_id = path.split("/")[2]
            guard = require_login(ctx, start_response)
            if guard is not None:
                return guard
            if not can_manage_player(ctx, player_id):
                return start_response_html(
                    start_response,
                    "403 Forbidden",
                    layout("没有权限", '<div class="alert alert-danger">你没有权限编辑这位队员的资料。</div>', ctx),
                )
            return handle_player_edit(ctx, start_response, player_id)
        if path.startswith("/players/") and path.endswith("/legacy"):
            parts = path.strip("/").split("/")
            if len(parts) == 3 and parts[0] == "players" and parts[2] == "legacy":
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_player_legacy_page(ctx, parts[1]),
                )
        if path.startswith("/players/"):
            player_id = path.split("/", 2)[2]
            return handle_player_page(ctx, start_response, player_id)
        if path.startswith("/teams/"):
            team_id = path.split("/", 2)[2]
            return handle_team_page(ctx, start_response, team_id)

        guard = require_login(ctx, start_response)
        if guard is not None:
            return guard

        if path == "/accounts":
            admin_guard = require_admin(ctx, start_response)
            if admin_guard is not None:
                return admin_guard
            return handle_accounts(ctx, start_response)
        if path == "/permissions":
            return handle_permission_control(ctx, start_response)
        if path == "/profile":
            return handle_profile(ctx, start_response)
        if path == "/bindings":
            return handle_player_bindings(ctx, start_response)
        if path == "/team-center":
            return handle_team_center(ctx, start_response)
        if path == "/team-admin":
            admin_guard = require_admin(ctx, start_response)
            if admin_guard is not None:
                return admin_guard
            return handle_team_admin(ctx, start_response)
        if path == "/series-manage":
            manager_guard = require_series_manager(ctx, start_response)
            if manager_guard is not None:
                return manager_guard
            return handle_series_manage(ctx, start_response)

        return start_response_html(
            start_response,
            "404 Not Found",
            layout("页面不存在", '<div class="alert alert-danger">你访问的页面不存在。</div>', ctx),
        )
    except Exception as exc:
        return start_response_html(
            start_response,
            "500 Internal Server Error",
            f"<h1>服务运行出错</h1><pre>{escape(str(exc))}</pre>",
        )


def main() -> int:
    with make_server(HOST, PORT, app) as server:
        listen_host = HOST or "127.0.0.1"
        print(f"本地站点已启动：http://{listen_host}:{PORT}")
        print("中国时间：", china_now_label())
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
