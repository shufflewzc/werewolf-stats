#!/usr/bin/env python3

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import py_compile
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import check_runtime_schema
import check_postgres_indexes
import benchmark_miniprogram_api
import check_prediction_cache
import import_rollback_check
import runtime_db_smoke
import web_app
from db_runtime import connect_runtime_db, database_backend, runtime_database_summary
from sqlite_store import DB_PATH, record_access_log, record_audit_log
from sqlite_store import delete_session, save_session
from web.features.ai_admin import get_access_stats_page, get_audit_logs_page, get_ops_page, get_request_trace_page, handle_access_stats
from web.features.matches import get_match_create_page
from web_app import (
    CONTENT_SECURITY_POLICY,
    READYZ_TABLES,
    SESSION_COOKIE,
    SLOW_REQUEST_THRESHOLD_MS,
    RequestContext,
    build_request_log_fields,
    csrf_token_for_session,
    get_dashboard_page,
    handle_readyz,
    app,
    with_security_headers,
)


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


class ReleaseCheckError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release readiness checks without binding a web port.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this check.")
    parser.add_argument(
        "--require-miniprogram-data",
        action="store_true",
        help="Fail miniprogram API contract check when the runtime database has no competition data.",
    )
    return parser.parse_args(argv)


def admin_ctx(
    *,
    method: str = "GET",
    path: str = "/",
    query: dict[str, list[str]] | None = None,
    form: dict[str, list[str]] | None = None,
    request_id: str = "req_release_check",
) -> RequestContext:
    return RequestContext(
        method=method,
        path=path,
        query=query or {},
        form=form or {},
        files={},
        current_user={
            "username": "admin",
            "display_name": "管理员",
            "role": "admin",
            "active": True,
            "province_name": "",
            "region_name": "",
            "permissions": [],
            "manager_scope_keys": [],
        },
        now_label="2026-06-17 00:00:00 中国时间",
        remote_addr="127.0.0.1",
        request_id=request_id,
    )


def capture_start_response():
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
        captured["status"] = status
        captured["headers"] = headers

    return captured, start_response


def assert_contains(page: str, needles: list[str], page_name: str) -> None:
    missing = [needle for needle in needles if needle not in page]
    if missing:
        raise ReleaseCheckError(f"{page_name} 缺少关键内容：" + "、".join(missing))


def compile_python_files() -> None:
    files = [
        "wsgi.py",
        "scripts/web_app.py",
        "scripts/sqlite_store.py",
        "scripts/db_runtime.py",
        "scripts/web/features/ai_admin.py",
        "scripts/web/features/matches.py",
        "scripts/web/features/admin.py",
        "scripts/runtime_db_smoke.py",
        "scripts/check_runtime_schema.py",
        "scripts/check_postgres_indexes.py",
        "scripts/benchmark_miniprogram_api.py",
        "scripts/check_prediction_cache.py",
        "scripts/production_config_check.py",
        "scripts/pre_deploy_check.py",
        "scripts/import_worker.py",
        "scripts/cleanup_runtime_state.py",
        "scripts/start_production.sh",
    ]
    for relative_path in files:
        path = ROOT / relative_path
        if path.suffix != ".py":
            continue
        py_compile.compile(str(path), doraise=True)


def check_miniprogram_release() -> None:
    script_path = ROOT / "scripts" / "check_miniprogram_release.js"
    if not script_path.exists():
        print("[SKIP] 小程序发布自检：脚本不存在。")
        return
    node_path = shutil.which("node")
    if not node_path:
        print("[SKIP] 小程序发布自检：当前环境没有 Node.js。")
        return
    completed = subprocess.run(
        [node_path, str(script_path)],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        detail = (completed.stdout + "\n" + completed.stderr).strip()
        raise ReleaseCheckError("小程序发布自检未通过：" + detail)


def check_user_visible_prediction_terms() -> None:
    forbidden_terms = ("盘口", "赔率", "下注", "投注", "走水", "通杀")
    allowed_suffixes = {".py", ".js", ".wxml", ".wxss", ".html", ".css", ".swift"}
    roots = [ROOT / "assets", ROOT / "miniprogram", ROOT / "ios", ROOT / "scripts" / "web"]
    files = [ROOT / "scripts" / "web_app.py"]
    for root in roots:
        files.extend(
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in allowed_suffixes
        )
    violations = []
    for path in files:
        content = path.read_text(encoding="utf-8", errors="ignore")
        matched = [term for term in forbidden_terms if term in content]
        if matched:
            violations.append(f"{path.relative_to(ROOT)}（{'、'.join(matched)}）")
    if violations:
        raise ReleaseCheckError("用户可见页面仍包含禁用预测用语：" + "；".join(violations))


def run_existing_database_checks(database_url: str) -> None:
    schema_code = check_runtime_schema.main(["--database-url", database_url] if database_url else [])
    if schema_code != 0:
        raise ReleaseCheckError("运行时数据库结构检查未通过")
    smoke_code = runtime_db_smoke.main(["--database-url", database_url] if database_url else [])
    if smoke_code != 0:
        raise ReleaseCheckError("运行时数据库烟测未通过")
    index_errors = check_postgres_indexes.check_indexes(database_url)
    if index_errors:
        raise ReleaseCheckError("PostgreSQL 索引检查未通过：" + "；".join(index_errors))


def check_import_rollback_self_check() -> None:
    if not DB_PATH.exists():
        print("[SKIP] 导入回滚自检：SQLite 源库不存在，正式 PostgreSQL 环境可跳过。")
        return
    message = import_rollback_check.run_check(DB_PATH.resolve())
    if not message:
        raise ReleaseCheckError("导入回滚自检没有返回验证结果")


def check_key_pages() -> None:
    dashboard = get_dashboard_page(admin_ctx(path="/"))
    assert_contains(dashboard, ["赛事", "选手", "门派"], "首页")

    matches = get_match_create_page(admin_ctx(path="/matches/new"))
    assert_contains(
        matches,
        ["Excel 批量补录比赛详情", "新增比赛", "批量管理比赛", "每页显示", 'id="match-list"'],
        "比赛管理页",
    )
    upload_index = matches.find("Excel 批量补录比赛详情")
    list_index = matches.find('id="match-list"')
    if upload_index < 0 or list_index < 0 or upload_index > list_index:
        raise ReleaseCheckError("比赛管理页顺序异常：上传操作应在比赛列表之前")

    ops = get_ops_page(admin_ctx(path="/ops"))
    assert_contains(ops, ["运维总览", "健康评分", "健康告警", "预测缓存", "最慢 API", "近期问题请求"], "运维总览页")

    access_stats = get_access_stats_page(admin_ctx(path="/access-stats"))
    assert_contains(access_stats, ["访问统计", "日志留存", "访问日志保留天数", "预览过期日志"], "访问统计页")

    audit_logs = get_audit_logs_page(admin_ctx(path="/audit-logs"))
    assert_contains(audit_logs, ["操作审计", "audit-search", "请求编号"], "操作审计页")

    request_trace = get_request_trace_page(admin_ctx(path="/request-trace"))
    assert_contains(request_trace, ["请求编号排障", "请求编号", "访问记录", "操作审计"], "请求排障页")


def check_readyz_payload() -> None:
    captured, start_response = capture_start_response()
    body = b"".join(handle_readyz(admin_ctx(path="/readyz"), start_response)).decode("utf-8")
    status = str(captured.get("status") or "")
    if not status.startswith("200"):
        raise ReleaseCheckError(f"/readyz 返回异常状态：{status}；{body[:200]}")
    payload = json.loads(body)
    checks = payload.get("checks") if isinstance(payload, dict) else {}
    if not payload.get("ok"):
        raise ReleaseCheckError("/readyz 未就绪：" + body[:200])
    required_keys = ["schema_version", "required_schema_version", "missing_tables", "write_check"]
    missing_keys = [key for key in required_keys if key not in checks]
    if missing_keys:
        raise ReleaseCheckError("/readyz 缺少检查项：" + ", ".join(missing_keys))
    if checks.get("missing_tables"):
        raise ReleaseCheckError("/readyz 报告缺表：" + ", ".join(checks["missing_tables"]))
    if checks.get("table_counts"):
        raise ReleaseCheckError("/readyz 不应扫描业务表行数")
    if checks.get("write_check") != "skipped":
        raise ReleaseCheckError("/readyz 默认不应执行写入探针")


def check_structured_error_log_fields() -> None:
    ctx = admin_ctx(path="/release-check-structured-log", request_id="req_release_check_structured_log")
    fields = build_request_log_fields(
        ctx,
        {
            "QUERY_STRING": "x=" + ("1" * 800),
            "REMOTE_ADDR": "127.0.0.1",
            "HTTP_USER_AGENT": "release-check",
        },
        request_id=ctx.request_id,
        status_code=500,
        duration_ms=max(SLOW_REQUEST_THRESHOLD_MS, 1),
    )
    required_keys = ["request_id", "method", "path", "status_code", "duration_ms", "username", "ip_address", "user_agent"]
    missing_keys = [key for key in required_keys if key not in fields]
    if missing_keys:
        raise ReleaseCheckError("结构化日志字段缺失：" + ", ".join(missing_keys))
    if fields["request_id"] != ctx.request_id or fields["status_code"] != 500:
        raise ReleaseCheckError("结构化日志字段内容异常")
    json.dumps({"event": "request.exception", **fields}, ensure_ascii=False)


def check_security_headers() -> None:
    html_headers = dict(
        with_security_headers(
            [
                ("Content-Type", "text/html; charset=utf-8"),
            ]
        )
    )
    json_headers = dict(
        with_security_headers(
            [
                ("Content-Type", "application/json; charset=utf-8"),
            ]
        )
    )
    required_headers = [
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Permissions-Policy",
        "Cross-Origin-Opener-Policy",
        "Cross-Origin-Resource-Policy",
    ]
    missing_html = [header for header in required_headers if header not in html_headers]
    missing_json = [header for header in required_headers if header not in json_headers]
    if missing_html or missing_json:
        raise ReleaseCheckError(
            "安全响应头缺失："
            + ("HTML " + ", ".join(missing_html) if missing_html else "")
            + ("；" if missing_html and missing_json else "")
            + ("JSON " + ", ".join(missing_json) if missing_json else "")
        )
    if html_headers.get("Content-Security-Policy") != CONTENT_SECURITY_POLICY:
        raise ReleaseCheckError("HTML 响应缺少预期 CSP")
    if "Content-Security-Policy" in json_headers:
        raise ReleaseCheckError("JSON 响应不应默认带 HTML CSP")


def call_wsgi(
    path: str,
    *,
    method: str = "GET",
    body: str = "",
    cookie: str = "",
    query_string: str = "",
) -> tuple[str, dict[str, str], str]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": method,
        "PATH_INFO": path,
        "QUERY_STRING": query_string,
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_USER_AGENT": "release-check",
        "HTTP_COOKIE": cookie,
        "wsgi.input": io.BytesIO(body.encode("utf-8")),
        "CONTENT_LENGTH": str(len(body.encode("utf-8"))),
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
    }
    payload = b"".join(app(environ, start_response)).decode("utf-8", errors="replace")
    return str(captured.get("status") or ""), captured.get("headers") or {}, payload


def api_get_json(path: str, query: dict[str, str] | None = None) -> dict:
    status, _headers, body = call_wsgi(path, query_string=urlencode(query or {}))
    if not status.startswith("200"):
        raise ReleaseCheckError(f"{path} 返回异常状态：{status}；{body[:200]}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise ReleaseCheckError(f"{path} 返回不是 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ReleaseCheckError(f"{path} 返回 JSON 顶层不是对象")
    return payload


def assert_json_keys(payload: dict, keys: list[str], name: str) -> None:
    missing = [key for key in keys if key not in payload]
    if missing:
        raise ReleaseCheckError(f"{name} 缺少字段：" + ", ".join(missing))


def assert_pagination(payload: dict, name: str) -> None:
    pagination = payload.get("pagination")
    if not isinstance(pagination, dict):
        raise ReleaseCheckError(f"{name} 缺少 pagination 对象")
    for key in ["offset", "limit", "total", "has_more"]:
        if key not in pagination:
            raise ReleaseCheckError(f"{name} pagination 缺少字段：{key}")


def assert_power_rating(payload: object, name: str) -> None:
    if not isinstance(payload, dict):
        raise ReleaseCheckError(f"{name} 缺少 power_rating 对象")
    for key in ["grade", "auto_grade", "score", "source", "source_label"]:
        if key not in payload:
            raise ReleaseCheckError(f"{name} power_rating 缺少字段：{key}")
    if payload.get("grade") not in {"S", "A", "B", "C", "D"}:
        raise ReleaseCheckError(f"{name} power_rating.grade 不是 S/A/B/C/D")


def check_miniprogram_api_contract(*, require_data: bool = False) -> None:
    competitions = api_get_json("/api/competitions")
    assert_json_keys(competitions, ["cards", "metrics", "hero"], "/api/competitions")
    if competitions.get("view") != "list":
        raise ReleaseCheckError("/api/competitions 默认 view 必须保持为 list")
    grouped_competitions = api_get_json("/api/competitions", {"grouped": "1"})
    assert_json_keys(
        grouped_competitions,
        ["view", "city_groups", "cards", "metrics", "hero"],
        "/api/competitions?grouped=1",
    )
    if grouped_competitions.get("view") != "grouped":
        raise ReleaseCheckError("/api/competitions?grouped=1 的 view 必须为 grouped")
    grouped_cards = (
        grouped_competitions.get("cards")
        if isinstance(grouped_competitions.get("cards"), list)
        else []
    )
    city_groups = (
        grouped_competitions.get("city_groups")
        if isinstance(grouped_competitions.get("city_groups"), list)
        else []
    )
    grouped_competition_names: list[str] = []
    for group in city_groups:
        if not isinstance(group, dict):
            raise ReleaseCheckError("/api/competitions?grouped=1 city_groups 包含非对象数据")
        assert_json_keys(
            group,
            ["region_name", "competition_count", "latest_played_on", "cards"],
            "/api/competitions?grouped=1 city_group",
        )
        region_name = str(group.get("region_name") or "").strip()
        if not region_name:
            raise ReleaseCheckError("/api/competitions?grouped=1 city_group 缺少 region_name")
        city_cards = group.get("cards") if isinstance(group.get("cards"), list) else []
        if int(group.get("competition_count") or 0) != len(city_cards):
            raise ReleaseCheckError(
                f"/api/competitions?grouped=1 {region_name} 的 competition_count 与 cards 数量不一致"
            )
        for card in city_cards:
            if not isinstance(card, dict):
                raise ReleaseCheckError(
                    f"/api/competitions?grouped=1 {region_name} cards 包含非对象数据"
                )
            if str(card.get("region_name") or "").strip() != region_name:
                raise ReleaseCheckError(
                    f"/api/competitions?grouped=1 {region_name} 包含其他城市的赛事"
                )
            competition_name = str(card.get("competition_name") or "").strip()
            if not competition_name:
                raise ReleaseCheckError(
                    f"/api/competitions?grouped=1 {region_name} 的赛事缺少 competition_name"
                )
            grouped_competition_names.append(competition_name)
    flat_competition_names = [
        str(card.get("competition_name") or "").strip()
        for card in grouped_cards
        if isinstance(card, dict) and str(card.get("competition_name") or "").strip()
    ]
    if sorted(grouped_competition_names) != sorted(flat_competition_names):
        raise ReleaseCheckError(
            "/api/competitions?grouped=1 的 city_groups 与扁平 cards 赛事范围不一致"
        )
    if len(grouped_competition_names) != len(set(grouped_competition_names)):
        raise ReleaseCheckError("/api/competitions?grouped=1 存在重复分组的赛事")
    cards = competitions.get("cards") if isinstance(competitions.get("cards"), list) else []
    if not cards:
        if require_data:
            raise ReleaseCheckError("/api/competitions 没有赛事 cards，小程序无法进入赛事")
        print("[SKIP] 小程序深度 API 契约：当前没有赛事数据，只检查基础字段。")
        return
    first_card = cards[0] if isinstance(cards[0], dict) else {}
    competition_name = str(first_card.get("competition_name") or "").strip()
    if not competition_name:
        raise ReleaseCheckError("/api/competitions 第一条赛事缺少 competition_name")
    seasons = first_card.get("seasons") if isinstance(first_card.get("seasons"), list) else []
    scope_query = {
        "competition": competition_name,
        "season": str(seasons[0] if seasons else ""),
        "region": str(first_card.get("region_name") or ""),
    }
    scope_query = {key: value for key, value in scope_query.items() if value}

    dashboard = api_get_json("/api/dashboard", scope_query)
    assert_json_keys(dashboard, ["scope", "metrics", "top_players", "top_teams", "match_days"], "/api/dashboard")
    team_rows = dashboard.get("top_teams") if isinstance(dashboard.get("top_teams"), list) else []
    active_team = next((row for row in team_rows if isinstance(row, dict) and row.get("team_id")), None)
    if active_team:
        team_id = str(active_team.get("team_id") or "").strip()
        if team_id:
            team_detail = api_get_json(f"/api/teams/{team_id}", scope_query)
            assert_json_keys(team_detail, ["team", "metrics", "insights", "roster", "matches", "power_rating"], "/api/teams/{id}")
            assert_power_rating(team_detail.get("power_rating"), "/api/teams/{id}")
            match_rows = team_detail.get("matches") if isinstance(team_detail.get("matches"), list) else []
            for match in match_rows:
                if not isinstance(match, dict):
                    raise ReleaseCheckError("/api/teams/{id} matches 包含非对象数据")
                if "identity_summary" not in match:
                    raise ReleaseCheckError("/api/teams/{id} matches 缺少 identity_summary，战队最近比赛无法显示身份")

    players = api_get_json("/api/players", {**scope_query, "limit": "30", "offset": "0"})
    assert_json_keys(players, ["scope", "metrics", "players"], "/api/players")
    assert_pagination(players, "/api/players")
    player_rows = players.get("players") if isinstance(players.get("players"), list) else []
    if player_rows:
        assert_power_rating(player_rows[0].get("power_rating"), "/api/players players[0]")
    active_player = next(
        (
            row
            for row in player_rows
            if isinstance(row, dict) and int(row.get("games_played") or 0) > 0
        ),
        None,
    )
    if active_player:
        player_id = str(active_player.get("player_id") or "").strip()
        if player_id:
            player_detail = api_get_json(f"/api/players/{player_id}", scope_query)
            assert_json_keys(player_detail, ["player", "metrics", "insights", "dimension", "power_rating"], "/api/players/{id}")
            assert_power_rating(player_detail.get("power_rating"), "/api/players/{id}")

    guilds = api_get_json("/api/guilds", scope_query)
    assert_json_keys(guilds, ["hero", "metrics", "cards"], "/api/guilds")
    guild_rows = guilds.get("cards") if isinstance(guilds.get("cards"), list) else []
    if guild_rows:
        guild_id = str((guild_rows[0] or {}).get("guild_id") or "").strip()
        if guild_id:
            guild_detail = api_get_json(f"/api/guilds/{guild_id}", scope_query)
            assert_json_keys(guild_detail, ["guild", "metrics", "ongoing_teams", "history_sections"], "/api/guilds/{id}")

    predictions = api_get_json("/api/predictions", {**scope_query, "limit": "30", "offset": "0"})
    assert_json_keys(predictions, ["scope", "days", "predictions", "notice"], "/api/predictions")
    assert_json_keys(predictions, ["pagination", "focused_prediction", "band_summary"], "/api/predictions")
    assert_pagination(predictions, "/api/predictions")
    days = predictions.get("days") if isinstance(predictions.get("days"), list) else []
    played_on = str((days[0] or {}).get("played_on") or "").strip() if days else ""
    if played_on:
        day_detail = api_get_json(f"/api/days/{played_on}", scope_query)
        assert_json_keys(day_detail, ["hero", "metrics", "player_leaderboard", "team_leaderboard", "competitions"], "/api/days/{played_on}")
        day_sections = (
            day_detail.get("competitions")
            if isinstance(day_detail.get("competitions"), list)
            else []
        )
        for section in day_sections:
            if not isinstance(section, dict):
                raise ReleaseCheckError("/api/days/{played_on} competitions 包含非对象数据")
            if section.get("competition_name") != competition_name:
                raise ReleaseCheckError("/api/days/{played_on} 混入其他赛事数据")
            if scope_query.get("season") and section.get("season_name") != scope_query["season"]:
                raise ReleaseCheckError("/api/days/{played_on} 混入其他赛季数据")


def check_miniprogram_api_benchmark(*, require_data: bool = False) -> None:
    benchmark_miniprogram_api.run_benchmark(
        runs=2,
        warmup_runs=1,
        warn_ms=1200.0,
        fail_ms=3000.0,
        require_data=require_data,
    )


def check_prediction_cache_consistency(*, require_data: bool = False) -> None:
    check_prediction_cache.run_check(require_data=require_data)


def check_ops_api() -> None:
    status, _headers, body = call_wsgi("/api/ops")
    if not status.startswith("403"):
        raise ReleaseCheckError("/api/ops 未登录访问没有返回 403")
    session_token = "ops_release_check_session"
    save_session(session_token, "admin")
    cookie = f"{SESSION_COOKIE}={session_token}"
    try:
        status, _headers, body = call_wsgi("/api/ops", cookie=cookie)
        if not status.startswith("200"):
            raise ReleaseCheckError(f"/api/ops 管理员访问异常：{status}")
        payload = json.loads(body)
    finally:
        delete_session(session_token)
    assert_json_keys(payload, ["ok", "health", "rates", "overview", "prediction_cache", "public_api_cache"], "/api/ops")
    health = payload.get("health") if isinstance(payload.get("health"), dict) else {}
    if "score" not in health or "level" not in health:
        raise ReleaseCheckError("/api/ops health 缺少 score 或 level")
    public_cache = payload.get("public_api_cache") if isinstance(payload.get("public_api_cache"), dict) else {}
    if "enabled" not in public_cache or "hit_rate" not in public_cache:
        raise ReleaseCheckError("/api/ops public_api_cache 缺少 enabled 或 hit_rate")


def check_request_rate_limit() -> None:
    original_enabled = web_app.REQUEST_RATE_LIMIT_ENABLED
    original_sensitive = web_app.REQUEST_RATE_LIMIT_SENSITIVE_MAX
    original_window = web_app.REQUEST_RATE_LIMIT_WINDOW_SECONDS
    with web_app.REQUEST_RATE_LIMIT_LOCK:
        original_limits = {key: list(value) for key, value in web_app.REQUEST_RATE_LIMITS.items()}
        web_app.REQUEST_RATE_LIMITS.clear()
    try:
        bucket_key = "127.0.0.1:GET:/api/web-login/status"
        with connect_runtime_db() as connection:
            connection.execute(
                "DELETE FROM request_rate_limits WHERE bucket_key = ?",
                (bucket_key,),
            )
            connection.commit()
        web_app.REQUEST_RATE_LIMIT_ENABLED = True
        web_app.REQUEST_RATE_LIMIT_SENSITIVE_MAX = 2
        web_app.REQUEST_RATE_LIMIT_WINDOW_SECONDS = 60
        statuses = [
            call_wsgi("/api/web-login/status", query_string="token=release_check_rate_limit")[0]
            for _ in range(3)
        ]
        if not statuses[0].startswith("404") or not statuses[1].startswith("404") or not statuses[2].startswith("429"):
            raise ReleaseCheckError("敏感接口限流未按预期触发：" + ", ".join(statuses))
    finally:
        with connect_runtime_db() as connection:
            connection.execute(
                "DELETE FROM request_rate_limits WHERE bucket_key = ?",
                ("127.0.0.1:GET:/api/web-login/status",),
            )
            connection.commit()
        web_app.REQUEST_RATE_LIMIT_ENABLED = original_enabled
        web_app.REQUEST_RATE_LIMIT_SENSITIVE_MAX = original_sensitive
        web_app.REQUEST_RATE_LIMIT_WINDOW_SECONDS = original_window
        with web_app.REQUEST_RATE_LIMIT_LOCK:
            web_app.REQUEST_RATE_LIMITS.clear()
            web_app.REQUEST_RATE_LIMITS.update(original_limits)


def check_duplicate_write_protection() -> None:
    original_enabled = web_app.IDEMPOTENCY_PROTECTION_ENABLED
    original_ttl = web_app.IDEMPOTENCY_PROTECTION_TTL_SECONDS
    with web_app.IDEMPOTENCY_LOCK:
        original_fingerprints = dict(web_app.IDEMPOTENCY_FINGERPRINTS)
        web_app.IDEMPOTENCY_FINGERPRINTS.clear()
    try:
        web_app.IDEMPOTENCY_PROTECTION_ENABLED = True
        web_app.IDEMPOTENCY_PROTECTION_TTL_SECONDS = 30
        unique_marker = f"{os.getpid()}-{time.time_ns()}"
        body = "session_token=missing&display_name=测试&province_name=广东省&region_name=广州市&gender=male&bio=重复提交检查" + unique_marker
        first_status, _headers, _body = call_wsgi("/api/miniprogram/profile", method="POST", body=body)
        second_status, _headers, second_body = call_wsgi("/api/miniprogram/profile", method="POST", body=body)
        if not first_status.startswith("401") or not second_status.startswith("409"):
            raise ReleaseCheckError(
                "重复提交保护未按预期触发："
                + first_status
                + ", "
                + second_status
                + "；"
                + second_body[:120]
            )
    finally:
        web_app.IDEMPOTENCY_PROTECTION_ENABLED = original_enabled
        web_app.IDEMPOTENCY_PROTECTION_TTL_SECONDS = original_ttl
        with web_app.IDEMPOTENCY_LOCK:
            web_app.IDEMPOTENCY_FINGERPRINTS.clear()
            web_app.IDEMPOTENCY_FINGERPRINTS.update(original_fingerprints)


def check_csrf_protection() -> None:
    session_token = "csrf_release_check_session"
    save_session(session_token, "admin")
    cookie = f"{SESSION_COOKIE}={session_token}"
    try:
        status, _headers, body = call_wsgi("/profile", cookie=cookie)
        if not status.startswith("200") or "_csrf_token" not in body:
            raise ReleaseCheckError("登录后页面没有自动注入 CSRF token")
        token = csrf_token_for_session(session_token)
        if token not in body:
            raise ReleaseCheckError("页面中的 CSRF token 与当前会话不匹配")
        with contextlib.redirect_stderr(io.StringIO()):
            status, _headers, body = call_wsgi("/does-not-exist", method="POST", body="action=test", cookie=cookie)
        if not status.startswith("403") or "请求已过期" not in body:
            raise ReleaseCheckError("缺少 CSRF token 的浏览器 POST 未被拦截")
        status, _headers, body = call_wsgi(
            "/does-not-exist",
            method="POST",
            body="_csrf_token=" + token,
            cookie=cookie,
        )
        if status.startswith("403") or "请求已过期" in body:
            raise ReleaseCheckError("携带正确 CSRF token 的 POST 被误拦截")
    finally:
        delete_session(session_token)


def check_cleanup_confirmation_guard() -> None:
    ctx = admin_ctx(
        method="POST",
        path="/access-stats",
        form={
            "action": ["cleanup_logs_confirm"],
            "access_retention_days": ["30"],
            "audit_retention_days": ["365"],
            "danger_confirmation": ["错误确认文字"],
        },
        request_id="req_release_check_cleanup_guard",
    )
    captured, start_response = capture_start_response()
    body = b"".join(handle_access_stats(ctx, start_response)).decode("utf-8")
    status = str(captured.get("status") or "")
    if not status.startswith("200"):
        raise ReleaseCheckError(f"日志清理确认保护返回异常状态：{status}")
    assert_contains(body, ["执行清理前，请输入确认文字：清理日志。", "清理预览"], "日志清理确认保护")


def cleanup_trace_fixture(request_id: str) -> None:
    with connect_runtime_db() as connection:
        connection.execute("DELETE FROM access_logs WHERE request_id = ?", (request_id,))
        connection.execute("DELETE FROM audit_logs WHERE request_id = ?", (request_id,))
        connection.commit()


def check_request_trace_roundtrip() -> None:
    request_id = "req_release_check_trace"
    cleanup_trace_fixture(request_id)
    record_access_log(
        path="/release-check-trace",
        method="GET",
        status_code=503,
        duration_ms=1234,
        query_string="",
        username="admin",
        ip_address="127.0.0.1",
        user_agent="release-check",
        created_at="2026-06-17 00:00:00",
        request_id=request_id,
    )
    record_audit_log(
        action="release.check",
        target_type="system",
        target_id="trace",
        summary="上线体检请求追踪验证",
        username="admin",
        request_id=request_id,
        ip_address="127.0.0.1",
        created_at="2026-06-17 00:00:01",
        metadata={"source": "release_check"},
    )
    try:
        page = get_request_trace_page(admin_ctx(path="/request-trace", query={"request_id": [request_id]}))
        assert_contains(
            page,
            [request_id, "/release-check-trace", "release.check", "服务端错误", "1.23s"],
            "请求追踪链路",
        )
    finally:
        cleanup_trace_fixture(request_id)


def run_check(name: str, fn: Callable[[], None]) -> CheckResult:
    try:
        fn()
    except Exception as exc:
        return CheckResult(name=name, ok=False, detail=str(exc))
    return CheckResult(name=name, ok=True)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    database_url = args.database_url or os.getenv("DATABASE_URL", "").strip()
    summary = runtime_database_summary(database_url or None)
    print("上线前综合体检")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    if database_backend(database_url or None) == "postgres" and not database_url:
        print("- 提示：未传入 DATABASE_URL，将使用当前环境变量。")
    checks = [
        ("Python 文件语法", compile_python_files),
        ("小程序发布自检", check_miniprogram_release),
        ("预测页面用语检查", check_user_visible_prediction_terms),
        ("小程序 API 契约", lambda: check_miniprogram_api_contract(require_data=args.require_miniprogram_data)),
        ("预测缓存一致性", lambda: check_prediction_cache_consistency(require_data=args.require_miniprogram_data)),
        ("小程序 API 耗时基准", lambda: check_miniprogram_api_benchmark(require_data=args.require_miniprogram_data)),
        ("运维状态接口", check_ops_api),
        ("敏感接口限流", check_request_rate_limit),
        ("重复提交保护", check_duplicate_write_protection),
        ("数据库结构与烟测", lambda: run_existing_database_checks(database_url)),
        ("导入回滚自检", check_import_rollback_self_check),
        ("健康检查接口", check_readyz_payload),
        ("结构化错误日志字段", check_structured_error_log_fields),
        ("安全响应头", check_security_headers),
        ("CSRF 防护", check_csrf_protection),
        ("核心后台页面渲染", check_key_pages),
        ("日志清理确认保护", check_cleanup_confirmation_guard),
        ("请求编号追踪链路", check_request_trace_roundtrip),
    ]
    results = [run_check(name, fn) for name, fn in checks]
    print("\n检查结果：")
    for result in results:
        prefix = "[OK]" if result.ok else "[FAIL]"
        suffix = f"：{result.detail}" if result.detail else ""
        print(f"{prefix} {result.name}{suffix}")
    failed = [result for result in results if not result.ok]
    if failed:
        print("\n体检未通过，请先处理失败项。", file=sys.stderr)
        return 1
    print("\n体检通过，可以进入下一步发布验证。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
