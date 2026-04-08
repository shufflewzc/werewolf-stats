#!/usr/bin/env python3

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import mimetypes
import re
import secrets
import sys
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
    load_membership_requests,
    load_users,
    save_matches as persist_matches,
    save_membership_requests,
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
DEFAULT_TEAM_LOGO = "assets/teams/default-team.png"
SESSION_COOKIE = "werewolf_session"
PORT = 8000
SESSIONS: dict[str, str] = {}
CAPTCHA_CHALLENGES: dict[str, dict[str, str]] = {}
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
SLUG_SANITIZE_PATTERN = re.compile(r"[^a-z0-9_-]+")
MATCH_ID_PATTERN = re.compile(r"^[a-z0-9]{1,6}-[a-z0-9]{1,8}-\d{6}-\d{2}$")
ALIAS_SPLIT_PATTERN = re.compile(r"[\n,，、]+")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}


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

    username = SESSIONS.get(token.value)
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
        existing["latest_played_on"] = max(existing["latest_played_on"], row["latest_played_on"])
        existing["summary"] = existing["summary"] or row["summary"]
        combined_seasons = {*existing["seasons"], *row["seasons"]}
        existing["seasons"] = sorted(combined_seasons, reverse=True)

    return sorted(
        series_index.values(),
        key=lambda item: (item["latest_played_on"], item["series_name"]),
        reverse=True,
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
    tokens_to_remove = [token for token, session_username in SESSIONS.items() if session_username == username]
    for token in tokens_to_remove:
        SESSIONS.pop(token, None)


def start_response_html(start_response, status: str, body: str, headers: list[tuple[str, str]] | None = None):
    extra_headers = headers or []
    payload = body.encode("utf-8")
    start_response(
        status,
        [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(payload)))] + extra_headers,
    )
    return [payload]


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


def layout(title: str, body: str, ctx: RequestContext, alert: str = "") -> str:
    user_html = ""
    nav_links = []
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        role_label = account_role_label(ctx.current_user)
        region_label = get_user_region_label(ctx.current_user)
        user_html = f"""
        <div class="account-actions d-flex flex-wrap align-items-center gap-3">
          <span class="small text-secondary">当前登录：{escape(display_name)} · {escape(role_label)}{' · ' + escape(region_label) if region_label else ''}</span>
          <form method="post" action="/logout" class="m-0">
            <button type="submit" class="btn btn-outline-dark btn-sm">退出登录</button>
          </form>
        </div>
        """
        nav_links = [
            '<a class="nav-link nav-pill px-0" href="/dashboard">首页</a>',
            '<a class="nav-link nav-pill px-0" href="/competitions">比赛页面</a>',
            '<a class="nav-link nav-pill px-0" href="/guilds">门派</a>',
            '<a class="nav-link nav-pill px-0" href="/profile">个人中心</a>',
            '<a class="nav-link nav-pill px-0" href="/team-center">战队操作</a>',
        ]
        if can_manage_matches(ctx.current_user):
            nav_links.append('<a class="nav-link nav-pill px-0" href="/matches/new">录入比赛</a>')
        if can_access_series_management(ctx.current_user):
            nav_links.append('<a class="nav-link nav-pill px-0" href="/series-manage">系列赛管理</a>')
        if is_admin_user(ctx.current_user):
            nav_links.append('<a class="nav-link nav-pill px-0" href="/accounts">账号管理</a>')
            nav_links.append('<a class="nav-link nav-pill px-0" href="/permissions">权限控制</a>')
    else:
        nav_links = [
            '<a class="nav-link nav-pill px-0" href="/dashboard">首页</a>',
            '<a class="nav-link nav-pill px-0" href="/competitions">比赛页面</a>',
            '<a class="nav-link nav-pill px-0" href="/guilds">门派</a>',
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
        --bg: #eef2f7;
        --bg-alt: #fafbfd;
        --surface: rgba(255, 255, 255, 0.68);
        --surface-strong: rgba(255, 255, 255, 0.92);
        --ink: #111827;
        --muted: #667085;
        --accent: #2d7ff9;
        --accent-dark: #175cd3;
        --accent-soft: rgba(45, 127, 249, 0.12);
        --sky-soft: rgba(182, 219, 255, 0.24);
        --sun-soft: rgba(255, 255, 255, 0.52);
        --line: rgba(15, 23, 42, 0.08);
        --line-strong: rgba(15, 23, 42, 0.12);
        --shadow: 0 1.8rem 5rem rgba(15, 23, 42, 0.14);
        --shadow-soft: 0 1rem 2.6rem rgba(15, 23, 42, 0.08);
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
          radial-gradient(circle at top left, rgba(182, 219, 255, 0.4), transparent 28%),
          radial-gradient(circle at top right, rgba(221, 236, 255, 0.48), transparent 24%),
          radial-gradient(circle at bottom right, rgba(203, 227, 255, 0.3), transparent 30%),
          linear-gradient(180deg, var(--bg-alt) 0%, var(--bg) 100%);
      }}
      body::before {{
        content: "";
        position: fixed;
        inset: 0;
        pointer-events: none;
        background:
          linear-gradient(135deg, rgba(255, 255, 255, 0.42), transparent 42%),
          radial-gradient(circle at 20% 20%, rgba(255, 255, 255, 0.34), transparent 26%);
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
        max-width: 1400px;
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
        border-radius: 30px;
      }}
      .topbar {{
        position: sticky;
        top: 1rem;
        z-index: 40;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.84), rgba(246, 249, 255, 0.88));
      }}
      .brand-kicker {{
        display: inline-flex;
        align-items: center;
        gap: 0.45rem;
        padding: 0.42rem 0.84rem;
        margin-bottom: 0.75rem;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.74);
        color: var(--accent-dark);
        font-size: 0.75rem;
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
        background: linear-gradient(135deg, #ffffff, #74b6ff 65%, var(--accent));
        box-shadow: 0 0 0 0.24rem rgba(45, 127, 249, 0.12);
      }}
      .brand-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.18rem, 2.2vw, 1.45rem);
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .topbar-actions {{
        justify-content: flex-end;
      }}
      .primary-nav {{
        row-gap: 0.7rem;
      }}
      .hero {{
        position: relative;
        overflow: hidden;
        isolation: isolate;
        background:
          linear-gradient(135deg, rgba(255, 255, 255, 0.78), rgba(248, 250, 255, 0.68) 42%, rgba(231, 241, 255, 0.72)),
          linear-gradient(180deg, rgba(255, 255, 255, 0.54), rgba(255, 255, 255, 0.24));
        color: var(--ink);
        border: 1px solid rgba(255, 255, 255, 0.84);
        border-radius: 38px;
        box-shadow: var(--shadow);
      }}
      .hero::before {{
        content: "";
        position: absolute;
        right: -10%;
        bottom: -24%;
        width: min(42vw, 420px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(119, 188, 255, 0.42), rgba(119, 188, 255, 0));
        z-index: -1;
      }}
      .hero::after {{
        content: "";
        position: absolute;
        left: -10%;
        top: -20%;
        width: min(36vw, 340px);
        aspect-ratio: 1 / 1;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255, 255, 255, 0.95), rgba(255, 255, 255, 0));
        z-index: -1;
      }}
      .hero-layout {{
        display: grid;
        grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.92fr);
        gap: 1.4rem;
        align-items: stretch;
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
        color: var(--accent-dark);
      }}
      .eyebrow::before {{
        content: "";
        width: 0.8rem;
        height: 1px;
        background: currentColor;
      }}
      .hero-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(2.3rem, 4.3vw, 4.75rem);
        line-height: 0.98;
        letter-spacing: -0.06em;
      }}
      .hero-copy {{
        max-width: 58ch;
        color: rgba(17, 24, 39, 0.74);
        font-size: clamp(1rem, 1.25vw, 1.08rem);
      }}
      .hero-switchers {{
        display: flex;
        flex-wrap: wrap;
        gap: 0.72rem;
      }}
      .hero-kpis {{
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 0.85rem;
        margin-top: 1.5rem;
      }}
      .hero-pill {{
        padding: 1rem 1.05rem;
        border-radius: 24px;
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
        margin-top: 0.5rem;
        font-size: clamp(1.2rem, 2vw, 1.5rem);
        line-height: 1.1;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-weight: 800;
        letter-spacing: -0.04em;
      }}
      .hero-pill small {{
        display: block;
        margin-top: 0.35rem;
        color: var(--muted);
      }}
      .hero-stage-card {{
        position: relative;
        min-height: 100%;
        padding: 1.5rem;
        border-radius: 30px;
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
        margin-top: 1rem;
        font-size: 0.76rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(244, 247, 255, 0.66);
      }}
      .hero-stage-title {{
        margin-top: 0.8rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.9rem, 3vw, 2.9rem);
        font-weight: 800;
        line-height: 1.02;
        letter-spacing: -0.05em;
      }}
      .hero-stage-note {{
        margin-top: 0.8rem;
        color: rgba(244, 247, 255, 0.74);
        line-height: 1.7;
      }}
      .hero-stage-grid {{
        display: grid;
        grid-template-columns: repeat(2, minmax(0, 1fr));
        gap: 0.85rem;
        margin-top: 1.35rem;
      }}
      .hero-stage-metric {{
        padding: 1rem;
        border-radius: 22px;
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
        margin-top: 0.55rem;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: 1.36rem;
        font-weight: 800;
        line-height: 1.08;
        letter-spacing: -0.04em;
      }}
      .hero-stage-metric small {{
        display: block;
        margin-top: 0.35rem;
        color: rgba(244, 247, 255, 0.62);
      }}
      .section-title {{
        font-family: "Manrope", "Noto Sans SC", sans-serif;
        font-size: clamp(1.4rem, 3vw, 2rem);
        letter-spacing: -0.04em;
      }}
      .section-copy {{
        color: var(--muted);
        max-width: 68ch;
      }}
      .card-kicker {{
        font-size: 0.74rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: var(--accent-dark);
        font-weight: 700;
        font-family: "Manrope", "Noto Sans SC", sans-serif;
      }}
      .stat-card {{
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(247, 249, 255, 0.78));
        border-radius: 28px;
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
        font-size: clamp(1.85rem, 4vw, 2.65rem);
        line-height: 1;
        font-weight: 800;
        letter-spacing: -0.05em;
      }}
      .team-link-card {{
        display: block;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.9), rgba(246, 249, 255, 0.78));
        border-radius: 28px;
        color: inherit;
        text-decoration: none;
        transition: transform 0.2s ease, box-shadow 0.2s ease, border-color 0.2s ease;
      }}
      .team-link-card:hover {{
        transform: translateY(-5px);
        border-color: rgba(45, 127, 249, 0.2);
        box-shadow: 0 1.4rem 3rem rgba(15, 23, 42, 0.12);
      }}
      .table-responsive {{
        overflow: auto;
        border-radius: 28px;
        background: linear-gradient(180deg, rgba(255, 255, 255, 0.82), rgba(248, 250, 255, 0.76));
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
        padding-top: 1rem;
        padding-bottom: 1rem;
      }}
      .table tbody td {{
        padding-top: 0.95rem;
        padding-bottom: 0.95rem;
      }}
      .table tbody tr {{
        transition: background-color 0.18s ease;
      }}
      .table tbody tr:hover {{
        background: rgba(226, 238, 255, 0.44);
      }}
      .small-muted {{
        color: var(--muted);
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 0.42rem 0.86rem;
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.82), rgba(225, 238, 255, 0.72));
        color: var(--accent-dark);
        font-size: 0.88rem;
        font-weight: 600;
        border: 1px solid rgba(45, 127, 249, 0.12);
      }}
      .hero .chip {{
        background: rgba(255, 255, 255, 0.5);
        border-color: rgba(255, 255, 255, 0.82);
      }}
      .form-panel {{
        border-radius: 28px;
      }}
      .form-label {{
        font-size: 0.88rem;
        font-weight: 600;
        color: var(--muted);
      }}
      .form-control,
      .form-select {{
        border-radius: 18px;
        border-color: rgba(17, 24, 39, 0.08);
        background: rgba(255, 255, 255, 0.86);
        color: var(--ink);
        padding: 0.85rem 1rem;
        box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
      }}
      .form-control:focus,
      .form-select:focus {{
        border-color: rgba(45, 127, 249, 0.36);
        box-shadow: 0 0 0 0.25rem rgba(45, 127, 249, 0.12);
        background: #ffffff;
      }}
      textarea.form-control {{
        min-height: 140px;
      }}
      .player-photo-frame {{
        width: min(100%, 260px);
        aspect-ratio: 1 / 1;
        border-radius: 32px;
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
        min-height: 2.75rem;
        padding: 0.6rem 1.05rem !important;
        border-radius: 999px;
        background: rgba(255, 255, 255, 0.56);
        border: 1px solid rgba(255, 255, 255, 0.78);
        transition: transform 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
      }}
      .nav-pill:hover {{
        transform: translateY(-1px);
        background: rgba(255, 255, 255, 0.78);
        border-color: rgba(45, 127, 249, 0.12);
      }}
      .switcher-chip {{
        display: inline-flex;
        align-items: center;
        justify-content: center;
        min-height: 2.6rem;
        padding: 0.58rem 1rem;
        border-radius: 999px;
        border: 1px solid rgba(255, 255, 255, 0.82);
        background: rgba(255, 255, 255, 0.56);
        color: var(--ink);
        text-decoration: none;
        font-size: 0.9rem;
        font-weight: 600;
        transition: transform 0.18s ease, background-color 0.18s ease, box-shadow 0.18s ease;
      }}
      .switcher-chip:hover {{
        transform: translateY(-1px);
        background: rgba(255, 255, 255, 0.84);
        box-shadow: 0 0.9rem 1.8rem rgba(15, 23, 42, 0.08);
      }}
      .switcher-chip.is-active {{
        background: linear-gradient(135deg, rgba(255, 255, 255, 0.9), rgba(225, 238, 255, 0.9));
        color: var(--accent-dark);
        border-color: rgba(45, 127, 249, 0.12);
      }}
      .btn {{
        border-radius: 999px;
        font-weight: 700;
        letter-spacing: -0.01em;
        padding: 0.7rem 1.1rem;
        transition: transform 0.18s ease, box-shadow 0.18s ease, background-color 0.18s ease, border-color 0.18s ease;
      }}
      .btn:hover {{
        transform: translateY(-1px);
      }}
      .btn-sm {{
        padding: 0.48rem 0.92rem;
      }}
      .btn-dark {{
        background: linear-gradient(135deg, #5aa7ff, var(--accent-dark));
        border-color: transparent;
        color: #ffffff;
        box-shadow: 0 0.9rem 1.9rem rgba(45, 127, 249, 0.22);
      }}
      .btn-dark:hover,
      .btn-dark:focus {{
        color: #ffffff;
        background: linear-gradient(135deg, #3d93fb, #0f5cc6);
        border-color: transparent;
        box-shadow: 0 1.05rem 2.1rem rgba(45, 127, 249, 0.24);
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
        border-color: rgba(45, 127, 249, 0.16);
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
        border-color: rgba(45, 127, 249, 0.12);
      }}
      .alert {{
        border-radius: 22px;
        border: 1px solid rgba(255, 204, 102, 0.3);
        background: linear-gradient(135deg, rgba(255, 252, 243, 0.96), rgba(255, 247, 228, 0.94));
        color: #7a5b14;
        box-shadow: var(--shadow-soft);
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
      @media (max-width: 991.98px) {{
        .hero-layout {{
          grid-template-columns: 1fr;
        }}
        .topbar,
        .panel,
        .form-panel,
        .hero {{
          border-radius: 26px;
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
          border-radius: 28px;
        }}
        .hero-title {{
          font-size: clamp(2rem, 12vw, 3rem);
        }}
        .hero-kpis {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .hero-stage-grid {{
          grid-template-columns: 1fr 1fr;
        }}
        .section-title {{
          font-size: clamp(1.24rem, 6vw, 1.72rem);
        }}
        .table-responsive .table {{
          min-width: 720px;
        }}
      }}
      @media (max-width: 575.98px) {{
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
  <body>
    <div class="container-fluid px-3 px-md-4 px-xl-5 py-4">
      <div class="shell mx-auto">
        <div class="topbar shadow-sm px-3 px-lg-4 py-3 py-lg-4 mb-4">
          <div class="d-flex flex-column flex-xl-row justify-content-between gap-3 align-items-xl-center">
            <div>
              <div class="brand-kicker">Official League Site</div>
              <div class="brand-title">狼人杀赛事数据中心</div>
              <div class="small text-secondary">当前时间：{escape(ctx.now_label)}</div>
            </div>
            <div class="topbar-actions d-flex flex-wrap align-items-center gap-3 gap-xl-4">
              <nav class="primary-nav d-flex flex-wrap gap-2 gap-lg-3">{''.join(nav_links)}</nav>
              {user_html}
            </div>
          </div>
        </div>
        {alert_html}
        {body}
      </div>
    </div>
  </body>
</html>
"""


def load_validated_data() -> dict[str, Any]:
    errors, data = validate_repository()
    if errors:
        raise ValueError("\n".join(errors))
    return data


def save_matches(matches: list[dict[str, Any]]) -> list[str]:
    _, backup_data = validate_repository()
    backup_matches = backup_data.get("matches", [])
    normalized_matches, _ = canonicalize_match_ids(matches)
    try:
        persist_matches(normalized_matches)
        errors, _ = validate_repository()
        if errors:
            persist_matches(backup_matches)
            return errors
        return []
    except Exception:
        if backup_matches:
            persist_matches(backup_matches)
        raise


def save_repository_state(data: dict[str, Any], users: list[dict[str, Any]]) -> list[str]:
    backup_errors, backup_data = validate_repository()
    if backup_errors:
        return backup_errors
    backup_users = load_users()
    try:
        save_repository_data(data, users)
        errors, _ = validate_repository()
        if errors:
            save_repository_data(backup_data, backup_users)
            return errors
        return []
    except Exception:
        save_repository_data(backup_data, backup_users)
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


def ensure_player_asset_dirs() -> None:
    PLAYER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def ensure_team_asset_dirs() -> None:
    TEAM_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def public_asset_url(path: str) -> str:
    normalized = path.strip().lstrip("/")
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
    if is_admin_user(acting_user) or user_has_permission(acting_user, "player_binding_manage"):
        return True
    captained_team_ids = get_user_captained_team_ids(data, acting_user)
    if not captained_team_ids:
        return False
    if source_player and source_player.get("team_id") in captained_team_ids:
        return True
    if target_user:
        target_bound_ids = set(get_user_bound_player_ids(target_user))
        for player in data["players"]:
            if (
                player["player_id"] in target_bound_ids
                and player.get("team_id") in captained_team_ids
            ):
                return True
    return False


def build_placeholder_player(
    player_id: str,
    team_id: str,
    competition_name: str,
    season_name: str,
) -> dict[str, Any]:
    return {
        "player_id": player_id,
        "display_name": player_id,
        "team_id": team_id,
        "photo": DEFAULT_PLAYER_PHOTO,
        "aliases": [],
        "active": True,
        "joined_on": china_today_label(),
        "notes": (
            f"比赛录入时自动预留的参赛ID档案：{competition_name} · {season_name}。"
            " 等待选手注册后绑定认领。"
        ),
    }


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
    return team.get("captain_player_id") or (team["members"][0] if team["members"] else None)


def is_team_captain(team: dict[str, Any] | None, player: dict[str, Any] | None) -> bool:
    if not team or not player:
        return False
    return get_team_captain_id(team) == player["player_id"]


def remove_member_from_team(team: dict[str, Any], player_id: str) -> None:
    team["members"] = [member_id for member_id in team["members"] if member_id != player_id]
    if get_team_captain_id(team) == player_id:
        team["captain_player_id"] = team["members"][0] if team["members"] else None


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


def list_ongoing_team_scopes(data: dict[str, Any]) -> list[dict[str, str]]:
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)
    scopes: list[dict[str, str]] = []
    for season_entry in season_catalog:
        if get_season_status(season_entry) != "ongoing":
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
                    "label": (
                        f"{competition_entry['series_name']} · {competition_name} · {season_name}"
                    ),
                }
            )
    scopes.sort(key=lambda item: (item["competition_name"], item["season_name"]))
    return scopes


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

    if seen:
        return seen

    team = get_team_by_id(data, team_id)
    return team["members"] if team else []


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
        )
        registered_team_ids = {
            team_id
            for season_entry in season_entries
            for team_id in season_entry.get("registered_team_ids", [])
        }
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
                "team_count": max(len(team_ids), len(registered_team_ids)),
                "player_count": len(player_ids),
                "latest_played_on": max((match["played_on"] for match in matches), default=""),
                "seasons": seasons,
            }
        )
    return rows


def get_competitions_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_rows = scope["competition_rows"]
    competition_names = scope["competition_names"]
    selected_competition = scope["selected_competition"]
    selected_entry = scope["selected_entry"]
    selected_region = scope["selected_region"]
    selected_series_slug = scope["selected_series_slug"]
    region_rows = scope["region_rows"]
    filtered_rows = scope["filtered_rows"]
    series_rows = scope["series_rows"]
    season_catalog = load_season_catalog(data)
    season_names = list_seasons(data, selected_competition) if selected_competition else []
    selected_season = get_selected_season(ctx, season_names)
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    featured_competition = max(
        filtered_rows or region_rows or competition_rows,
        key=lambda row: (row["latest_played_on"], row["competition_name"]),
        default=None,
    )
    region_switcher = build_region_switcher(
        "/competitions",
        scope["region_names"],
        selected_region,
        selected_series_slug,
    )
    series_switcher = build_series_switcher(
        "/competitions",
        series_rows,
        selected_region,
        selected_series_slug,
    )

    if not selected_competition:
        cards = []
        for row in filtered_rows or region_rows:
            topic_path = build_series_topic_path(row["series_slug"])
            competition_path = build_scoped_path(
                "/competitions",
                row["competition_name"],
                None,
                row["region_name"],
                row["series_slug"],
            )
            card_summary = row["summary"] or (
                f"{row['region_name']}赛区的 {row['series_name']} 官方赛事页。"
            )
            cards.append(
                f"""
                <div class="col-12 col-lg-6">
                  <div class="team-link-card shadow-sm p-4 h-100">
                    <div class="d-flex justify-content-between align-items-start gap-3">
                      <div>
                        <div class="card-kicker mb-2">{escape(row['region_name'])} · {escape(row['series_name'])}</div>
                        <h2 class="h4 mb-2">{escape(row['competition_name'])}</h2>
                        <div class="small-muted mb-2">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div>
                        <div class="small-muted mb-3">最近比赛日 {f'<span>{escape(row["latest_played_on"])}</span>' if row['latest_played_on'] else '待更新'}</div>
                        <p class="section-copy mb-0">{escape(card_summary)}</p>
                      </div>
                      <span class="chip">专题 + 地区站点</span>
                    </div>
                    <div class="row g-3">
                      <div class="col-4">
                        <div class="small text-secondary">战队</div>
                        <div class="fw-semibold">{row['team_count']} 支</div>
                      </div>
                      <div class="col-4">
                        <div class="small text-secondary">队员</div>
                        <div class="fw-semibold">{row['player_count']} 名</div>
                      </div>
                      <div class="col-4">
                        <div class="small text-secondary">对局</div>
                        <div class="fw-semibold">{row['match_count']} 场</div>
                      </div>
                    </div>
                    <div class="d-flex flex-wrap gap-2 mt-4">
                      <a class="btn btn-dark" href="{escape(topic_path)}">查看系列专题</a>
                      <a class="btn btn-outline-dark" href="{escape(competition_path)}">进入地区赛事页</a>
                    </div>
                  </div>
                </div>
                """
            )

        total_match_count = sum(row["match_count"] for row in (filtered_rows or region_rows))
        total_team_count = max((row["team_count"] for row in (filtered_rows or region_rows)), default=0)
        total_player_count = max((row["player_count"] for row in (filtered_rows or region_rows)), default=0)
        featured_name = (
            featured_competition["competition_name"] if featured_competition else "等待录入赛事"
        )
        featured_latest = (
            featured_competition["latest_played_on"] if featured_competition else "待更新"
        )
        featured_seasons = (
            " / ".join(featured_competition["seasons"][:2])
            if featured_competition and featured_competition["seasons"]
            else "赛季待录入"
        )
        manage_button = ""
        if can_access_series_management(ctx.current_user):
            manage_button = '<a class="btn btn-dark" href="/series-manage">创建或维护系列赛</a>'
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="hero-layout">
            <div>
              <div class="eyebrow mb-3">地区赛事站点</div>
              <h1 class="hero-title mb-3">{escape(selected_region or DEFAULT_REGION_NAME)}赛区官方入口</h1>
              <p class="hero-copy mb-0">先选择地区，再筛选系列赛。每张卡片都同时提供系列赛专题页和该地区的独立赛事站点，方便按赛区管理和按品牌汇总浏览。</p>
              <div class="hero-switchers mt-4">{region_switcher}</div>
              <div class="hero-switchers mt-3">{series_switcher}</div>
              <div class="hero-kpis">
                <div class="hero-pill">
                  <span>地区站点</span>
                  <strong>{len(filtered_rows or region_rows)}</strong>
                  <small>{escape(selected_region or DEFAULT_REGION_NAME)} 当前可见</small>
                </div>
                <div class="hero-pill">
                  <span>覆盖战队</span>
                  <strong>{total_team_count}</strong>
                  <small>当前地区口径</small>
                </div>
                <div class="hero-pill">
                  <span>累计对局</span>
                  <strong>{total_match_count}</strong>
                  <small>当前筛选下完整赛程</small>
                </div>
              </div>
            </div>
            <div class="hero-stage-card">
              <div class="official-mark">Official Event Portal</div>
              <div class="hero-stage-label">Featured Regional Event</div>
              <div class="hero-stage-title">{escape(featured_name)}</div>
              <div class="hero-stage-note">未登录时首页默认展示广州赛区；登录后会优先按账号所在地区进入对应赛区。进入单个地区赛事页后，你会继续看到该站自己的战队入口、赛程表和赛季切换，不会和其他地区混排。</div>
              <div class="hero-stage-grid">
                <div class="hero-stage-metric">
                  <span>最近比赛日</span>
                  <strong>{escape(featured_latest)}</strong>
                  <small>{escape(featured_seasons)}</small>
                </div>
                <div class="hero-stage-metric">
                  <span>参赛战队</span>
                  <strong>{featured_competition['team_count'] if featured_competition else 0}</strong>
                  <small>当前特色赛事</small>
                </div>
                <div class="hero-stage-metric">
                  <span>参赛队员</span>
                  <strong>{featured_competition['player_count'] if featured_competition else 0}</strong>
                  <small>当前特色赛事</small>
                </div>
                <div class="hero-stage-metric">
                  <span>赛事场次</span>
                  <strong>{featured_competition['match_count'] if featured_competition else 0}</strong>
                  <small>当前特色地区站点</small>
                </div>
              </div>
            </div>
          </div>
        </section>
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-4">
            <div>
              <h2 class="section-title mb-2">该地区系列赛站点</h2>
              <p class="section-copy mb-0">同一系列赛可以进入专题页查看跨地区汇总，也可以单独进入当前地区赛事页查看该站独立赛季。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {manage_button}
            </div>
          </div>
          <div class="row g-3 g-lg-4">{''.join(cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前地区还没有系列赛站点，请先创建系列赛。</div></div>'}</div>
        </section>
        """
        return layout("比赛页面", body, ctx, alert=alert)

    competition_switcher = build_competition_switcher(
        "/competitions",
        [row["competition_name"] for row in (filtered_rows or region_rows or competition_rows)],
        selected_competition,
        tone="light",
        all_label="返回地区赛事列表",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher = build_season_switcher(
        "/competitions",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    competition_meta = selected_entry
    current_player = get_user_player(data, ctx.current_user)
    can_manage_selected_match_scope = bool(
        selected_competition
        and can_manage_matches(ctx.current_user, data, selected_competition)
    )
    can_edit_selected_competition = bool(
        selected_competition
        and can_manage_competition_catalog(ctx.current_user, data, selected_competition)
    )
    can_manage_selected_seasons = bool(
        selected_competition
        and can_manage_competition_seasons(ctx.current_user, data, selected_competition)
    )
    _, current_user_team = (
        get_user_captained_team_for_scope(data, ctx.current_user, selected_competition, selected_season)
        if selected_competition and selected_season
        else (None, None)
    )
    season_entry = (
        get_season_entry(
            season_catalog,
            selected_series_slug,
            selected_season,
            competition_name=selected_competition,
        )
        if selected_series_slug and selected_season
        else None
    )
    team_rows = [
        row
        for row in build_team_rows(data, selected_competition, selected_season)
        if row["matches_represented"] > 0
    ]
    player_rows = [
        row
        for row in build_player_rows(data, selected_competition, selected_season)
        if row["games_played"] > 0
    ]
    team_rows.sort(
        key=lambda row: (
            row.get("points_rank", 9999),
            -row["points_earned_total"],
            row["name"],
        )
    )
    player_rows.sort(
        key=lambda row: (
            row["rank"],
            -row["points_earned_total"],
            row["display_name"],
        )
    )
    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    player_count = len(
        {
            entry["player_id"]
            for match in match_rows
            for entry in match["players"]
        }
    )
    scope_label = " / ".join(
        item for item in [selected_competition, selected_season] if item
    ) or "比赛总览"
    season_switcher_html = (
        f'<div class="hero-switchers mt-3">{season_switcher}</div>' if season_switcher else ""
    )
    region_switcher_html = (
        f'<div class="hero-switchers mt-4">{region_switcher}</div>' if region_switcher else ""
    )
    series_switcher_html = (
        f'<div class="hero-switchers mt-3">{series_switcher}</div>' if series_switcher else ""
    )
    current_competition_path = build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    page_badge = (
        competition_meta["page_badge"]
        if competition_meta and competition_meta.get("page_badge")
        else f"{competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} · 赛事专属页面"
    )
    hero_title = (
        competition_meta["hero_title"]
        if competition_meta and competition_meta.get("hero_title")
        else selected_competition
    )
    hero_intro = (
        competition_meta["hero_intro"]
        if competition_meta and competition_meta.get("hero_intro")
        else "当前页面只展示这个地区赛事站点下指定赛季的战队、队员和对局。你可以先切换地区与系列赛，再切换赛季，然后继续进入战队详情页查看更深一层的数据。"
    )
    hero_note = (
        competition_meta["hero_note"]
        if competition_meta and competition_meta.get("hero_note")
        else f"这里会保留 {competition_meta['series_name'] if competition_meta else selected_competition} 在 {competition_meta['region_name'] if competition_meta else selected_region or DEFAULT_REGION_NAME} 赛区当前赛季独立的排名和赛程视角。"
    )
    create_match_button = ""
    if can_manage_selected_match_scope:
        create_match_button = (
            f'<a class="btn btn-dark" href="/matches/new?'
            f'{urlencode({"competition": selected_competition, "season": selected_season or "", "next": current_competition_path})}">录入今日比赛</a>'
        )
    schedule_page_button = (
        f'<a class="btn btn-outline-dark" href="{escape(build_schedule_path(selected_competition, selected_season, current_competition_path, selected_region, selected_series_slug))}">查看全部场次</a>'
    )
    series_topic_button = ""
    if competition_meta:
        series_topic_button = (
            f'<a class="btn btn-outline-dark" href="{escape(build_series_topic_path(competition_meta["series_slug"], selected_season))}">查看系列专题页</a>'
        )
    edit_competition_button = ""
    if can_edit_selected_competition:
        edit_competition_button = (
            f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, None, "catalog"))}">编辑赛事页信息</a>'
        )
    season_manage_button = ""
    if can_manage_selected_seasons:
        season_manage_button = (
            f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition, current_competition_path, selected_season, "season"))}">管理赛季档期</a>'
        )
    latest_played_on = max((match["played_on"] for match in match_rows), default="待更新")
    registered_team_ids = season_entry.get("registered_team_ids", []) if season_entry else []
    registered_team_cards = []
    for registered_team_id in registered_team_ids:
        registered_team = team_lookup.get(registered_team_id)
        if not registered_team:
            continue
        registered_team_cards.append(
            f"""
            <div class="col-12 col-md-6 col-xl-4">
              <a class="team-link-card shadow-sm p-3 h-100" href="{escape(build_scoped_path('/teams/' + registered_team_id, selected_competition, selected_season, selected_region, selected_series_slug))}">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">已报名战队</div>
                    <div class="fw-semibold">{escape(registered_team['name'])}</div>
                  </div>
                  <span class="chip">查看战队</span>
                </div>
              </a>
            </div>
            """
        )
    registration_form_html = ""
    season_status_text = "待配置"
    season_period_text = "请先设置赛季起止时间"
    season_note_text = "当前赛季还没有配置档期，暂时无法开放战队报名。"
    if season_entry:
        season_status_text = season_status_label(season_entry)
        season_period_text = (
            f"{format_datetime_local_label(season_entry.get('start_at', ''))} - "
            f"{format_datetime_local_label(season_entry.get('end_at', ''))}"
        )
        season_note_text = season_entry.get("notes") or "可以在这里查看本赛季的进行状态，并管理已报名战队。"
        if current_user_team and can_manage_team(ctx, current_user_team, current_player):
            is_registered = current_user_team["team_id"] in registered_team_ids
            action_name = "cancel_team_registration" if is_registered else "register_team_for_season"
            action_label = "取消报名我的战队" if is_registered else "报名我的战队"
            helper_text = (
                f"当前账号可为 {current_user_team['name']} 执行报名操作。"
                if get_season_status(season_entry) == "ongoing"
                else "只有进行中的赛季才开放战队报名。"
            )
            registration_form_html = f"""
            <form method="post" action="/competitions">
              <input type="hidden" name="action" value="{action_name}">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season or '')}">
              <input type="hidden" name="team_id" value="{escape(current_user_team['team_id'])}">
              <input type="hidden" name="next" value="{escape(current_competition_path)}">
              <div class="small text-secondary mb-3">{escape(helper_text)}</div>
              <button type="submit" class="btn btn-dark"{'' if get_season_status(season_entry) == 'ongoing' else ' disabled'}>{escape(action_label)}</button>
            </form>
            """
        elif is_admin_user(ctx.current_user):
            eligible_admin_teams = [
                team
                for team in data["teams"]
                if team_matches_scope(team, selected_competition, selected_season or "")
            ]
            team_options_html = "".join(
                f'<option value="{escape(team["team_id"])}">{escape(team["name"])}</option>'
                for team in eligible_admin_teams
            )
            registration_form_html = f"""
            <form method="post" action="/competitions">
              <input type="hidden" name="action" value="register_team_for_season">
              <input type="hidden" name="competition_name" value="{escape(selected_competition)}">
              <input type="hidden" name="season_name" value="{escape(selected_season or '')}">
              <input type="hidden" name="next" value="{escape(current_competition_path)}">
              <div class="small text-secondary mb-3">管理员可代任意战队提交报名。</div>
              <div class="d-flex flex-column gap-3">
                <select class="form-select" name="team_id">{team_options_html}</select>
                <button type="submit" class="btn btn-dark"{'' if get_season_status(season_entry) == 'ongoing' else ' disabled'}>为所选战队报名</button>
              </div>
            </form>
            """
    season_registration_panel = ""
    if selected_season:
        season_registration_panel = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">赛季档期与战队报名</h2>
              <p class="section-copy mb-0">当前查看的是 {escape(selected_season)}。赛事负责人可以维护赛季起止时间，具备战队管理权限的账号或战队队长可以为自己的战队报名正在进行中的赛季。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {season_manage_button}
            </div>
          </div>
          <div class="row g-3 mb-4">
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="card-kicker mb-2">赛季状态</div>
                <h3 class="h5 mb-2">{escape(season_status_text)}</h3>
                <div class="small-muted mb-2">起止时间 {escape(season_period_text)}</div>
                <p class="section-copy mb-0">{escape(season_note_text)}</p>
              </div>
            </div>
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="card-kicker mb-2">报名概览</div>
                <h3 class="h5 mb-2">已报名 {len(registered_team_cards)} 支战队</h3>
                <div class="small-muted mb-2">仅进行中的赛季允许新增或取消报名</div>
                <p class="section-copy mb-0">报名成功后，战队会出现在本赛季赛事页的已报名名单中，方便赛程安排前统一确认参赛队伍。</p>
              </div>
            </div>
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="card-kicker mb-2">我的战队操作</div>
                <h3 class="h5 mb-2">{escape(current_user_team['name']) if current_user_team else '未绑定战队'}</h3>
                <div class="small-muted mb-2">{'队长或管理员可执行报名' if current_user_team else ('管理员可代战队报名' if is_admin_user(ctx.current_user) else '当前账号还没有加入战队')}</div>
                {registration_form_html or '<div class="section-copy">当前账号没有可用于报名的战队，或你不是该战队的队长。</div>'}
              </div>
            </div>
          </div>
          <div class="row g-3">{''.join(registered_team_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前赛季还没有战队报名。</div></div>'}</div>
        </section>
        """
    team_points_rows = []
    for row in team_rows:
        team_points_rows.append(
            f"""
            <tr>
              <td>{row.get('points_rank', '-')}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['name'])}</a></td>
              <td>{row['matches_represented']}</td>
              <td>{row['player_count']}</td>
              <td>{row['points_earned_total']:.2f}</td>
              <td>{row.get('points_per_match', 0.0):.2f}</td>
              <td>{format_pct(row['win_rate'])}</td>
            </tr>
            """
        )
    player_points_rows = []
    for row in player_rows:
        player_points_rows.append(
            f"""
            <tr>
              <td>{row['rank']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">{escape(row['display_name'])}</a></td>
              <td>{escape(row['team_name'])}</td>
              <td>{row['games_played']}</td>
              <td>{escape(row['record'])}</td>
              <td>{row['points_earned_total']:.2f}</td>
              <td>{row['average_points']:.2f}</td>
              <td>{format_pct(row['win_rate'])}</td>
            </tr>
            """
        )

    team_cards = []
    for row in team_rows:
        team_cards.append(
            f"""
            <div class="col-12 col-md-6">
              <a class="team-link-card shadow-sm p-4 h-100" href="{escape(build_scoped_path('/teams/' + row['team_id'], selected_competition, selected_season, selected_region, selected_series_slug))}">
                <div class="card-kicker mb-2">Team Access</div>
                <h2 class="h4 mb-2">{escape(row['name'])}</h2>
                <div class="small-muted mb-3">当前赛季积分榜第 {row.get('points_rank', row['rank'])} 名 · {row['player_count']} 名队员 · 对局 {row['matches_represented']} 场</div>
                <div class="row g-3">
                  <div class="col-4"><div class="small text-secondary">总积分</div><div class="fw-semibold">{row['points_earned_total']:.2f}</div></div>
                  <div class="col-4"><div class="small text-secondary">场均积分</div><div class="fw-semibold">{row.get('points_per_match', 0.0):.2f}</div></div>
                  <div class="col-4"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(row['win_rate'])}</div></div>
                </div>
              </a>
            </div>
            """
        )

    match_table_rows = []
    for match in match_rows:
        team_names = "、".join(
            sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]})
        )
        match_detail_path = f"/matches/{match['match_id']}?next={quote(build_scoped_path('/competitions', selected_competition, selected_season, selected_region, selected_series_slug))}"
        day_path = build_match_day_path(
            match["played_on"],
            build_scoped_path("/competitions", selected_competition, selected_season, selected_region, selected_series_slug),
        )
        match_table_rows.append(
            f"""
            <tr>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(match['match_id'])}</a></td>
              <td>{escape(match['season'])}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(day_path)}">{escape(match['played_on'])}</a></td>
              <td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td>
              <td>第 {match['round']} 轮</td>
              <td>第 {match['game_no']} 局</td>
              <td>{escape(team_names)}</td>
              <td>{escape(match['table_label'])}</td>
              <td>{escape(match['format'])}</td>
              <td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看详情</a></td>
            </tr>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">{escape(page_badge)}</div>
          <h1 class="hero-title mb-3">{escape(hero_title)}</h1>
          <p class="hero-copy mb-0">{escape(hero_intro)}</p>
          {region_switcher_html}
          {series_switcher_html}
          <div class="hero-switchers mt-3">{competition_switcher}</div>
          {season_switcher_html}
          <div class="hero-kpis">
            <div class="hero-pill">
              <span>参赛战队</span>
              <strong>{len(team_rows)}</strong>
              <small>{escape(selected_season or '当前赛季')} 真实参赛</small>
            </div>
            <div class="hero-pill">
              <span>参赛队员</span>
              <strong>{player_count}</strong>
              <small>{escape(selected_season or '当前赛季')} 已上场</small>
            </div>
            <div class="hero-pill">
              <span>赛季场次</span>
              <strong>{len(match_rows)}</strong>
              <small>{escape(scope_label)} 完整赛程</small>
            </div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Event Sheet</div>
          <div class="hero-stage-label">Season Overview</div>
          <div class="hero-stage-title">{escape(scope_label)}</div>
          <div class="hero-stage-note">{escape(hero_note)}</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>最近比赛日</span>
              <strong>{escape(latest_played_on)}</strong>
              <small>{escape(selected_season or (' / '.join(competition_meta['seasons'][:2]) if competition_meta and competition_meta['seasons'] else '赛季待录入'))}</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛战队</span>
              <strong>{len(team_rows)}</strong>
              <small>该赛季参赛战队</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛队员</span>
              <strong>{player_count}</strong>
              <small>该赛季实际出场</small>
            </div>
            <div class="hero-stage-metric">
              <span>赛季场次</span>
              <strong>{len(match_rows)}</strong>
              <small>该赛季完整赛程</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    {season_registration_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">战队积分排行榜</h2>
          <p class="section-copy mb-0">本榜单按当前赛事与赛季下所有上场队员的个人积分累计而成。也就是说，队员个人积分会直接计入战队赛季积分。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>排名</th>
              <th>战队</th>
              <th>场次</th>
              <th>上场队员</th>
              <th>赛季总积分</th>
              <th>场均积分</th>
              <th>胜率</th>
            </tr>
          </thead>
          <tbody>
            {''.join(team_points_rows) or '<tr><td colspan="7" class="text-secondary">当前赛季还没有战队积分数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">选手积分排行榜</h2>
          <p class="section-copy mb-0">这里按当前赛事与赛季统计个人积分排名，方便直接查看这个小赛季下的选手表现。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>排名</th>
              <th>选手</th>
              <th>战队</th>
              <th>出场</th>
              <th>战绩</th>
              <th>赛季总积分</th>
              <th>场均得分</th>
              <th>胜率</th>
            </tr>
          </thead>
          <tbody>
            {''.join(player_points_rows) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有选手积分数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该赛季战队入口</h2>
          <p class="section-copy mb-0">这里只列出这个系列赛当前赛季真实参赛的战队，避免和其他赛季混在一起。点进战队卡片后，会继续看到同一赛季口径下的统计。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          {create_match_button}
          {edit_competition_button}
          {series_topic_button}
          {schedule_page_button}
          <a class="btn btn-outline-dark" href="{escape(build_scoped_path('/competitions', None, None, selected_region, selected_series_slug))}">返回地区赛事列表</a>
        </div>
      </div>
      <div class="row g-3 g-lg-4">{''.join(team_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前赛季还没有战队数据。</div></div>'}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该赛季完整赛程</h2>
          <p class="section-copy mb-0">先在这里确认当前赛季的轮次和参赛战队，再从上面的战队入口继续查看更深一层的数据页面。</p>
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
              <th>局次</th>
              <th>参赛战队</th>
              <th>桌号</th>
              <th>板型</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(match_table_rows)}</tbody>
        </table>
      </div>
    </section>
    """
    return layout(scope_label, body, ctx, alert=alert)


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
    top_player = displayed_player_rows[0] if displayed_player_rows else None
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
    featured_competition = max(
        scoped_competition_rows or competition_catalog,
        key=lambda row: (row["latest_played_on"], row["competition_name"]),
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
    latest_played_on = max(
        (
            match["played_on"]
            for match in stats_data["matches"]
            if (
                match_in_scope(match, selected_competition, selected_season)
                if selected_competition
                else get_match_competition_name(match) in scoped_competition_names
            )
        ),
        default="待更新",
    )
    featured_seasons = selected_season or (
        " / ".join((selected_series_row or featured_competition or {}).get("seasons", [])[:2])
        if (selected_series_row or featured_competition)
        and (selected_series_row or featured_competition).get("seasons")
        else "赛季待录入"
    )
    region_switcher_html = (
        f'<div class="hero-switchers mt-4">{region_switcher}</div>' if region_switcher else ""
    )
    series_switcher_html = (
        f'<div class="hero-switchers mt-3">{series_switcher}</div>' if series_switcher else ""
    )
    competition_switcher_html = (
        f'<div class="hero-switchers mt-3">{competition_switcher}</div>'
        if competition_switcher and selected_competition
        else ""
    )
    season_switcher_html = (
        f'<div class="hero-switchers mt-3">{season_switcher}</div>' if season_switcher else ""
    )
    stat_cards = f"""
    <div class="row g-3 g-lg-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">官方快照 · 战队</div>
          <div class="stat-value mt-2">{active_team_count}</div>
          <div class="small-muted mt-2">{escape(scope_label)} 口径</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">官方快照 · 队员</div>
          <div class="stat-value mt-2">{active_player_count}</div>
          <div class="small-muted mt-2">当前口径下已出场队员</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">官方快照 · 对局</div>
          <div class="stat-value mt-2">{active_match_count}</div>
          <div class="small-muted mt-2">当前口径下比赛记录</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">实时榜首</div>
          <div class="stat-value mt-2">{escape(top_player['display_name'] if top_player else '-')}</div>
          <div class="small-muted mt-2">{escape(top_player['team_name'] if top_player else '暂无数据')}</div>
        </div>
      </div>
    </div>
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
            <div class="col-12 col-md-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(selected_region or DEFAULT_REGION_NAME)} · Series Topic</div>
                    <h2 class="h4 mb-1">{escape(row['series_name'])}</h2>
                    <div class="small-muted">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '未设置'}</div>
                    <div class="small-muted mt-1">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div>
                  </div>
                  <span class="chip">专题页 + 地区站点</span>
                </div>
                <div class="row g-3 mt-2">
                  <div class="col-4">
                    <div class="small text-secondary">战队</div>
                    <div class="fw-semibold">{row['team_count']} 支</div>
                  </div>
                  <div class="col-4">
                    <div class="small text-secondary">队员</div>
                    <div class="fw-semibold">{row['player_count']} 名</div>
                  </div>
                  <div class="col-4">
                    <div class="small text-secondary">对局</div>
                    <div class="fw-semibold">{row['match_count']} 场</div>
                  </div>
                </div>
                <div class="d-flex flex-wrap gap-2 mt-4">
                  <a class="btn btn-dark" href="{escape(topic_path)}">查看系列专题</a>
                  <a class="btn btn-outline-dark" href="{escape(competition_path)}">进入地区赛事页</a>
                </div>
              </div>
            </div>
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
            <div class="col-12 col-md-6 col-xl-4">
              <a class="team-link-card shadow-sm p-4 h-100" href="{escape(build_match_day_path(played_on, build_scoped_path('/dashboard', selected_competition, selected_season, selected_region, selected_series_slug)))}">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">Match Day</div>
                    <h2 class="h4 mb-1">{escape(played_on)}</h2>
                    <div class="small-muted">系列赛 {len(day_competitions)} 个 · 比赛 {len(day_matches)} 场</div>
                    <div class="small-muted mt-1">{escape('、'.join(day_competitions[:2]))}{' 等' if len(day_competitions) > 2 else ''}</div>
                  </div>
                  <span class="chip">查看当日总览</span>
                </div>
              </a>
            </div>
            """
        )

    player_rows_html = []
    for row in displayed_player_rows[:10]:
        player_rows_html.append(
            f"""
            <tr>
              <td>{row['rank']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + row['player_id'], selected_competition, selected_season))}">{escape(row['display_name'])}</a></td>
              <td>{escape(row['team_name'])}</td>
              <td>{row['games_played']}</td>
              <td>{escape(row['record'])}</td>
              <td>{format_pct(row['win_rate'])}</td>
              <td>{format_pct(row['stance_rate'])}</td>
              <td>{row['points_earned_total']:.2f}</td>
              <td>{row['average_points']:.2f}</td>
            </tr>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">官方赛事数据中心</div>
          <h1 class="hero-title mb-3">{escape(selected_region or DEFAULT_REGION_NAME)}赛区首页<br>像赛事官网一样浏览榜单与赛程</h1>
          <p class="hero-copy mb-0">未登录时首页默认显示广州赛区；登录后会优先按你的账号地区展示对应赛区。先切换地区，再切换系列赛；如果进入某个地区赛事页，就可以继续选择赛季，并查看该站独立的战队和队员数据。</p>
          {region_switcher_html}
          {series_switcher_html}
          {competition_switcher_html}
          {season_switcher_html}
          <div class="hero-kpis">
            <div class="hero-pill">
              <span>地区系列赛</span>
              <strong>{len(scoped_competition_rows)}</strong>
              <small>{escape(selected_region or DEFAULT_REGION_NAME)} 当前站点</small>
            </div>
            <div class="hero-pill">
              <span>当前对局</span>
              <strong>{active_match_count}</strong>
              <small>{escape(scope_label)}</small>
            </div>
            <div class="hero-pill">
              <span>当前榜首</span>
              <strong>{escape(top_player['display_name'] if top_player else '待更新')}</strong>
              <small>{escape(top_player['team_name'] if top_player else '暂无数据')}</small>
            </div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Data Panel</div>
          <div class="hero-stage-label">Featured Scope</div>
          <div class="hero-stage-title">{escape(featured_label)}</div>
          <div class="hero-stage-note">数据更新时间 {escape(ctx.now_label)}。当前视角为 {escape(scope_label)}，适合先总览官方榜单，再继续进入单个赛事页面。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>最近比赛日</span>
              <strong>{escape(latest_played_on)}</strong>
              <small>{escape(featured_seasons)}</small>
            </div>
            <div class="hero-stage-metric">
              <span>收录战队</span>
              <strong>{active_team_count}</strong>
              <small>当前口径下战队</small>
            </div>
            <div class="hero-stage-metric">
              <span>收录队员</span>
              <strong>{active_player_count}</strong>
              <small>当前口径下出场</small>
            </div>
            <div class="hero-stage-metric">
              <span>实时榜首</span>
              <strong>{escape(top_player['display_name'] if top_player else '待更新')}</strong>
              <small>{escape(top_player['team_name'] if top_player else '暂无数据')}</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    {stat_cards}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">系列赛专题入口</h2>
          <p class="section-copy mb-0">这里优先展示当前地区的系列赛专题。进入专题后，可以把同一品牌下不同地区的比赛一起查看；进入地区赛事页，则会保留单站视角。</p>
        </div>
        <a class="btn btn-outline-dark" href="/competitions">进入全部赛事</a>
      </div>
      <div class="row g-3 g-lg-4">
        {''.join(series_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前地区还没有系列赛，请先创建系列赛目录。</div></div>'}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近比赛日</h2>
          <p class="section-copy mb-0">每个有比赛的日期都可以单独打开一个页面。进入后会按系列赛展示当天总览，并可继续点击单场详情。</p>
        </div>
      </div>
      <div class="row g-3 g-lg-4">
        {''.join(recent_day_cards)}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">官方榜单 · 队员表现前十</h2>
          <p class="section-copy mb-0">这里先给出官网首页的总榜视图。你可以保持全部赛事汇总，也可以切到单个系列赛和赛季，再点进队员页面看更完整的个人数据面板。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>排名</th>
              <th>队员</th>
              <th>战队</th>
              <th>出场</th>
              <th>战绩</th>
              <th>胜率</th>
              <th>站边率</th>
              <th>总积分</th>
              <th>场均得分</th>
            </tr>
          </thead>
          <tbody>
            {''.join(player_rows_html)}
          </tbody>
        </table>
      </div>
    </section>
    """
    return layout("首页", body, ctx, alert=alert)


def get_series_page(ctx: RequestContext, series_slug: str) -> str:
    data = load_validated_data()
    catalog = load_series_catalog(data)
    series_entries = get_series_entries_by_slug(catalog, series_slug)
    if not series_entries:
        return layout(
            "未找到系列赛",
            '<div class="alert alert-danger">没有找到对应的系列赛专题页。</div>',
            ctx,
        )

    competition_rows = build_competition_catalog_rows(data, catalog)
    series_rows = [
        row for row in competition_rows if row["series_slug"] == series_slug
    ]
    if not series_rows:
        return layout(
            "未找到系列赛",
            '<div class="alert alert-danger">该系列赛还没有关联任何地区赛事。</div>',
            ctx,
        )

    allowed_competitions = {row["competition_name"] for row in series_rows}
    series_data = build_filtered_data(data, allowed_competitions)
    season_names = list_seasons(series_data, series_slug=series_slug)
    selected_season = get_selected_season(ctx, season_names)
    filtered_matches = [
        match
        for match in sorted(
            series_data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if not selected_season or (match.get("season") or "").strip() == selected_season
    ]
    filtered_series_data = {
        "teams": series_data["teams"],
        "players": series_data["players"],
        "matches": filtered_matches,
    }
    player_rows = [
        row for row in build_player_rows(filtered_series_data) if row["games_played"] > 0
    ]
    team_rows = [
        row
        for row in build_team_rows(filtered_series_data)
        if row["matches_represented"] > 0
    ]
    team_rows.sort(
        key=lambda row: (
            row.get("points_rank", 9999),
            -row["points_earned_total"],
            row["name"],
        )
    )
    player_rows.sort(
        key=lambda row: (
            row["rank"],
            -row["points_earned_total"],
            row["display_name"],
        )
    )
    season_switcher = build_series_season_switcher(
        series_slug,
        season_names,
        selected_season,
    )
    season_switcher_html = (
        f'<div class="hero-switchers mt-4">{season_switcher}</div>' if season_switcher else ""
    )
    region_names = "、".join(sorted({row["region_name"] for row in series_rows}))
    latest_played_on = max((match["played_on"] for match in filtered_matches), default="待更新")
    top_player = player_rows[0] if player_rows else None
    region_cards = []
    for row in series_rows:
        competition_path = build_scoped_path(
            "/competitions",
            row["competition_name"],
            selected_season if selected_season in row["seasons"] else None,
            row["region_name"],
            row["series_slug"],
        )
        region_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <a class="team-link-card shadow-sm p-4 h-100" href="{escape(competition_path)}">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(row['region_name'])} · Regional Event</div>
                    <h2 class="h4 mb-2">{escape(row['competition_name'])}</h2>
                    <div class="small-muted mb-2">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div>
                    <div class="small-muted">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div>
                  </div>
                  <span class="chip">进入地区赛事页</span>
                </div>
                <div class="row g-3 mt-2">
                  <div class="col-4"><div class="small text-secondary">战队</div><div class="fw-semibold">{row['team_count']} 支</div></div>
                  <div class="col-4"><div class="small text-secondary">队员</div><div class="fw-semibold">{row['player_count']} 名</div></div>
                  <div class="col-4"><div class="small text-secondary">对局</div><div class="fw-semibold">{row['match_count']} 场</div></div>
                </div>
              </a>
            </div>
            """
        )

    match_rows_html = []
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    for match in filtered_matches[:12]:
        detail_path = f"/matches/{match['match_id']}?next={quote(build_series_topic_path(series_slug, selected_season))}"
        competition_name = get_match_competition_name(match)
        series_entry = get_series_entry_by_competition(catalog, competition_name)
        region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
        team_names = "、".join(
            sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]})
        )
        match_rows_html.append(
            f"""
            <tr>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(detail_path)}">{escape(match['match_id'])}</a></td>
              <td>{escape(region_name)}</td>
              <td>{escape(competition_name)}</td>
              <td>{escape(match['played_on'])}</td>
              <td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td>
              <td>第 {match['round']} 轮 / 第 {match['game_no']} 局</td>
              <td>{escape(team_names)}</td>
              <td><a class="btn btn-sm btn-outline-dark" href="{escape(detail_path)}">详情</a></td>
            </tr>
            """
        )

    team_points_rows = []
    for row in team_rows:
        team_points_rows.append(
            f"""
            <tr>
              <td>{row.get('points_rank', '-')}</td>
              <td>{escape(row['name'])}</td>
              <td>{row['matches_represented']}</td>
              <td>{row['player_count']}</td>
              <td>{row['points_earned_total']:.2f}</td>
              <td>{row.get('points_per_match', 0.0):.2f}</td>
              <td>{format_pct(row['win_rate'])}</td>
            </tr>
            """
        )

    leaderboard_rows = []
    for row in player_rows:
        detail_path = f"/players/{row['player_id']}"
        leaderboard_rows.append(
            f"""
            <tr>
              <td>{row['rank']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(detail_path)}">{escape(row['display_name'])}</a></td>
              <td>{escape(row['team_name'])}</td>
              <td>{row['games_played']}</td>
              <td>{escape(row['record'])}</td>
              <td>{row['points_earned_total']:.2f}</td>
              <td>{row['average_points']:.2f}</td>
              <td>{format_pct(row['win_rate'])}</td>
            </tr>
            """
        )

    manage_button = ""
    if can_access_series_management(ctx.current_user):
        manage_button = '<a class="btn btn-outline-dark" href="/series-manage">维护系列赛目录</a>'

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">系列赛专题页</div>
          <h1 class="hero-title mb-3">{escape(series_rows[0]['series_name'])}</h1>
          <p class="hero-copy mb-0">这里会把同一系列赛在不同地区的比赛放到同一个专题页下浏览。你可以继续切换赛季，再进入任一地区赛事页查看该站独立数据。</p>
          {season_switcher_html}
          <div class="hero-kpis">
            <div class="hero-pill">
              <span>覆盖地区</span>
              <strong>{len(series_rows)}</strong>
              <small>{escape(region_names)}</small>
            </div>
            <div class="hero-pill">
              <span>专题场次</span>
              <strong>{len(filtered_matches)}</strong>
              <small>{escape(selected_season or '全部赛季')}</small>
            </div>
            <div class="hero-pill">
              <span>专题榜首</span>
              <strong>{escape(top_player['display_name'] if top_player else '待更新')}</strong>
              <small>{escape(top_player['team_name'] if top_player else '暂无数据')}</small>
            </div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Cross Region Series</div>
          <div class="hero-stage-label">Series Snapshot</div>
          <div class="hero-stage-title">{escape(selected_season or '全部赛季')}</div>
          <div class="hero-stage-note">这个专题页按系列赛品牌聚合，不按单一地区拆分。需要查看某个地区独立赛程时，可直接进入下面的地区赛事页。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>最近比赛日</span>
              <strong>{escape(latest_played_on)}</strong>
              <small>{escape(region_names)}</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛战队</span>
              <strong>{len(team_rows)}</strong>
              <small>当前专题战队</small>
            </div>
            <div class="hero-stage-metric">
              <span>参赛队员</span>
              <strong>{len(player_rows)}</strong>
              <small>当前专题出场</small>
            </div>
            <div class="hero-stage-metric">
              <span>地区站点</span>
              <strong>{len(series_rows)}</strong>
              <small>系列赛覆盖地区</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">地区赛事页</h2>
          <p class="section-copy mb-0">同一系列赛的不同地区站点会一起列在这里，点击后可进入各地区自己的赛季页与战队页。</p>
        </div>
        <div class="d-flex flex-wrap gap-2">
          {manage_button}
          <a class="btn btn-outline-dark" href="{escape(build_scoped_path('/dashboard', None, None, DEFAULT_REGION_NAME, None))}">返回首页</a>
        </div>
      </div>
      <div class="row g-3 g-lg-4">{''.join(region_cards)}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">专题战队积分排行榜</h2>
          <p class="section-copy mb-0">这里会把同一系列赛下不同地区、同一赛季的战队积分合并统计，形成该系列赛赛季口径的官方战队积分榜。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>排名</th>
              <th>战队</th>
              <th>场次</th>
              <th>上场队员</th>
              <th>赛季总积分</th>
              <th>场均积分</th>
              <th>胜率</th>
            </tr>
          </thead>
          <tbody>
            {''.join(team_points_rows) or '<tr><td colspan="7" class="text-secondary">当前赛季还没有战队积分数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">专题选手积分排行榜</h2>
          <p class="section-copy mb-0">该榜单会把同系列赛下不同地区、同一赛季的比赛一起统计，形成该系列赛赛季口径的选手积分榜。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>排名</th>
              <th>选手</th>
              <th>战队</th>
              <th>出场</th>
              <th>战绩</th>
              <th>赛季总积分</th>
              <th>场均得分</th>
              <th>胜率</th>
            </tr>
          </thead>
          <tbody>
            {''.join(leaderboard_rows) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有选手积分数据。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">系列赛全部场次</h2>
          <p class="section-copy mb-0">这里展示当前专题页下最近的场次，方便跨地区追踪同系列赛进展。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>编号</th>
              <th>地区</th>
              <th>赛事页</th>
              <th>日期</th>
              <th>阶段</th>
              <th>轮次</th>
              <th>参赛战队</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {''.join(match_rows_html) or '<tr><td colspan="8" class="text-secondary">当前赛季还没有比赛记录。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    """
    return layout(f"{series_rows[0]['series_name']} 专题页", body, ctx)


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


def get_series_manage_page(
    ctx: RequestContext,
    alert: str = "",
    form_values: dict[str, str] | None = None,
) -> str:
    data = load_validated_data()
    catalog = load_series_catalog(data)
    season_catalog = load_season_catalog(data)
    manageable_catalog = [
        entry for entry in catalog if can_manage_series_entry(ctx.current_user, entry)
    ] if not is_admin_user(ctx.current_user) else catalog
    competition_rows = build_competition_catalog_rows(data, manageable_catalog)
    requested_competition_name = form_value(ctx.query, "competition_name").strip()
    requested_season_name = form_value(ctx.query, "season_name").strip()
    requested_edit_mode = (
        str(form_values.get("edit_mode") or "").strip()
        if form_values and form_values.get("edit_mode") is not None
        else form_value(ctx.query, "edit").strip()
    )
    if requested_edit_mode not in {"catalog", "season", "create"}:
        requested_edit_mode = ""
    selected_entry = (
        get_series_entry_by_competition(manageable_catalog, requested_competition_name)
        if requested_competition_name
        else None
    )
    if requested_competition_name and not selected_entry:
        return layout(
            "没有权限",
            '<div class="alert alert-danger">你只能管理自己负责地区系列赛下的赛季和赛事页。</div>',
            ctx,
            alert=alert,
        )
    selected_season_entry = (
        get_season_entry(
            season_catalog,
            selected_entry["series_slug"],
            requested_season_name,
            competition_name=requested_competition_name,
        )
        if selected_entry and requested_season_name
        else None
    )
    current_form = {
        "series_name": "",
        "series_code": "",
        "region_name": DEFAULT_REGION_NAME,
        "competition_name": "",
        "summary": "",
        "page_badge": "",
        "hero_title": "",
        "hero_intro": "",
        "hero_note": "",
        "original_competition_name": "",
        "next": form_value(ctx.query, "next").strip(),
        "edit_mode": requested_edit_mode,
    }
    season_form = {
        "competition_name": requested_competition_name,
        "original_season_name": requested_season_name,
        "season_name": "",
        "start_at": "",
        "end_at": "",
        "notes": "",
        "edit_mode": requested_edit_mode,
    }
    if selected_entry:
        current_form.update(
            {
                "series_name": selected_entry["series_name"],
                "series_code": selected_entry["series_code"],
                "region_name": selected_entry["region_name"],
                "competition_name": selected_entry["competition_name"],
                "summary": selected_entry.get("summary", ""),
                "page_badge": selected_entry.get("page_badge", ""),
                "hero_title": selected_entry.get("hero_title", ""),
                "hero_intro": selected_entry.get("hero_intro", ""),
                "hero_note": selected_entry.get("hero_note", ""),
                "original_competition_name": selected_entry["competition_name"],
            }
        )
    if selected_season_entry:
        season_form.update(
            {
                "competition_name": requested_competition_name,
                "original_season_name": selected_season_entry["season_name"],
                "season_name": selected_season_entry["season_name"],
                "start_at": selected_season_entry.get("start_at", ""),
                "end_at": selected_season_entry.get("end_at", ""),
                "notes": selected_season_entry.get("notes", ""),
            }
        )
    if form_values:
        current_form.update(form_values)
        season_form.update(
            {
                key: form_values[key]
                for key in ("competition_name", "original_season_name", "season_name", "start_at", "end_at", "notes", "edit_mode")
                if key in form_values
            }
        )
    editing_existing = bool(current_form["original_competition_name"])
    return_path = current_form["next"].strip() or "/series-manage"
    return_label = "返回赛事页" if current_form["next"].strip() else "返回系列赛列表"
    form_heading = "编辑赛事页信息" if editing_existing else "新建地区系列赛"
    form_copy = (
        "这里可以调整这个地区赛事页的顶部标识、主标题、导语和说明文案。为了避免历史比赛脱钩，已有赛事页名称在编辑模式下保持只读。"
        if editing_existing
        else "如果同一系列赛要在多个地区共用一个专题页，请保持“系列编码”一致，例如同系列的广州站和北京站都使用同一个编码。"
    )
    competition_name_field = (
        f"""
        <input class="form-control" name="competition_name" value="{escape(current_form['competition_name'])}" readonly>
        <div class="small text-secondary mt-2">已有赛事页名称作为比赛挂载键使用，当前编辑模式下保持只读。</div>
        """
        if editing_existing
        else f'<input class="form-control" name="competition_name" value="{escape(current_form["competition_name"])}" required>'
    )
    region_name_field = (
        f"""
        <input class="form-control" name="region_name" value="{escape(current_form['region_name'])}" readonly>
        <div class="small text-secondary mt-2">已有地区赛事页的所属地区会参与赛事负责人权限匹配，编辑模式下保持只读。</div>
        """
        if editing_existing
        else f'<input class="form-control" name="region_name" value="{escape(current_form["region_name"])}" required>'
    )
    selected_competition_name = current_form["competition_name"].strip()
    selected_series_slug = selected_entry["series_slug"] if selected_entry else ""
    can_edit_selected_catalog = bool(
        selected_competition_name
        and can_manage_competition_catalog(ctx.current_user, data, selected_competition_name)
    )
    can_manage_selected_seasons = bool(
        selected_competition_name
        and can_manage_competition_seasons(ctx.current_user, data, selected_competition_name)
    )
    catalog_editor_active = bool(
        requested_edit_mode == "catalog"
        or (requested_edit_mode == "create" and is_admin_user(ctx.current_user))
    )
    season_editor_active = bool(requested_edit_mode == "season")
    competition_season_entries = (
        get_season_entries_for_series(
            season_catalog,
            selected_series_slug,
            include_non_ongoing=True,
            competition_name=selected_competition_name,
        )
        if selected_series_slug
        else []
    )

    existing_cards = []
    for row in competition_rows:
        detail_path = build_series_manage_path(row["competition_name"], current_form["next"])
        edit_path = build_series_manage_path(
            row["competition_name"],
            current_form["next"],
            None,
            "catalog",
        )
        season_manage_path = build_series_manage_path(
            row["competition_name"],
            current_form["next"],
            None,
            "season",
        )
        row_can_edit_catalog = can_manage_competition_catalog(
            ctx.current_user,
            data,
            row["competition_name"],
        )
        row_can_manage_seasons = can_manage_competition_seasons(
            ctx.current_user,
            data,
            row["competition_name"],
        )
        is_selected_row = row["competition_name"] == selected_competition_name
        existing_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">{escape(row['region_name'])} · {escape(row['series_name'])}</div>
                    <h2 class="h5 mb-2">{escape(row['competition_name'])}</h2>
                    <div class="small-muted">系列编码 {escape(row['series_code'])} · 赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '待录入'}</div>
                    <div class="small-muted mt-1">最近比赛日 {escape(row['latest_played_on'] or '待更新')}</div>
                  </div>
                  <span class="chip">{'当前查看' if is_selected_row else ('启用中' if row['active'] else '已停用')}</span>
                </div>
                <p class="section-copy mt-3 mb-2">{escape(row['summary'] or '暂无专题说明。')}</p>
                <div class="small-muted">赛事页标题 {escape(row.get('hero_title') or row['competition_name'])}</div>
                <div class="small-muted mt-1">顶部标识 {escape(row.get('page_badge') or (row['region_name'] + ' · 赛事专属页面'))}</div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(detail_path)}">查看详情</a>
                  {(
                    f'<a class="btn btn-sm btn-outline-dark" href="{escape(edit_path)}">编辑赛事页</a>'
                    if row_can_edit_catalog
                    else ''
                  )}
                  {(
                    f'<a class="btn btn-sm btn-outline-dark" href="{escape(season_manage_path)}">赛季管理</a>'
                    if row_can_manage_seasons
                    else ''
                  )}
                  <a class="btn btn-sm btn-outline-dark" href="{escape(build_scoped_path('/competitions', row['competition_name'], None, row['region_name'], row['series_slug']))}">打开赛事页</a>
                </div>
              </div>
            </div>
            """
        )

    selected_overview_html = ""
    if selected_entry:
        selected_competition_path = build_scoped_path(
            "/competitions",
            selected_entry["competition_name"],
            None,
            selected_entry["region_name"],
            selected_entry["series_slug"],
        )
        selected_overview_html = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-4">
            <div>
              <div class="eyebrow mb-2">{escape(selected_entry['region_name'])} · {escape(selected_entry['series_name'])}</div>
              <h2 class="section-title mb-2">{escape(selected_entry['competition_name'])}</h2>
              <p class="section-copy mb-0">默认只读展示这个地区系列赛的信息。需要修改时，再进入单独的编辑页。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              <a class="btn btn-outline-dark" href="/series-manage">返回全部系列赛</a>
              {(
                f'<a class="btn btn-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "catalog"))}">编辑赛事页</a>'
                if can_edit_selected_catalog
                else ''
              )}
              {(
                f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "season"))}">新增赛季</a>'
                if can_manage_selected_seasons
                else ''
              )}
              <a class="btn btn-outline-dark" href="{escape(selected_competition_path)}">打开赛事页</a>
            </div>
          </div>
          <div class="row g-3">
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">系列编码</div>
                <div class="fw-semibold mt-1">{escape(selected_entry['series_code'])}</div>
                <div class="small text-secondary mt-3">赛事页标题</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_title') or selected_entry['competition_name'])}</div>
                <div class="small text-secondary mt-3">顶部标识</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('page_badge') or (selected_entry['region_name'] + ' · 赛事专属页面'))}</div>
              </div>
            </div>
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">专题说明</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('summary') or '暂无专题说明')}</div>
                <div class="small text-secondary mt-3">导语</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_intro') or '暂无导语')}</div>
                <div class="small text-secondary mt-3">说明备注</div>
                <div class="fw-semibold mt-1">{escape(selected_entry.get('hero_note') or '暂无说明备注')}</div>
              </div>
            </div>
          </div>
        </section>
        """

    selected_season_overview_html = ""
    if selected_season_entry:
        selected_season_overview_html = f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3">
            <div>
              <div class="eyebrow mb-2">当前赛季</div>
              <h2 class="section-title mb-2">{escape(selected_season_entry['season_name'])}</h2>
              <p class="section-copy mb-0">这里先显示赛季信息。只有点“编辑当前赛季”才会进入修改模式。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {(
                f'<a class="btn btn-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], selected_season_entry["season_name"], "season"))}">编辑当前赛季</a>'
                if can_manage_selected_seasons
                else ''
              )}
              <a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form['next']))}">返回该系列赛</a>
            </div>
          </div>
          <div class="row g-3 mt-1">
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">开始时间</div>
                <div class="fw-semibold mt-1">{escape(format_datetime_local_label(selected_season_entry.get('start_at', '')))}</div>
              </div>
            </div>
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">结束时间</div>
                <div class="fw-semibold mt-1">{escape(format_datetime_local_label(selected_season_entry.get('end_at', '')))}</div>
              </div>
            </div>
            <div class="col-12 col-lg-4">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="small text-secondary">状态</div>
                <div class="fw-semibold mt-1">{escape(season_status_label(selected_season_entry))}</div>
              </div>
            </div>
            <div class="col-12">
              <div class="team-link-card shadow-sm p-4">
                <div class="small text-secondary">赛季说明</div>
                <div class="fw-semibold mt-1">{escape(selected_season_entry.get('notes') or '暂无赛季说明')}</div>
              </div>
            </div>
          </div>
        </section>
        """

    season_cards = []
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    for season_entry in competition_season_entries:
        season_detail_path = build_series_manage_path(
            selected_competition_name,
            current_form["next"],
            season_entry["season_name"],
        )
        season_edit_path = build_series_manage_path(
            selected_competition_name,
            current_form["next"],
            season_entry["season_name"],
            "season",
        )
        registered_team_names = [
            team_lookup[team_id]["name"]
            for team_id in season_entry.get("registered_team_ids", [])
            if team_id in team_lookup
        ]
        season_cards.append(
            f"""
            <div class="col-12 col-lg-6">
              <div class="team-link-card shadow-sm p-4 h-100">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="card-kicker mb-2">赛季档期</div>
                    <h2 class="h5 mb-2">{escape(season_entry['season_name'])}</h2>
                    <div class="small-muted">起止时间 {escape(format_datetime_local_label(season_entry.get('start_at', '')))} - {escape(format_datetime_local_label(season_entry.get('end_at', '')))}</div>
                    <div class="small-muted mt-1">状态 {escape(season_status_label(season_entry))} · 已报名战队 {len(season_entry.get('registered_team_ids', []))} 支</div>
                  </div>
                  <span class="chip">{'当前赛季' if season_entry['season_name'] == requested_season_name else escape(season_status_label(season_entry))}</span>
                </div>
                <p class="section-copy mt-3 mb-2">{escape(season_entry.get('notes') or '这个赛季还没有补充说明。')}</p>
                <div class="small-muted">{escape('、'.join(registered_team_names) if registered_team_names else '当前还没有战队报名。')}</div>
                <div class="d-flex flex-wrap gap-2 mt-3">
                  <a class="btn btn-sm btn-outline-dark" href="{escape(season_detail_path)}">查看赛季</a>
                  {(
                    f'<a class="btn btn-sm btn-outline-dark" href="{escape(season_edit_path)}">编辑赛季</a>'
                    if can_manage_selected_seasons
                    else ''
                  )}
                </div>
              </div>
            </div>
            """
        )

    season_section_html = ""
    if selected_entry:
        season_section_html = selected_season_overview_html + f"""
        <section class="panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">赛季列表</h2>
              <p class="section-copy mb-0">赛季信息默认只读展示。点击某个赛季的编辑按钮后，再单独修改该赛季。</p>
            </div>
            <div class="d-flex flex-wrap gap-2">
              {(
                f'<a class="btn btn-outline-dark" href="{escape(build_series_manage_path(selected_competition_name, current_form["next"], None, "season"))}">新建赛季</a>'
                if can_manage_selected_seasons
                else ''
              )}
            </div>
          </div>
          <div class="row g-3 g-lg-4">{''.join(season_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">这个赛事页还没有配置赛季，请先创建第一个赛季。</div></div>'}</div>
        </section>
        """
        if season_editor_active:
            if can_manage_selected_seasons:
                delete_season_form_html = ""
                delete_season_helper_html = '<div class="small text-secondary">当前正在新建赛季，保存后会回到正常展示状态。</div>'
                if season_form["original_season_name"]:
                    target_season_name = season_form["original_season_name"]
                    target_season_entry = get_season_entry(
                        season_catalog,
                        selected_series_slug,
                        target_season_name,
                        competition_name=selected_competition_name,
                    )
                    selected_season_has_matches = any(
                        get_match_competition_name(match) == selected_competition_name
                        and str(match.get("season") or "").strip() == target_season_name
                        for match in data["matches"]
                    )
                    selected_season_registered_team_count = (
                        len(target_season_entry.get("registered_team_ids", []))
                        if target_season_entry
                        else 0
                    )
                    delete_button_disabled = ""
                    delete_button_confirm = ' onclick="return confirm(\'确认删除当前赛季吗？该操作不可恢复。\')"'
                    if selected_season_has_matches:
                        delete_button_disabled = " disabled"
                        delete_button_confirm = ""
                        delete_season_helper_html = '<div class="small text-secondary">当前赛季下已经存在比赛记录，因此不能直接删除。</div>'
                    elif selected_season_registered_team_count:
                        delete_button_disabled = " disabled"
                        delete_button_confirm = ""
                        delete_season_helper_html = f'<div class="small text-secondary">当前赛季下还有 {selected_season_registered_team_count} 支已报名战队，清空报名后才能删除。</div>'
                    else:
                        delete_season_helper_html = '<div class="small text-secondary">当前赛季还没有比赛记录，也没有已报名战队，可以直接删除。</div>'
                    delete_season_form_html = f"""
                    <form method="post" action="/series-manage" class="m-0">
                      <input type="hidden" name="action" value="delete_season">
                      <input type="hidden" name="competition_name" value="{escape(selected_competition_name)}">
                      <input type="hidden" name="season_name" value="{escape(target_season_name)}">
                      <input type="hidden" name="next" value="{escape(current_form['next'])}">
                      <button type="submit" class="btn btn-outline-danger"{delete_button_disabled}{delete_button_confirm}>删除当前赛季</button>
                    </form>
                    """
                season_form_title = "编辑赛季档期" if season_form["original_season_name"] else "新建赛季档期"
                season_cancel_path = build_series_manage_path(
                    selected_competition_name,
                    current_form["next"],
                    season_form["original_season_name"] or requested_season_name or None,
                )
                season_section_html = f"""
                <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                    <div>
                      <h2 class="section-title mb-2">{season_form_title}</h2>
                      <p class="section-copy mb-0">赛季信息与列表页分开编辑，保存后会回到正常展示状态。</p>
                    </div>
                  </div>
                  <form method="post" action="/series-manage">
                    <input type="hidden" name="action" value="save_season">
                    <input type="hidden" name="edit_mode" value="season">
                    <input type="hidden" name="competition_name" value="{escape(selected_competition_name)}">
                    <input type="hidden" name="original_season_name" value="{escape(season_form['original_season_name'])}">
                    <input type="hidden" name="next" value="{escape(current_form['next'])}">
                    <div class="row g-3">
                      <div class="col-12 col-md-4">
                        <label class="form-label">赛季名称</label>
                        <input class="form-control" name="season_name" value="{escape(season_form['season_name'])}" placeholder="例如：2026春季联赛" required>
                      </div>
                      <div class="col-12 col-md-4">
                        <label class="form-label">开始时间</label>
                        <input class="form-control" name="start_at" type="datetime-local" value="{escape(season_form['start_at'])}" required>
                      </div>
                      <div class="col-12 col-md-4">
                        <label class="form-label">结束时间</label>
                        <input class="form-control" name="end_at" type="datetime-local" value="{escape(season_form['end_at'])}" required>
                      </div>
                      <div class="col-12">
                        <label class="form-label">赛季说明</label>
                        <textarea class="form-control" name="notes" rows="3" placeholder="可写赛季定位、报名要求或档期说明。">{escape(season_form['notes'])}</textarea>
                      </div>
                    </div>
                    <div class="d-flex flex-wrap gap-2 mt-4">
                      <button type="submit" class="btn btn-dark">保存赛季档期</button>
                      <a class="btn btn-outline-dark" href="{escape(season_cancel_path)}">取消编辑</a>
                    </div>
                  </form>
                  <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-2 mt-2">
                    <div>{delete_season_helper_html}</div>
                    <div class="d-flex flex-wrap gap-2">{delete_season_form_html}</div>
                  </div>
                </section>
                """ + season_section_html
            else:
                season_section_html = """
                <section class="panel shadow-sm p-3 p-lg-4 mb-4">
                  <div class="alert alert-secondary mb-0">你当前可以查看这个地区系列赛，但没有赛季档期管理权限。</div>
                </section>
                """ + season_section_html

    catalog_form_html = ""
    if catalog_editor_active:
        if editing_existing and can_edit_selected_catalog:
            catalog_cancel_path = build_series_manage_path(
                selected_competition_name,
                current_form["next"],
                requested_season_name or None,
            )
            catalog_form_html = f"""
            <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">{form_heading}</h2>
                  <p class="section-copy mb-0">{form_copy}</p>
                </div>
              </div>
              <form method="post" action="/series-manage">
                <input type="hidden" name="original_competition_name" value="{escape(current_form['original_competition_name'])}">
                <input type="hidden" name="edit_mode" value="catalog">
                <input type="hidden" name="next" value="{escape(current_form['next'])}">
                <div class="row g-3">
                  <div class="col-12 col-md-6">
                    <label class="form-label">系列赛名称</label>
                    <input class="form-control" name="series_name" value="{escape(current_form['series_name'])}" required>
                  </div>
                  <div class="col-12 col-md-6">
                    <label class="form-label">系列编码</label>
                    <input class="form-control" name="series_code" value="{escape(current_form['series_code'])}" placeholder="可选，留空则自动生成">
                  </div>
                  <div class="col-12 col-md-4">
                    <label class="form-label">地区</label>
                    {region_name_field}
                  </div>
                  <div class="col-12 col-md-8">
                    <label class="form-label">地区赛事页名称</label>
                    {competition_name_field}
                  </div>
                  <div class="col-12">
                    <label class="form-label">专题说明</label>
                    <textarea class="form-control" name="summary" rows="3">{escape(current_form['summary'])}</textarea>
                  </div>
                  <div class="col-12 col-md-6">
                    <label class="form-label">赛事页顶部标识</label>
                    <input class="form-control" name="page_badge" value="{escape(current_form['page_badge'])}" placeholder="例如：广州 · 春季公开赛官方页">
                  </div>
                  <div class="col-12 col-md-6">
                    <label class="form-label">赛事页主标题</label>
                    <input class="form-control" name="hero_title" value="{escape(current_form['hero_title'])}" placeholder="留空则默认显示赛事页名称">
                  </div>
                  <div class="col-12">
                    <label class="form-label">赛事页导语</label>
                    <textarea class="form-control" name="hero_intro" rows="3" placeholder="展示在赛事页头部左侧，适合写当前赛事定位、浏览方式和亮点。">{escape(current_form['hero_intro'])}</textarea>
                  </div>
                  <div class="col-12">
                    <label class="form-label">赛事页说明备注</label>
                    <textarea class="form-control" name="hero_note" rows="3" placeholder="展示在赛事页头部右侧信息卡，适合写这个赛区、本赛季或该赛事页的说明。">{escape(current_form['hero_note'])}</textarea>
                  </div>
                </div>
                <div class="d-flex flex-wrap gap-2 mt-4">
                  <button type="submit" class="btn btn-dark">保存赛事页信息</button>
                  <a class="btn btn-outline-dark" href="{escape(catalog_cancel_path)}">取消编辑</a>
                </div>
              </form>
            </section>
            """
        elif editing_existing:
            catalog_form_html = """
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="alert alert-secondary mb-0">你当前可以查看这个地区系列赛，但没有赛事页信息编辑权限。</div>
            </section>
            """
        elif is_admin_user(ctx.current_user):
            catalog_form_html = f"""
        <section class="form-panel shadow-sm p-3 p-lg-4 mb-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
            <div>
              <h2 class="section-title mb-2">{form_heading}</h2>
              <p class="section-copy mb-0">{form_copy}</p>
            </div>
          </div>
          <form method="post" action="/series-manage">
            <input type="hidden" name="original_competition_name" value="{escape(current_form['original_competition_name'])}">
            <input type="hidden" name="edit_mode" value="create">
            <input type="hidden" name="next" value="{escape(current_form['next'])}">
            <div class="row g-3">
              <div class="col-12 col-md-6">
                <label class="form-label">系列赛名称</label>
                <input class="form-control" name="series_name" value="{escape(current_form['series_name'])}" required>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">系列编码</label>
                <input class="form-control" name="series_code" value="{escape(current_form['series_code'])}" placeholder="可选，留空则自动生成">
              </div>
              <div class="col-12 col-md-4">
                <label class="form-label">地区</label>
                {region_name_field}
              </div>
              <div class="col-12 col-md-8">
                <label class="form-label">地区赛事页名称</label>
                {competition_name_field}
              </div>
              <div class="col-12">
                <label class="form-label">专题说明</label>
                <textarea class="form-control" name="summary" rows="3">{escape(current_form['summary'])}</textarea>
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">赛事页顶部标识</label>
                <input class="form-control" name="page_badge" value="{escape(current_form['page_badge'])}" placeholder="例如：广州 · 春季公开赛官方页">
              </div>
              <div class="col-12 col-md-6">
                <label class="form-label">赛事页主标题</label>
                <input class="form-control" name="hero_title" value="{escape(current_form['hero_title'])}" placeholder="留空则默认显示赛事页名称">
              </div>
              <div class="col-12">
                <label class="form-label">赛事页导语</label>
                <textarea class="form-control" name="hero_intro" rows="3" placeholder="展示在赛事页头部左侧，适合写当前赛事定位、浏览方式和亮点。">{escape(current_form['hero_intro'])}</textarea>
              </div>
              <div class="col-12">
                <label class="form-label">赛事页说明备注</label>
                <textarea class="form-control" name="hero_note" rows="3" placeholder="展示在赛事页头部右侧信息卡，适合写这个赛区、本赛季或该赛事页的说明。">{escape(current_form['hero_note'])}</textarea>
              </div>
            </div>
            <div class="d-flex flex-wrap gap-2 mt-4">
              <button type="submit" class="btn btn-dark">保存系列赛目录</button>
              <a class="btn btn-outline-dark" href="/series-manage">取消创建</a>
            </div>
          </form>
        </section>
            """
        else:
            catalog_form_html = """
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="alert alert-secondary mb-0">当前账号没有新建地区赛事页的权限；如需新增目录，请使用管理员账号操作。</div>
            </section>
            """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">系列赛目录管理</div>
          <h1 class="hero-title mb-3">系列赛与赛季分开管理</h1>
      <p class="hero-copy mb-0">这里先展示全部地区系列赛；赛事页信息和赛季信息默认只读，只有点击编辑按钮时才进入修改模式。赛事负责人只能修改自己被分配到的地区系列赛范围。</p>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Series Catalog</div>
          <div class="hero-stage-label">Manager Access</div>
          <div class="hero-stage-title">{len(competition_rows)}</div>
          <div class="hero-stage-note">当前目录中的地区赛事页数量。相同系列赛只要保持相同系列编码，就会自动聚合到同一个专题页。</div>
        </div>
      </div>
    </section>
    {(
      '<section class="panel shadow-sm p-3 p-lg-4 mb-4"><div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-center gap-3"><div><h2 class="section-title mb-2">新增系列赛</h2><p class="section-copy mb-0">新建入口与现有系列赛的查看页分开，避免在列表页误改已有数据。</p></div><div><a class="btn btn-dark" href="/series-manage?edit=create">新建系列赛</a></div></div></section>'
      if is_admin_user(ctx.current_user) and not catalog_editor_active
      else ''
    )}
    {selected_overview_html}
    {catalog_form_html}
    {season_section_html}
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">当前系列赛目录</h2>
          <p class="section-copy mb-0">这里展示已经配置好的地区赛事页。先查看详情，再按需进入赛事页编辑或赛季编辑。</p>
        </div>
      </div>
      <div class="row g-3 g-lg-4">{''.join(existing_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">目前还没有系列赛目录。</div></div>'}</div>
    </section>
    """
    return layout("系列赛管理", body, ctx, alert=alert)


def handle_series_manage(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_series_manage_page(ctx))

    data = load_validated_data()
    catalog = load_series_catalog(data)
    season_catalog = load_season_catalog(data)
    action = form_value(ctx.form, "action").strip() or "save_catalog"
    if action == "save_season":
        edit_mode = form_value(ctx.form, "edit_mode").strip() or "season"
        competition_name = form_value(ctx.form, "competition_name").strip()
        original_season_name = form_value(ctx.form, "original_season_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        start_at = form_value(ctx.form, "start_at").strip()
        end_at = form_value(ctx.form, "end_at").strip()
        notes = form_value(ctx.form, "notes").strip()
        next_path = form_value(ctx.form, "next").strip()
        permission_guard = require_competition_season_manager(
            ctx,
            start_response,
            data,
            competition_name,
            "你只能编辑自己负责地区系列赛下的赛季。",
        )
        if permission_guard is not None:
            return permission_guard
        selected_entry = get_series_entry_by_competition(catalog, competition_name)
        series_slug = selected_entry["series_slug"] if selected_entry else ""
        form_values = {
            "competition_name": competition_name,
            "original_season_name": original_season_name,
            "season_name": season_name,
            "start_at": start_at,
            "end_at": end_at,
            "notes": notes,
            "original_competition_name": competition_name,
            "next": next_path,
            "edit_mode": edit_mode,
        }
        error = validate_season_catalog_form(series_slug, season_name, start_at, end_at)
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert=error, form_values=form_values),
            )

        lookup_season_name = original_season_name or season_name
        existing_entry = get_season_entry(
            season_catalog,
            series_slug,
            lookup_season_name,
            competition_name=competition_name,
        )
        new_entry = normalize_season_catalog_entry(
            {
                "series_slug": series_slug,
                "series_name": selected_entry["series_name"] if selected_entry else "",
                "series_code": selected_entry["series_code"] if selected_entry else "",
                "competition_name": competition_name,
                "season_name": season_name,
                "start_at": start_at,
                "end_at": end_at,
                "notes": notes,
                "registered_team_ids": (
                    existing_entry.get("registered_team_ids", []) if existing_entry else []
                ),
                "created_by": (
                    existing_entry.get("created_by")
                    if existing_entry
                    else (ctx.current_user["username"] if ctx.current_user else "system")
                ),
                "created_on": existing_entry.get("created_on", china_today_label())
                if existing_entry
                else china_today_label(),
            }
        )
        if not new_entry:
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert="赛季保存失败。", form_values=form_values),
            )
        updated_catalog = [
            item
            for item in season_catalog
            if not (
                item["series_slug"] == series_slug
                and item.get("competition_name", "") == competition_name
                and item["season_name"] == lookup_season_name
            )
        ]
        updated_catalog.append(new_entry)
        save_season_catalog(updated_catalog)
        if lookup_season_name and lookup_season_name != season_name:
            for match in data["matches"]:
                if (
                    get_match_competition_name(match) == competition_name
                    and str(match.get("season") or "").strip() == lookup_season_name
                ):
                    match["season"] = season_name
            for team in data["teams"]:
                if (
                    str(team.get("competition_name") or "").strip() == competition_name
                    and str(team.get("season_name") or "").strip() == lookup_season_name
                ):
                    team["season_name"] = season_name
            requests = [
                {
                    **item,
                    "scope_season_name": (
                        season_name
                        if item.get("scope_competition_name") == competition_name
                        and item.get("scope_season_name") == lookup_season_name
                        else item.get("scope_season_name", "")
                    ),
                }
                for item in load_membership_requests()
            ]
            users = load_users()
            errors = save_repository_state(data, users)
            if errors:
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_series_manage_page(ctx, alert="赛季改名失败：" + "；".join(errors[:3]), form_values=form_values),
                )
            save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_series_manage_page(
                RequestContext(
                    method="GET",
                    path=ctx.path,
                    query={
                        "competition_name": [competition_name],
                        "season_name": [season_name],
                        **({"next": [next_path]} if next_path else {}),
                    },
                    form={},
                    files={},
                    current_user=ctx.current_user,
                    now_label=ctx.now_label,
                ),
                alert=f"{competition_name} / {season_name} 的赛季档期已保存。",
            ),
        )

    if action == "delete_season":
        competition_name = form_value(ctx.form, "competition_name").strip()
        season_name = form_value(ctx.form, "season_name").strip()
        next_path = form_value(ctx.form, "next").strip()
        permission_guard = require_competition_season_manager(
            ctx,
            start_response,
            data,
            competition_name,
            "你只能删除自己负责地区系列赛下的赛季。",
        )
        if permission_guard is not None:
            return permission_guard
        selected_entry = get_series_entry_by_competition(catalog, competition_name)
        if not selected_entry:
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert="没有找到对应的地区系列赛。"),
            )
        target_entry = get_season_entry(
            season_catalog,
            selected_entry["series_slug"],
            season_name,
            competition_name=competition_name,
        )
        if not target_entry:
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert="没有找到要删除的赛季。"),
            )
        has_matches = any(
            get_match_competition_name(match) == competition_name
            and str(match.get("season") or "").strip() == season_name
            for match in data["matches"]
        )
        if has_matches:
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert="该赛季下已经有比赛记录，不能直接删除。"),
            )
        if target_entry.get("registered_team_ids"):
            return start_response_html(
                start_response,
                "200 OK",
                get_series_manage_page(ctx, alert="该赛季下还有已报名战队，不能直接删除。"),
            )
        updated_catalog = [
            item
            for item in season_catalog
            if not (
                item["series_slug"] == selected_entry["series_slug"]
                and item.get("competition_name", "") == competition_name
                and item["season_name"] == season_name
            )
        ]
        save_season_catalog(updated_catalog)
        return start_response_html(
            start_response,
            "200 OK",
            get_series_manage_page(
                RequestContext(
                    method="GET",
                    path=ctx.path,
                    query={
                        "competition_name": [competition_name],
                        **({"next": [next_path]} if next_path else {}),
                    },
                    form={},
                    files={},
                    current_user=ctx.current_user,
                    now_label=ctx.now_label,
                ),
                alert=f"{competition_name} / {season_name} 已删除。",
            ),
        )

    series_name = form_value(ctx.form, "series_name").strip()
    series_code = form_value(ctx.form, "series_code").strip()
    region_name = form_value(ctx.form, "region_name").strip()
    competition_name = form_value(ctx.form, "competition_name").strip()
    summary = form_value(ctx.form, "summary").strip()
    page_badge = form_value(ctx.form, "page_badge").strip()
    hero_title = form_value(ctx.form, "hero_title").strip()
    hero_intro = form_value(ctx.form, "hero_intro").strip()
    hero_note = form_value(ctx.form, "hero_note").strip()
    original_competition_name = form_value(ctx.form, "original_competition_name").strip()
    next_path = form_value(ctx.form, "next").strip()
    edit_mode = form_value(ctx.form, "edit_mode").strip() or (
        "catalog" if original_competition_name else "create"
    )
    form_values = {
        "series_name": series_name,
        "series_code": series_code,
        "region_name": region_name,
        "competition_name": competition_name,
        "summary": summary,
        "page_badge": page_badge,
        "hero_title": hero_title,
        "hero_intro": hero_intro,
        "hero_note": hero_note,
        "original_competition_name": original_competition_name,
        "next": next_path,
        "edit_mode": edit_mode,
    }
    error = validate_series_catalog_form(series_name, region_name, competition_name)
    if not error and original_competition_name and original_competition_name != competition_name:
        error = "已有赛事页名称暂不支持直接修改，请保留原名称并编辑页面信息。"
    existing_entry = (
        get_series_entry_by_competition(catalog, original_competition_name)
        if original_competition_name
        else None
    )
    if not original_competition_name and not is_admin_user(ctx.current_user):
        error = error or "只有管理员可以创建新的地区系列赛目录。"
    if original_competition_name:
        permission_guard = require_competition_catalog_manager(
            ctx,
            start_response,
            data,
            original_competition_name,
            "你只能编辑自己负责地区系列赛下的赛事页信息。",
        )
        if permission_guard is not None:
            return permission_guard
        if existing_entry and region_name != existing_entry["region_name"]:
            error = error or "已有地区赛事页的所属地区不能直接修改。"
    if error:
        return start_response_html(
            start_response,
            "200 OK",
            get_series_manage_page(ctx, alert=error, form_values=form_values),
        )
    new_entry = normalize_series_catalog_entry(
        {
            "series_name": series_name,
            "series_code": series_code,
            "region_name": region_name,
            "competition_name": competition_name,
            "series_slug": existing_entry["series_slug"] if existing_entry else "",
            "summary": summary,
            "page_badge": page_badge,
            "hero_title": hero_title,
            "hero_intro": hero_intro,
            "hero_note": hero_note,
            "active": True,
            "created_by": (
                existing_entry.get("created_by")
                if existing_entry
                else (ctx.current_user["username"] if ctx.current_user else "system")
            ),
            "created_on": existing_entry.get("created_on", china_today_label())
            if existing_entry
            else china_today_label(),
        }
    )
    if not new_entry:
        return start_response_html(
            start_response,
            "200 OK",
            get_series_manage_page(ctx, alert="系列赛目录保存失败。", form_values=form_values),
        )

    remove_key = original_competition_name or competition_name
    updated_catalog = [item for item in catalog if item["competition_name"] != remove_key]
    updated_catalog.append(new_entry)
    save_series_catalog(updated_catalog)
    return start_response_html(
        start_response,
        "200 OK",
        get_series_manage_page(
            RequestContext(
                method="GET",
                path=ctx.path,
                query={
                    "competition_name": [new_entry["competition_name"]],
                    **({"next": [next_path]} if next_path else {}),
                },
                form={},
                files={},
                current_user=ctx.current_user,
                now_label=ctx.now_label,
            ),
            alert=(
                f"{competition_name} 的赛事页信息已更新。"
                if original_competition_name
                else f"{competition_name} 已写入系列赛目录。"
            ),
        ),
    )


def get_teams_page(ctx: RequestContext) -> str:
    return get_competitions_page(ctx)


def handle_competitions(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_competitions_page(ctx))

    guard = require_login(ctx, start_response)
    if guard is not None:
        return guard

    action = form_value(ctx.form, "action").strip()
    if action not in {"register_team_for_season", "cancel_team_registration"}:
        return start_response_html(
            start_response,
            "405 Method Not Allowed",
            layout("请求无效", '<div class="alert alert-danger">未识别的赛事报名操作。</div>', ctx),
        )

    data = load_validated_data()
    season_catalog = load_season_catalog(data)
    series_catalog = load_series_catalog(data)
    current_player = get_user_player(data, ctx.current_user)
    next_path = form_value(ctx.form, "next").strip() or "/competitions"
    competition_name = form_value(ctx.form, "competition_name").strip()
    season_name = form_value(ctx.form, "season_name").strip()
    team_id = form_value(ctx.form, "team_id").strip()
    render_ctx = RequestContext(
        method="GET",
        path="/competitions",
        query={
            **({"competition": [competition_name]} if competition_name else {}),
            **({"season": [season_name]} if season_name else {}),
        },
        form={},
        files={},
        current_user=ctx.current_user,
        now_label=ctx.now_label,
    )
    team = get_team_by_id(data, team_id)
    if not team:
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="没有找到要报名的战队。"),
        )
    if not team_matches_scope(team, competition_name, season_name):
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="战队只能报名自己所属赛事赛季。"),
        )
    if not can_manage_team(ctx, team, current_player):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、战队队长或管理员可以为战队报名赛季。</div>', ctx),
        )
    series_slug = build_series_context_from_competition(
        competition_name,
        series_catalog,
    )["series_slug"]
    season_entry = get_season_entry(
        season_catalog,
        series_slug,
        season_name,
        competition_name=competition_name,
    )
    if not season_entry:
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="当前赛季还没有配置起止时间，请先让赛事负责人完成赛季设置。"),
        )
    if get_season_status(season_entry) != "ongoing":
        return start_response_html(
            start_response,
            "200 OK",
            get_competitions_page(render_ctx, alert="只有进行中的赛季才允许战队报名。"),
        )

    registered_team_ids = [
        registered_team_id
        for registered_team_id in season_entry.get("registered_team_ids", [])
        if registered_team_id != team_id
    ]
    if action == "register_team_for_season":
        registered_team_ids.append(team_id)

    updated_catalog = []
    for item in season_catalog:
        if (
            item["series_slug"] == series_slug
            and item.get("competition_name", "") == competition_name
            and item["season_name"] == season_name
        ):
            updated_catalog.append({**item, "registered_team_ids": registered_team_ids})
        else:
            updated_catalog.append(item)
    save_season_catalog(updated_catalog)
    return redirect(start_response, next_path)


def summarize_team_match(team_id: str, match: dict[str, Any], team_lookup: dict[str, Any]) -> dict[str, Any]:
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


def build_match_next_path(match: dict[str, Any]) -> str:
    return build_scoped_path(
        "/competitions",
        get_match_competition_name(match),
        (match.get("season") or "").strip() or None,
    )


def list_match_days(data: dict[str, Any]) -> list[str]:
    return sorted(
        {
            str(match.get("played_on") or "").strip()
            for match in data["matches"]
            if str(match.get("played_on") or "").strip()
        },
        reverse=True,
    )


def build_match_day_path(played_on: str, next_path: str | None = None) -> str:
    base_path = f"/days/{played_on}"
    if not next_path:
        return base_path
    return f"{base_path}?{urlencode({'next': next_path})}"


def build_schedule_path(
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


def is_valid_match_day(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def get_match_day_page(ctx: RequestContext, played_on: str) -> str:
    if not is_valid_match_day(played_on):
        return layout("未找到比赛日", '<div class="alert alert-danger">比赛日期格式不正确。</div>', ctx)

    data = load_validated_data()
    catalog = load_series_catalog(data)
    player_lookup = {player["player_id"]: player for player in data["players"]}
    day_matches = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (
                get_match_competition_name(item),
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        )
        if str(match.get("played_on") or "").strip() == played_on
    ]
    if not day_matches:
        return layout("未找到比赛日", '<div class="alert alert-danger">这一天还没有比赛记录。</div>', ctx)

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    next_path = form_value(ctx.query, "next").strip() or "/dashboard"
    grouped_matches: dict[str, list[dict[str, Any]]] = {}
    for match in day_matches:
        grouped_matches.setdefault(get_match_competition_name(match), []).append(match)

    competition_sections = []
    for competition_name, matches in grouped_matches.items():
        series_entry = get_series_entry_by_competition(catalog, competition_name)
        region_name = series_entry["region_name"] if series_entry else DEFAULT_REGION_NAME
        series_name = series_entry["series_name"] if series_entry else competition_name
        series_slug = series_entry["series_slug"] if series_entry else None
        player_count = len(
            {
                entry["player_id"]
                for match in matches
                for entry in match["players"]
            }
        )
        team_count = len(
            {
                entry["team_id"]
                for match in matches
                for entry in match["players"]
            }
        )
        match_cards = []
        for match in sorted(
            matches,
            key=lambda item: (
                (item.get("season") or "").strip(),
                item["round"],
                item["game_no"],
                item["match_id"],
            ),
        ):
            season_name = (match.get("season") or "").strip()
            detail_path = build_match_day_path(played_on)
            match_detail_path = f"/matches/{match['match_id']}?next={quote(detail_path)}"
            team_links = "、".join(
                f'<a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path("/teams/" + entry["team_id"], competition_name, season_name, region_name, series_slug))}">{escape(team_lookup[entry["team_id"]]["name"])}</a>'
                for entry in sorted(
                    {item["team_id"]: item for item in match["players"]}.values(),
                    key=lambda item: team_lookup[item["team_id"]]["name"],
                )
            )
            player_rows = []
            for participant in sorted(
                match["players"],
                key=lambda item: (
                    -float(item["points_earned"]),
                    item["seat"],
                    player_lookup.get(item["player_id"], {}).get("display_name", item["player_id"]),
                ),
            ):
                player_name = player_lookup.get(participant["player_id"], {}).get(
                    "display_name",
                    participant["player_id"],
                )
                team_name = team_lookup.get(participant["team_id"], {}).get(
                    "name",
                    participant["team_id"],
                )
                player_rows.append(
                    f"""
                    <tr>
                      <td>{participant['seat']}</td>
                      <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + participant['player_id'], competition_name, season_name, region_name, series_slug))}">{escape(player_name)}</a></td>
                      <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name, region_name, series_slug))}">{escape(team_name)}</a></td>
                      <td>{escape(participant['role'])}</td>
                      <td>{escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
                      <td>{float(participant['points_earned']):.2f}</td>
                    </tr>
                    """
                )
            match_cards.append(
                f"""
                <div class="col-12">
                  <div class="team-link-card shadow-sm p-4 h-100">
                    <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-start gap-3 mb-3">
                      <div>
                        <div class="card-kicker mb-2">个人积分日报</div>
                        <h3 class="h5 mb-2">{escape(match['match_id'])}</h3>
                        <div class="small-muted">赛季 {escape(season_name)} · {escape(STAGE_OPTIONS.get(match['stage'], match['stage']))} · 第 {match['round']} 轮 / 第 {match['game_no']} 局</div>
                        <div class="small-muted mt-1">参赛战队 {team_links} · {escape(match['table_label'])} · {match['duration_minutes']} 分钟</div>
                      </div>
                      <div class="d-flex flex-wrap gap-2">
                        <a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看详情</a>
                      </div>
                    </div>
                    <div class="table-responsive">
                      <table class="table align-middle mb-0">
                        <thead>
                          <tr>
                            <th>座位</th>
                            <th>队员</th>
                            <th>战队</th>
                            <th>角色</th>
                            <th>结果</th>
                            <th>个人积分</th>
                          </tr>
                        </thead>
                        <tbody>
                          {''.join(player_rows)}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </div>
                """
            )

        competition_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2">{escape(series_name)} · {escape(region_name)}</h2>
                  <div class="small-muted mb-2">{escape(competition_name)}</div>
                  <p class="section-copy mb-0">当天该系列赛共有 {len(matches)} 场比赛，涉及 {team_count} 支战队、{player_count} 名队员。日报按单场个人积分展示，战队积分将累计进赛季排行榜。</p>
                </div>
                <a class="btn btn-outline-dark" href="{escape(build_scoped_path('/competitions', competition_name, (matches[0].get('season') or '').strip() or None, region_name, series_slug))}">进入该赛事页</a>
              </div>
              <div class="row g-3">{''.join(match_cards)}</div>
            </section>
            """
        )

    total_team_count = len(
        {
            entry["team_id"]
            for match in day_matches
            for entry in match["players"]
        }
    )
    total_player_count = len(
        {
            entry["player_id"]
            for match in day_matches
            for entry in match["players"]
        }
    )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">比赛日总览</div>
          <h1 class="hero-title mb-3">{escape(played_on)} 比赛日</h1>
          <p class="hero-copy mb-0">这里按系列赛拆分展示这一天的全部比赛。你可以先看当天总览，再点进单场详情页继续查看每局完整数据。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
          </div>
          <div class="hero-kpis">
            <div class="hero-pill">
              <span>系列赛数量</span>
              <strong>{len(grouped_matches)}</strong>
              <small>当天涉及系列赛</small>
            </div>
            <div class="hero-pill">
              <span>比赛场次</span>
              <strong>{len(day_matches)}</strong>
              <small>当天全部比赛</small>
            </div>
            <div class="hero-pill">
              <span>参赛战队</span>
              <strong>{total_team_count}</strong>
              <small>当天全部战队</small>
            </div>
            <div class="hero-pill">
              <span>参赛队员</span>
              <strong>{total_player_count}</strong>
              <small>当天全部上场</small>
            </div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Match Day</div>
          <div class="hero-stage-label">Daily Overview</div>
          <div class="hero-stage-title">{escape(played_on)}</div>
          <div class="hero-stage-note">当天所有比赛会按系列赛分块展示，每场比赛都保留详情入口，方便回看当日完整赛程。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>系列赛</span>
              <strong>{len(grouped_matches)}</strong>
              <small>当天开赛系列赛</small>
            </div>
            <div class="hero-stage-metric">
              <span>场次</span>
              <strong>{len(day_matches)}</strong>
              <small>当天完整对局</small>
            </div>
            <div class="hero-stage-metric">
              <span>战队</span>
              <strong>{total_team_count}</strong>
              <small>当天参赛战队</small>
            </div>
            <div class="hero-stage-metric">
              <span>队员</span>
              <strong>{total_player_count}</strong>
              <small>当天上场人数</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    {''.join(competition_sections)}
    """
    return layout(f"{played_on} 比赛日", body, ctx)


def get_schedule_page(ctx: RequestContext) -> str:
    data = load_validated_data()
    scope = resolve_catalog_scope(ctx, data)
    competition_names = scope["competition_names"]
    selected_competition = scope["selected_competition"]
    if not selected_competition:
        return get_competitions_page(ctx)

    selected_entry = scope["selected_entry"]
    selected_region = selected_entry["region_name"] if selected_entry else scope["selected_region"]
    selected_series_slug = (
        selected_entry["series_slug"] if selected_entry else scope["selected_series_slug"]
    )
    season_names = list_seasons(data, selected_competition)
    selected_season = get_selected_season(ctx, season_names)
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
        "/competitions",
        selected_competition,
        selected_season,
        selected_region,
        selected_series_slug,
    )
    competition_switcher = build_competition_switcher(
        "/schedule",
        [row["competition_name"] for row in (scope["filtered_rows"] or scope["region_rows"] or scope["competition_rows"])],
        selected_competition,
        tone="light",
        all_label="返回赛事总览",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher = build_season_switcher(
        "/schedule",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
        region_name=selected_region,
        series_slug=selected_series_slug,
    )
    season_switcher_html = (
        f'<div class="hero-switchers mt-3">{season_switcher}</div>' if season_switcher else ""
    )

    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if match_in_scope(match, selected_competition, selected_season)
    ]
    if not match_rows:
        return layout(
            "赛事场次页",
            '<div class="alert alert-secondary">当前系列赛和赛季下还没有比赛记录。</div>',
            ctx,
        )

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    day_groups: dict[str, list[dict[str, Any]]] = {}
    for match in match_rows:
        day_groups.setdefault(match["played_on"], []).append(match)

    create_match_button = ""
    if can_manage_matches(ctx.current_user, data, selected_competition):
        create_match_button = (
            f'<a class="btn btn-dark" href="/matches/new?'
            f'{urlencode({"competition": selected_competition, "season": selected_season or "", "next": build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug)})}">录入比赛</a>'
        )

    day_sections = []
    for played_on, matches in day_groups.items():
        rows = []
        for match in matches:
            match_detail_path = (
                f"/matches/{match['match_id']}?next="
                f"{quote(build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug))}"
            )
            team_names = "、".join(
                sorted({team_lookup[entry["team_id"]]["name"] for entry in match["players"]})
            )
            rows.append(
                f"""
                <tr>
                  <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(match_detail_path)}">{escape(match['match_id'])}</a></td>
                  <td>{escape(match['season'])}</td>
                  <td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td>
                  <td>第 {match['round']} 轮</td>
                  <td>第 {match['game_no']} 局</td>
                  <td>{escape(team_names)}</td>
                  <td>{escape(match['table_label'])}</td>
                  <td>{escape(match['format'])}</td>
                  <td><a class="btn btn-sm btn-outline-dark" href="{escape(match_detail_path)}">查看详情</a></td>
                </tr>
                """
            )
        day_sections.append(
            f"""
            <section class="panel shadow-sm p-3 p-lg-4 mb-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
                <div>
                  <h2 class="section-title mb-2"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_match_day_path(played_on, build_schedule_path(selected_competition, selected_season, None, selected_region, selected_series_slug)))}">{escape(played_on)}</a></h2>
                  <p class="section-copy mb-0">当天共有 {len(matches)} 场比赛。点击日期可切换到该比赛日总览，点击单场编号可进入详情页。</p>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead>
                    <tr>
                      <th>编号</th>
                      <th>赛季</th>
                      <th>阶段</th>
                      <th>轮次</th>
                      <th>局次</th>
                      <th>参赛战队</th>
                      <th>桌号</th>
                      <th>板型</th>
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

    total_team_count = len(
        {
            entry["team_id"]
            for match in match_rows
            for entry in match["players"]
        }
    )
    total_player_count = len(
        {
            entry["player_id"]
            for match in match_rows
            for entry in match["players"]
        }
    )
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="hero-layout">
        <div>
          <div class="eyebrow mb-3">赛事场次页</div>
          <h1 class="hero-title mb-3">{escape(selected_competition)} · 全部场次</h1>
          <p class="hero-copy mb-0">这里集中展示该系列赛当前赛季的所有场次。你可以按日期查看，也可以直接点击某一场进入详情页。</p>
          <div class="hero-switchers mt-4">{competition_switcher}</div>
          {season_switcher_html}
          <div class="d-flex flex-wrap gap-2 mt-4">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回赛事页</a>
            {create_match_button}
          </div>
          <div class="hero-kpis">
            <div class="hero-pill">
              <span>比赛日</span>
              <strong>{len(day_groups)}</strong>
              <small>当前赛季涉及日期</small>
            </div>
            <div class="hero-pill">
              <span>比赛场次</span>
              <strong>{len(match_rows)}</strong>
              <small>当前赛季全部场次</small>
            </div>
            <div class="hero-pill">
              <span>参赛战队</span>
              <strong>{total_team_count}</strong>
              <small>当前赛季战队</small>
            </div>
            <div class="hero-pill">
              <span>参赛队员</span>
              <strong>{total_player_count}</strong>
              <small>当前赛季上场</small>
            </div>
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Schedule Board</div>
          <div class="hero-stage-label">All Matches</div>
          <div class="hero-stage-title">{escape(selected_season or selected_competition)}</div>
          <div class="hero-stage-note">这个页面只保留场次视角，不混入战队入口，适合连续查看该比赛全部赛程。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>首个比赛日</span>
              <strong>{escape(min(day_groups.keys()))}</strong>
              <small>当前赛季起始</small>
            </div>
            <div class="hero-stage-metric">
              <span>最后比赛日</span>
              <strong>{escape(max(day_groups.keys()))}</strong>
              <small>当前赛季最新</small>
            </div>
            <div class="hero-stage-metric">
              <span>比赛日</span>
              <strong>{len(day_groups)}</strong>
              <small>按日期拆分展示</small>
            </div>
            <div class="hero-stage-metric">
              <span>总场次</span>
              <strong>{len(match_rows)}</strong>
              <small>当前赛季记录</small>
            </div>
          </div>
        </div>
      </div>
    </section>
    {''.join(day_sections)}
    """
    return layout(f"{selected_competition} 场次页", body, ctx)


def get_match_page(ctx: RequestContext, match_id: str) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)
    alert = form_value(ctx.query, "alert").strip()
    if alert == "placeholder-created":
        alert = "本场比赛涉及未注册选手，系统已自动为对应参赛ID预留档案，可稍后在绑定页认领并合并。"

    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    competition_name = get_match_competition_name(match)
    season_name = (match.get("season") or "").strip()
    selected_region = form_value(ctx.query, "region").strip() or None
    selected_series_slug = form_value(ctx.query, "series").strip() or None
    next_path = form_value(ctx.query, "next").strip() or build_match_next_path(match)
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
        participant_rows.append(
            f"""
            <tr>
              <td>{participant['seat']}</td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="{escape(build_scoped_path('/players/' + participant['player_id'], competition_name, season_name))}">{escape(player_name)}</a></td>
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + participant['team_id'], competition_name, season_name))}">{escape(team_name)}</a></td>
              <td>{escape(participant['role'])}</td>
              <td>{escape(to_chinese_camp(participant['camp']))}</td>
              <td>{escape(RESULT_OPTIONS.get(participant['result'], participant['result']))}</td>
              <td>{escape(STANCE_OPTIONS.get(stance_result, stance_result))}</td>
              <td>{float(participant['points_earned']):.2f}</td>
              <td>{escape(participant['notes'] or '无')}</td>
            </tr>
            """
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
          <p class="hero-copy mb-0">这里展示单场比赛的完整信息，包括比赛编号、阶段、参赛战队以及所有上场成员的个人明细。</p>
          <div class="d-flex flex-wrap gap-2 mt-4">
            <span class="chip">编号 {escape(match['match_id'])}</span>
            <span class="chip">{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</span>
            <span class="chip">第 {match['round']} 轮 · 第 {match['game_no']} 局</span>
            <a class="switcher-chip" href="{escape(build_match_day_path(match['played_on'], build_scoped_path('/matches/' + match_id, competition_name, season_name)))}">{escape(match['played_on'])}</a>
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">
            <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
            {edit_button}
          </div>
        </div>
        <div class="hero-stage-card">
          <div class="official-mark">Official Match Detail</div>
          <div class="hero-stage-label">Match Overview</div>
          <div class="hero-stage-title">{escape(match['match_id'])}</div>
          <div class="hero-stage-note">比赛详情页会固定当前系列赛和赛季口径，方便从战队页、队员页和赛事页继续回看单场内容。</div>
          <div class="hero-stage-grid">
            <div class="hero-stage-metric">
              <span>桌号</span>
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
              <span>参赛战队</span>
              <strong>{len(score_rows)}</strong>
              <small>本场涉及战队</small>
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
          <p class="section-copy mb-0">点击队员或战队名称，可以继续跳转到对应的详情页，并保持当前系列赛与赛季口径。</p>
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


def get_team_page(ctx: RequestContext, team_id: str, alert: str = "") -> str:
    data = load_validated_data()
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team = team_lookup.get(team_id)
    if not team:
        return layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx)
    current_player = get_user_player(data, ctx.current_user)
    can_manage_team_profile = can_manage_team(ctx, team, current_player)
    team_competition_name, team_season_name = get_team_scope(team)
    team_status = get_team_season_status(data, team)
    team_status_label = get_team_season_status_label(team_status)
    can_edit_team_page = can_manage_team_profile and team_status == "ongoing"
    guild = get_guild_by_id(data, str(team.get("guild_id") or "").strip())
    team_logo_html = build_team_logo_html(team["logo"], team["name"])
    current_team_path = build_scoped_path(
        f"/teams/{team_id}",
        form_value(ctx.query, "competition").strip() or team_competition_name or None,
        form_value(ctx.query, "season").strip() or team_season_name or None,
    )
    team_logo_panel = f"""
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4 align-items-start">
        <div class="col-12 col-lg-4 col-xl-3">
          {team_logo_html}
        </div>
        <div class="col-12 col-lg-8 col-xl-9">
          <h2 class="section-title mb-2">战队图标</h2>
          <p class="section-copy mb-3">当前队标会出现在战队页面和后续战队展示卡片中。</p>
          <div class="small text-secondary mb-3">当前路径：{escape(team['logo'])}</div>
          {(
            f'''
            <form method="post" action="/teams/{escape(team_id)}/logo" enctype="multipart/form-data">
              <input type="hidden" name="next" value="{escape(current_team_path)}">
              <div class="row g-3 align-items-end">
                <div class="col-12 col-lg-8">
                  <label class="form-label">上传新的战队图标</label>
                  <input class="form-control" name="logo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
                  <div class="small text-secondary mt-2">支持 PNG、JPG、JPEG、WEBP、GIF、SVG，大小不超过 5 MB。</div>
                </div>
                <div class="col-12 col-lg-4 d-flex gap-2">
                  <button type="submit" class="btn btn-dark">更新队标</button>
                </div>
              </div>
            </form>
            '''
            if can_edit_team_page
            else (
              '<div class="small text-secondary">当前赛季已结束，战队资料已锁定，仅保留展示。</div>'
              if team_status != "ongoing"
              else '<div class="small text-secondary">只有具备战队管理权限的账号、战队队长或管理员可以更新队标。</div>'
            )
          )}
        </div>
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
    season_names = (
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
    if team_season_name and team_season_name not in season_names:
        season_names.append(team_season_name)
    selected_season = (
        form_value(ctx.query, "season").strip()
        or team_season_name
        or get_selected_season(ctx, season_names)
    )
    competition_switcher = build_competition_switcher(
        f"/teams/{team_id}",
        team_competition_names,
        selected_competition,
        tone="light",
        all_label="比赛总览",
    )
    season_switcher = build_season_switcher(
        f"/teams/{team_id}",
        selected_competition,
        season_names,
        selected_season,
        tone="light",
    )
    competition_groups: dict[str, list[dict[str, Any]]] = {}
    for match in team_matches:
        competition_name = get_match_competition_name(match)
        competition_groups.setdefault(competition_name, []).append(
            summarize_team_match(team_id, match, team_lookup)
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
                      <div class="col-4"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(competition_team_stats['win_rate'])}</div></div>
                      <div class="col-4"><div class="small text-secondary">站边率</div><div class="fw-semibold">{format_pct(competition_team_stats['stance_rate'])}</div></div>
                      <div class="col-4"><div class="small text-secondary">总积分</div><div class="fw-semibold">{competition_team_stats['points_earned_total']:.2f}</div></div>
                    </div>
                  </a>
                </div>
                """
            )

        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">战队比赛总览</div>
          <h1 class="display-6 fw-semibold mb-3">{escape(team['name'])}</h1>
          <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
          <p class="mb-2 opacity-75">{escape(team['notes'])}</p>
          <div class="d-flex flex-wrap gap-2 mt-3">
            {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
          </div>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
        </section>
        {team_logo_panel}
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
    team_stats = team_rows[team_id]
    roster_player_ids = resolve_team_player_ids(
        data, team_id, selected_competition, selected_season
    )
    players = []
    for player_id in roster_player_ids:
        player = player_lookup.get(player_id)
        player_stats = player_rows.get(player_id)
        if not player or not player_stats:
            continue
        players.append(
            {
                **player,
                "win_rate": format_pct(player_stats["win_rate"]),
                "stance_rate": format_pct(player_stats["stance_rate"]),
                "points_total": f"{player_stats['points_earned_total']:.2f}",
                "games_played": player_stats["games_played"],
                "average_points": player_stats["average_points"],
            }
        )

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
            reverse=True,
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
                  <td>第 {item['game_no']} 局</td>
                  <td>{escape(item['opponents'])}</td>
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
                      <th>局次</th>
                      <th>对手</th>
                      <th>桌号</th>
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

    roster_html = "".join(
        f"""
        <a class="team-link-card shadow-sm p-3 h-100" href="{escape(build_scoped_path('/players/' + player['player_id'], selected_competition, selected_season))}">
          <div class="d-flex justify-content-between align-items-start gap-3">
            <div>
              <div class="fw-semibold mb-1">{escape(player["display_name"])}</div>
              <div class="small text-secondary">出场 {player["games_played"]} 次 · 场均得分 {player["average_points"]:.2f}</div>
            </div>
            <span class="chip">查看队员</span>
          </div>
          <div class="row g-2 mt-2">
            <div class="col-4">
              <div class="small text-secondary">胜率</div>
              <div class="fw-semibold">{player["win_rate"]}</div>
            </div>
            <div class="col-4">
              <div class="small text-secondary">站边率</div>
              <div class="fw-semibold">{player["stance_rate"]}</div>
            </div>
            <div class="col-4">
              <div class="small text-secondary">总积分</div>
              <div class="fw-semibold">{player["points_total"]}</div>
            </div>
          </div>
        </a>
        """
        for player in players
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
          <p class="section-copy mb-4">当前赛季战队还没有门派归属。具备战队管理权限的账号或战队队长可以从这里向某个门派提交加入申请，等待门主或门派管理员审核。</p>
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
      <div class="eyebrow mb-3">战队比赛页面</div>
      <h1 class="display-6 fw-semibold mb-3">{escape(team['name'])}</h1>
      <p class="mb-2 opacity-75">{escape(team_scope_label(team))}</p>
      <p class="mb-2 opacity-75">{escape(team['notes'])}</p>
      <div class="d-flex flex-wrap gap-2 mt-3">
        <span class="chip">{escape(team_status_label)}</span>
        {f'<a class="chip" href="/guilds/{escape(guild["guild_id"])}">关联门派：{escape(guild["name"])}</a>' if guild else '<span class="chip">未加入门派</span>'}
      </div>
      <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
      {f'<div class="d-flex flex-wrap gap-2 mt-3">{season_switcher}</div>' if season_switcher else ''}
      <div class="d-flex flex-wrap gap-3">
        <span class="chip">{escape(selected_season or '当前赛季')}</span>
        <span class="chip">胜率 {format_pct(team_stats['win_rate'])}</span>
        <span class="chip">站边率 {format_pct(team_stats['stance_rate'])}</span>
        <span class="chip">总积分 {team_stats['points_earned_total']:.2f}</span>
        <span class="chip">队员 {team_stats['player_count']} 名</span>
      </div>
    </section>
    {(
      '<div class="alert alert-secondary mb-4">当前战队所属赛季已结束，战队资料和门派申请入口已关闭，页面仅保留公开展示。</div>'
      if team_status != "ongoing"
      else ''
    )}
    {team_logo_panel}
    {guild_panel}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该赛季参赛队员</h2>
          <p class="section-copy mb-0">点击任意队员卡片，可以继续查看该队员在同一系列赛和赛季口径下的综合数据。</p>
        </div>
      </div>
      <div class="row g-3">{roster_html or '<div class="col-12"><div class="alert alert-secondary mb-0">当前统计口径下，这支战队还没有参赛队员数据。</div></div>'}</div>
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


def build_guild_honor_rows(data: dict[str, Any], guild_id: str) -> list[dict[str, str]]:
    honors: list[dict[str, str]] = []
    guild_teams = [team for team in data["teams"] if str(team.get("guild_id") or "").strip() == guild_id]
    for team in guild_teams:
        competition_name, season_name = get_team_scope(team)
        if not competition_name or not season_name:
            continue
        team_row = {
            row["team_id"]: row
            for row in build_team_rows(data, competition_name, season_name)
        }.get(team["team_id"])
        if not team_row:
            continue
        if team_row.get("points_rank", 9999) <= 3:
            honors.append(
                {
                    "title": f"{competition_name} {season_name} 战队积分第 {team_row['points_rank']} 名",
                    "team_name": team["name"],
                    "scope": f"{competition_name} / {season_name}",
                }
            )
    honors.sort(key=lambda item: (item["scope"], item["title"]), reverse=True)
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



def handle_guild_page(ctx: RequestContext, start_response, guild_id: str):
    from web.features.guilds import handle_guild_page as impl

    return impl(ctx, start_response, guild_id)



def get_player_page(ctx: RequestContext, player_id: str) -> str:
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

    role_chips = "".join(
        f'<span class="chip">{escape(item["role"])} {item["games"]} 局</span>' for item in detail["roles"]
    ) or '<span class="chip">暂无角色记录</span>'

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
              <td>第 {item['game_no']} 局</td>
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

    competition_rows = []
    for item in detail["competition_stats"]:
        competition_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td>{escape(item['team_name'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['record'])}</td>
              <td>{escape(item['win_rate'])}</td>
              <td>{escape(item['stance_rate'])}</td>
              <td>{escape(item['points_total'])}</td>
              <td>{escape(item['average_points'])}</td>
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
            <span class="chip">站边率 {escape(detail['stance_rate'])}</span>
            <span class="chip">总积分 {escape(detail['points_total'])}</span>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-3">
        <div class="col-12 col-lg-7">
          <h2 class="section-title mb-3">个人资料</h2>
          <div class="row g-3">
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">当前统计战队</div>
                <div class="fw-semibold mt-2"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="{escape(build_scoped_path('/teams/' + team_id, selected_competition, selected_season))}">{escape(detail['team_name'])}</a></div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">总出场</div>
                <div class="stat-value mt-2">{detail['games_played']}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">场均得分</div>
                <div class="stat-value mt-2">{escape(detail['average_points'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">总胜率</div>
                <div class="fw-semibold mt-2">{escape(detail['overall_win_rate'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">累计得分</div>
                <div class="fw-semibold mt-2">{escape(detail['points_total'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">好人胜率</div>
                <div class="fw-semibold mt-2">{escape(detail['villagers_win_rate'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">狼人胜率</div>
                <div class="fw-semibold mt-2">{escape(detail['werewolves_win_rate'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">站对边</div>
                <div class="fw-semibold mt-2">{detail['correct_stances']} / {detail['stance_calls']}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">站错边</div>
                <div class="fw-semibold mt-2">{detail['incorrect_stances']}</div>
              </div>
            </div>
          </div>
        </div>
        <div class="col-12 col-lg-5">
          <h2 class="section-title mb-3">补充信息</h2>
          <div class="panel h-100 shadow-sm p-3">
            <div class="mb-3">{build_player_photo_html(detail['photo'], detail['display_name'])}</div>
            <div class="mb-2"><strong>别名：</strong>{escape(aliases)}</div>
            <div class="mb-2"><strong>入库日期：</strong>{escape(detail['joined_on'])}</div>
            <div class="mb-2"><strong>照片路径：</strong>{escape(detail['photo'])}</div>
            <div class="mb-0"><strong>备注：</strong>{escape(detail['notes'] or '无')}</div>
          </div>
        </div>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">分赛季胜率统计</h2>
          <p class="section-copy mb-0">先单独统计每个小赛季的好人胜率、狼人胜率和总胜率，再结合上方当前口径查看综合表现。</p>
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
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">角色分布</h2>
      <p class="section-copy mb-3">按当前录入比赛统计该队员使用过的角色次数。</p>
      <div class="d-flex flex-wrap gap-2">{role_chips}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">分赛事统计</h2>
          <p class="section-copy mb-0">同一个队员可以在不同赛事代表不同战队，这里单独拆开展示。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛事</th>
              <th>战队</th>
              <th>出场</th>
              <th>战绩</th>
              <th>胜率</th>
              <th>站边率</th>
              <th>总积分</th>
              <th>场均得分</th>
            </tr>
          </thead>
          <tbody>
            {''.join(competition_rows) or '<tr><td colspan="8" class="text-secondary">暂无分赛事统计。</td></tr>'}
          </tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">最近比赛记录</h2>
          <p class="section-copy mb-0">这里会展示该队员在当前统计口径下的全部对局明细，方便继续核对赛事归属和表现。</p>
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
              <th>局次</th>
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
    return layout(f"{detail['display_name']} 页面", body, ctx)


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
) -> str:
    aliases_value = "、".join(player.get("aliases", []))
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
            <p class="section-copy mb-4">可以修改队员名称、别名、备注，并上传新的队员照片。</p>
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
              <label class="form-label">上传照片</label>
              <input class="form-control" name="photo_file" type="file" accept=".png,.jpg,.jpeg,.webp,.gif,.svg,image/*">
              <div class="small text-secondary mt-2">支持 PNG、JPG、JPEG、WEBP、GIF、SVG，大小不超过 5 MB。</div>
            </div>
          </div>
        </div>
        <div class="col-12 {'col-xl-6' if show_account_fields else 'col-xl-5'}">
          <div class="panel h-100 shadow-sm p-3 p-lg-4">
            <h2 class="section-title mb-3">当前照片预览</h2>
            <div class="mb-3">{build_player_photo_html(player['photo'], player['display_name'])}</div>
            <div class="mb-2"><strong>当前照片路径：</strong>{escape(player['photo'])}</div>
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
        <div class="col-6 col-xl-3"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">站边率</div><div class="stat-value mt-2">{escape(summary['stance_rate'])}</div></div></div>
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
    if not ctx.current_user:
        return layout("未登录", '<div class="alert alert-danger">请先登录后再管理绑定关系。</div>', ctx)
    data = load_validated_data()
    users = load_users()
    selected_player_id = selected_player_id.strip() or form_value(ctx.query, "player_id").strip()
    selected_player = next(
        (player for player in data["players"] if player["player_id"] == selected_player_id),
        None,
    )
    target_name = target_username.strip() or form_value(ctx.query, "username").strip() or ctx.current_user["username"]
    target_user = next((user for user in users if user["username"] == target_name), None)
    if not target_user:
        return layout("未找到账号", '<div class="alert alert-danger">没有找到要绑定的账号。</div>', ctx)
    if not can_manage_player_bindings(data, ctx.current_user, target_user, selected_player):
        return layout("没有权限", '<div class="alert alert-danger">你没有权限管理该账号的赛事绑定。</div>', ctx)
    summary = build_bound_player_summary(data, target_user)
    candidates = build_player_binding_candidates(data, users, target_user)
    bound_rows = []
    for player_id in get_user_bound_player_ids(target_user):
        player = next((item for item in data["players"] if item["player_id"] == player_id), None)
        scope_labels = "、".join(get_player_binding_scope_labels(data, player_id)) or "暂无比赛范围"
        team_name = (
            get_team_by_id(data, player["team_id"])["name"]
            if player and get_team_by_id(data, player["team_id"])
            else (player["team_id"] if player else "未知战队")
        )
        action_html = (
            '<span class="small text-secondary">当前主身份</span>'
            if target_user.get("player_id") == player_id
            else f"""
            <form method="post" action="/bindings" class="m-0">
              <input type="hidden" name="action" value="unbind_player_id">
              <input type="hidden" name="target_username" value="{escape(target_user['username'])}">
              <input type="hidden" name="player_id" value="{escape(player_id)}">
              <button type="submit" class="btn btn-sm btn-outline-danger">解绑</button>
            </form>
            """
        )
        bound_rows.append(
            f"""
            <tr>
              <td>{escape(player_id)}</td>
              <td>{escape(player['display_name']) if player else '未找到档案'}</td>
              <td>{escape(scope_labels)}</td>
              <td>{escape(team_name)}</td>
              <td>{action_html}</td>
            </tr>
            """
        )
    candidate_rows = []
    for item in candidates:
        action_html = (
            '<span class="small text-secondary">已绑定到当前账号</span>'
            if item["already_bound"]
            else f"""
            <form method="post" action="/bindings" class="m-0">
              <input type="hidden" name="action" value="bind_player_id">
              <input type="hidden" name="target_username" value="{escape(target_user['username'])}">
              <input type="hidden" name="player_id" value="{escape(item['player_id'])}">
              <button type="submit" class="btn btn-sm btn-dark">绑定到该账号</button>
            </form>
            """
        )
        row_class = "table-active" if item["player_id"] == selected_player_id else ""
        candidate_rows.append(
            f"""
            <tr class="{row_class}">
              <td>{escape(item['player_id'])}</td>
              <td>{escape(item['display_name'])}</td>
              <td>{escape(item['team_name'])}</td>
              <td>{item['games_played']}</td>
              <td>{escape(item['scope_labels'])}</td>
              <td>{action_html}</td>
            </tr>
            """
        )
    username_picker_html = ""
    if (
        is_admin_user(ctx.current_user)
        or user_has_permission(ctx.current_user, "player_binding_manage")
        or is_team_captain_user(data, ctx.current_user)
    ):
        username_picker_html = f"""
        <form method="get" action="/bindings" class="row g-3 align-items-end mb-4">
          <div class="col-12 col-lg-5">
            <label class="form-label">目标账号</label>
            <input class="form-control" name="username" value="{escape(target_user['username'])}" placeholder="输入用户名">
          </div>
          <div class="col-12 col-lg-4">
            <label class="form-label">预选参赛ID</label>
            <input class="form-control" name="player_id" value="{escape(selected_player_id)}" placeholder="例如 p001-s1">
          </div>
          <div class="col-12 col-lg-3">
            <button type="submit" class="btn btn-outline-dark w-100">切换绑定对象</button>
          </div>
        </form>
        """
    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">赛事数据绑定</div>
      <h1 class="display-6 fw-semibold mb-3">管理参赛ID与账号绑定</h1>
      <p class="mb-0 opacity-75">比赛录入时如果选手还没注册，系统会先为赛季参赛ID预留档案。后续只要把该赛季ID绑定一次，这个赛季下的全部比赛就会自动归到该账号名下；不同赛季则可以继续绑定不同ID。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">目标账号</h2>
          <p class="section-copy mb-0">当前正在为 <strong>{escape(target_user['username'])}</strong> 维护绑定关系。</p>
        </div>
        <a class="btn btn-outline-dark" href="/profile">返回个人中心</a>
      </div>
      {username_picker_html}
      {build_profile_binding_summary(summary) if summary else '<div class="alert alert-secondary mb-0">该账号暂时还没有已绑定的赛事数据。</div>'}
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">当前已绑定ID</h2>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛季参赛ID</th>
              <th>档案名称</th>
              <th>覆盖赛季</th>
              <th>当前战队</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(bound_rows) or '<tr><td colspan="5" class="text-secondary">当前还没有绑定任何赛季参赛ID。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <h2 class="section-title mb-2">可绑定的赛季参赛ID</h2>
      <p class="section-copy mb-3">这里只展示已有比赛记录、且尚未绑定到其他账号的赛季参赛ID档案。同一账号在同一赛事赛季内只需要绑定一个ID。</p>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛季参赛ID</th>
              <th>档案名称</th>
              <th>战队</th>
              <th>出场</th>
              <th>覆盖范围</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>{''.join(candidate_rows) or '<tr><td colspan="6" class="text-secondary">当前没有可绑定的赛季参赛ID。</td></tr>'}</tbody>
        </table>
      </div>
    </section>
    """
    return layout("赛事数据绑定", body, ctx, alert=alert)


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
            <div class="mb-2"><strong>绑定账号：</strong>{escape(owner_user['username']) if owner_user else '未绑定账号'}</div>
            <div class="mb-0"><strong>账号显示名称：</strong>{escape(owner_user.get('display_name') or owner_user['username']) if owner_user else '无'}</div>
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
    current_form = form_values or {
        "editing_username": "",
        "username": "",
        "display_name": "",
        "role": "member",
        "province_name": DEFAULT_PROVINCE_NAME,
        "region_name": "广州市",
        "manager_scope_keys": [],
    }
    users = load_users()
    data = load_validated_data()
    requested_edit_username = str(current_form.get("editing_username") or "").strip()
    if not requested_edit_username:
        requested_edit_username = form_value(ctx.query, "edit_username").strip()
    editing_user = next(
        (user for user in users if user["username"] == requested_edit_username),
        None,
    )
    if editing_user and not form_values:
        current_form.update(
            {
                "editing_username": editing_user["username"],
                "username": editing_user["username"],
                "display_name": editing_user.get("display_name") or editing_user["username"],
                "role": editing_user.get("role") or "member",
                "province_name": editing_user.get("province_name") or DEFAULT_PROVINCE_NAME,
                "region_name": editing_user.get("region_name") or "广州市",
                "manager_scope_keys": list(editing_user.get("manager_scope_keys", [])),
            }
        )
    editing_account = bool(str(current_form.get("editing_username") or "").strip())
    rows = []
    for user in users:
        username = user["username"]
        display_name = user.get("display_name") or username
        region_name = get_user_region_label(user) or "未设置"
        tags = []
        if username == ADMIN_USERNAME:
            tags.append('<span class="chip">主管理员</span>')
        else:
            tags.append(f'<span class="chip">{escape(account_role_label(user))}</span>')
        if ctx.current_user and username == ctx.current_user["username"]:
            tags.append('<span class="chip">当前账号</span>')
        if user.get("active"):
            tags.append('<span class="chip">启用中</span>')
        else:
            tags.append('<span class="chip">已停用</span>')
        if get_user_manager_scope_keys(user):
            manager_labels = get_manager_scope_labels(user, data)
            if manager_labels:
                tags.append(
                    f'<span class="chip">{escape("；".join(manager_labels[:2]))}</span>'
                )
        permission_labels = get_user_permission_labels(user)
        if permission_labels and not is_admin_user(user):
            tags.append(
                f'<span class="chip">{escape("；".join(permission_labels[:2]))}</span>'
            )

        can_delete = username != ADMIN_USERNAME and not (
            ctx.current_user and username == ctx.current_user["username"]
        )
        edit_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/accounts?{urlencode({"edit_username": username})}">编辑账号</a>'
        )
        permission_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/permissions?{urlencode({"username": username})}">权限控制</a>'
        )
        if user.get("player_id"):
            edit_button += (
                f'<a class="btn btn-sm btn-outline-dark" href="/players/{escape(user["player_id"])}'
                f'/edit">编辑队员资料</a>'
            )
        binding_button = (
            f'<a class="btn btn-sm btn-outline-dark" href="/bindings?{urlencode({"username": username})}">绑定参赛ID</a>'
            if is_admin_user(ctx.current_user)
            else ""
        )
        delete_button = (
            f"""
            <form method="post" action="/accounts" class="m-0">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="username" value="{escape(username)}">
              <button type="submit" class="btn btn-sm btn-outline-danger">删除账号</button>
            </form>
            """
            if can_delete
            else '<span class="small text-secondary">不可删除</span>'
        )

        rows.append(
            f"""
            <tr>
              <td>{escape(username)}</td>
              <td>{escape(display_name)}</td>
              <td>{escape(region_name)}</td>
              <td>{''.join(tags)}</td>
              <td><div class="d-flex flex-wrap gap-2">{edit_button}{permission_button}{binding_button}{delete_button}</div></td>
            </tr>
            """
        )

    account_form_title = "编辑账号" if editing_account else "新增账号"
    account_form_copy = (
        "可以在这里调整赛事负责人权限范围、所在地区和登录密码。"
        if editing_account
        else "新增后即可使用新账号登录当前网站。"
    )
    username_field_html = (
        f"""
        <input type="hidden" name="editing_username" value="{escape(current_form['editing_username'])}">
        <input class="form-control" name="username" value="{escape(current_form['username'])}" readonly>
        <div class="small text-secondary mt-2">编辑模式下用户名保持不变。</div>
        """
        if editing_account
        else f'<input class="form-control" name="username" value="{escape(current_form["username"])}" placeholder="例如 team_manager">'
    )
    password_help = (
        "留空表示不修改当前密码。"
        if editing_account
        else "至少 6 位。"
    )
    submit_action = "update" if editing_account else "create"
    submit_label = "保存账号设置" if editing_account else "创建账号"
    cancel_edit_button = (
        '<a class="btn btn-outline-dark" href="/accounts">取消编辑</a>'
        if editing_account
        else ""
    )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">管理员后台</div>
      <h1 class="display-6 fw-semibold mb-3">账号管理</h1>
      <p class="mb-0 opacity-75">这里只有管理员可以访问，用来新增账号和删除账号。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="row g-4">
        <div class="col-12 col-xl-5">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h2 class="section-title mb-2">{account_form_title}</h2>
            <p class="section-copy mb-4">{account_form_copy}</p>
            <form method="post" action="/accounts">
              <input type="hidden" name="action" value="{submit_action}">
              <div class="mb-3">
                <label class="form-label">用户名</label>
                {username_field_html}
              </div>
              <div class="mb-3">
                <label class="form-label">显示名称</label>
                <input class="form-control" name="display_name" value="{escape(current_form['display_name'])}" placeholder="例如 赛事运营">
              </div>
              <div class="mb-3">
                <label class="form-label">账号类型</label>
                <select class="form-select" name="role">
                  {option_tags({k: v for k, v in ACCOUNT_ROLE_OPTIONS.items() if k != 'admin'}, current_form['role'])}
                </select>
                <div class="small text-secondary mt-2">赛事负责人只能管理自己被分配到的“地区系列赛”范围；普通账号不能操作比赛结果。</div>
              </div>
              <div class="mb-3">
                <label class="form-label">赛事负责人管辖范围</label>
                {build_manager_scope_options(ctx.current_user, current_form.get('manager_scope_keys', []))}
                <div class="small text-secondary mt-2">仅当账号类型选择“赛事负责人”时生效，可多选。</div>
              </div>
              <div class="mb-3">
                <label class="form-label">所在地区</label>
                {build_region_picker(current_form['province_name'], current_form['region_name'], 'account-create')}
              </div>
              <div class="mb-4">
                <label class="form-label">登录密码</label>
                <input class="form-control" name="password" type="password" autocomplete="new-password">
                <div class="small text-secondary mt-2">{password_help}</div>
              </div>
              <div class="d-flex flex-wrap gap-2">
                <button type="submit" class="btn btn-dark">{submit_label}</button>
                {cancel_edit_button}
              </div>
            </form>
          </div>
        </div>
        <div class="col-12 col-xl-7">
          <div class="panel h-100 shadow-sm p-3 p-lg-4">
            <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
              <div>
                <h2 class="section-title mb-2">现有账号</h2>
                <p class="section-copy mb-0">管理员账号会被保护，当前登录账号也不能在这里直接删除；更细的能力授权请进入“权限控制”。</p>
              </div>
              <a class="btn btn-outline-dark" href="/permissions">打开权限控制页</a>
            </div>
            <div class="table-responsive">
              <table class="table align-middle">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>显示名称</th>
                    <th>地区</th>
                    <th>身份 / 状态</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {''.join(rows)}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </section>
    """
    return layout("账号管理", body, ctx, alert=alert)


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
    users = load_users()
    data = load_validated_data()
    requested_username = (
        str(form_values.get("username") or "").strip()
        if form_values
        else selected_username.strip() or form_value(ctx.query, "username").strip()
    )
    target_user = next((user for user in users if user["username"] == requested_username), None)
    if not target_user and users:
        target_user = users[0]
    current_form = {
        "username": target_user["username"] if target_user else "",
        "permission_keys": list(target_user.get("permissions", [])) if target_user else [],
        "manager_scope_keys": list(target_user.get("manager_scope_keys", [])) if target_user else [],
    }
    if form_values:
        current_form.update(
            {
                "username": str(form_values.get("username") or current_form["username"]).strip(),
                "permission_keys": normalize_permission_keys(form_values.get("permission_keys", [])),
                "manager_scope_keys": [
                    str(scope_key or "").strip()
                    for scope_key in form_values.get("manager_scope_keys", [])
                    if str(scope_key or "").strip()
                ],
            }
        )
        target_user = next(
            (user for user in users if user["username"] == current_form["username"]),
            target_user,
        )

    user_cards: list[str] = []
    for user in users:
        permission_labels = get_user_permission_labels(user)
        user_cards.append(
            f"""
            <a class="team-link-card shadow-sm p-3 h-100 d-block" href="/permissions?{urlencode({"username": user["username"]})}">
              <div class="d-flex justify-content-between align-items-start gap-3">
                <div>
                  <div class="fw-semibold">{escape(user.get("display_name") or user["username"])}</div>
                  <div class="small text-secondary mt-1">{escape(user["username"])} · {escape(account_role_label(user))}</div>
                  <div class="small text-secondary mt-1">{escape(get_user_region_label(user) or "未设置地区")}</div>
                </div>
                <span class="chip">{'管理员' if is_admin_user(user) else f'{len(permission_labels)} 项权限'}</span>
              </div>
            </a>
            """
        )

    permission_panel = '<div class="alert alert-secondary mb-0">请先从左侧选择一个账号。</div>'
    if target_user:
        role_label = account_role_label(target_user)
        permission_summary = "；".join(get_user_permission_labels(target_user)) or "暂未授予额外权限"
        if is_admin_user(target_user):
            permission_panel = f"""
            <section class="panel shadow-sm p-3 p-lg-4">
              <h2 class="section-title mb-2">权限详情</h2>
              <p class="section-copy mb-3">当前账号是管理员，默认拥有全部权限，不通过这里单独配置。</p>
              <div class="row g-3">
                <div class="col-12 col-md-6"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">账号</div><div class="stat-value mt-2">{escape(target_user['username'])}</div></div></div>
                <div class="col-12 col-md-6"><div class="stat-card h-100 p-3 shadow-sm border-0"><div class="stat-label">身份</div><div class="stat-value mt-2">{escape(role_label)}</div></div></div>
              </div>
              <div class="alert alert-light mt-4 mb-0">管理员自动具备：{escape('；'.join(PERMISSION_LABELS[key] for key in get_all_permission_keys()))}</div>
            </section>
            """
        else:
            permission_panel = f"""
            <section class="form-panel shadow-sm p-3 p-lg-4">
              <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
                <div>
                  <h2 class="section-title mb-2">编辑账号权限</h2>
                  <p class="section-copy mb-0">勾选后会立即更新该账号的实际权限。赛事类权限还需要配合下方“负责范围”一起保存。</p>
                </div>
                <div class="small text-secondary">
                  目标账号：{escape(target_user['username'])}<br>
                  基础身份：{escape(role_label)}<br>
                  当前权限：{escape(permission_summary)}
                </div>
              </div>
              <form method="post" action="/permissions">
                <input type="hidden" name="username" value="{escape(current_form['username'])}">
                {build_permission_options(current_form['permission_keys'])}
                <div class="mb-4">
                  <h3 class="h6 mb-2">赛事负责范围</h3>
                  <p class="small text-secondary mb-3">只有勾选了赛事权限的账号才会用到这里的范围。范围口径为“地区 + 系列赛”。</p>
                  {build_manager_scope_options(ctx.current_user, current_form['manager_scope_keys'])}
                </div>
                <div class="d-flex flex-wrap gap-2">
                  <button type="submit" class="btn btn-dark">保存权限设置</button>
                  <a class="btn btn-outline-dark" href="/permissions?{urlencode({'username': target_user['username']})}">重置表单</a>
                </div>
              </form>
            </section>
            """

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">管理员后台</div>
      <h1 class="display-6 fw-semibold mb-3">用户权限控制</h1>
      <p class="mb-0 opacity-75">这里集中控制账号的门派、战队、赛事与数据维护权限。一个账号可以同时拥有多个权限，最终以管理员勾选结果为准。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="row g-4">
        <div class="col-12 col-xl-4">
          <h2 class="section-title mb-3">账号列表</h2>
          <div class="row g-3">{''.join(f'<div class="col-12">{card}</div>' for card in user_cards)}</div>
        </div>
        <div class="col-12 col-xl-8">
          {permission_panel}
        </div>
      </div>
    </section>
    """
    return layout("权限控制", body, ctx, alert=alert)


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
            linked_player_ids = [
                item
                for item in get_user_bound_player_ids(user)
                if item != normalized_player_id
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
        linked_player_ids = get_user_bound_player_ids(user)
        if normalized_player_id and normalized_player_id not in linked_player_ids:
            linked_player_ids.append(normalized_player_id)
        updated_users.append(
            {
                **user,
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
    mvp_player_id = str(match.get("mvp_player_id") or "").strip()
    svp_player_id = str(match.get("svp_player_id") or "").strip()
    scapegoat_player_id = str(match.get("scapegoat_player_id") or "").strip()
    winning_camp = str(match.get("winning_camp") or "").strip()

    if not mvp_player_id:
        return "请选择本场 MVP。"
    if mvp_player_id not in participant_map:
        return "MVP 必须从本场参赛选手中选择。"
    if not svp_player_id:
        return "请选择本场 SVP。"
    if svp_player_id not in participant_map:
        return "SVP 必须从本场参赛选手中选择。"
    if mvp_player_id == svp_player_id:
        return "MVP 和 SVP 不能选择同一位选手。"
    if winning_camp == "villagers":
        if scapegoat_player_id:
            return "好人胜利时不设置背锅选手。"
        return ""
    if not scapegoat_player_id:
        return "狼人胜利时请选择本场背锅选手。"
    if scapegoat_player_id not in participant_map:
        return "背锅选手必须从本场参赛选手中选择。"
    if str(participant_map[scapegoat_player_id].get("camp") or "").strip() == winning_camp:
        return "背锅选手需要从失利阵营中选择。"
    return ""


def parse_match_form(form: dict[str, list[str]], existing_match: dict[str, Any]) -> dict[str, Any]:
    participants = []
    for index in range(len(existing_match["players"])):
        participants.append(
            {
                "player_id": form_value(form, f"player_id_{index}"),
                "team_id": form_value(form, f"team_id_{index}"),
                "seat": int(form_value(form, f"seat_{index}", "0") or "0"),
                "role": form_value(form, f"role_{index}"),
                "camp": form_value(form, f"camp_{index}"),
                "result": form_value(form, f"result_{index}"),
                "points_earned": float(form_value(form, f"points_earned_{index}", "0") or "0"),
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
        "played_on": form_value(form, "played_on").strip(),
        "table_label": form_value(form, "table_label").strip(),
        "format": form_value(form, "format").strip(),
        "duration_minutes": int(form_value(form, "duration_minutes", "0") or "0"),
        "winning_camp": form_value(form, "winning_camp"),
        "mvp_player_id": form_value(form, "mvp_player_id").strip(),
        "svp_player_id": form_value(form, "svp_player_id").strip(),
        "scapegoat_player_id": form_value(form, "scapegoat_player_id").strip(),
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
) -> str:
    if not season_name.strip():
        return "请选择赛季。"
    available_seasons = list_seasons(
        data,
        competition_name,
        selected_season=existing_season_name or season_name,
    )
    if season_name not in available_seasons:
        return "请选择该系列赛当前可录入的赛季。"
    return ""


def build_empty_match(competition_name: str = "", season_name: str = "") -> dict[str, Any]:
    return {
        "match_id": "pending-new-match",
        "competition_name": competition_name,
        "season": season_name,
        "stage": "regular_season",
        "round": 1,
        "game_no": 1,
        "played_on": china_today_label(),
        "table_label": "一号桌",
        "format": "经典十二人局",
        "duration_minutes": 60,
        "winning_camp": "villagers",
        "mvp_player_id": "",
        "svp_player_id": "",
        "scapegoat_player_id": "",
        "notes": "",
        "players": [
            {
                "player_id": "",
                "team_id": "",
                "seat": seat,
                "role": "",
                "camp": "villagers",
                "result": "win",
                "points_earned": 0.0,
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
    try:
        data = load_validated_data()
        catalog = load_series_catalog(data)
    except Exception:
        data = {"matches": []}
        catalog = []
    if current_user and not is_admin_user(current_user):
        catalog = [
            entry
            for entry in catalog
            if can_manage_matches(current_user, data, entry["competition_name"])
        ]

    if not catalog:
        return (
            f'<input class="form-control" name="competition_name" required value="{escape(current_competition_name)}">'
            '<div class="small text-secondary mt-2">当前没有你可管理的地区赛事页，请先联系管理员分配赛事负责人范围。</div>'
        )

    grouped_entries: dict[str, list[dict[str, Any]]] = {}
    for entry in catalog:
        grouped_entries.setdefault(entry["region_name"], []).append(entry)

    option_groups: list[str] = []
    known_competitions = {entry["competition_name"] for entry in catalog}
    if current_competition_name and current_competition_name not in known_competitions:
        option_groups.append(
            f'<option value="{escape(current_competition_name)}" selected>{escape(current_competition_name)}（历史赛事）</option>'
        )
    for region_name, entries in grouped_entries.items():
        option_tags_html = []
        for entry in sorted(entries, key=lambda item: (item["series_name"], item["competition_name"])):
            selected = " selected" if entry["competition_name"] == current_competition_name else ""
            option_tags_html.append(
                f'<option value="{escape(entry["competition_name"])}"{selected}>{escape(entry["series_name"])} · {escape(entry["competition_name"])}</option>'
            )
        option_groups.append(
            f'<optgroup label="{escape(region_name)}">{ "".join(option_tags_html) }</optgroup>'
        )

    return (
        f'<select class="form-select" id="match-competition-select" data-match-competition-select name="competition_name" required>{"".join(option_groups)}</select>'
        '<div class="small text-secondary mt-2">比赛会挂到已创建的地区赛事页下；如果没有对应赛事，请先去“系列赛管理”里创建。</div>'
    )


def build_match_season_field(
    current_competition_name: str,
    current_season_name: str,
) -> str:
    try:
        data = load_validated_data()
        catalog = load_series_catalog(data)
    except Exception:
        data = {"matches": []}
        catalog = []

    if not catalog:
        return (
            f'<input class="form-control" name="season" required value="{escape(current_season_name)}">'
            '<div class="small text-secondary mt-2">还没有系列赛目录时，可先手动输入赛季名称。</div>'
        )

    season_map: dict[str, list[str]] = {}
    for entry in catalog:
        season_names = list_seasons(
            data,
            entry["competition_name"],
            selected_season=current_season_name if entry["competition_name"] == current_competition_name else "",
        )
        if season_names:
            season_map[entry["competition_name"]] = season_names
    if current_competition_name and current_competition_name not in season_map and current_season_name:
        season_map[current_competition_name] = [current_season_name]
    selected_json = escape(json.dumps(season_map, ensure_ascii=False))
    return f"""
    <div class="match-season-picker" data-season-map='{selected_json}'>
      <select class="form-select" name="season" required data-match-season-select data-selected="{escape(current_season_name)}"></select>
      <div class="small text-secondary mt-2" data-match-season-helper>只显示当前正在进行中的赛季；赛季需要先在系列赛管理里配置起止时间。</div>
    </div>
    <script>
      (function() {{
        const scope = document.currentScript.previousElementSibling;
        if (!scope) return;
        const seasonMap = JSON.parse(scope.getAttribute("data-season-map") || "{{}}");
        const seasonSelect = scope.querySelector("[data-match-season-select]");
        const helper = scope.querySelector("[data-match-season-helper]");
        const competitionSelect = document.querySelector("[data-match-competition-select]");
        if (!seasonSelect || !competitionSelect) return;
        function renderSeasons() {{
          const seasons = seasonMap[competitionSelect.value] || [];
          const selected = seasonSelect.getAttribute("data-selected") || "";
          seasonSelect.innerHTML = seasons.map((season) => {{
            const isSelected = season === selected ? " selected" : "";
            return `<option value="${{season}}"${{isSelected}}>${{season}}</option>`;
          }}).join("");
          if (!seasonSelect.value && seasons.length) {{
            seasonSelect.value = seasons[0];
          }}
          if (!seasons.length) {{
            seasonSelect.innerHTML = '<option value="">暂无进行中赛季</option>';
          }}
          if (helper) {{
            helper.textContent = seasons.length
              ? '只显示当前正在进行中的赛季；赛季需要先在系列赛管理里配置起止时间。'
              : '当前地区赛事页所属系列赛还没有进行中的赛季，请先到系列赛管理里配置。';
          }}
          seasonSelect.setAttribute("data-selected", seasonSelect.value || selected);
        }}
        competitionSelect.addEventListener("change", function() {{
          seasonSelect.setAttribute("data-selected", "");
          renderSeasons();
        }});
        renderSeasons();
      }})();
    </script>
    """


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
    competition_field_html = build_match_competition_field(
        str(current.get("competition_name", "")),
        ctx.current_user,
    )
    season_field_html = build_match_season_field(
        str(current.get("competition_name", "")),
        str(current.get("season", "")),
    )
    scapegoat_hidden_attr = (
        ' style="display:none;"'
        if str(current.get("winning_camp")) == "villagers"
        else ""
    )
    participant_rows = []
    for index, player in enumerate(current["players"]):
        participant_rows.append(
            f"""
            <tr>
              <td><input class="form-control form-control-sm" data-award-player-id name="player_id_{index}" value="{escape(str(player['player_id']))}"></td>
              <td><input class="form-control form-control-sm" name="team_id_{index}" value="{escape(str(player['team_id']))}"></td>
              <td><input class="form-control form-control-sm" data-award-seat name="seat_{index}" type="number" value="{escape(str(player['seat']))}"></td>
              <td><input class="form-control form-control-sm" data-award-role name="role_{index}" value="{escape(str(player['role']))}"></td>
              <td>
                <select class="form-select form-select-sm" data-award-camp name="camp_{index}">
                  {option_tags({k: v for k, v in CAMP_OPTIONS.items() if k != 'draw'}, str(player['camp']))}
                </select>
              </td>
              <td>
                <select class="form-select form-select-sm" name="result_{index}">
                  {option_tags(RESULT_OPTIONS, str(player['result']))}
                </select>
              </td>
              <td><input class="form-control form-control-sm" name="points_earned_{index}" type="number" step="0.1" value="{escape(str(player['points_earned']))}"></td>
              <td>
                <select class="form-select form-select-sm" name="stance_result_{index}">
                  {option_tags(STANCE_OPTIONS, str(player.get('stance_result', normalize_stance_result(player))))}
                </select>
              </td>
              <td><input class="form-control form-control-sm" name="notes_{index}" value="{escape(str(player['notes']))}"></td>
            </tr>
            """
        )

    body = f"""
    <section class="form-panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-4">
        <div>
          <h1 class="section-title mb-2">{escape(heading)}</h1>
          <p class="section-copy mb-0">这里可以录入或修改一场比赛的基础信息和全部上场选手数据。比赛编号会按“城市缩写-赛季缩写-六位日期-局序号”自动生成，赛季为必填项。</p>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
        </div>
      </div>
      <form method="post" action="{escape(action_url)}">
        <div class="row g-3 mb-4">
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">比赛编号</label>
            <input class="form-control" value="{escape(str(match_code_hint))}" readonly>
            <div class="small text-secondary mt-2">保存后会根据城市、赛季、日期自动重算编号。</div>
          </div>
          <div class="col-12 col-md-6 col-xl-4">
            <label class="form-label">系列赛名称</label>
            {competition_field_html}
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">赛季</label>
            {season_field_html}
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">阶段</label>
            <select class="form-select" name="stage">
              {option_tags(STAGE_OPTIONS, str(current['stage']))}
            </select>
          </div>
          <div class="col-6 col-md-3 col-xl-1">
            <label class="form-label">轮次</label>
            <input class="form-control" name="round" type="number" value="{escape(str(current['round']))}">
          </div>
          <div class="col-6 col-md-3 col-xl-1">
            <label class="form-label">局次</label>
            <input class="form-control" name="game_no" type="number" value="{escape(str(current['game_no']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-2">
            <label class="form-label">日期</label>
            <input class="form-control" name="played_on" type="date" value="{escape(str(current['played_on']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">桌号</label>
            <input class="form-control" name="table_label" value="{escape(str(current['table_label']))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">板型</label>
            <input class="form-control" name="format" value="{escape(str(current['format']))}">
          </div>
          <div class="col-12 col-md-3 col-xl-2">
            <label class="form-label">时长</label>
            <input class="form-control" name="duration_minutes" type="number" value="{escape(str(current['duration_minutes']))}">
          </div>
          <div class="col-12 col-md-3 col-xl-4">
            <label class="form-label">胜利阵营</label>
            <select class="form-select" data-winning-camp-select name="winning_camp">
              {option_tags(WINNING_CAMP_OPTIONS, str(current['winning_camp']))}
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">MVP</label>
            <select class="form-select" data-award-select="mvp" data-selected="{escape(str(current.get('mvp_player_id', '')))}" name="mvp_player_id">
              {build_match_award_select('mvp_player_id', str(current.get('mvp_player_id', '')), current['players'], '请选择 MVP')}
            </select>
          </div>
          <div class="col-12 col-md-4">
            <label class="form-label">SVP</label>
            <select class="form-select" data-award-select="svp" data-selected="{escape(str(current.get('svp_player_id', '')))}" name="svp_player_id">
              {build_match_award_select('svp_player_id', str(current.get('svp_player_id', '')), current['players'], '请选择 SVP')}
            </select>
          </div>
          <div class="col-12 col-md-4" data-scapegoat-field{scapegoat_hidden_attr}>
            <label class="form-label">背锅</label>
            <select class="form-select" data-award-select="scapegoat" data-selected="{escape(str(current.get('scapegoat_player_id', '')))}" name="scapegoat_player_id">
              {build_match_award_select('scapegoat_player_id', str(current.get('scapegoat_player_id', '')), current['players'], '请选择背锅选手', str(current.get('winning_camp', '')), True)}
            </select>
            <div class="small text-secondary mt-2">仅在狼人胜利时设置背锅选手。</div>
          </div>
          <div class="col-12">
            <label class="form-label">比赛备注</label>
            <textarea class="form-control" name="notes" rows="3">{escape(str(current['notes']))}</textarea>
          </div>
        </div>

        <div class="d-flex flex-column flex-lg-row justify-content-between gap-3 mb-3">
          <div>
            <h2 class="h5 mb-1">上场选手数据</h2>
            <div class="small text-secondary">这里按当前顺序编辑所有参赛选手信息。</div>
          </div>
        </div>

        <div class="table-responsive mb-4">
          <table class="table align-middle">
            <thead>
              <tr>
                <th>队员编号</th>
                <th>战队编号</th>
                <th>座位</th>
                <th>角色</th>
                <th>阵营</th>
                <th>结果</th>
                <th>得分</th>
                <th>站边结果</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {''.join(participant_rows)}
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap gap-2">
          <button type="submit" class="btn btn-dark">{escape(submit_label)}</button>
          <a class="btn btn-outline-dark" href="{escape(next_path)}">取消</a>
        </div>
      </form>
    </section>
    <script>
      (function() {{
        const form = document.currentScript.previousElementSibling.querySelector("form");
        if (!form) return;
        const winningCampSelect = form.querySelector("[data-winning-camp-select]");
        const mvpSelect = form.querySelector('[data-award-select="mvp"]');
        const svpSelect = form.querySelector('[data-award-select="svp"]');
        const scapegoatSelect = form.querySelector('[data-award-select="scapegoat"]');
        const scapegoatField = form.querySelector("[data-scapegoat-field]");
        const playerInputs = Array.from(form.querySelectorAll("[data-award-player-id]"));
        const seatInputs = Array.from(form.querySelectorAll("[data-award-seat]"));
        const roleInputs = Array.from(form.querySelectorAll("[data-award-role]"));
        const campInputs = Array.from(form.querySelectorAll("[data-award-camp]"));
        function collectParticipants() {{
          return playerInputs.map((input, index) => {{
            const playerId = (input.value || "").trim();
            const seat = (seatInputs[index] && seatInputs[index].value) || "";
            const role = (roleInputs[index] && roleInputs[index].value) || "";
            const camp = (campInputs[index] && campInputs[index].value) || "";
            return {{ playerId, seat, role, camp }};
          }}).filter((item) => item.playerId);
        }}
        function buildOptions(select, participants, placeholder, losingOnly) {{
          if (!select) return;
          const selectedValue = select.value || select.getAttribute("data-selected") || "";
          const winningCamp = winningCampSelect ? winningCampSelect.value : "";
          const filtered = losingOnly
            ? participants.filter((item) => item.camp && item.camp !== winningCamp)
            : participants;
          const options = [`<option value="">${{placeholder}}</option>`].concat(
            filtered.map((item) => {{
              const pieces = [`${{item.seat}}号`, item.playerId];
              if (item.role) pieces.push(item.role);
              const selected = item.playerId === selectedValue ? " selected" : "";
              return `<option value="${{item.playerId}}"${{selected}}>${{pieces.join(" · ")}}</option>`;
            }})
          );
          select.innerHTML = options.join("");
          if (selectedValue && !filtered.some((item) => item.playerId === selectedValue)) {{
            select.value = "";
          }}
          select.setAttribute("data-selected", select.value || "");
        }}
        function renderAwards() {{
          const participants = collectParticipants();
          buildOptions(mvpSelect, participants, "请选择 MVP", false);
          buildOptions(svpSelect, participants, "请选择 SVP", false);
          if (winningCampSelect && winningCampSelect.value === "villagers") {{
            if (scapegoatField) scapegoatField.style.display = "none";
            if (scapegoatSelect) {{
              scapegoatSelect.value = "";
              scapegoatSelect.setAttribute("data-selected", "");
            }}
          }} else {{
            if (scapegoatField) scapegoatField.style.display = "";
            buildOptions(scapegoatSelect, participants, "请选择背锅选手", true);
          }}
        }}
        [winningCampSelect, ...playerInputs, ...seatInputs, ...roleInputs, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("input", renderAwards));
        [winningCampSelect, ...campInputs]
          .filter(Boolean)
          .forEach((element) => element.addEventListener("change", renderAwards));
        renderAwards();
      }})();
    </script>
    """
    return layout(page_title, body, ctx, alert=alert)


def get_match_edit_page(
    ctx: RequestContext, match_id: str, alert: str = "", field_values: dict[str, Any] | None = None
) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)
    if ctx.current_user and not can_manage_matches(
        ctx.current_user,
        data,
        get_match_competition_name(match),
    ):
        return layout("没有权限", '<div class="alert alert-danger">你不能编辑这个地区系列赛下的比赛。</div>', ctx)

    current = field_values or match
    next_path = form_value(ctx.query, "next", "/dashboard")
    match_code_hint = current.get("match_id", match_id)
    return render_match_form_page(
        ctx,
        current,
        f"/matches/{match_id}/edit?next={quote(next_path)}",
        "编辑比赛",
        "编辑比赛",
        "保存修改",
        next_path,
        match_code_hint,
        alert=alert,
    )


def get_match_create_page(
    ctx: RequestContext,
    alert: str = "",
    field_values: dict[str, Any] | None = None,
) -> str:
    current = field_values or build_empty_match(
        form_value(ctx.query, "competition").strip(),
        form_value(ctx.query, "season").strip(),
    )
    if current.get("competition_name"):
        data = load_validated_data()
        if ctx.current_user and not can_manage_matches(
            ctx.current_user,
            data,
            str(current.get("competition_name") or ""),
        ):
            return layout("没有权限", '<div class="alert alert-danger">你不能在这个地区系列赛下创建比赛。</div>', ctx)
    next_path = form_value(ctx.query, "next").strip() or build_scoped_path(
        "/competitions",
        current.get("competition_name") or None,
        current.get("season") or None,
    ) or "/competitions"
    return render_match_form_page(
        ctx,
        current,
        f"/matches/new?next={quote(next_path)}",
        "录入比赛",
        "录入比赛结果",
        "创建比赛",
        next_path,
        "保存后自动生成",
        alert=alert,
    )


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
          <span class="small text-secondary">默认账号：admin，默认密码：admin123</span>
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
    users.append(
        {
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
        }
    )
    save_users(users)
    return start_response_html(
        start_response,
        "200 OK",
        login_page(ctx, alert="注册成功，请使用新账号登录。"),
    )


def handle_login(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", login_page(ctx))

    username = form_value(ctx.form, "username").strip()
    password = form_value(ctx.form, "password")
    for user in load_users():
        if user["username"] == username and user.get("active") and verify_password(password, user):
            token = secrets.token_urlsafe(24)
            SESSIONS[token] = username
            next_path = form_value(ctx.query, "next", "/dashboard")
            return redirect(
                start_response,
                next_path,
                headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")],
            )

    return start_response_html(start_response, "200 OK", login_page(ctx, alert="用户名或密码不正确。"))


def handle_logout(start_response, environ: dict[str, Any]):
    jar = parse_cookies(environ)
    token = jar.get(SESSION_COOKIE)
    if token is not None:
        SESSIONS.pop(token.value, None)
    return redirect(
        start_response,
        "/login",
        headers=[("Set-Cookie", f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax")],
    )


def handle_accounts(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_accounts_page(ctx))

    action = form_value(ctx.form, "action")
    users = load_users()

    if action == "create":
        username = form_value(ctx.form, "username").strip()
        display_name = form_value(ctx.form, "display_name").strip()
        role = form_value(ctx.form, "role", "member").strip()
        province_name = form_value(ctx.form, "province_name", DEFAULT_PROVINCE_NAME).strip()
        region_name = form_value(ctx.form, "region_name", "广州市").strip()
        manager_scope_keys = [
            str(item or "").strip()
            for item in ctx.form.get("manager_scope_key", [])
            if str(item or "").strip()
        ]
        password = form_value(ctx.form, "password")
        error = validate_account_form(
            username,
            display_name,
            password,
            users,
            role,
            province_name,
            region_name,
            manager_scope_keys=manager_scope_keys,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(
                    ctx,
                    alert=error,
                    form_values={
                        "username": username,
                        "display_name": display_name,
                        "role": role,
                        "province_name": province_name or DEFAULT_PROVINCE_NAME,
                        "region_name": region_name or "广州市",
                        "manager_scope_keys": manager_scope_keys,
                    },
                ),
            )

        password_salt, password_hash = hash_password(password)
        normalized_province, normalized_region = normalize_user_location(
            province_name,
            region_name,
        )
        users.append(
            {
                "username": username,
                "display_name": display_name,
                "password_salt": password_salt,
                "password_hash": password_hash,
                "active": True,
                "player_id": None,
                "linked_player_ids": [],
                "manager_scope_keys": manager_scope_keys if role == "event_manager" else [],
                "permissions": (
                    list(DEFAULT_EVENT_MANAGER_PERMISSION_KEYS)
                    if role == "event_manager"
                    else []
                ),
                "role": role,
                "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
                "region_name": normalized_region or "广州市",
            }
        )
        save_users(users)
        return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert=f"账号 {username} 已创建。"))

    if action == "update":
        editing_username = form_value(ctx.form, "editing_username").strip()
        display_name = form_value(ctx.form, "display_name").strip()
        role = form_value(ctx.form, "role", "member").strip()
        province_name = form_value(ctx.form, "province_name", DEFAULT_PROVINCE_NAME).strip()
        region_name = form_value(ctx.form, "region_name", "广州市").strip()
        manager_scope_keys = [
            str(item or "").strip()
            for item in ctx.form.get("manager_scope_key", [])
            if str(item or "").strip()
        ]
        password = form_value(ctx.form, "password")
        existing_user = next((user for user in users if user["username"] == editing_username), None)
        if not existing_user:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(ctx, alert="没有找到要编辑的账号。"),
            )
        if editing_username == ADMIN_USERNAME and role != "admin":
            role = "admin"
        error = validate_account_update_form(
            display_name,
            password,
            role,
            province_name,
            region_name,
            manager_scope_keys=manager_scope_keys,
        )
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_accounts_page(
                    ctx,
                    alert=error,
                    form_values={
                        "editing_username": editing_username,
                        "username": editing_username,
                        "display_name": display_name,
                        "role": role,
                        "province_name": province_name or DEFAULT_PROVINCE_NAME,
                        "region_name": region_name or "广州市",
                        "manager_scope_keys": manager_scope_keys,
                    },
                ),
            )
        normalized_province, normalized_region = normalize_user_location(
            province_name,
            region_name,
        )
        updated_users = []
        for user in users:
            if user["username"] != editing_username:
                updated_users.append(user)
                continue
            updated_user = {
                **user,
                "display_name": display_name,
                "role": role,
                "manager_scope_keys": (
                    manager_scope_keys
                    if role == "event_manager"
                    else list(user.get("manager_scope_keys", []))
                ),
                "permissions": (
                    list(DEFAULT_EVENT_MANAGER_PERMISSION_KEYS)
                    if role == "event_manager" and not normalize_permission_keys(user.get("permissions", []))
                    else normalize_permission_keys(user.get("permissions", []))
                ),
                "province_name": normalized_province or DEFAULT_PROVINCE_NAME,
                "region_name": normalized_region or "广州市",
            }
            if password:
                password_salt, password_hash = hash_password(password)
                updated_user["password_salt"] = password_salt
                updated_user["password_hash"] = password_hash
            updated_users.append(updated_user)
        save_users(updated_users)
        return start_response_html(
            start_response,
            "200 OK",
            get_accounts_page(ctx, alert=f"账号 {editing_username} 已更新。"),
        )

    if action == "delete":
        username = form_value(ctx.form, "username").strip()
        if not username:
            return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert="缺少要删除的账号。"))
        if username == ADMIN_USERNAME:
            return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert="主管理员账号不能删除。"))
        if ctx.current_user and username == ctx.current_user["username"]:
            return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert="当前登录账号不能删除。"))
        if not any(user["username"] == username for user in users):
            return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert="没有找到要删除的账号。"))

        users = [user for user in users if user["username"] != username]
        revoke_user_sessions(username)
        save_users(users)
        return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert=f"账号 {username} 已删除。"))

    return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert="未识别的操作。"))


def handle_permission_control(ctx: RequestContext, start_response):
    guard = require_admin(ctx, start_response)
    if guard is not None:
        return guard

    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_permission_control_page(ctx))

    users = load_users()
    username = form_value(ctx.form, "username").strip()
    permission_keys = [
        str(permission_key or "").strip()
        for permission_key in ctx.form.get("permission_key", [])
        if str(permission_key or "").strip()
    ]
    manager_scope_keys = [
        str(scope_key or "").strip()
        for scope_key in ctx.form.get("manager_scope_key", [])
        if str(scope_key or "").strip()
    ]
    target_user = next((user for user in users if user["username"] == username), None)
    if not target_user:
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(ctx, alert="没有找到要设置权限的账号。"),
        )
    if is_admin_user(target_user):
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(
                ctx,
                alert="管理员默认拥有全部权限，无需单独配置。",
                selected_username=username,
            ),
        )

    error = validate_permission_assignment(permission_keys, manager_scope_keys)
    if error:
        return start_response_html(
            start_response,
            "200 OK",
            get_permission_control_page(
                ctx,
                alert=error,
                selected_username=username,
                form_values={
                    "username": username,
                    "permission_keys": permission_keys,
                    "manager_scope_keys": manager_scope_keys,
                },
            ),
        )

    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue
        updated_users.append(
            {
                **user,
                "permissions": normalize_permission_keys(permission_keys),
                "manager_scope_keys": manager_scope_keys,
            }
        )
    save_users(updated_users)
    return start_response_html(
        start_response,
        "200 OK",
        get_permission_control_page(
            ctx,
            alert=f"账号 {username} 的权限已更新。",
            selected_username=username,
        ),
    )


def update_user_account_fields(
    users: list[dict[str, Any]],
    username: str,
    display_name: str,
    province_name: str,
    region_name: str,
    gender: str,
    bio: str,
    password: str,
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
        updated_users.append(next_user)
    return updated_users


def handle_profile(ctx: RequestContext, start_response):
    from web.features.profile import handle_profile as impl

    return impl(ctx, start_response)



def handle_player_bindings(ctx: RequestContext, start_response):
    if not ctx.current_user:
        return redirect(start_response, "/login?next=/bindings")
    if ctx.method == "GET":
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                target_username=form_value(ctx.query, "username").strip(),
                selected_player_id=form_value(ctx.query, "player_id").strip(),
            ),
        )

    data = load_validated_data()
    users = load_users()
    action = form_value(ctx.form, "action").strip()
    target_username = form_value(ctx.form, "target_username").strip() or ctx.current_user["username"]
    player_id = form_value(ctx.form, "player_id").strip()
    target_user = next((user for user in users if user["username"] == target_username), None)
    source_player = next((player for player in data["players"] if player["player_id"] == player_id), None)
    if not target_user:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(ctx, alert="没有找到要绑定的账号。"),
        )
    if not source_player:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert="没有找到对应的参赛ID档案。",
                target_username=target_username,
            ),
        )
    if not can_manage_player_bindings(data, ctx.current_user, target_user, source_player):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">你没有权限操作这条绑定关系。</div>', ctx),
        )

    owner_user = get_user_by_player_id(users, player_id)
    if owner_user and owner_user["username"] != target_user["username"]:
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"参赛ID {player_id} 已经绑定到账号 {owner_user['username']}。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "bind_player_id":
        season_conflict = find_season_binding_conflict(data, target_user, player_id)
        if season_conflict:
            conflict_player_id, conflict_scopes = season_conflict
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert=(
                        f"账号 {target_username} 已经绑定赛季参赛ID {conflict_player_id}，"
                        f"覆盖范围：{'、'.join(conflict_scopes)}。同一赛季只需要绑定一个ID。"
                    ),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        users = add_user_linked_player_id(users, target_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="保存绑定失败：" + "；".join(errors[:3]),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已将参赛ID {player_id} 绑定到账号 {target_username}。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    if action == "unbind_player_id":
        if target_user.get("player_id") == player_id:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="当前主身份不能直接解绑；如需变更，请联系管理员处理。",
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        users = remove_user_linked_player_id(users, target_username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_player_bindings_page(
                    ctx,
                    alert="解绑失败：" + "；".join(errors[:3]),
                    target_username=target_username,
                    selected_player_id=player_id,
                ),
            )
        return start_response_html(
            start_response,
            "200 OK",
            get_player_bindings_page(
                ctx,
                alert=f"已解除账号 {target_username} 与参赛ID {player_id} 的绑定。",
                target_username=target_username,
                selected_player_id=player_id,
            ),
        )

    return start_response_html(
        start_response,
        "200 OK",
        get_player_bindings_page(ctx, alert="未识别的绑定操作。", target_username=target_username),
    )


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
    if get_team_season_status(data, team) != "ongoing":
        return start_response_html(
            start_response,
            "200 OK",
            get_team_page(ctx, team_id, alert="当前战队所属赛季已结束，队标与战队资料不再允许修改。"),
        )
    if not can_manage_team(ctx, team, current_player):
        return start_response_html(
            start_response,
            "403 Forbidden",
            layout("没有权限", '<div class="alert alert-danger">只有具备战队管理权限的账号、战队队长或管理员可以更新队标。</div>', ctx),
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



def handle_match_edit(ctx: RequestContext, start_response, match_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_match_edit_page(ctx, match_id))

    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return start_response_html(start_response, "404 Not Found", layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx))
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        get_match_competition_name(match),
        "你不能编辑这个地区系列赛下的比赛。",
    )
    if permission_guard is not None:
        return permission_guard

    updated_match = parse_match_form(ctx.form, match)
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        updated_match["competition_name"],
        "你不能把比赛保存到未授权的地区系列赛下。",
    )
    if permission_guard is not None:
        return permission_guard
    competition_error = validate_match_competition_selection(
        data,
        updated_match["competition_name"],
    )
    if competition_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=competition_error, field_values=updated_match),
        )
    season_error = validate_match_season_selection(
        data,
        updated_match["competition_name"],
        updated_match["season"],
        existing_season_name=(match.get("season") or "").strip(),
    )
    if season_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=season_error, field_values=updated_match),
        )
    award_error = validate_match_awards(updated_match)
    if award_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert=award_error, field_values=updated_match),
        )
    matches = []
    for item in data["matches"]:
        if item["match_id"] == match_id:
            matches.append(updated_match)
        else:
            matches.append(item)

    normalized_matches, resolved_match_id = canonicalize_match_ids(
        matches,
        target_original_id=match_id,
    )
    users = load_users()
    data["matches"] = normalized_matches
    created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert="保存失败：" + "；".join(errors[:3]), field_values=updated_match),
        )

    next_path = form_value(ctx.query, "next").strip() or f"/matches/{resolved_match_id}"
    next_path = replace_match_path_id(next_path, match_id, resolved_match_id or match_id)
    if created_player_ids and next_path.startswith("/matches/"):
        next_path = append_alert_query(next_path, "placeholder-created")
    return redirect(start_response, next_path)


def handle_match_create(ctx: RequestContext, start_response):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_match_create_page(ctx))

    data = load_validated_data()
    new_match = parse_match_form(ctx.form, build_empty_match())
    permission_guard = require_competition_manager(
        ctx,
        start_response,
        data,
        new_match["competition_name"],
        "你不能在这个地区系列赛下创建比赛。",
    )
    if permission_guard is not None:
        return permission_guard
    competition_error = validate_match_competition_selection(
        data,
        new_match["competition_name"],
    )
    if competition_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=competition_error,
                field_values=new_match,
            ),
        )
    season_error = validate_match_season_selection(
        data,
        new_match["competition_name"],
        new_match["season"],
    )
    if season_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=season_error,
                field_values=new_match,
            ),
        )
    award_error = validate_match_awards(new_match)
    if award_error:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert=award_error,
                field_values=new_match,
            ),
        )
    normalized_matches, resolved_match_id = canonicalize_match_ids(
        [*data["matches"], new_match],
        target_original_id=new_match["match_id"],
    )
    users = load_users()
    data["matches"] = normalized_matches
    created_player_ids = ensure_placeholder_players_for_matches(data, normalized_matches)
    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_create_page(
                ctx,
                alert="保存失败：" + "；".join(errors[:3]),
                field_values=new_match,
            ),
        )

    next_path = form_value(ctx.query, "next").strip()
    if next_path:
        if created_player_ids and next_path.startswith("/matches/"):
            next_path = append_alert_query(next_path, "placeholder-created")
        return redirect(start_response, next_path)
    redirect_path = f"/matches/{resolved_match_id}"
    if created_player_ids:
        redirect_path = append_alert_query(redirect_path, "placeholder-created")
    return redirect(start_response, redirect_path)


def app(environ, start_response):
    try:
        ctx = build_context(environ)
        path = ctx.path

        if path == "/":
            return redirect(start_response, "/dashboard")
        if path.startswith("/assets/"):
            return serve_asset(start_response, path)
        if path == "/login":
            return handle_login(ctx, start_response)
        if path == "/register":
            return handle_register(ctx, start_response)
        if path == "/logout":
            return handle_logout(start_response, environ)

        if path == "/dashboard":
            return start_response_html(start_response, "200 OK", get_dashboard_page(ctx))
        if path == "/competitions":
            return handle_competitions(ctx, start_response)
        if path == "/schedule":
            return start_response_html(start_response, "200 OK", get_schedule_page(ctx))
        if path.startswith("/series/"):
            series_slug = path.split("/", 2)[2]
            return start_response_html(start_response, "200 OK", get_series_page(ctx, series_slug))
        if path.startswith("/days/"):
            played_on = path.split("/", 2)[2]
            return start_response_html(start_response, "200 OK", get_match_day_page(ctx, played_on))
        if path == "/guilds":
            return handle_guilds(ctx, start_response)
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
        if path == "/matches/new":
            guard = require_login(ctx, start_response)
            if guard is not None:
                return guard
            manager_guard = require_match_manager(ctx, start_response)
            if manager_guard is not None:
                return manager_guard
            return handle_match_create(ctx, start_response)
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
            return start_response_html(start_response, "200 OK", get_match_page(ctx, match_id))
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
        if path.startswith("/players/"):
            player_id = path.split("/", 2)[2]
            return start_response_html(start_response, "200 OK", get_player_page(ctx, player_id))
        if path.startswith("/teams/"):
            team_id = path.split("/", 2)[2]
            return start_response_html(start_response, "200 OK", get_team_page(ctx, team_id))

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
    with make_server("", PORT, app) as server:
        print(f"本地站点已启动：http://localhost:{PORT}")
        print("中国时间：", china_now_label())
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
