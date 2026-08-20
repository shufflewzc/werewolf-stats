from __future__ import annotations

from datetime import datetime, timedelta
from hashlib import sha256
from html import escape
import hmac
import json
import secrets
from typing import Any

import web_app as legacy
from import_preflight import PreflightError, confirm_preflight
from sqlite_store import mutate_json_meta_value, save_season_dimension_stats


TOKEN_META_KEY = "data_upload_tokens_v1"
REQUEST_META_KEY = "data_upload_requests_v1"
TOKEN_PREFIX = "wdu_"
DATA_UPLOAD_SCOPE_PERMISSIONS = {
    "match_import_manage",
    "dimension_data_manage",
    "season_asset_manage",
}


def can_manage_data_upload(user: dict[str, Any] | None) -> bool:
    """Return whether an account may upload either supported desktop data type."""

    return legacy.user_has_any_scoped_capability(
        user,
        DATA_UPLOAD_SCOPE_PERMISSIONS,
    )


def _load_json_meta(key: str, fallback):
    raw = legacy.load_meta_value(key) or ""
    try:
        value = json.loads(raw) if raw else fallback
    except json.JSONDecodeError:
        return fallback
    return value


def _save_json_meta(key: str, value) -> None:
    # Upload tokens and request deduplication are operational state. Updating
    # them must not invalidate a preflight that guards the competition data.
    legacy.save_meta_value(
        key,
        json.dumps(value, ensure_ascii=False),
        bump_revision=False,
    )


def load_tokens() -> list[dict[str, Any]]:
    value = _load_json_meta(TOKEN_META_KEY, [])
    return value if isinstance(value, list) else []


def save_tokens(tokens: list[dict[str, Any]]) -> None:
    _save_json_meta(TOKEN_META_KEY, tokens[-500:])


def _mutate_tokens(mutator):
    def apply(value):
        tokens = [dict(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []
        next_tokens, result = mutator(tokens)
        if next_tokens is not None:
            next_tokens = next_tokens[-500:]
        return next_tokens, result

    return mutate_json_meta_value(
        TOKEN_META_KEY,
        [],
        apply,
        bump_revision=False,
    )


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
        if competition
        and season
        and (
            legacy.can_manage_competition_action(
                user, current_data, competition, "match_import_manage"
            )
            or legacy.can_manage_competition_action(
                user, current_data, competition, "dimension_data_manage"
            )
            or legacy.can_manage_competition_action(
                user, current_data, competition, "season_asset_manage"
            )
        )
    ]


def create_token(
    user: dict[str, Any],
    name: str,
    expires_days: str,
    scope_mode: str,
    scope_keys: list[str],
    note: str = "",
) -> tuple[str, dict[str, Any]]:
    raw = TOKEN_PREFIX + secrets.token_urlsafe(32)
    now = legacy.china_now()
    days = int(expires_days) if expires_days in {"30", "90", "365"} else 0
    record = {
        "token_id": "dut_" + secrets.token_hex(8),
        "username": str(user.get("username") or ""),
        "name": name.strip()[:80] or "每日数据生成器",
        "note": note.strip()[:300],
        "token_hash": sha256(raw.encode("utf-8")).hexdigest(),
        "scope_mode": "selected" if scope_mode == "selected" else "all",
        "scope_keys": sorted(set(scope_keys)) if scope_mode == "selected" else [],
        "created_at": legacy.china_now_label(),
        "expires_at": (now + timedelta(days=days)).isoformat() if days else "",
        "last_used_at": "",
        "revoked_at": "",
    }
    def append_token(tokens):
        tokens.append(dict(record))
        return tokens, None

    _mutate_tokens(append_token)
    return raw, record


def update_token(username: str, token_id: str, name: str, note: str) -> bool:
    def update(tokens):
        changed = False
        for item in tokens:
            if item.get("token_id") != token_id or item.get("username") != username:
                continue
            next_name = name.strip()[:80] or "每日数据生成器"
            next_note = note.strip()[:300]
            if item.get("name") != next_name or str(item.get("note") or "") != next_note:
                item["name"] = next_name
                item["note"] = next_note
                item["updated_at"] = legacy.china_now_label()
                changed = True
            break
        return (tokens if changed else None), changed

    return bool(_mutate_tokens(update))


def revoke_token(username: str, token_id: str) -> bool:
    def revoke(tokens):
        changed = False
        for item in tokens:
            if item.get("token_id") == token_id and item.get("username") == username and not item.get("revoked_at"):
                item["revoked_at"] = legacy.china_now_label()
                changed = True
        return (tokens if changed else None), changed

    return bool(_mutate_tokens(revoke))


def _token_validity_error(record: dict[str, Any] | None) -> str:
    if not record or record.get("revoked_at"):
        return "上传令牌无效或已撤销。"
    expires_at = str(record.get("expires_at") or "")
    if expires_at:
        try:
            if legacy.china_now() >= datetime.fromisoformat(expires_at):
                return "上传令牌已过期。"
        except ValueError:
            return "上传令牌无效。"
    return ""


def authenticate(ctx) -> tuple[dict[str, Any] | None, dict[str, Any] | None, str]:
    header = str(getattr(ctx, "authorization", "") or "").strip()
    if not header.lower().startswith("bearer "):
        return None, None, "请提供上传令牌。"
    raw = header[7:].strip()
    digest = sha256(raw.encode("utf-8")).hexdigest()
    tokens = load_tokens()
    record = next((item for item in tokens if hmac.compare_digest(str(item.get("token_hash") or ""), digest)), None)
    validity_error = _token_validity_error(record)
    if validity_error:
        return None, None, validity_error
    user = next((item for item in legacy.load_users() if item.get("username") == record.get("username")), None)
    if not user:
        return None, None, "令牌所属账号不存在。"
    if not user.get("active", True):
        return None, None, "令牌所属账号已停用。"

    def touch(tokens):
        current = next(
            (
                item
                for item in tokens
                if hmac.compare_digest(str(item.get("token_hash") or ""), digest)
            ),
            None,
        )
        current_error = _token_validity_error(current)
        if current_error:
            return None, (None, current_error)
        current["last_used_at"] = legacy.china_now_label()
        return tokens, (dict(current), "")

    touched_record, touch_error = _mutate_tokens(touch)
    if touch_error:
        return None, None, touch_error
    return user, touched_record, ""


def target_allowed(record: dict[str, Any], competition: str, season: str) -> bool:
    key = json.dumps([competition, season], ensure_ascii=False, separators=(",", ":"))
    return record.get("scope_mode") == "all" or key in record.get("scope_keys", [])


def token_panel(ctx, revealed_token: str = "") -> str:
    user = ctx.current_user
    can_create_token = can_manage_data_upload(user)
    owned_tokens = [
        item
        for item in load_tokens()
        if item.get("username") == user.get("username")
    ]
    if not can_create_token and not owned_tokens:
        return ""
    targets = available_targets(user)
    target_labels = {item["scope_key"]: item["label"] for item in targets}
    rows = []
    for token in reversed(owned_tokens):
        expires_at = str(token.get("expires_at") or "")
        if token.get("revoked_at"):
            state = '<span class="badge text-bg-secondary">已撤销</span>'
        elif expires_at:
            try:
                expired = legacy.china_now() >= datetime.fromisoformat(expires_at)
            except ValueError:
                expired = True
            state = f'<span class="badge text-bg-{"danger" if expired else "success"}">{"已过期" if expired else "使用中"}</span>'
        else:
            state = '<span class="badge text-bg-success">使用中</span>'
        if token.get("scope_mode") == "all":
            scope_label = "全部当前及未来有权赛季"
        else:
            scope_names = []
            for key in token.get("scope_keys", []):
                label = target_labels.get(key)
                if not label:
                    try:
                        competition, season = json.loads(key)
                        label = f"{competition} / {season}"
                    except (TypeError, ValueError, json.JSONDecodeError):
                        label = ""
                if label:
                    scope_names.append(label)
            scope_label = "、".join(scope_names) or f"指定 {len(token.get('scope_keys', []))} 个赛季"
        token_id = escape(token.get("token_id") or "")
        form_id = f"edit-{token_id}"
        revoke_action = "" if token.get("revoked_at") else f'''<form method="post" action="/profile" class="d-inline"><input type="hidden" name="action" value="revoke_upload_token"><input type="hidden" name="token_id" value="{token_id}"><button class="btn btn-sm btn-outline-danger" type="submit">撤销令牌</button></form>'''
        rows.append(f'''
        <div class="border rounded-3 p-3 mb-3">
          <div class="d-flex flex-column flex-lg-row justify-content-between gap-2 mb-3">
            <div><div class="d-flex align-items-center gap-2"><strong>{escape(token.get("name") or "")}</strong>{state}</div><small class="text-secondary font-monospace">{token_id}</small></div>
            <div class="d-flex align-items-start gap-2"><button class="btn btn-sm btn-dark" type="submit" form="{form_id}">保存名称与备注</button>{revoke_action}</div>
          </div>
          <div class="row g-2 small text-secondary mb-3">
            <div class="col-12"><strong class="text-body">权限范围：</strong>{escape(scope_label)}</div>
            <div class="col-md-4"><strong class="text-body">创建时间：</strong>{escape(token.get("created_at") or "-")}</div>
            <div class="col-md-4"><strong class="text-body">有效期：</strong>{escape(expires_at[:10] if expires_at else "永不过期")}</div>
            <div class="col-md-4"><strong class="text-body">最后使用：</strong>{escape(token.get("last_used_at") or "尚未使用")}</div>
          </div>
          <form id="{form_id}" method="post" action="/profile" class="row g-3">
            <input type="hidden" name="action" value="update_upload_token"><input type="hidden" name="token_id" value="{token_id}">
            <div class="col-md-4"><label class="form-label">令牌名称</label><input class="form-control" name="token_name" maxlength="80" value="{escape(token.get("name") or "")}"></div>
            <div class="col-md-8"><label class="form-label">备注</label><input class="form-control" name="token_note" maxlength="300" value="{escape(token.get("note") or "")}" placeholder="例如：赛场 Windows 电脑、京师 S2 专用"></div>
          </form>
        </div>''')
    target_options = "".join(f'<label class="form-check"><input class="form-check-input" type="checkbox" name="scope_key" value="{escape(item["scope_key"])}"><span class="form-check-label">{escape(item["label"])}</span></label>' for item in targets)
    revealed = f'''<div class="alert alert-warning"><strong>请立即复制，关闭页面后无法再次查看：</strong><div class="font-monospace text-break mt-2" id="upload-token-value">{escape(revealed_token)}</div></div>''' if revealed_token else ""
    create_form = f'''
      <form method="post" action="/profile" class="row g-3 mb-4">
        <input type="hidden" name="action" value="create_upload_token">
        <div class="col-md-4"><label class="form-label">令牌名称</label><input class="form-control" name="token_name" value="每日数据生成器"></div>
        <div class="col-md-3"><label class="form-label">有效期</label><select class="form-select" name="expires_days"><option value="90">90 天</option><option value="30">30 天</option><option value="365">365 天</option><option value="never">永不过期</option></select></div>
        <div class="col-md-5"><label class="form-label">权限范围</label><select class="form-select" name="scope_mode" onchange="document.getElementById('upload-token-targets').hidden=this.value!=='selected'"><option value="all">全部有权赛季</option><option value="selected">指定赛季</option></select></div>
        <div class="col-12" id="upload-token-targets" hidden>{target_options or '<span class="text-secondary">暂无可管理赛季</span>'}</div>
        <div class="col-12"><label class="form-label">备注</label><input class="form-control" name="token_note" maxlength="300" placeholder="记录使用设备、用途或赛季，不会包含令牌原文"></div>
        <div class="col-12"><button class="btn btn-dark" type="submit">创建令牌</button></div>
      </form>
    ''' if can_create_token else '<div class="alert alert-secondary">当前上传权限已收回；历史令牌已无法上传数据，你仍可在下方撤销或整理它们。</div>'
    return f'''
    <section class="panel shadow-sm p-3 p-lg-4 mb-4">
      <h2 class="section-title mb-2">数据生成器上传令牌</h2>
      <p class="section-copy">令牌用于桌面工具上传比赛、维度和赛季头像文件，只能访问账号有管理权限的赛季。</p>
      {revealed}
      {create_form}
      <div><h3 class="h6 mb-3">已创建令牌</h3>{''.join(rows) or '<div class="text-secondary">尚未创建令牌</div>'}</div>
    </section>'''


def handle_profile_action(ctx, start_response):
    action = legacy.form_value(ctx.form, "action").strip()
    if action == "create_upload_token":
        if not can_manage_data_upload(ctx.current_user):
            return False, "当前账号没有比赛数据或维度数据上传权限。", ""
        scope_mode = legacy.form_value(ctx.form, "scope_mode").strip()
        keys = [str(value) for value in ctx.form.get("scope_key", [])]
        allowed = {item["scope_key"] for item in available_targets(ctx.current_user)}
        if scope_mode == "selected" and (not keys or any(key not in allowed for key in keys)):
            return None, "请至少选择一个当前有权限的赛事赛季。", ""
        raw, record = create_token(ctx.current_user, legacy.form_value(ctx.form, "token_name"), legacy.form_value(ctx.form, "expires_days"), scope_mode, keys, legacy.form_value(ctx.form, "token_note"))
        legacy.audit_action(ctx, "data_upload_token.create", target_type="upload_token", target_id=record["token_id"], summary="创建数据生成器上传令牌", metadata={"scope_mode": record["scope_mode"], "scope_count": len(record["scope_keys"]), "expires_at": record["expires_at"], "has_note": bool(record["note"])})
        return True, "上传令牌已创建。", raw
    if action == "update_upload_token":
        token_id = legacy.form_value(ctx.form, "token_id").strip()
        changed = update_token(
            str(ctx.current_user.get("username") or ""),
            token_id,
            legacy.form_value(ctx.form, "token_name"),
            legacy.form_value(ctx.form, "token_note"),
        )
        if changed:
            legacy.audit_action(ctx, "data_upload_token.update", target_type="upload_token", target_id=token_id, summary="更新数据生成器令牌名称或备注")
        return changed, "令牌信息已更新。" if changed else "令牌信息未变更或令牌不存在。", ""
    if action == "revoke_upload_token":
        token_id = legacy.form_value(ctx.form, "token_id").strip()
        changed = revoke_token(str(ctx.current_user.get("username") or ""), token_id)
        if changed:
            legacy.audit_action(ctx, "data_upload_token.revoke", target_type="upload_token", target_id=token_id, summary="撤销数据生成器上传令牌")
        return changed, "上传令牌已撤销。" if changed else "没有找到可撤销的令牌。", ""
    return False, "", ""


def _json(start_response, status: str, payload: dict[str, Any]):
    return legacy.start_response_json(start_response, status, payload)


def _handle_player_photo_upload(
    ctx,
    start_response,
    *,
    user: dict[str, Any],
    record: dict[str, Any],
    data: dict[str, Any],
    permitted: list[dict[str, str]],
):
    if ctx.method != "POST":
        return _json(
            start_response,
            "405 Method Not Allowed",
            {"error": "头像上传只支持 POST。"},
        )

    competition = legacy.form_value(ctx.form, "competition_name").strip()
    season = legacy.form_value(ctx.form, "season_name").strip()
    if not target_allowed(record, competition, season):
        return _json(
            start_response,
            "403 Forbidden",
            {"error": "令牌没有该赛事赛季的上传权限。"},
        )
    if not any(
        item["competition_name"] == competition and item["season_name"] == season
        for item in permitted
    ):
        return _json(
            start_response,
            "400 Bad Request",
            {"error": "目标赛事赛季不存在或当前不可管理。"},
        )
    if not legacy.can_manage_competition_action(
        user,
        data,
        competition,
        "season_asset_manage",
    ):
        return _json(
            start_response,
            "403 Forbidden",
            {"error": "当前账号没有该赛事赛季的头像上传权限。"},
        )

    request_key = legacy.form_value(ctx.form, "request_id").strip()[:100]
    requests = _load_json_meta(REQUEST_META_KEY, {})
    identity = f"{record['token_id']}:{request_key}" if request_key else ""
    if identity and identity in requests:
        cached_payload = requests[identity]
        cached_batch_id = str(
            cached_payload.get("batch_id")
            if isinstance(cached_payload, dict)
            else ""
        ).strip()
        cached_batch = next(
            (
                item
                for item in legacy.load_import_batches()
                if str(item.get("batch_id") or "") == cached_batch_id
            ),
            None,
        )
        cached_status = str((cached_batch or {}).get("status") or "")
        if cached_batch and cached_status in {
            "awaiting_confirmation",
            "queued",
            "running",
            "succeeded",
        }:
            return _json(start_response, "200 OK", cached_payload)
        requests.pop(identity, None)
        _save_json_meta(REQUEST_META_KEY, dict(list(requests.items())[-500:]))

    from web.features import matches as matches_feature

    upload = legacy.file_value(ctx.files, "player_photo_zip")
    upload_error = matches_feature.validate_zip_upload(upload)
    if upload_error:
        return _json(
            start_response,
            "422 Unprocessable Entity",
            {"status": "failed", "error": upload_error},
        )

    preview, blocking_errors, warnings = (
        matches_feature.preflight_player_photo_zip_upload(
            ctx,
            data,
            upload,
            competition,
            season,
        )
    )
    if blocking_errors:
        return _json(
            start_response,
            "422 Unprocessable Entity",
            {
                "status": "failed",
                "error": "；".join(blocking_errors[:3]),
                "preview": preview,
                "warnings": warnings,
            },
        )

    try:
        batch_id = matches_feature.create_import_upload_preflight(
            ctx,
            data,
            upload,
            action="player_photo.import_zip",
            preview=preview,
            action_metadata={
                "competition_name": competition,
                "season_name": season,
                "source": "player-photo-matcher",
                "request_id": request_key,
                "upload_token_id": record.get("token_id"),
            },
            competition_names={competition},
            warnings=warnings,
        )
        confirm_preflight(
            batch_id,
            actor=str(user.get("username") or ""),
            creator_check=lambda actor, created_by, _job: actor == created_by,
            permission_check=lambda _actor, scope_key, permission_key: bool(
                legacy.user_has_scope_permission(user, scope_key, permission_key)
            ),
            now_label=ctx.now_label,
        )
    except PreflightError as exc:
        return _json(
            start_response,
            "409 Conflict",
            {"status": "failed", "error": str(exc)},
        )
    except Exception as exc:
        legacy.emit_structured_log(
            "player_photo_upload.enqueue_failed",
            "error",
            request_id=str(getattr(ctx, "request_id", "") or ""),
            username=str(user.get("username") or ""),
            competition_name=competition,
            season_name=season,
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return _json(
            start_response,
            "500 Internal Server Error",
            {"status": "failed", "error": "创建头像导入任务失败，请稍后重试。"},
        )

    matched_count = int((preview.get("counts") or {}).get("matched_photos") or 0)
    payload = {
        "status": "queued",
        "batch_id": batch_id,
        "message": f"头像 ZIP 已通过预检，{matched_count} 张头像进入后台导入队列。",
        "preview": preview,
        "warnings": warnings,
    }
    if identity:
        requests[identity] = payload
        _save_json_meta(REQUEST_META_KEY, dict(list(requests.items())[-500:]))
    legacy.audit_action(
        ctx,
        "data_upload.player_photos",
        target_type="season",
        target_id=f"{competition}/{season}",
        summary="头像匹配器上传选手头像 ZIP",
        metadata={
            "request_id": request_key,
            "batch_id": batch_id,
            "matched_photos": matched_count,
        },
    )
    return _json(start_response, "200 OK", payload)


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
    if ctx.path == "/api/data-upload/player-photos":
        return _handle_player_photo_upload(
            ctx,
            start_response,
            user=user,
            record=record,
            data=data,
            permitted=permitted,
        )
    if ctx.path != "/api/data-upload":
        return _json(start_response, "405 Method Not Allowed", {"error": "请求方法或路径不受支持。"})
    if ctx.method != "POST":
        return _json(start_response, "405 Method Not Allowed", {"error": "上传只支持 POST。"})

    competition = legacy.form_value(ctx.form, "competition_name").strip()
    season = legacy.form_value(ctx.form, "season_name").strip()
    if not target_allowed(record, competition, season):
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
    if match_upload and dimension_upload:
        message = "上传必须先单独导入 match，等待比赛批次成功并创建新选手后，再单独上传 dimension。"
        return _json(start_response, "409 Conflict", {
            "status": "failed",
            "results": {
                "match": {"status": "failed", "message": message},
                "dimension": {"status": "failed", "message": message},
            },
        })
    for kind, upload in (("match", match_upload), ("dimension", dimension_upload)):
        if upload is None:
            continue
        issue = matches_feature.validate_excel_upload(upload)
        if issue:
            results[kind] = {"status": "failed", "message": issue}
            validation_errors.append(issue)
    if not match_upload and not dimension_upload:
        return _json(start_response, "400 Bad Request", {"error": "请至少上传一个 Excel 文件。"})
    required_permission = (
        "match_import_manage" if match_upload else "dimension_data_manage"
    )
    if not legacy.can_manage_competition_action(
        user,
        data,
        competition,
        required_permission,
    ):
        permission_label = "比赛数据上传" if match_upload else "维度数据上传"
        return _json(
            start_response,
            "403 Forbidden",
            {"error": f"当前账号没有该赛事赛季的{permission_label}权限。"},
        )

    match_batch_id = legacy.form_value(ctx.form, "match_batch_id").strip()
    if dimension_upload:
        match_batch = next(
            (
                item
                for item in legacy.load_import_batches()
                if str(item.get("batch_id") or "") == match_batch_id
            ),
            None,
        )
        batch_metadata = (match_batch or {}).get("metadata") or {}
        valid_batch = (
            match_batch
            and str(match_batch.get("status") or "") == "succeeded"
            and batch_metadata.get("upload_token_id") == record.get("token_id")
            and batch_metadata.get("competition_name") == competition
            and batch_metadata.get("season_name") == season
        )
        if not valid_batch:
            message = "dimension 上传前必须先完成同一令牌、同一赛季的 match 导入。"
            return _json(start_response, "409 Conflict", {
                "status": "failed",
                "results": {"dimension": {"status": "failed", "message": message}},
            })

    next_player_rows = next_team_rows = None
    dimension_message = ""
    match_preview: dict[str, Any] = {}
    match_warnings: list[str] = []
    match_competition_names: set[str] = set()
    if dimension_upload and "dimension" not in results:
        next_player_rows, next_team_rows, dimension_message = matches_feature.import_dimension_stats_from_excel(ctx, data, dimension_upload, competition, season)
        if next_player_rows is None:
            results["dimension"] = {"status": "failed", "message": dimension_message}
            validation_errors.append(dimension_message)
    if match_upload and "match" not in results:
        (
            match_preview,
            match_errors,
            match_warnings,
            match_competition_names,
        ) = matches_feature.preflight_match_excel_upload(
            ctx,
            data,
            match_upload,
            "",
        )
        if match_errors:
            message = "；".join(match_errors[:3])
            results["match"] = {"status": "failed", "message": message}
            validation_errors.append(message)
        else:
            matched_scopes = {
                (
                    str(item.get("competition_name") or "").strip(),
                    str(item.get("season_name") or "").strip(),
                )
                for item in match_preview.get("matched_scopes", [])
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
        for kind, upload in (("match", match_upload), ("dimension", dimension_upload)):
            if upload is not None and kind not in results:
                results[kind] = {
                    "status": "failed",
                    "message": "双文件统一预检未通过，本文件尚未上传；修正后请与失败文件一并重试。",
                }
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
            try:
                batch_id = matches_feature.create_import_upload_preflight(
                    ctx,
                    data,
                    match_upload,
                    action="matches.import_excel",
                    preview=match_preview,
                    action_metadata={
                        "source": "daily-data-generator",
                        "request_id": request_key,
                        "upload_token_id": record.get("token_id"),
                        "competition_name": competition,
                        "season_name": season,
                    },
                    competition_names=match_competition_names or {competition},
                    warnings=match_warnings,
                )
                confirm_preflight(
                    batch_id,
                    actor=str(user.get("username") or ""),
                    creator_check=lambda actor, created_by, _job: actor == created_by,
                    permission_check=lambda _actor, scope_key, permission_key: bool(
                        legacy.user_has_scope_permission(
                            user,
                            scope_key,
                            permission_key,
                        )
                    ),
                    now_label=ctx.now_label,
                )
                results["match"] = {
                    "status": "queued",
                    "message": "比赛数据已通过预检并进入后台导入队列。",
                    "batch_id": batch_id,
                }
            except PreflightError as exc:
                results["match"] = {
                    "status": "failed",
                    "message": f"比赛导入预检确认失败：{exc}",
                }
            except Exception as exc:
                legacy.emit_structured_log(
                    "data_upload.match_enqueue_failed",
                    "error",
                    request_id=str(getattr(ctx, "request_id", "") or ""),
                    username=str(user.get("username") or ""),
                    competition_name=competition,
                    season_name=season,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                results["match"] = {
                    "status": "failed",
                    "message": "创建比赛导入任务失败，请稍后重试。",
                }

    overall = "succeeded" if all(item["status"] in {"succeeded", "queued"} for item in results.values()) else "partial"
    payload = {"status": overall, "results": results}
    if identity:
        requests[identity] = payload
        _save_json_meta(REQUEST_META_KEY, dict(list(requests.items())[-500:]))
    legacy.audit_action(ctx, "data_upload.submit", target_type="season", target_id=f"{competition}/{season}", summary="数据生成器上传数据", metadata={"request_id": request_key, "results": results})
    return _json(start_response, "200 OK", payload)
