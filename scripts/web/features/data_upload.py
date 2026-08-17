from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from html import escape
import hmac
import json
import secrets
from typing import Any

import web_app as legacy
from sqlite_store import save_season_dimension_stats


TOKEN_META_KEY = "data_upload_tokens_v1"
REQUEST_META_KEY = "data_upload_requests_v1"
TOKEN_PREFIX = "wdu_"


def _load_json_meta(key: str, fallback):
    raw = legacy.load_meta_value(key) or ""
    try:
        value = json.loads(raw) if raw else fallback
    except json.JSONDecodeError:
        return fallback
    return value


def _save_json_meta(key: str, value) -> None:
    legacy.save_meta_value(key, json.dumps(value, ensure_ascii=False))


def load_tokens() -> list[dict[str, Any]]:
    value = _load_json_meta(TOKEN_META_KEY, [])
    return value if isinstance(value, list) else []


def save_tokens(tokens: list[dict[str, Any]]) -> None:
    _save_json_meta(TOKEN_META_KEY, tokens[-500:])


def available_targets(user: dict[str, Any] | None, data: dict[str, Any] | None = None) -> list[dict[str, str]]:
    if not user:
        return []
    current_data = data or legacy.load_validated_data()
    scopes = {
        (str(match.get("competition_name") or "").strip(), str(match.get("season") or "").strip())
        for match in current_data.get("matches", [])
    }
    return [
        {"competition_name": competition, "season_name": season, "label": f"{competition} / {season}", "scope_key": json.dumps([competition, season], ensure_ascii=False, separators=(",", ":"))}
        for competition, season in sorted(scopes)
        if competition and season and legacy.can_manage_matches(user, current_data, competition)
    ]


def create_token(user: dict[str, Any], name: str, expires_days: str, scope_mode: str, scope_keys: list[str]) -> tuple[str, dict[str, Any]]:
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = legacy.china_now()
    days = int(expires_days) if expires_days in {"30", "90", "365"} else 0
    record = {
        "token_id": "dut_" + secrets.token_hex(8),
        "username": str(user.get("username") or ""),
        "name": name.strip()[:80] or "每日数据生成器",
        "token_hash": sha256(raw.encode("utf-8")).hexdigest(),
        "scope_mode": "selected" if scope_mode == "selected" else "all",
        "scope_keys": sorted(set(scope_keys)) if scope_mode == "selected" else [],
        "created_at": legacy.china_now_label(),
        "expires_at": (now + timedelta(days=days)).isoformat() if days else "",
        "last_used_at": "",
        "revoked_at": "",
    }
    tokens = load_tokens()
    tokens.append(record)
    save_tokens(tokens)
    return raw, record


def revoke_token(username: str, token_id: str) -> bool:
    tokens = load_tokens()
    changed = False
    for item in tokens:
        if item.get("token_id") == token_id and item.get("username") == username and not item.get("revoked_at"):
            item["revoked_at"] = legacy.china_now_label()
            changed = True
    if changed:
        save_tokens(tokens)
    return changed


def authenticate(ctx) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    header = str(getattr(ctx, "authorization", "") or "").strip()
    if not header.lower().startswith("bearer "):
        return None, None, "请提供上传令牌。"
    raw = header[7:].strip()
    digest = sha256(raw.encode("utf-8")).hexdigest()
    tokens = load_tokens()
    record = next((item for item in tokens if hmac.compare_digest(str(item.get("token_hash") or ""), digest)), None)
    if not record or record.get("revoked_at"):
        return None, None, "上传令牌无效或已撤销。"
    expires_at = str(record.get("expires_at") or "")
    if expires_at:
        try:
            if legacy.china_now() >= datetime.fromisoformat(expires_at):
                return None, None, "上传令牌已过期。"
        except ValueError:
            return None, None, "上传令牌无效。"
    user = next((item for item in legacy.load_users() if item.get("username") == record.get("username")), None)
    if not user:
        return None, None, "令牌所属账号不存在。"
    record["last_used_at"] = legacy.china_now_label()
    save_tokens(tokens)
    return user, record, ""


def target_allowed(record: dict[str, Any], competition: str, season: str) -> bool:
    key = json.dumps([competition, season], ensure_ascii=False, separators=(",", ":"))
    return record.get("scope_mode") == "all" or key in record.get("scope_keys", [])


def token_panel(ctx, revealed_token: str = "") -> str:
    user = ctx.current_user
    targets = available_targets(user)
    rows = []
    for token in reversed([item for item in load_tokens() if item.get("username") == user.get("username")]):
        state = "已撤销" if token.get("revoked_at") else (f"有效至 {escape(token['expires_at'][:10])}" if token.get("expires_at") else "永不过期")
        action = "" if token.get("revoked_at") else f'''<form method="post" action="/profile" class="d-inline"><input type="hidden" name="action" value="revoke_upload_token"><input type="hidden" name="token_id" value="{escape(token['token_id'])}"><button class="btn btn-sm btn-outline-danger" type="submit">撤销</button></form>'''
        rows.append(f"<tr><td>{escape(token.get('name') or '')}</td><td>{escape(token.get('created_at') or '')}</td><td>{state}</td><td>{escape(token.get('last_used_at') or '尚未使用')}</td><td>{action}</td></tr>")
    target_options = "".join(f'<label class="form-check"><input class="form-check-input" type="checkbox" name="scope_key" value="{escape(item["scope_key"])}"><span class="form-check-label">{escape(item["label"])}</span></label>' for item in targets)
    revealed = f'''<div class="alert alert-warning"><strong>请立即复制，关闭页面后无法再次查看：</strong><div class="font-monospace text-break mt-2" id="upload-token-value">{escape(revealed_token)}</div></div>''' if revealed_token else ""
    return f'''
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">数据生成器上传令牌</h2>
      <p class="section-copy">令牌用于桌面生成器上传 match 与 dimension 文件，只能访问账号有管理权限的赛季。</p>
      {revealed}
      <form method="post" action="/profile" class="row g-3 mb-4">
        <input type="hidden" name="action" value="create_upload_token">
        <div class="col-md-4"><label class="form-label">令牌名称</label><input class="form-control" name="token_name" value="每日数据生成器"></div>
        <div class="col-md-3"><label class="form-label">有效期</label><select class="form-select" name="expires_days"><option value="90">90 天</option><option value="30">30 天</option><option value="365">365 天</option><option value="never">永不过期</option></select></div>
        <div class="col-md-5"><label class="form-label">权限范围</label><select class="form-select" name="scope_mode" onchange="document.getElementById('upload-token-targets').hidden=this.value!=='selected'"><option value="all">全部有权赛季</option><option value="selected">指定赛季</option></select></div>
        <div class="col-12" id="upload-token-targets" hidden>{target_options or '<span class="text-secondary">暂无可管理赛季</span>'}</div>
        <div class="col-12"><button class="btn btn-dark" type="submit">创建令牌</button></div>
      </form>
      <div class="table-responsive"><table class="table"><thead><tr><th>名称</th><th>创建时间</th><th>状态</th><th>最后使用</th><th></th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="5" class="text-secondary">尚未创建令牌</td></tr>'}</tbody></table></div>
    </section>'''


def handle_profile_action(ctx, start_response):
    action = legacy.form_value(ctx.form, "action").strip()
    if action == "create_upload_token":
        scope_mode = legacy.form_value(ctx.form, "scope_mode").strip()
        keys = [str(value) for value in ctx.form.get("scope_key", [])]
        allowed = {item["scope_key"] for item in available_targets(ctx.current_user)}
        if scope_mode == "selected" and (not keys or any(key not in allowed for key in keys)):
            return None, "请至少选择一个当前有权限的赛事赛季。", ""
        raw, record = create_token(ctx.current_user, legacy.form_value(ctx.form, "token_name"), legacy.form_value(ctx.form, "expires_days"), scope_mode, keys)
        legacy.audit_action(ctx, "data_upload_token.create", target_type="upload_token", target_id=record["token_id"], summary="创建数据生成器上传令牌", metadata={"scope_mode": record["scope_mode"], "scope_count": len(record["scope_keys"]), "expires_at": record["expires_at"]})
        return True, "上传令牌已创建。", raw
    if action == "revoke_upload_token":
        token_id = legacy.form_value(ctx.form, "token_id").strip()
        changed = revoke_token(str(ctx.current_user.get("username") or ""), token_id)
        if changed:
            legacy.audit_action(ctx, "data_upload_token.revoke", target_type="upload_token", target_id=token_id, summary="撤销数据生成器上传令牌")
        return changed, "上传令牌已撤销。" if changed else "没有找到可撤销的令牌。", ""
    return False, "", ""


def _json(start_response, status: str, payload: dict[str, Any]):
    return legacy.start_response_json(start_response, status, payload)


def handle_api(ctx, start_response):
    user, record, error = authenticate(ctx)
    if error:
        return _json(start_response, "401 Unauthorized", {"error": error})
    ctx.current_user = user
    data = legacy.load_validated_data()
    permitted = [item for item in available_targets(user, data) if target_allowed(record, item["competition_name"], item["season_name"])]
    if ctx.path == "/api/data-upload/targets" and ctx.method == "GET":
        return _json(start_response, "200 OK", {"targets": permitted, "token": {"name": record.get("name"), "expires_at": record.get("expires_at")}})
    if ctx.path == "/api/data-upload/matches" and ctx.method == "GET":
        competition = legacy.form_value(ctx.query, "competition_name").strip()
        season = legacy.form_value(ctx.query, "season_name").strip()
        if not target_allowed(record, competition, season) or not any(
            item["competition_name"] == competition and item["season_name"] == season
            for item in permitted
        ):
            return _json(start_response, "403 Forbidden", {"error": "令牌没有该赛事赛季的读取权限。"})
        matches = [
            {
                "match_id": str(match.get("match_id") or ""),
                "played_on": str(match.get("played_on") or ""),
                "round": int(match.get("round") or 0),
                "game_no": int(match.get("game_no") or 0),
                "stage": str(match.get("stage") or ""),
                "table_label": str(match.get("table_label") or ""),
            }
            for match in data.get("matches", [])
            if str(match.get("competition_name") or "").strip() == competition
            and str(match.get("season") or "").strip() == season
        ]
        matches.sort(key=lambda item: (item["played_on"], item["round"], item["game_no"], item["match_id"]))
        return _json(start_response, "200 OK", {"competition_name": competition, "season_name": season, "matches": matches})
    if ctx.path.startswith("/api/data-upload/jobs/") and ctx.method == "GET":
        batch_id = ctx.path.rsplit("/", 1)[-1].strip()
        batch = next((item for item in legacy.load_import_batches() if str(item.get("batch_id") or "") == batch_id), None)
        metadata = (batch or {}).get("metadata") or {}
        if not batch or metadata.get("upload_token_id") != record.get("token_id"):
            return _json(start_response, "404 Not Found", {"error": "没有找到该上传批次。"})
        return _json(start_response, "200 OK", {"batch_id": batch_id, "status": batch.get("status"), "summary": batch.get("summary") or "", "completed_at": batch.get("completed_at") or ""})
    if ctx.path != "/api/data-upload":
        return _json(start_response, "405 Method Not Allowed", {"error": "请求方法或路径不受支持。"})
    if ctx.method != "POST":
        return _json(start_response, "405 Method Not Allowed", {"error": "上传只支持 POST。"})

    competition = legacy.form_value(ctx.form, "competition_name").strip()
    season = legacy.form_value(ctx.form, "season_name").strip()
    if not target_allowed(record, competition, season) or not legacy.can_manage_matches(user, data, competition):
        return _json(start_response, "403 Forbidden", {"error": "令牌没有该赛事赛季的上传权限。"})
    if not any(item["competition_name"] == competition and item["season_name"] == season for item in permitted):
        return _json(start_response, "400 Bad Request", {"error": "目标赛事赛季不存在或当前不可管理。"})

    request_key = legacy.form_value(ctx.form, "request_id").strip()[:100]
    requests = _load_json_meta(REQUEST_META_KEY, {})
    identity = f"{record['token_id']}:{request_key}" if request_key else ""
    if identity and identity in requests:
        return _json(start_response, "200 OK", requests[identity])

    from web.features import matches as matches_feature
    match_upload = legacy.file_value(ctx.files, "match_file")
    dimension_upload = legacy.file_value(ctx.files, "dimension_file")
    results: dict[str, dict[str, Any]] = {}
    validation_errors = []
    for kind, upload in (("match", match_upload), ("dimension", dimension_upload)):
        if upload is None:
            continue
        issue = matches_feature.validate_excel_upload(upload)
        if issue:
            results[kind] = {"status": "failed", "message": issue}
            validation_errors.append(issue)
    if not match_upload and not dimension_upload:
        return _json(start_response, "400 Bad Request", {"error": "请至少上传一个 Excel 文件。"})

    next_player_rows = next_team_rows = None
    dimension_message = ""
    if dimension_upload and "dimension" not in results:
        next_player_rows, next_team_rows, dimension_message = matches_feature.import_dimension_stats_from_excel(ctx, data, dimension_upload, competition, season)
        if next_player_rows is None:
            results["dimension"] = {"status": "failed", "message": dimension_message}
            validation_errors.append(dimension_message)
    if match_upload and "match" not in results:
        match_metadata: dict[str, Any] = {}
        parsed, message = matches_feature.import_matches_from_excel(
            ctx,
            data,
            match_upload,
            result_metadata=match_metadata,
        )
        if parsed is None:
            results["match"] = {"status": "failed", "message": message}
            validation_errors.append(message)
        else:
            matched_scopes = {
                (
                    str(item.get("competition_name") or "").strip(),
                    str(item.get("season_name") or "").strip(),
                )
                for item in match_metadata.get("matched_scopes", [])
                if isinstance(item, dict)
            }
            if matched_scopes != {(competition, season)}:
                scope_labels = "、".join(
                    f"{scope_competition}/{scope_season}"
                    for scope_competition, scope_season in sorted(matched_scopes)
                ) or "无法识别"
                message = f"match 文件中的比赛属于 {scope_labels}，与当前上传目标 {competition}/{season} 不一致。"
                results["match"] = {"status": "failed", "message": message}
                validation_errors.append(message)
    if validation_errors:
        payload = {"status": "failed", "results": results}
        return _json(start_response, "422 Unprocessable Entity", payload)

    if dimension_upload:
        try:
            save_season_dimension_stats(next_player_rows, next_team_rows)
            legacy.invalidate_validated_data_cache()
            results["dimension"] = {"status": "succeeded", "message": dimension_message}
        except Exception as exc:
            results["dimension"] = {"status": "failed", "message": f"维度数据保存失败：{exc}"}

    if match_upload:
        running = [item for item in legacy.load_import_batches() if str(item.get("status") or "") in {"queued", "running"}]
        if running:
            results["match"] = {"status": "failed", "message": "已有导入任务正在处理中，请稍后只重试 match 文件。"}
        else:
            batch_id = legacy.create_import_batch(ctx=ctx, action="matches.import_excel", label="数据生成器上传比赛详情", filename=match_upload.filename, metadata={"background": True, "source": "daily-data-generator", "request_id": request_key, "upload_token_id": record.get("token_id")}, payload_data=match_upload.data)
            results["match"] = {"status": "queued", "message": "比赛数据已进入后台导入队列。", "batch_id": batch_id}

    overall = "succeeded" if all(item["status"] in {"succeeded", "queued"} for item in results.values()) else "partial"
    payload = {"status": overall, "results": results}
    if identity:
        requests[identity] = payload
        _save_json_meta(REQUEST_META_KEY, dict(list(requests.items())[-500:]))
    legacy.audit_action(ctx, "data_upload.submit", target_type="season", target_id=f"{competition}/{season}", summary="数据生成器上传数据", metadata={"request_id": request_key, "results": results})
    return _json(start_response, "200 OK", payload)
