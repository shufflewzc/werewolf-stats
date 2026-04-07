#!/usr/bin/env python3

from __future__ import annotations

import base64
import cgi
import hashlib
import hmac
import mimetypes
import re
import secrets
import sys
from dataclasses import dataclass
from datetime import datetime
from html import escape
from http import cookies
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode

from wsgiref.simple_server import make_server

from generate_stats import (
    build_player_details,
    build_player_rows,
    build_team_rows,
    format_pct,
    get_match_competition_name,
    list_competitions,
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

from zoneinfo import ZoneInfo


CHINA_TZ = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
ASSETS_DIR = ROOT / "assets"
PLAYER_ASSETS_DIR = ASSETS_DIR / "players"
PLAYER_UPLOAD_DIR = PLAYER_ASSETS_DIR / "uploads"
DEFAULT_PLAYER_PHOTO = "assets/players/default-player.svg"
SESSION_COOKIE = "werewolf_session"
PORT = 8000
SESSIONS: dict[str, str] = {}
CAPTCHA_CHALLENGES: dict[str, dict[str, str]] = {}
ADMIN_USERNAME = "admin"
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,31}$")
SLUG_SANITIZE_PATTERN = re.compile(r"[^a-z0-9_-]+")
ALIAS_SPLIT_PATTERN = re.compile(r"[\n,，、]+")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}
STAGE_OPTIONS = {
    "regular_season": "常规赛",
    "playoffs": "季后赛",
    "finals": "总决赛",
    "showmatch": "表演赛",
}
CAMP_OPTIONS = {
    "villagers": "好人阵营",
    "werewolves": "狼人阵营",
    "third_party": "第三方阵营",
    "draw": "平局",
}
RESULT_OPTIONS = {
    "win": "胜",
    "loss": "负",
    "draw": "平",
}
STANCE_OPTIONS = {
    "villagers": "站好人",
    "werewolves": "站狼人",
    "third_party": "站第三方",
    "none": "未站边",
}


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
        if content_type.startswith("multipart/form-data"):
            storage = cgi.FieldStorage(
                fp=environ["wsgi.input"],
                environ=environ,
                keep_blank_values=True,
            )
            for field in storage.list or []:
                if field.filename:
                    files.setdefault(field.name, []).append(
                        UploadedFile(
                            filename=field.filename,
                            content_type=field.type or "application/octet-stream",
                            data=field.file.read(),
                        )
                    )
                else:
                    form.setdefault(field.name, []).append(field.value)
        else:
            size = int(environ.get("CONTENT_LENGTH") or 0)
            raw = environ["wsgi.input"].read(size).decode("utf-8")
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


def is_admin_user(user: dict[str, Any] | None) -> bool:
    return bool(user and user.get("username") == ADMIN_USERNAME)


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


def layout(title: str, body: str, ctx: RequestContext, alert: str = "") -> str:
    user_html = ""
    nav_links = []
    if ctx.current_user:
        display_name = ctx.current_user.get("display_name") or ctx.current_user["username"]
        user_html = f"""
        <div class="d-flex flex-wrap align-items-center gap-3">
          <span class="small text-secondary">当前登录：{escape(display_name)}</span>
          <form method="post" action="/logout" class="m-0">
            <button type="submit" class="btn btn-outline-dark btn-sm">退出登录</button>
          </form>
        </div>
        """
        nav_links = [
            '<a class="nav-link px-0" href="/dashboard">首页</a>',
            '<a class="nav-link px-0" href="/competitions">比赛页面</a>',
            '<a class="nav-link px-0" href="/profile">个人后台</a>',
            '<a class="nav-link px-0" href="/team-center">战队操作</a>',
        ]
        if is_admin_user(ctx.current_user):
            nav_links.append('<a class="nav-link px-0" href="/accounts">账号管理</a>')
    else:
        nav_links = [
            '<a class="nav-link px-0" href="/dashboard">首页</a>',
            '<a class="nav-link px-0" href="/competitions">比赛页面</a>',
        ]
        user_html = """
        <div class="d-flex flex-wrap align-items-center gap-2">
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
    <title>{escape(title)}</title>
    <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.8/dist/css/bootstrap.min.css">
    <style>
      :root {{
        --bg: #f5f3ed;
        --surface: rgba(255, 255, 255, 0.92);
        --ink: #1d2a22;
        --muted: #627066;
        --accent: #9e2a2b;
        --accent-dark: #5c1a1b;
        --line: rgba(34, 48, 40, 0.08);
      }}
      body {{
        min-height: 100vh;
        color: var(--ink);
        background:
          radial-gradient(circle at top left, rgba(158, 42, 43, 0.14), transparent 28%),
          radial-gradient(circle at top right, rgba(33, 84, 58, 0.08), transparent 24%),
          linear-gradient(180deg, #faf7f1 0%, var(--bg) 100%);
      }}
      .shell {{
        max-width: 1360px;
      }}
      .topbar, .panel {{
        background: var(--surface);
        border-radius: 24px;
      }}
      .hero {{
        background: linear-gradient(135deg, rgba(27, 35, 30, 0.97), rgba(74, 27, 28, 0.94));
        color: #fff7f2;
        border-radius: 28px;
      }}
      .eyebrow {{
        font-size: 0.74rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: rgba(255, 248, 243, 0.74);
      }}
      .section-title {{
        font-size: clamp(1.35rem, 3vw, 2rem);
        letter-spacing: -0.03em;
      }}
      .section-copy {{
        color: var(--muted);
      }}
      .stat-card {{
        background: var(--surface);
        border-radius: 22px;
      }}
      .stat-label {{
        font-size: 0.78rem;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: var(--muted);
      }}
      .stat-value {{
        font-size: clamp(1.7rem, 4vw, 2.5rem);
        line-height: 1;
        font-weight: 700;
      }}
      .team-link-card {{
        display: block;
        background: var(--surface);
        border-radius: 22px;
        color: inherit;
        text-decoration: none;
        transition: transform 0.16s ease, box-shadow 0.16s ease;
      }}
      .team-link-card:hover {{
        transform: translateY(-3px);
        box-shadow: 0 1rem 2rem rgba(22, 28, 24, 0.08);
      }}
      .table {{
        --bs-table-bg: transparent;
        --bs-table-border-color: var(--line);
      }}
      .table thead th {{
        white-space: nowrap;
        font-size: 0.78rem;
        letter-spacing: 0.08em;
        text-transform: uppercase;
        color: var(--muted);
      }}
      .small-muted {{
        color: var(--muted);
      }}
      .chip {{
        display: inline-flex;
        align-items: center;
        border-radius: 999px;
        padding: 0.35rem 0.7rem;
        background: rgba(29, 42, 34, 0.06);
        color: var(--ink);
        font-size: 0.9rem;
      }}
      .hero .chip {{
        background: rgba(255, 247, 242, 0.18);
        color: #fffdfa;
        border: 1px solid rgba(255, 247, 242, 0.28);
        box-shadow: 0 0.5rem 1.2rem rgba(12, 16, 14, 0.18);
      }}
      .form-panel {{
        background: var(--surface);
        border-radius: 24px;
      }}
      .form-label {{
        font-size: 0.9rem;
        color: var(--muted);
      }}
      .player-photo-frame {{
        width: min(100%, 260px);
        aspect-ratio: 1 / 1;
        border-radius: 28px;
        overflow: hidden;
        background:
          radial-gradient(circle at top, rgba(158, 42, 43, 0.16), transparent 42%),
          linear-gradient(160deg, rgba(255, 248, 243, 0.96), rgba(236, 228, 219, 0.9));
        border: 1px solid rgba(255, 247, 242, 0.22);
        box-shadow: 0 1.2rem 2.6rem rgba(12, 16, 14, 0.18);
      }}
      .panel .player-photo-frame {{
        border-color: rgba(29, 42, 34, 0.08);
        box-shadow: 0 1rem 2rem rgba(22, 28, 24, 0.08);
      }}
      .player-photo {{
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
      }}
      .nav-link {{
        color: var(--muted);
        font-weight: 600;
      }}
      .nav-link:hover {{
        color: var(--accent-dark);
      }}
    </style>
  </head>
  <body>
    <div class="container-fluid px-3 px-md-4 px-xl-5 py-4">
      <div class="shell mx-auto">
        <div class="topbar shadow-sm px-4 py-3 mb-4">
          <div class="d-flex flex-column flex-xl-row justify-content-between gap-3 align-items-xl-center">
            <div>
              <div class="fw-semibold">狼人杀联赛管理台</div>
              <div class="small text-secondary">当前时间：{escape(ctx.now_label)}</div>
            </div>
            <div class="d-flex flex-wrap align-items-center gap-4">
              <nav class="d-flex flex-wrap gap-4">{''.join(nav_links)}</nav>
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
    try:
        persist_matches(matches)
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


def get_user_by_player_id(users: list[dict[str, Any]], player_id: str) -> dict[str, Any] | None:
    for user in users:
        if user.get("player_id") == player_id:
            return user
    return None


def ensure_player_asset_dirs() -> None:
    PLAYER_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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


def can_manage_player(ctx: RequestContext, player_id: str) -> bool:
    if not ctx.current_user:
        return False
    if is_admin_user(ctx.current_user):
        return True
    return ctx.current_user.get("player_id") == player_id


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


def build_player_photo_html(photo_path: str, display_name: str, extra_class: str = "") -> str:
    return (
        f'<div class="player-photo-frame mx-auto {escape(extra_class)}">'
        f'<img class="player-photo" src="{escape(public_asset_url(resolve_player_photo_path(photo_path)))}" alt="{escape(display_name)} 照片">'
        "</div>"
    )


def get_team_by_id(data: dict[str, Any], team_id: str) -> dict[str, Any] | None:
    for team in data["teams"]:
        if team["team_id"] == team_id:
            return team
    return None


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


def user_has_match_history(data: dict[str, Any], player_id: str) -> bool:
    for match in data["matches"]:
        if any(entry["player_id"] == player_id for entry in match["players"]):
            return True
    return False


def get_selected_competition(
    ctx: RequestContext, competition_names: list[str]
) -> str | None:
    selected = form_value(ctx.query, "competition").strip()
    if selected and selected in competition_names:
        return selected
    return None


def build_competition_switcher(
    base_path: str,
    competition_names: list[str],
    selected_competition: str | None,
    tone: str = "dark",
    all_label: str = "全部赛事",
) -> str:
    if not competition_names:
        return ""

    links = [
        (
            all_label,
            base_path,
            selected_competition is None,
        )
    ]
    for competition_name in competition_names:
        links.append(
            (
                competition_name,
                f"{base_path}?{urlencode({'competition': competition_name})}",
                selected_competition == competition_name,
            )
        )

    if tone == "light":
        return "".join(
            (
                f'<a class="btn {"btn-light text-dark shadow-sm" if is_active else "btn-light text-white border-white bg-transparent"} btn-sm" '
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


def resolve_team_player_ids(
    data: dict[str, Any], team_id: str, selected_competition: str | None = None
) -> list[str]:
    seen: list[str] = []
    for match in sorted(
        data["matches"],
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    ):
        if selected_competition and get_match_competition_name(match) != selected_competition:
            continue
        for entry in match["players"]:
            if entry["team_id"] == team_id and entry["player_id"] not in seen:
                seen.append(entry["player_id"])

    if seen:
        return seen

    team = get_team_by_id(data, team_id)
    return team["members"] if team else []


def build_competition_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    rows = []
    for competition_name in list_competitions(data):
        matches = [
            match
            for match in data["matches"]
            if get_match_competition_name(match) == competition_name
        ]
        team_ids = sorted(
            {
                entry["team_id"]
                for match in matches
                for entry in match["players"]
            }
        )
        player_ids = sorted(
            {
                entry["player_id"]
                for match in matches
                for entry in match["players"]
            }
        )
        seasons = sorted({match["season"] for match in matches}, reverse=True)
        rows.append(
            {
                "competition_name": competition_name,
                "match_count": len(matches),
                "team_count": len(team_ids),
                "player_count": len(player_ids),
                "latest_played_on": max((match["played_on"] for match in matches), default=""),
                "seasons": seasons,
            }
        )
    return rows


def get_competitions_page(ctx: RequestContext) -> str:
    data = load_validated_data()
    competition_rows = build_competition_rows(data)
    selected_competition = get_selected_competition(
        ctx, [row["competition_name"] for row in competition_rows]
    )
    team_lookup = {team["team_id"]: team for team in data["teams"]}

    if not selected_competition:
        cards = []
        for row in competition_rows:
            cards.append(
                f"""
                <div class="col-12 col-lg-6">
                  <a class="team-link-card shadow-sm p-4 h-100" href="/competitions?{urlencode({'competition': row['competition_name']})}">
                    <div class="d-flex justify-content-between align-items-start gap-3">
                      <div>
                        <div class="small text-secondary mb-2">比赛入口</div>
                        <h2 class="h4 mb-2">{escape(row['competition_name'])}</h2>
                        <div class="small-muted mb-3">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '未设置'}</div>
                      </div>
                      <span class="chip">进入比赛</span>
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
                  </a>
                </div>
                """
            )

        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">比赛入口页</div>
          <h1 class="display-6 fw-semibold mb-3">先选比赛，再看战队</h1>
          <p class="mb-0 opacity-75">每个比赛都有自己参赛的战队和队员名单。先进入比赛，再选择该比赛里的战队查看统计。</p>
        </section>
        <section class="panel shadow-sm p-3 p-lg-4">
          <h2 class="section-title mb-2">比赛列表</h2>
          <p class="section-copy mb-4">点击比赛卡片后，会进入该比赛的专属页面，再从里面选择战队。</p>
          <div class="row g-3 g-lg-4">{''.join(cards)}</div>
        </section>
        """
        return layout("比赛页面", body, ctx)

    team_rows = [
        row for row in build_team_rows(data, selected_competition) if row["matches_represented"] > 0
    ]
    match_rows = [
        match
        for match in sorted(
            data["matches"],
            key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
            reverse=True,
        )
        if get_match_competition_name(match) == selected_competition
    ]

    team_cards = []
    for row in team_rows:
        team_cards.append(
            f"""
            <div class="col-12 col-md-6">
              <a class="team-link-card shadow-sm p-4 h-100" href="/teams/{escape(row['team_id'])}?{urlencode({'competition': selected_competition})}">
                <div class="small text-secondary mb-2">该比赛战队第 {row['rank']} 名</div>
                <h2 class="h4 mb-2">{escape(row['name'])}</h2>
                <div class="small-muted mb-3">{row['player_count']} 名队员 · 对局 {row['matches_represented']} 场</div>
                <div class="row g-3">
                  <div class="col-4"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(row['win_rate'])}</div></div>
                  <div class="col-4"><div class="small text-secondary">站边率</div><div class="fw-semibold">{format_pct(row['stance_rate'])}</div></div>
                  <div class="col-4"><div class="small text-secondary">得分率</div><div class="fw-semibold">{format_pct(row['score_rate'])}</div></div>
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
        match_table_rows.append(
            f"""
            <tr>
              <td>{escape(match['season'])}</td>
              <td>{escape(match['played_on'])}</td>
              <td>{escape(STAGE_OPTIONS.get(match['stage'], match['stage']))}</td>
              <td>第 {match['round']} 轮</td>
              <td>第 {match['game_no']} 局</td>
              <td>{escape(team_names)}</td>
              <td>{escape(match['table_label'])}</td>
              <td>{escape(match['format'])}</td>
            </tr>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">比赛专属页面</div>
      <h1 class="display-6 fw-semibold mb-3">{escape(selected_competition)}</h1>
      <p class="mb-0 opacity-75">当前页面只展示这个比赛下的战队、队员和对局。先选战队，再进入战队详情页继续看数据。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该比赛战队入口</h2>
          <p class="section-copy mb-0">这里只列出这个比赛真正参赛的战队，避免和其他比赛混在一起。</p>
        </div>
        <a class="btn btn-outline-dark" href="/competitions">返回比赛列表</a>
      </div>
      <div class="row g-3 g-lg-4">{''.join(team_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">当前比赛还没有战队数据。</div></div>'}</div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该比赛全部对局</h2>
          <p class="section-copy mb-0">你可以先确认比赛包含哪些战队，再点上面的战队卡片进入详细页面。</p>
        </div>
      </div>
      <div class="table-responsive">
        <table class="table align-middle">
          <thead>
            <tr>
              <th>赛季</th>
              <th>日期</th>
              <th>阶段</th>
              <th>轮次</th>
              <th>局次</th>
              <th>参赛战队</th>
              <th>桌号</th>
              <th>板型</th>
            </tr>
          </thead>
          <tbody>{''.join(match_table_rows)}</tbody>
        </table>
      </div>
    </section>
    """
    return layout(selected_competition, body, ctx)


def get_dashboard_page(ctx: RequestContext, alert: str = "") -> str:
    data = load_validated_data()
    competition_names = list_competitions(data)
    selected_competition = get_selected_competition(ctx, competition_names)
    player_rows = build_player_rows(data, selected_competition)
    team_rows = build_team_rows(data, selected_competition)
    visible_player_rows = [row for row in player_rows if row["games_played"] > 0]
    visible_team_rows = [row for row in team_rows if row["matches_represented"] > 0]
    displayed_player_rows = visible_player_rows or player_rows
    displayed_team_rows = visible_team_rows or team_rows
    scope_label = selected_competition or "按比赛去重汇总"
    competition_switcher = build_competition_switcher(
        "/dashboard", competition_names, selected_competition, tone="light"
    )
    top_player = displayed_player_rows[0] if displayed_player_rows else None
    stat_cards = f"""
    <div class="row g-3 g-lg-4 mb-4">
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">已收录战队</div>
          <div class="stat-value mt-2">{len(visible_team_rows) if selected_competition else len(data['teams'])}</div>
          <div class="small-muted mt-2">{escape(scope_label)}</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">队员数量</div>
          <div class="stat-value mt-2">{len(visible_player_rows) if selected_competition else len(data['players'])}</div>
          <div class="small-muted mt-2">当前统计口径下有数据的队员</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">对局数量</div>
          <div class="stat-value mt-2">{sum(1 for match in data['matches'] if not selected_competition or get_match_competition_name(match) == selected_competition)}</div>
          <div class="small-muted mt-2">当前统计口径下的比赛记录</div>
        </div>
      </div>
      <div class="col-6 col-xl-3">
        <div class="stat-card h-100 p-4 shadow-sm border-0">
          <div class="stat-label">当前榜首队员</div>
          <div class="stat-value mt-2">{escape(top_player['display_name'] if top_player else '-')}</div>
          <div class="small-muted mt-2">{escape(top_player['team_name'] if top_player else '暂无数据')}</div>
        </div>
      </div>
    </div>
    """

    competition_cards = []
    for row in build_competition_rows(data):
        competition_cards.append(
            f"""
            <div class="col-12 col-md-6">
              <a class="team-link-card shadow-sm p-4 h-100" href="/competitions?{urlencode({'competition': row['competition_name']})}">
                <div class="d-flex justify-content-between align-items-start gap-3">
                  <div>
                    <div class="small text-secondary mb-2">比赛入口</div>
                    <h2 class="h4 mb-1">{escape(row['competition_name'])}</h2>
                    <div class="small-muted">赛季 {escape('、'.join(row['seasons'])) if row['seasons'] else '未设置'}</div>
                  </div>
                  <span class="chip">进入比赛</span>
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
              <td><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover fw-semibold" href="/players/{escape(row['player_id'])}{'?competition=' + quote(selected_competition) if selected_competition else ''}">{escape(row['display_name'])}</a></td>
              <td>{escape(row['team_name'])}</td>
              <td>{row['games_played']}</td>
              <td>{escape(row['record'])}</td>
              <td>{format_pct(row['win_rate'])}</td>
              <td>{format_pct(row['stance_rate'])}</td>
              <td>{format_pct(row['score_rate'])}</td>
              <td>{row['average_points']:.2f}</td>
            </tr>
            """
        )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">中国时间管理台</div>
      <h1 class="display-6 fw-semibold mb-3">先选比赛，再看战队与队员</h1>
      <p class="mb-2 opacity-75">首页展示队员总览，战队战绩和排名请进入具体比赛查看；登录后还可以继续编辑比赛表格和管理战队。</p>
      <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
    </section>
    {stat_cards}
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">比赛入口</h2>
          <p class="section-copy mb-0">先进入比赛，再从比赛页面里选择参赛战队。这样不同比赛的战队和队员不会混在一起看。</p>
        </div>
        <a class="btn btn-outline-dark" href="/competitions">查看全部比赛</a>
      </div>
      <div class="row g-3 g-lg-4">
        {''.join(competition_cards)}
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">队员表现前十</h2>
          <p class="section-copy mb-0">这里可以看全部赛事汇总，也可以切到单个比赛查看；详细数据请点击进入队员页面。</p>
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
              <th>得分率</th>
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


def get_teams_page(ctx: RequestContext) -> str:
    return get_competitions_page(ctx)


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


def get_team_page(ctx: RequestContext, team_id: str, alert: str = "") -> str:
    data = load_validated_data()
    team_lookup = {team["team_id"]: team for team in data["teams"]}
    player_lookup = {player["player_id"]: player for player in data["players"]}
    team = team_lookup.get(team_id)
    if not team:
        return layout("未找到战队", '<div class="alert alert-danger">没有找到对应的战队。</div>', ctx)

    team_competition_names = []
    for match in sorted(
        data["matches"],
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    ):
        if any(entry["team_id"] == team_id for entry in match["players"]):
            competition_name = get_match_competition_name(match)
            if competition_name not in team_competition_names:
                team_competition_names.append(competition_name)

    selected_competition = get_selected_competition(ctx, team_competition_names)
    competition_switcher = build_competition_switcher(
        f"/teams/{team_id}",
        team_competition_names,
        selected_competition,
        tone="light",
        all_label="比赛总览",
    )
    competition_groups: dict[str, list[dict[str, Any]]] = {}
    for match in data["matches"]:
        competition_name = get_match_competition_name(match)
        if any(entry["team_id"] == team_id for entry in match["players"]):
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
                    <div class="small-muted mb-3">对局 {competition_team_stats['matches_represented']} 场 · 队员 {competition_team_stats['player_count']} 名</div>
                    <div class="row g-3">
                      <div class="col-4"><div class="small text-secondary">胜率</div><div class="fw-semibold">{format_pct(competition_team_stats['win_rate'])}</div></div>
                      <div class="col-4"><div class="small text-secondary">站边率</div><div class="fw-semibold">{format_pct(competition_team_stats['stance_rate'])}</div></div>
                      <div class="col-4"><div class="small text-secondary">得分率</div><div class="fw-semibold">{format_pct(competition_team_stats['score_rate'])}</div></div>
                    </div>
                  </a>
                </div>
                """
            )

        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">战队比赛总览</div>
          <h1 class="display-6 fw-semibold mb-3">{escape(team['name'])}</h1>
          <p class="mb-2 opacity-75">{escape(team['notes'])}</p>
          <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
        </section>
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
            <div>
              <h2 class="section-title mb-2">请选择比赛</h2>
              <p class="section-copy mb-0">战队战绩和排名只在单个比赛里统计。先选比赛，再查看这支战队在该比赛中的队员和战绩。</p>
            </div>
            <a class="btn btn-outline-dark" href="/competitions">返回比赛列表</a>
          </div>
          <div class="row g-3 g-lg-4">{''.join(competition_cards) or '<div class="col-12"><div class="alert alert-secondary mb-0">这支战队暂时还没有比赛数据。</div></div>'}</div>
        </section>
        """
        return layout(f"{team['name']} 页面", body, ctx, alert=alert)

    player_rows = {
        row["player_id"]: row for row in build_player_rows(data, selected_competition)
    }
    team_rows = {
        row["team_id"]: row for row in build_team_rows(data, selected_competition)
    }
    team_stats = team_rows[team_id]
    roster_player_ids = resolve_team_player_ids(data, team_id, selected_competition)
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
                "score_rate": format_pct(player_stats["score_rate"]),
                "games_played": player_stats["games_played"],
                "average_points": player_stats["average_points"],
            }
        )

    competition_sections = []
    for competition_name, matches in competition_groups.items():
        if competition_name != selected_competition:
            continue
        seasons = sorted({item["season"] for item in matches}, reverse=True)
        rows = []
        for item in sorted(matches, key=lambda row: (row["played_on"], row["round"], row["game_no"]), reverse=True):
            rows.append(
                f"""
                <tr>
                  <td>{escape(item['season'])}</td>
                  <td>{escape(item['played_on'])}</td>
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
                    <a class="btn btn-sm btn-outline-dark" href="/matches/{escape(item['match_id'])}/edit?next={quote('/teams/' + team_id + ('?competition=' + selected_competition if selected_competition else ''))}">编辑比赛</a>
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
                  <p class="section-copy mb-0">涉及赛季：{escape('、'.join(seasons))}。这里展示 {escape(team['name'])} 在该赛事中的全部比赛。</p>
                </div>
              </div>
              <div class="table-responsive">
                <table class="table align-middle">
                  <thead>
                    <tr>
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
        <a class="team-link-card shadow-sm p-3 h-100" href="/players/{escape(player['player_id'])}{('?competition=' + quote(selected_competition)) if selected_competition else ''}">
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
              <div class="small text-secondary">得分率</div>
              <div class="fw-semibold">{player["score_rate"]}</div>
            </div>
          </div>
        </a>
        """
        for player in players
    )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">战队比赛页面</div>
      <h1 class="display-6 fw-semibold mb-3">{escape(team['name'])}</h1>
      <p class="mb-2 opacity-75">{escape(team['notes'])}</p>
      <div class="d-flex flex-wrap gap-2 mt-3">{competition_switcher}</div>
      <div class="d-flex flex-wrap gap-3">
        <span class="chip">胜率 {format_pct(team_stats['win_rate'])}</span>
        <span class="chip">站边率 {format_pct(team_stats['stance_rate'])}</span>
        <span class="chip">得分率 {format_pct(team_stats['score_rate'])}</span>
        <span class="chip">队员 {team_stats['player_count']} 名</span>
      </div>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
        <div>
          <h2 class="section-title mb-2">该赛事参赛队员</h2>
          <p class="section-copy mb-0">点击任意队员卡片，可以继续查看该队员的综合数据和分赛事数据。</p>
        </div>
      </div>
      <div class="row g-3">{roster_html or '<div class="col-12"><div class="alert alert-secondary mb-0">当前统计口径下，这支战队还没有参赛队员数据。</div></div>'}</div>
    </section>
    {''.join(competition_sections) if competition_sections else '<div class="alert alert-secondary">该战队在当前统计口径下暂时没有比赛记录。</div>'}
    """
    return layout(f"{team['name']} 页面", body, ctx, alert=alert)


def get_player_page(ctx: RequestContext, player_id: str) -> str:
    data = load_validated_data()
    player_competition_names = []
    for match in sorted(
        data["matches"],
        key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]),
        reverse=True,
    ):
        if any(entry["player_id"] == player_id for entry in match["players"]):
            competition_name = get_match_competition_name(match)
            if competition_name not in player_competition_names:
                player_competition_names.append(competition_name)

    selected_competition = get_selected_competition(ctx, player_competition_names)
    competition_switcher = build_competition_switcher(
        f"/players/{player_id}", player_competition_names, selected_competition, tone="light"
    )
    player_rows = build_player_rows(data, selected_competition)
    row_lookup = {row["player_id"]: row for row in player_rows}
    player_details = build_player_details(data, player_rows, selected_competition)
    detail = player_details.get(player_id)
    if not detail:
        return layout("未找到队员", '<div class="alert alert-danger">没有找到对应的队员。</div>', ctx)

    players = {player["player_id"]: player for player in data["players"]}
    player = players[player_id]
    player_row = row_lookup[player_id]
    team_id = player_row["team_id"]
    aliases = "、".join(detail["aliases"]) if detail["aliases"] else "无"
    photo_html = build_player_photo_html(detail["photo"], detail["display_name"])
    manage_button = ""
    if ctx.current_user and ctx.current_user.get("player_id") == player_id:
        manage_button = '<a class="btn btn-light text-dark shadow-sm" href="/profile">编辑我的资料</a>'
    elif can_manage_player(ctx, player_id):
        manage_button = f'<a class="btn btn-light text-dark shadow-sm" href="/players/{escape(player_id)}/edit">编辑队员资料</a>'
    manage_button_row = (
        f'<div class="d-flex flex-wrap gap-2 mt-3">{manage_button}</div>' if manage_button else ""
    )

    role_chips = "".join(
        f'<span class="chip">{escape(item["role"])} {item["games"]} 局</span>' for item in detail["roles"]
    ) or '<span class="chip">暂无角色记录</span>'

    history_rows = []
    for item in detail["history"]:
        history_rows.append(
            f"""
            <tr>
              <td>{escape(item['competition_name'])}</td>
              <td>{escape(item['played_on'])}</td>
              <td>{escape(item['season'])}</td>
              <td>{escape(item['stage_label'])}</td>
              <td>第 {item['round']} 轮</td>
              <td>第 {item['game_no']} 局</td>
              <td>{escape(item['role'])}</td>
              <td>{escape(item['camp_label'])}</td>
              <td>{escape(item['result_label'])}</td>
              <td>{escape(item['stance_pick_label'])}</td>
              <td>{escape(item['stance_correct_label'])}</td>
              <td>{item['points_earned']:.2f} / {item['points_available']:.2f}</td>
              <td>{escape(item['notes'] or '无')}</td>
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
              <td>{escape(item['score_rate'])}</td>
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
          {manage_button_row}
          <div class="d-flex flex-wrap gap-3 mt-5 pt-1">
            <span class="chip">战绩 {escape(detail['record'])}</span>
            <span class="chip">胜率 {escape(detail['win_rate'])}</span>
            <span class="chip">站边率 {escape(detail['stance_rate'])}</span>
            <span class="chip">得分率 {escape(detail['score_rate'])}</span>
            <span class="chip">存活率 {escape(detail['survival_rate'])}</span>
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
                <div class="fw-semibold mt-2"><a class="link-dark link-underline-opacity-0 link-underline-opacity-75-hover" href="/teams/{escape(team_id)}{('?competition=' + quote(selected_competition)) if selected_competition else ''}">{escape(detail['team_name'])}</a></div>
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
                <div class="stat-label">累计得分</div>
                <div class="fw-semibold mt-2">{escape(detail['points_total'])} / {escape(detail['points_cap'])}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">正确站边</div>
                <div class="fw-semibold mt-2">{detail['correct_stances']} / {detail['stance_calls']}</div>
              </div>
            </div>
            <div class="col-6 col-xl-4">
              <div class="stat-card h-100 p-3 shadow-sm border-0">
                <div class="stat-label">存活局数</div>
                <div class="fw-semibold mt-2">{detail['survivals']}</div>
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
              <th>得分率</th>
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
              <th>判断</th>
              <th>得分</th>
              <th>备注</th>
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
) -> str:
    current_user = ctx.current_user
    if not current_user:
        return layout("未登录", '<div class="alert alert-danger">请先登录后再访问个人后台。</div>', ctx)

    data = load_validated_data()
    current_player = get_user_player(data, current_user)
    current_account_name = account_values.get("account_display_name") if account_values else (
        current_user.get("display_name") or current_user["username"]
    )

    if current_player:
        player_form = {
            **current_player,
            **(player_values or {}),
        }
        editor_html = build_player_edit_form(
            player_form,
            "/profile",
            "保存我的资料",
            account_display_name=current_account_name,
            username=current_user["username"],
            password_note="如不需要修改密码，可以留空。",
            show_account_fields=True,
        )
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">个人后台</div>
          <h1 class="display-6 fw-semibold mb-3">编辑我的账号与队员资料</h1>
          <p class="mb-0 opacity-75">这里可以修改你的账号显示名称、密码、队员信息，并上传新的照片。</p>
        </section>
        {editor_html}
        """
    else:
        body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">个人后台</div>
          <h1 class="display-6 fw-semibold mb-3">账号资料</h1>
          <p class="mb-0 opacity-75">当前账号还没有绑定队员档案。先创建战队或加入战队，之后就可以在这里上传照片和维护队员资料。</p>
        </section>
        <section class="panel shadow-sm p-3 p-lg-4">
          <div class="form-panel p-3 p-lg-4">
            <form method="post" action="/profile">
              <div class="mb-3">
                <label class="form-label">用户名</label>
                <input class="form-control" value="{escape(current_user['username'])}" disabled>
              </div>
              <div class="mb-3">
                <label class="form-label">账号显示名称</label>
                <input class="form-control" name="account_display_name" value="{escape(current_account_name)}">
              </div>
              <div class="mb-3">
                <label class="form-label">新密码</label>
                <input class="form-control" name="password" type="password" autocomplete="new-password">
              </div>
              <div class="mb-4">
                <label class="form-label">确认新密码</label>
                <input class="form-control" name="password_confirm" type="password" autocomplete="new-password">
              </div>
              <div class="d-flex flex-wrap gap-2">
                <button type="submit" class="btn btn-dark">保存账号资料</button>
                <a class="btn btn-outline-dark" href="/team-center">去创建或加入战队</a>
              </div>
            </form>
          </div>
        </section>
        """

    return layout("个人后台", body, ctx, alert=alert)


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
          <a class="btn btn-outline-dark" href="/players/{escape(player_id)}">返回队员页面</a>
        </div>
      </div>
    </section>
    {build_player_edit_form(form_player, f"/players/{player_id}/edit", "保存队员资料")}
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
    current_form = form_values or {"username": "", "display_name": ""}
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
    data = load_validated_data()
    requests = load_membership_requests()
    current_user = ctx.current_user
    current_player = get_user_player(data, current_user)
    current_team = get_team_for_player(data, current_player)
    teams = sorted(data["teams"], key=lambda item: item["name"])
    create_form = create_values or {"name": "", "short_name": "", "notes": ""}
    join_form = join_values or {"team_id": ""}
    current_request = next((item for item in requests if current_user and item["username"] == current_user["username"]), None)

    if current_player:
        team_card = ""
        if current_team:
            captain_badge = ""
            if is_team_captain(current_team, current_player):
                captain_badge = '<span class="chip">当前队长</span>'
            pending_transfer = next(
                (
                    item
                    for item in requests
                    if current_user and item["username"] == current_user["username"] and item["request_type"] == "transfer"
                ),
                None,
            )
            leave_hint = (
                "你当前有转会申请正在处理中，请先取消申请或等待审核结果。"
                if pending_transfer
                else (
                    "你有历史比赛记录，当前不支持直接退出战队，请改用转会申请。"
                    if user_has_match_history(data, current_player["player_id"])
                    else "如果你还没有比赛记录，可以直接退出当前战队。"
                )
            )
            transfer_options = "".join(
                f'<option value="{escape(team["team_id"])}">{escape(team["name"])}</option>'
                for team in teams
                if team["team_id"] != current_team["team_id"]
            )
            transfer_panel = (
                f"""
                <div class="form-panel h-100 p-3 p-lg-4">
                  <h2 class="section-title mb-2">申请转会</h2>
                  <p class="section-copy mb-4">转会需要目标战队队长审核通过。</p>
                  <form method="post" action="/team-center">
                    <input type="hidden" name="action" value="request_transfer">
                    <div class="mb-4">
                      <label class="form-label">目标战队</label>
                      <select class="form-select" name="team_id">{transfer_options}</select>
                    </div>
                    <button type="submit" class="btn btn-dark">提交转会申请</button>
                  </form>
                </div>
                """
                if transfer_options and not pending_transfer
                else (
                    f"""
                    <div class="form-panel h-100 p-3 p-lg-4">
                      <h2 class="section-title mb-2">转会申请中</h2>
                      <p class="section-copy mb-4">你已经向目标战队提交了转会申请，等待队长审核。</p>
                      <form method="post" action="/team-center">
                        <input type="hidden" name="action" value="cancel_request">
                        <button type="submit" class="btn btn-outline-dark">取消当前申请</button>
                      </form>
                    </div>
                    """
                    if pending_transfer
                    else """
                    <div class="form-panel h-100 p-3 p-lg-4">
                      <h2 class="section-title mb-2">申请转会</h2>
                      <p class="section-copy mb-0">当前没有其他可转会的战队。</p>
                    </div>
                    """
                )
            )
            leave_panel = (
                '<span class="small text-secondary">转会申请处理中时不可直接退出</span>'
                if pending_transfer
                else (
                    """
                <form method="post" action="/team-center" class="m-0">
                  <input type="hidden" name="action" value="leave_team">
                  <button type="submit" class="btn btn-outline-danger">退出当前战队</button>
                </form>
                """
                    if not user_has_match_history(data, current_player["player_id"])
                    else '<span class="small text-secondary">已有比赛记录时不可直接退出</span>'
                )
            )
            captain_requests = []
            if is_team_captain(current_team, current_player):
                captain_requests = [item for item in requests if item["target_team_id"] == current_team["team_id"]]
            captain_panel = ""
            if captain_requests:
                request_rows = []
                for item in captain_requests:
                    request_type = "加入申请" if item["request_type"] == "join" else "转会申请"
                    request_rows.append(
                        f"""
                        <tr>
                          <td>{escape(item['display_name'])}</td>
                          <td>{escape(item['username'])}</td>
                          <td>{request_type}</td>
                          <td>{escape(item.get('source_team_id') or '无')}</td>
                          <td>{escape(item['created_on'])}</td>
                          <td>
                            <div class="d-flex flex-wrap gap-2">
                              <form method="post" action="/team-center" class="m-0">
                                <input type="hidden" name="action" value="approve_request">
                                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                                <button type="submit" class="btn btn-sm btn-dark">通过</button>
                              </form>
                              <form method="post" action="/team-center" class="m-0">
                                <input type="hidden" name="action" value="reject_request">
                                <input type="hidden" name="request_id" value="{escape(item['request_id'])}">
                                <button type="submit" class="btn btn-sm btn-outline-danger">拒绝</button>
                              </form>
                            </div>
                          </td>
                        </tr>
                        """
                    )
                captain_panel = f"""
                <section class="panel shadow-sm p-3 p-lg-4 mt-4">
                  <h2 class="section-title mb-2">待你审核的申请</h2>
                  <p class="section-copy mb-3">加入申请和转会申请都会在这里处理。</p>
                  <div class="table-responsive">
                    <table class="table align-middle">
                      <thead>
                        <tr>
                          <th>申请人</th>
                          <th>账号</th>
                          <th>类型</th>
                          <th>原战队</th>
                          <th>申请时间</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>{''.join(request_rows)}</tbody>
                    </table>
                  </div>
                </section>
                """
            team_card = f"""
            <section class="hero p-4 p-md-5 shadow-lg mb-4">
              <div class="eyebrow mb-3">当前战队状态</div>
              <h1 class="display-6 fw-semibold mb-3">{escape(current_team['name'])}</h1>
              <p class="mb-3 opacity-75">你当前以队员身份加入该战队，队员名称为 {escape(current_player['display_name'])}。</p>
              <div class="d-flex flex-wrap gap-2">
                {captain_badge}
                <a class="btn btn-light" href="/teams/{escape(current_team['team_id'])}">查看战队比赛页</a>
                <a class="btn btn-outline-light" href="/players/{escape(current_player['player_id'])}">查看我的数据</a>
              </div>
            </section>
            <section class="panel shadow-sm p-3 p-lg-4">
              <div class="row g-4">
                <div class="col-12 col-xl-6">
                  {transfer_panel}
                </div>
                <div class="col-12 col-xl-6">
                  <div class="form-panel h-100 p-3 p-lg-4">
                    <h2 class="section-title mb-2">退出当前战队</h2>
                    <p class="section-copy mb-4">{escape(leave_hint)}</p>
                    {leave_panel}
                  </div>
                </div>
              </div>
            </section>
            {captain_panel}
            """
        else:
            team_card = """
            <div class="alert alert-warning">当前账号已经绑定队员，但没有找到对应战队，请联系管理员排查数据。</div>
            """
        return layout("战队操作", team_card, ctx, alert=alert)

    if current_request:
        request_kind = "加入申请" if current_request["request_type"] == "join" else "转会申请"
        target_team = get_team_by_id(data, current_request["target_team_id"])
        pending_body = f"""
        <section class="hero p-4 p-md-5 shadow-lg mb-4">
          <div class="eyebrow mb-3">申请处理中</div>
          <h1 class="display-6 fw-semibold mb-3">{request_kind}</h1>
          <p class="mb-3 opacity-75">当前申请的目标战队：{escape(target_team['name'] if target_team else current_request['target_team_id'])}</p>
          <div class="d-flex flex-wrap gap-2">
            <form method="post" action="/team-center" class="m-0">
              <input type="hidden" name="action" value="cancel_request">
              <button type="submit" class="btn btn-light">取消当前申请</button>
            </form>
          </div>
        </section>
        """
        return layout("战队操作", pending_body, ctx, alert=alert)

    join_options = "".join(
        f'<option value="{escape(team["team_id"])}"{" selected" if join_form["team_id"] == team["team_id"] else ""}>{escape(team["name"])}</option>'
        for team in teams
    )
    join_panel = (
        f"""
        <div class="form-panel h-100 p-3 p-lg-4">
          <h2 class="section-title mb-2">申请加入战队</h2>
          <p class="section-copy mb-4">提交后需要目标战队队长审核，通过后才会正式加入。</p>
          <form method="post" action="/team-center">
            <input type="hidden" name="action" value="request_join">
            <div class="mb-4">
              <label class="form-label">选择战队</label>
              <select class="form-select" name="team_id">{join_options}</select>
            </div>
            <button type="submit" class="btn btn-dark">提交加入申请</button>
          </form>
        </div>
        """
        if teams
        else """
        <div class="form-panel h-100 p-3 p-lg-4">
          <h2 class="section-title mb-2">加入已有战队</h2>
          <p class="section-copy mb-0">当前还没有可加入的战队，你可以先创建一个新战队。</p>
        </div>
        """
    )

    body = f"""
    <section class="hero p-4 p-md-5 shadow-lg mb-4">
      <div class="eyebrow mb-3">战队操作中心</div>
      <h1 class="display-6 fw-semibold mb-3">创建战队或加入战队</h1>
      <p class="mb-0 opacity-75">每个账号当前只支持绑定一个队员身份。创建战队时，你会自动成为该战队的首位队员。</p>
    </section>
    <section class="panel shadow-sm p-3 p-lg-4">
      <div class="row g-4">
        <div class="col-12 col-xl-6">
          <div class="form-panel h-100 p-3 p-lg-4">
            <h2 class="section-title mb-2">创建新战队</h2>
            <p class="section-copy mb-4">战队创建完成后，会自动把你加入到该战队成员名单。</p>
            <form method="post" action="/team-center">
              <input type="hidden" name="action" value="create_team">
              <div class="mb-3">
                <label class="form-label">战队名称</label>
                <input class="form-control" name="team_name" value="{escape(create_form['name'])}">
              </div>
              <div class="mb-3">
                <label class="form-label">战队简称</label>
                <input class="form-control" name="short_name" value="{escape(create_form['short_name'])}">
              </div>
              <div class="mb-4">
                <label class="form-label">战队说明</label>
                <textarea class="form-control" name="notes" rows="4">{escape(create_form['notes'])}</textarea>
              </div>
              <button type="submit" class="btn btn-dark">创建战队</button>
            </form>
          </div>
        </div>
        <div class="col-12 col-xl-6">
          {join_panel}
        </div>
      </div>
    </section>
    """
    return layout("战队操作", body, ctx, alert=alert)


def get_accounts_page(
    ctx: RequestContext, alert: str = "", form_values: dict[str, str] | None = None
) -> str:
    current_form = form_values or {"username": "", "display_name": ""}
    users = load_users()
    rows = []
    for user in users:
        username = user["username"]
        display_name = user.get("display_name") or username
        tags = []
        if username == ADMIN_USERNAME:
            tags.append('<span class="chip">主管理员</span>')
        if ctx.current_user and username == ctx.current_user["username"]:
            tags.append('<span class="chip">当前账号</span>')
        if user.get("active"):
            tags.append('<span class="chip">启用中</span>')
        else:
            tags.append('<span class="chip">已停用</span>')

        can_delete = username != ADMIN_USERNAME and not (
            ctx.current_user and username == ctx.current_user["username"]
        )
        edit_button = ""
        if user.get("player_id"):
            edit_button = (
                f'<a class="btn btn-sm btn-outline-dark" href="/players/{escape(user["player_id"])}'
                f'/edit">编辑队员资料</a>'
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
              <td>{''.join(tags)}</td>
              <td><div class="d-flex flex-wrap gap-2">{edit_button}{delete_button}</div></td>
            </tr>
            """
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
            <h2 class="section-title mb-2">新增账号</h2>
            <p class="section-copy mb-4">新增后即可使用新账号登录当前网站。</p>
            <form method="post" action="/accounts">
              <input type="hidden" name="action" value="create">
              <div class="mb-3">
                <label class="form-label">用户名</label>
                <input class="form-control" name="username" value="{escape(current_form['username'])}" placeholder="例如 team_manager">
              </div>
              <div class="mb-3">
                <label class="form-label">显示名称</label>
                <input class="form-control" name="display_name" value="{escape(current_form['display_name'])}" placeholder="例如 赛事运营">
              </div>
              <div class="mb-4">
                <label class="form-label">登录密码</label>
                <input class="form-control" name="password" type="password" autocomplete="new-password">
              </div>
              <button type="submit" class="btn btn-dark">创建账号</button>
            </form>
          </div>
        </div>
        <div class="col-12 col-xl-7">
          <div class="panel h-100 shadow-sm p-3 p-lg-4">
            <div class="d-flex flex-column flex-lg-row justify-content-between align-items-lg-end gap-3 mb-3">
              <div>
                <h2 class="section-title mb-2">现有账号</h2>
                <p class="section-copy mb-0">管理员账号会被保护，当前登录账号也不能在这里直接删除。</p>
              </div>
            </div>
            <div class="table-responsive">
              <table class="table align-middle">
                <thead>
                  <tr>
                    <th>用户名</th>
                    <th>显示名称</th>
                    <th>状态</th>
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


def validate_account_form(
    username: str, display_name: str, password: str, existing_users: list[dict[str, Any]]
) -> str:
    if not USERNAME_PATTERN.match(username):
        return "用户名只能使用 3 到 32 位英文、数字、点、下划线或短横线，并且需以英文或数字开头。"
    if not display_name.strip():
        return "显示名称不能为空。"
    if len(password) < 6:
        return "密码至少需要 6 位。"
    if any(user["username"] == username for user in existing_users):
        return "该用户名已经存在。"
    return ""


def validate_registration_form(
    username: str,
    display_name: str,
    password: str,
    password_confirm: str,
    captcha_token: str,
    captcha_answer: str,
    existing_users: list[dict[str, Any]],
) -> str:
    account_error = validate_account_form(username, display_name, password, existing_users)
    if account_error:
        return account_error
    if password != password_confirm:
        return "两次输入的密码不一致。"
    if not consume_captcha(captcha_token, captcha_answer):
        return "验证码不正确或已失效，请重新输入。"
    return ""


def validate_team_creation(team_name: str, short_name: str, teams: list[dict[str, Any]]) -> str:
    if not team_name.strip():
        return "战队名称不能为空。"
    if not short_name.strip():
        return "战队简称不能为空。"
    if any(team["name"] == team_name for team in teams):
        return "战队名称已经存在。"
    if any(team["short_name"] == short_name for team in teams):
        return "战队简称已经存在。"
    return ""


def validate_profile_update(
    account_display_name: str,
    password: str,
    password_confirm: str,
    player_display_name: str = "",
) -> str:
    if not account_display_name.strip():
        return "账号显示名称不能为空。"
    if player_display_name and not player_display_name.strip():
        return "队员名称不能为空。"
    if password or password_confirm:
        if len(password) < 6:
            return "新密码至少需要 6 位。"
        if password != password_confirm:
            return "两次输入的新密码不一致。"
    return ""


def append_user_player_binding(users: list[dict[str, Any]], username: str, player_id: str) -> list[dict[str, Any]]:
    updated_users = []
    for user in users:
        if user["username"] == username:
            updated_users.append({**user, "player_id": player_id})
        else:
            updated_users.append(user)
    return updated_users


def parse_bool(value: str) -> bool:
    return value == "true"


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
                "survived": parse_bool(form_value(form, f"survived_{index}", "false")),
                "result": form_value(form, f"result_{index}"),
                "points_earned": float(form_value(form, f"points_earned_{index}", "0") or "0"),
                "points_available": float(form_value(form, f"points_available_{index}", "0") or "0"),
                "stance_pick": form_value(form, f"stance_pick_{index}"),
                "stance_correct": parse_bool(form_value(form, f"stance_correct_{index}", "false")),
                "notes": form_value(form, f"notes_{index}"),
            }
        )

    return {
        "match_id": existing_match["match_id"],
        "competition_name": form_value(form, "competition_name"),
        "season": form_value(form, "season"),
        "stage": form_value(form, "stage"),
        "round": int(form_value(form, "round", "0") or "0"),
        "game_no": int(form_value(form, "game_no", "0") or "0"),
        "played_on": form_value(form, "played_on"),
        "table_label": form_value(form, "table_label"),
        "format": form_value(form, "format"),
        "duration_minutes": int(form_value(form, "duration_minutes", "0") or "0"),
        "winning_camp": form_value(form, "winning_camp"),
        "players": participants,
        "notes": form_value(form, "notes"),
    }


def get_match_edit_page(
    ctx: RequestContext, match_id: str, alert: str = "", field_values: dict[str, Any] | None = None
) -> str:
    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx)

    current = field_values or match
    next_path = form_value(ctx.query, "next", "/dashboard")

    participant_rows = []
    for index, player in enumerate(current["players"]):
        participant_rows.append(
            f"""
            <tr>
              <td><input class="form-control form-control-sm" name="player_id_{index}" value="{escape(str(player['player_id']))}"></td>
              <td><input class="form-control form-control-sm" name="team_id_{index}" value="{escape(str(player['team_id']))}"></td>
              <td><input class="form-control form-control-sm" name="seat_{index}" type="number" value="{escape(str(player['seat']))}"></td>
              <td><input class="form-control form-control-sm" name="role_{index}" value="{escape(str(player['role']))}"></td>
              <td>
                <select class="form-select form-select-sm" name="camp_{index}">
                  {option_tags({k: v for k, v in CAMP_OPTIONS.items() if k != 'draw'}, str(player['camp']))}
                </select>
              </td>
              <td>
                <select class="form-select form-select-sm" name="survived_{index}">
                  <option value="true"{' selected' if player['survived'] else ''}>存活</option>
                  <option value="false"{'' if player['survived'] else ' selected'}>出局</option>
                </select>
              </td>
              <td>
                <select class="form-select form-select-sm" name="result_{index}">
                  {option_tags(RESULT_OPTIONS, str(player['result']))}
                </select>
              </td>
              <td><input class="form-control form-control-sm" name="points_earned_{index}" type="number" step="0.1" value="{escape(str(player['points_earned']))}"></td>
              <td><input class="form-control form-control-sm" name="points_available_{index}" type="number" step="0.1" value="{escape(str(player['points_available']))}"></td>
              <td>
                <select class="form-select form-select-sm" name="stance_pick_{index}">
                  {option_tags(STANCE_OPTIONS, str(player['stance_pick']))}
                </select>
              </td>
              <td>
                <select class="form-select form-select-sm" name="stance_correct_{index}">
                  <option value="true"{' selected' if player['stance_correct'] else ''}>正确</option>
                  <option value="false"{'' if player['stance_correct'] else ' selected'}>错误</option>
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
          <h1 class="section-title mb-2">编辑比赛</h1>
          <p class="section-copy mb-0">这里可以修改一场比赛的基础信息和全部上场选手数据。时间显示和操作均按中国时间习惯展示。</p>
        </div>
        <div class="d-flex gap-2">
          <a class="btn btn-outline-dark" href="{escape(next_path)}">返回上一页</a>
        </div>
      </div>
      <form method="post" action="/matches/{escape(match_id)}/edit?next={quote(next_path)}">
        <div class="row g-3 mb-4">
          <div class="col-12 col-md-6 col-xl-4">
            <label class="form-label">赛事名称</label>
            <input class="form-control" name="competition_name" value="{escape(str(current.get('competition_name', current['season'])))}">
          </div>
          <div class="col-12 col-md-6 col-xl-3">
            <label class="form-label">赛季</label>
            <input class="form-control" name="season" value="{escape(str(current['season']))}">
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
            <select class="form-select" name="winning_camp">
              {option_tags(CAMP_OPTIONS, str(current['winning_camp']))}
            </select>
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
                <th>状态</th>
                <th>结果</th>
                <th>得分</th>
                <th>满分</th>
                <th>站边</th>
                <th>判断</th>
                <th>备注</th>
              </tr>
            </thead>
            <tbody>
              {''.join(participant_rows)}
            </tbody>
          </table>
        </div>

        <div class="d-flex flex-wrap gap-2">
          <button type="submit" class="btn btn-dark">保存修改</button>
          <a class="btn btn-outline-dark" href="{escape(next_path)}">取消</a>
        </div>
      </form>
    </section>
    """
    return layout("编辑比赛", body, ctx, alert=alert)


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
    password = form_value(ctx.form, "password")
    password_confirm = form_value(ctx.form, "password_confirm")
    captcha_token = form_value(ctx.form, "captcha_token")
    captcha_answer = form_value(ctx.form, "captcha_answer")
    error = validate_registration_form(
        username,
        display_name,
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
                form_values={"username": username, "display_name": display_name},
                captcha_token=next_token,
                captcha_prompt=next_prompt,
            ),
        )

    password_salt, password_hash = hash_password(password)
    users.append(
        {
            "username": username,
            "display_name": display_name,
            "password_salt": password_salt,
            "password_hash": password_hash,
            "active": True,
            "player_id": None,
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
        password = form_value(ctx.form, "password")
        error = validate_account_form(username, display_name, password, users)
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
                    },
                ),
            )

        password_salt, password_hash = hash_password(password)
        users.append(
            {
                "username": username,
                "display_name": display_name,
                "password_salt": password_salt,
                "password_hash": password_hash,
                "active": True,
                "player_id": None,
            }
        )
        save_users(users)
        return start_response_html(start_response, "200 OK", get_accounts_page(ctx, alert=f"账号 {username} 已创建。"))

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


def update_user_account_fields(
    users: list[dict[str, Any]],
    username: str,
    display_name: str,
    password: str,
) -> list[dict[str, Any]]:
    updated_users = []
    for user in users:
        if user["username"] != username:
            updated_users.append(user)
            continue

        next_user = {**user, "display_name": display_name}
        if password:
            password_salt, password_hash = hash_password(password)
            next_user["password_salt"] = password_salt
            next_user["password_hash"] = password_hash
        updated_users.append(next_user)
    return updated_users


def handle_profile(ctx: RequestContext, start_response):
    current_user = ctx.current_user
    if not current_user:
        return redirect(start_response, "/login?next=/profile")

    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_profile_page(ctx))

    data = load_validated_data()
    users = load_users()
    current_player = get_user_player(data, current_user)
    account_display_name = form_value(ctx.form, "account_display_name").strip()
    password = form_value(ctx.form, "password")
    password_confirm = form_value(ctx.form, "password_confirm")
    player_display_name = form_value(ctx.form, "player_display_name").strip()
    aliases_raw = form_value(ctx.form, "aliases")
    notes = form_value(ctx.form, "notes").strip()
    upload = file_value(ctx.files, "photo_file")

    error = validate_profile_update(
        account_display_name,
        password,
        password_confirm,
        player_display_name if current_player else "",
    )
    if not error:
        error = validate_uploaded_photo(upload)
    if error:
        player_values = None
        if current_player:
            player_values = {
                **current_player,
                "display_name": player_display_name or current_player["display_name"],
                "aliases": parse_aliases_text(aliases_raw),
                "notes": notes,
            }
        return start_response_html(
            start_response,
            "200 OK",
            get_profile_page(
                ctx,
                alert=error,
                account_values={"account_display_name": account_display_name},
                player_values=player_values,
            ),
        )

    users = update_user_account_fields(users, current_user["username"], account_display_name, password)
    if current_player:
        for player in data["players"]:
            if player["player_id"] != current_player["player_id"]:
                continue
            player["display_name"] = player_display_name
            player["aliases"] = parse_aliases_text(aliases_raw)
            player["notes"] = notes
            new_photo = save_uploaded_player_photo(player["player_id"], upload)
            if new_photo:
                player["photo"] = new_photo
            break

    errors = save_repository_state(data, users)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_profile_page(ctx, alert="保存失败：" + "；".join(errors[:3])),
        )

    refreshed_user = next((user for user in users if user["username"] == current_user["username"]), current_user)
    refreshed_ctx = RequestContext(
        method="GET",
        path="/profile",
        query={},
        form={},
        files={},
        current_user=refreshed_user,
        now_label=china_now_label(),
    )
    message = "账号资料已更新。" if not current_player else "账号资料和队员资料已更新。"
    return start_response_html(start_response, "200 OK", get_profile_page(refreshed_ctx, alert=message))


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
    error = validate_profile_update("管理员", "", "", display_name)
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
    return redirect(start_response, f"/players/{player_id}")


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
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_team_center_page(ctx))

    current_user = ctx.current_user
    if not current_user:
        return redirect(start_response, "/login?next=/team-center")

    action = form_value(ctx.form, "action")
    data = load_validated_data()
    users = load_users()
    requests = load_membership_requests()
    existing_team_ids = {team["team_id"] for team in data["teams"]}
    existing_player_ids = {player["player_id"] for player in data["players"]}
    username = current_user["username"]
    display_name = current_user.get("display_name") or username
    current_request = next((item for item in requests if item["username"] == username), None)
    current_team = get_team_for_player(data, current_user and get_user_player(data, current_user))
    current_player = get_user_player(data, current_user)
    has_team_identity = bool(current_user.get("player_id") or current_player or current_team)

    if action == "create_team":
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前有待处理申请，请先取消或等待审核。"),
            )
        if has_team_identity:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号已经绑定战队身份，不能重复创建战队。"),
            )
        team_name = form_value(ctx.form, "team_name").strip()
        short_name = form_value(ctx.form, "short_name").strip()
        notes = form_value(ctx.form, "notes").strip()
        error = validate_team_creation(team_name, short_name, data["teams"])
        if error:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(
                    ctx,
                    alert=error,
                    create_values={"name": team_name, "short_name": short_name, "notes": notes},
                ),
            )

        player_id = build_unique_slug(existing_player_ids, "player", username, "player")
        team_id = build_unique_slug(existing_team_ids, "team", username, "team")
        data["players"].append(
            {
                "player_id": player_id,
                "display_name": display_name,
                "team_id": team_id,
                "photo": DEFAULT_PLAYER_PHOTO,
                "aliases": [],
                "active": True,
                "joined_on": china_today_label(),
                "notes": "网站账号创建战队时自动生成的队员档案。",
            }
        )
        data["teams"].append(
            {
                "team_id": team_id,
                "name": team_name,
                "short_name": short_name,
                "logo": "assets/teams/default-team.png",
                "active": True,
                "founded_on": china_today_label(),
                "captain_player_id": player_id,
                "members": [player_id],
                "notes": notes or "由网站注册账号创建。",
            }
        )
        users = append_user_player_binding(users, username, player_id)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(
                    ctx,
                    alert="创建战队失败：" + "；".join(errors[:3]),
                    create_values={"name": team_name, "short_name": short_name, "notes": notes},
                ),
            )
        return redirect(start_response, f"/teams/{team_id}")

    if action == "request_join":
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前已经有待处理申请。"),
            )
        if has_team_identity:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号已经在战队中，如需变更请使用转会申请。"),
            )
        team_id = form_value(ctx.form, "team_id").strip()
        target_team = next((team for team in data["teams"] if team["team_id"] == team_id), None)
        if not target_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到要加入的战队。"),
            )
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "join",
                "username": username,
                "display_name": display_name,
                "player_id": None,
                "source_team_id": None,
                "target_team_id": team_id,
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="加入申请已提交，等待队长审核。"),
        )

    if action == "request_transfer":
        if not current_player or not current_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号还没有战队身份，无法发起转会。"),
            )
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前已经有待处理申请。"),
            )
        team_id = form_value(ctx.form, "team_id").strip()
        if team_id == current_team["team_id"]:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="不能把自己转会到当前战队。"),
            )
        target_team = next((team for team in data["teams"] if team["team_id"] == team_id), None)
        if not target_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到目标战队。"),
            )
        requests.append(
            {
                "request_id": secrets.token_urlsafe(12),
                "request_type": "transfer",
                "username": username,
                "display_name": display_name,
                "player_id": current_player["player_id"],
                "source_team_id": current_team["team_id"],
                "target_team_id": team_id,
                "created_on": china_now_label(),
            }
        )
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="转会申请已提交，等待目标战队队长审核。"),
        )

    if action == "cancel_request":
        if not current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前没有可取消的申请。"),
            )
        requests = [item for item in requests if item["username"] != username]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="申请已取消。"),
        )

    if action == "leave_team":
        if not current_player or not current_team:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="当前账号没有可退出的战队。"),
            )
        if current_request:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="你当前有待处理申请，请先取消申请或等待审核后再退出战队。"),
            )
        if user_has_match_history(data, current_player["player_id"]):
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="已有比赛记录时不能直接退出战队，请改用转会申请。"),
            )
        remove_member_from_team(current_team, current_player["player_id"])
        data["players"] = [item for item in data["players"] if item["player_id"] != current_player["player_id"]]
        users = append_user_player_binding(users, username, None)
        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="退出战队失败：" + "；".join(errors[:3])),
            )
        revoke_user_sessions(username)
        token = secrets.token_urlsafe(24)
        SESSIONS[token] = username
        return redirect(
            start_response,
            "/team-center",
            headers=[("Set-Cookie", f"{SESSION_COOKIE}={token}; Path=/; HttpOnly; SameSite=Lax")],
        )

    if action in {"approve_request", "reject_request"}:
        if not current_player or not current_team or not is_team_captain(current_team, current_player):
            return start_response_html(
                start_response,
                "403 Forbidden",
                layout("没有权限", '<div class="alert alert-danger">只有当前战队队长可以审核申请。</div>', ctx),
            )
        request_id = form_value(ctx.form, "request_id").strip()
        request_item = next(
            (item for item in requests if item["request_id"] == request_id and item["target_team_id"] == current_team["team_id"]),
            None,
        )
        if not request_item:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="没有找到对应申请。"),
            )
        if action == "reject_request":
            requests = [item for item in requests if item["request_id"] != request_id]
            save_membership_requests(requests)
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="申请已拒绝。"),
            )

        requester = next((user for user in users if user["username"] == request_item["username"]), None)
        if not requester:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="申请账号不存在，无法审核。"),
            )
        if request_item["request_type"] == "join":
            if requester.get("player_id"):
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="该账号已经加入其他战队，申请已移除。"),
                )
            player_id = build_unique_slug(existing_player_ids, "player", requester["username"], "player")
            current_team["members"].append(player_id)
            if not current_team.get("captain_player_id"):
                current_team["captain_player_id"] = current_player["player_id"]
            data["players"].append(
                {
                    "player_id": player_id,
                    "display_name": requester.get("display_name") or requester["username"],
                    "team_id": current_team["team_id"],
                    "photo": DEFAULT_PLAYER_PHOTO,
                    "aliases": [],
                    "active": True,
                    "joined_on": china_today_label(),
                    "notes": "经战队队长审核通过后加入战队。",
                }
            )
            users = append_user_player_binding(users, requester["username"], player_id)
        else:
            transfer_player = next((item for item in data["players"] if item["player_id"] == request_item["player_id"]), None)
            source_team = get_team_by_id(data, request_item["source_team_id"] or "")
            if not transfer_player or not source_team:
                requests = [item for item in requests if item["request_id"] != request_id]
                save_membership_requests(requests)
                return start_response_html(
                    start_response,
                    "200 OK",
                    get_team_center_page(ctx, alert="转会申请对应的数据已失效，申请已移除。"),
                )
            remove_member_from_team(source_team, transfer_player["player_id"])
            current_team["members"].append(transfer_player["player_id"])
            transfer_player["team_id"] = current_team["team_id"]
            if not current_team.get("captain_player_id"):
                current_team["captain_player_id"] = current_player["player_id"]

        errors = save_repository_state(data, users)
        if errors:
            return start_response_html(
                start_response,
                "200 OK",
                get_team_center_page(ctx, alert="审核失败：" + "；".join(errors[:3])),
            )
        requests = [item for item in requests if item["request_id"] != request_id]
        save_membership_requests(requests)
        return start_response_html(
            start_response,
            "200 OK",
            get_team_center_page(ctx, alert="申请已通过。"),
        )

    return start_response_html(start_response, "200 OK", get_team_center_page(ctx, alert="未识别的操作。"))


def handle_match_edit(ctx: RequestContext, start_response, match_id: str):
    if ctx.method == "GET":
        return start_response_html(start_response, "200 OK", get_match_edit_page(ctx, match_id))

    data = load_validated_data()
    match = get_match_by_id(data["matches"], match_id)
    if not match:
        return start_response_html(start_response, "404 Not Found", layout("未找到比赛", '<div class="alert alert-danger">没有找到对应的比赛。</div>', ctx))

    updated_match = parse_match_form(ctx.form, match)
    matches = []
    for item in data["matches"]:
        if item["match_id"] == match_id:
            matches.append(updated_match)
        else:
            matches.append(item)

    errors = save_matches(matches)
    if errors:
        return start_response_html(
            start_response,
            "200 OK",
            get_match_edit_page(ctx, match_id, alert="保存失败：" + "；".join(errors[:3]), field_values=updated_match),
        )

    next_path = form_value(ctx.query, "next", "/dashboard")
    return redirect(start_response, next_path)


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
            return start_response_html(start_response, "200 OK", get_competitions_page(ctx))
        if path == "/teams":
            return start_response_html(start_response, "200 OK", get_teams_page(ctx))
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
        if path == "/profile":
            return handle_profile(ctx, start_response)
        if path == "/team-center":
            return handle_team_center(ctx, start_response)
        if path.startswith("/matches/") and path.endswith("/edit"):
            match_id = path.split("/")[2]
            return handle_match_edit(ctx, start_response, match_id)

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
