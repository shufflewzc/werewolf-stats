#!/usr/bin/env python3

"""Durable, side-effect-free upload preflight workflow.

Preflighting may persist the uploaded payload and an ``import_jobs`` runtime
record, but it never writes repository/business data.  The caller owns parsing
and validating the payload and passes the resulting preview to
``create_preflight``.  Confirmation only performs the atomic
``awaiting_confirmation -> queued`` transition; the import worker remains the
only component that applies repository mutations.
"""

from __future__ import annotations

import hashlib
import html
import json
import math
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

import sqlite_store


STATUS_AWAITING_CONFIRMATION = "awaiting_confirmation"
STATUS_QUEUED = "queued"
STATUS_RUNNING = "running"
STATUS_SUCCEEDED = "succeeded"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"
STATUS_STALE = "stale"

PREFLIGHT_STATUSES = {
    STATUS_AWAITING_CONFIRMATION,
    STATUS_QUEUED,
    STATUS_RUNNING,
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELLED,
    STATUS_STALE,
}
TERMINAL_STATUSES = {
    STATUS_SUCCEEDED,
    STATUS_FAILED,
    STATUS_CANCELLED,
    STATUS_STALE,
}
CANCELLABLE_STATUSES = {
    STATUS_AWAITING_CONFIRMATION,
    STATUS_QUEUED,
    STATUS_STALE,
}

CHINA_TZ = timezone(timedelta(hours=8))
DEFAULT_PAYLOAD_DIR = Path(__file__).resolve().parents[1] / "data" / "import-jobs"
MAX_SUMMARY_LENGTH = 1000
MAX_PREVIEW_DEPTH = 8
MAX_PREVIEW_ITEMS = 500
_CONTROL_CHAR_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_HTML_TAG_PATTERN = re.compile(r"<[^>]*>")
_SAFE_SUFFIX_PATTERN = re.compile(r"^\.[A-Za-z0-9][A-Za-z0-9._-]{0,31}$")
_SAFE_JOB_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


CreatorCheck = Callable[[str, str, Mapping[str, Any]], bool]
PermissionCheck = Callable[[str, str, str], bool]
RevisionGetter = Callable[[], int]


class PreflightError(RuntimeError):
    """Base class for expected preflight workflow failures."""

    code = "preflight_error"

    def __init__(self, message: str, *, job: dict[str, Any] | None = None):
        super().__init__(message)
        self.job = job


class PreflightNotFoundError(PreflightError):
    code = "not_found"


class PreflightTransitionError(PreflightError):
    code = "invalid_transition"


class PreflightCreatorError(PreflightError):
    code = "creator_mismatch"


class PreflightPermissionError(PreflightError):
    code = "permission_denied"

    def __init__(
        self,
        message: str,
        *,
        denied: list[dict[str, str]] | None = None,
        job: dict[str, Any] | None = None,
    ):
        super().__init__(message, job=job)
        self.denied = denied or []


class PreflightValidationError(PreflightError):
    code = "validation_failed"

    def __init__(
        self,
        message: str,
        *,
        errors: list[str] | None = None,
        job: dict[str, Any] | None = None,
    ):
        super().__init__(message, job=job)
        self.errors = errors or []


class PreflightStaleError(PreflightError):
    code = "stale_revision"

    def __init__(
        self,
        message: str,
        *,
        expected_revision: int,
        current_revision: int,
        job: dict[str, Any] | None = None,
    ):
        super().__init__(message, job=job)
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class PreflightRevisionError(PreflightError):
    code = "revision_check_failed"


def china_now_label() -> str:
    return datetime.now(CHINA_TZ).strftime("%Y-%m-%d %H:%M:%S 中国时间")


def sanitize_summary(value: Any, *, max_length: int = MAX_SUMMARY_LENGTH) -> str:
    """Return bounded plain text suitable for storage and later rendering.

    Views must still HTML-escape output.  Removing markup here prevents a job
    summary accidentally becoming an HTML transport between integrations.
    """

    text = html.unescape(str(value or ""))
    text = _HTML_TAG_PATTERN.sub("", text)
    text = _CONTROL_CHAR_PATTERN.sub("", text)
    text = " ".join(text.split())
    return text[: max(1, int(max_length))]


def _json_safe(value: Any, *, depth: int = 0) -> Any:
    """Build a bounded JSON-compatible copy of action metadata/preview data."""

    if depth >= MAX_PREVIEW_DEPTH:
        return "[内容层级过深，已省略]"
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, bytes):
        return f"[二进制内容 {len(value)} bytes，未写入元数据]"
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (raw_key, item) in enumerate(value.items()):
            if index >= MAX_PREVIEW_ITEMS:
                result["_truncated"] = True
                break
            key = sanitize_summary(raw_key, max_length=120)
            if not key:
                continue
            result[key] = _json_safe(item, depth=depth + 1)
        return result
    if isinstance(value, Iterable):
        result_list = []
        for index, item in enumerate(value):
            if index >= MAX_PREVIEW_ITEMS:
                result_list.append("[其余内容已省略]")
                break
            result_list.append(_json_safe(item, depth=depth + 1))
        return result_list
    return sanitize_summary(value)


def _sanitize_message_list(values: Iterable[Any] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        message = sanitize_summary(value, max_length=500)
        if message and message not in result:
            result.append(message)
        if len(result) >= 200:
            break
    return result


def normalize_scope_permissions(
    requirements: Mapping[str, Iterable[str]] | Iterable[Mapping[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Normalize scope/permission requirements into stable metadata records."""

    if requirements is None:
        return []
    if isinstance(requirements, Mapping):
        source = [
            {"scope_key": scope_key, "permission_keys": permission_keys}
            for scope_key, permission_keys in requirements.items()
        ]
    else:
        source = list(requirements)
    merged: dict[str, list[str]] = {}
    for item in source:
        if not isinstance(item, Mapping):
            raise ValueError("赛区权限要求必须是 scope_key/permission_keys 映射。")
        scope_key = sanitize_summary(item.get("scope_key"), max_length=240)
        if not scope_key:
            raise ValueError("赛区权限要求缺少 scope_key。")
        raw_permissions = item.get("permission_keys")
        if isinstance(raw_permissions, str):
            raw_permissions = [raw_permissions]
        permission_keys: list[str] = []
        for raw_permission in raw_permissions or []:
            permission_key = sanitize_summary(raw_permission, max_length=120)
            if permission_key and permission_key not in permission_keys:
                permission_keys.append(permission_key)
        if not permission_keys:
            raise ValueError(f"赛区 {scope_key} 没有声明需要校验的权限。")
        merged.setdefault(scope_key, [])
        for permission_key in permission_keys:
            if permission_key not in merged[scope_key]:
                merged[scope_key].append(permission_key)
    return [
        {"scope_key": scope_key, "permission_keys": sorted(permission_keys)}
        for scope_key, permission_keys in sorted(merged.items())
    ]


def check_scope_permissions(
    actor: str,
    requirements: Mapping[str, Iterable[str]] | Iterable[Mapping[str, Any]] | None,
    permission_check: PermissionCheck | None,
) -> list[dict[str, str]]:
    """Check every required scope/permission and return all denials.

    Checking every pair makes batch authorization all-or-nothing and gives the
    UI a complete conflict list rather than failing on the first scope.
    """

    normalized = normalize_scope_permissions(requirements)
    if not normalized:
        return []
    if permission_check is None:
        return [
            {
                "scope_key": item["scope_key"],
                "permission_key": permission_key,
            }
            for item in normalized
            for permission_key in item["permission_keys"]
        ]
    denied: list[dict[str, str]] = []
    for item in normalized:
        for permission_key in item["permission_keys"]:
            try:
                allowed = bool(
                    permission_check(actor, item["scope_key"], permission_key)
                )
            except Exception:
                allowed = False
            if not allowed:
                denied.append(
                    {
                        "scope_key": item["scope_key"],
                        "permission_key": permission_key,
                    }
                )
    return denied


def _safe_payload_suffix(filename: str, explicit_suffix: str = "") -> str:
    suffix = str(explicit_suffix or "").strip()
    if suffix and not suffix.startswith("."):
        suffix = "." + suffix
    if not suffix:
        suffix = Path(str(filename or "")).suffix
    if not _SAFE_SUFFIX_PATTERN.fullmatch(suffix):
        return ".bin"
    return suffix.lower()


def _new_job_id() -> str:
    timestamp = datetime.now(CHINA_TZ).strftime("%Y%m%d_%H%M%S_")
    return "imp_" + timestamp + secrets.token_hex(4)


def _payload_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as payload_file:
        for chunk in iter(lambda: payload_file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _record_from_row(row: Any) -> dict[str, Any]:
    try:
        metadata = json.loads(row["metadata_json"] or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "batch_id": str(row["job_id"] or ""),
        "action": str(row["action"] or ""),
        "label": str(row["label"] or ""),
        "filename": str(row["filename"] or ""),
        "status": str(row["status"] or ""),
        "created_at": str(row["created_at"] or ""),
        "created_by": str(row["created_by"] or ""),
        "completed_at": str(row["completed_at"] or ""),
        "rolled_back_at": str(row["rolled_back_at"] or ""),
        "rolled_back_by": str(row["rolled_back_by"] or ""),
        "summary": str(row["summary"] or ""),
        "metadata": metadata,
        "payload_path": str(row["payload_path"] or ""),
        "attempts": int(row["attempts"] or 0),
        "locked_at_epoch": int(row["locked_at_epoch"] or 0),
        "locked_by": str(row["locked_by"] or ""),
    }


def get_preflight(job_id: str) -> dict[str, Any] | None:
    """Load one preflight job without the 200-row history-list limit."""

    normalized_job_id = str(job_id or "").strip()
    if not normalized_job_id:
        return None
    with sqlite_store.connect_read_db() as connection:
        sqlite_store.require_initialized_database(connection)
        row = connection.execute(
            """
            SELECT job_id, action, label, filename, status, created_at, created_by,
                   completed_at, rolled_back_at, rolled_back_by, summary,
                   metadata_json, payload_path, attempts, locked_at_epoch, locked_by
            FROM import_jobs
            WHERE job_id = ?
            """,
            (normalized_job_id,),
        ).fetchone()
    if not row:
        return None
    record = _record_from_row(row)
    preflight = record["metadata"].get("preflight")
    if not isinstance(preflight, dict):
        return None
    return record


def _require_preflight(job_id: str) -> dict[str, Any]:
    job = get_preflight(job_id)
    if job is None:
        raise PreflightNotFoundError("没有找到这个上传预检任务。")
    return job


def create_preflight(
    *,
    action: str,
    label: str,
    filename: str,
    created_by: str,
    payload_data: bytes | bytearray | memoryview | None = None,
    payload_path: str | Path | None = None,
    payload_suffix: str = "",
    content_type: str = "application/octet-stream",
    payload: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
    required_scope_permissions: (
        Mapping[str, Iterable[str]] | Iterable[Mapping[str, Any]] | None
    ) = None,
    validation_errors: Iterable[Any] | None = None,
    warnings: Iterable[Any] | None = None,
    data_revision: int | None = None,
    revision_getter: RevisionGetter = sqlite_store.get_data_revision,
    snapshot_json: str = "{}",
    summary: str = "",
    created_at: str = "",
    job_id: str = "",
    payload_dir: str | Path | None = None,
    delete_payload_on_cancel: bool = True,
) -> str:
    """Persist a validated preview and its payload, returning the import job id.

    ``payload`` is the bounded JSON preview shown before confirmation;
    ``payload_data`` is the original uploaded file.  ``payload_path`` supports a
    caller that already staged the upload.  The two file arguments are mutually
    exclusive.  Suffixes are not type-whitelisted, so ``.zip`` and future upload
    formats work without changing this module.
    """

    normalized_action = sanitize_summary(action, max_length=160)
    normalized_label = sanitize_summary(label, max_length=240)
    normalized_creator = sanitize_summary(created_by, max_length=160)
    normalized_filename = sanitize_summary(Path(str(filename or "")).name, max_length=255)
    if not normalized_action or not normalized_label or not normalized_creator:
        raise ValueError("action、label 和 created_by 均不能为空。")
    if payload_data is not None and payload_path:
        raise ValueError("payload_data 和 payload_path 只能提供一个。")

    normalized_requirements = normalize_scope_permissions(
        required_scope_permissions
    )
    blocking_errors = _sanitize_message_list(validation_errors)
    normalized_warnings = _sanitize_message_list(warnings)
    try:
        captured_revision = int(
            revision_getter() if data_revision is None else data_revision
        )
    except Exception as exc:
        raise PreflightRevisionError("无法读取当前数据版本，未创建预检任务。") from exc

    normalized_job_id = str(job_id or _new_job_id()).strip()
    if not _SAFE_JOB_ID_PATTERN.fullmatch(normalized_job_id):
        raise ValueError("job_id 只能包含字母、数字、点、下划线和连字符。")
    suffix = _safe_payload_suffix(normalized_filename, payload_suffix)
    raw_payload = bytes(payload_data) if payload_data is not None else None
    safe_metadata = _json_safe(metadata or {})
    if not isinstance(safe_metadata, dict):
        safe_metadata = {}
    safe_preview_payload = _json_safe(payload or {})
    scope_keys = [item["scope_key"] for item in normalized_requirements]
    stored_payload_path = str(payload_path or "")
    created_payload_path: Path | None = None
    if raw_payload is not None:
        target_dir = Path(payload_dir or DEFAULT_PAYLOAD_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        created_payload_path = target_dir / f"{normalized_job_id}{suffix}"
        # Random ids make collisions exceptionally unlikely; fail closed rather
        # than overwriting another task if a caller supplies a duplicate id.
        try:
            with created_payload_path.open("xb") as payload_file:
                payload_file.write(raw_payload)
        except Exception:
            created_payload_path.unlink(missing_ok=True)
            raise
        stored_payload_path = str(created_payload_path)

    stored_payload_file = Path(stored_payload_path) if stored_payload_path else None
    try:
        payload_size = (
            len(raw_payload)
            if raw_payload is not None
            else (
                stored_payload_file.stat().st_size
                if stored_payload_file is not None and stored_payload_file.is_file()
                else 0
            )
        )
        payload_sha256 = (
            hashlib.sha256(raw_payload).hexdigest()
            if raw_payload is not None
            else (
                _payload_digest(stored_payload_file)
                if stored_payload_file is not None and stored_payload_file.is_file()
                else ""
            )
        )
    except OSError as exc:
        if created_payload_path is not None:
            created_payload_path.unlink(missing_ok=True)
        raise ValueError("无法读取暂存的上传文件。") from exc
    preflight_metadata = {
        "version": 1,
        "data_revision": captured_revision,
        "payload": safe_preview_payload,
        "blocking_errors": blocking_errors,
        "warnings": normalized_warnings,
        "can_confirm": not blocking_errors,
        "permission_scope_keys": scope_keys,
        "required_scope_permissions": normalized_requirements,
        "content_type": sanitize_summary(content_type, max_length=255),
        "payload_suffix": suffix,
        "payload_size": payload_size,
        "payload_sha256": payload_sha256,
        "delete_payload_on_cancel": bool(delete_payload_on_cancel),
    }
    safe_metadata.update(
        {
            "data_revision": captured_revision,
            "permission_scope_keys": scope_keys,
            "required_scope_permissions": normalized_requirements,
            "content_type": preflight_metadata["content_type"],
            "preflight": preflight_metadata,
        }
    )
    record_summary = sanitize_summary(summary) or (
        f"预检发现 {len(blocking_errors)} 项阻断错误"
        if blocking_errors
        else "预检完成，等待确认"
    )
    record = {
        "batch_id": normalized_job_id,
        "action": normalized_action,
        "label": normalized_label,
        "filename": normalized_filename,
        "status": STATUS_AWAITING_CONFIRMATION,
        "created_at": sanitize_summary(created_at, max_length=80) or china_now_label(),
        "created_by": normalized_creator,
        "summary": record_summary,
        "metadata": safe_metadata,
        "payload_path": stored_payload_path,
    }
    try:
        sqlite_store.create_import_job_record(record, snapshot_json=snapshot_json)
    except Exception:
        if created_payload_path is not None:
            created_payload_path.unlink(missing_ok=True)
        raise
    return normalized_job_id


def _check_creator(
    actor: str,
    job: dict[str, Any],
    creator_check: CreatorCheck | None,
) -> None:
    normalized_actor = str(actor or "").strip()
    created_by = str(job.get("created_by") or "").strip()
    try:
        allowed = (
            bool(creator_check(normalized_actor, created_by, job))
            if creator_check is not None
            else bool(normalized_actor and normalized_actor == created_by)
        )
    except Exception:
        allowed = False
    if not allowed:
        raise PreflightCreatorError("只能由上传任务创建人确认或取消。", job=job)


def _requirements_from_job(job: Mapping[str, Any]) -> list[dict[str, Any]]:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    preflight = metadata.get("preflight") if isinstance(metadata, dict) else {}
    raw_requirements = (
        preflight.get("required_scope_permissions")
        if isinstance(preflight, dict)
        else None
    )
    return normalize_scope_permissions(raw_requirements)


def _preflight_metadata(job: Mapping[str, Any]) -> dict[str, Any]:
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    preflight = metadata.get("preflight") if isinstance(metadata, dict) else {}
    return dict(preflight) if isinstance(preflight, dict) else {}


def _transition(
    job: dict[str, Any],
    *,
    from_statuses: set[str],
    to_status: str,
    summary: str,
    preflight_updates: Mapping[str, Any],
    completed_at: str = "",
    clear_payload: bool = False,
) -> dict[str, Any]:
    metadata = dict(job.get("metadata") or {})
    preflight = _preflight_metadata(job)
    preflight.update(_json_safe(preflight_updates))
    metadata["preflight"] = preflight
    placeholders = ",".join("?" for _ in from_statuses)
    params: list[Any] = [
        to_status,
        sanitize_summary(summary),
        json.dumps(metadata, ensure_ascii=False),
        completed_at,
        completed_at,
        1 if clear_payload else 0,
        str(job["batch_id"]),
        *sorted(from_statuses),
    ]
    with sqlite_store.connect_write_db() as connection:
        sqlite_store.require_initialized_database(connection)
        with sqlite_store.transaction_context(connection):
            cursor = connection.execute(
                f"""
                UPDATE import_jobs
                SET status = ?,
                    summary = ?,
                    metadata_json = ?,
                    completed_at = CASE WHEN ? != '' THEN ? ELSE completed_at END,
                    payload_path = CASE WHEN ? = 1 THEN '' ELSE payload_path END,
                    locked_at_epoch = 0,
                    locked_by = ''
                WHERE job_id = ?
                  AND status IN ({placeholders})
                """,
                params,
            )
            if cursor.rowcount != 1:
                raise PreflightTransitionError(
                    "上传任务状态已发生变化，请刷新后重试。",
                    job=job,
                )
    return _require_preflight(str(job["batch_id"]))


def confirm_preflight(
    job_id: str,
    *,
    actor: str,
    permission_check: PermissionCheck | None,
    revision_getter: RevisionGetter = sqlite_store.get_data_revision,
    creator_check: CreatorCheck | None = None,
    now_label: str = "",
) -> dict[str, Any]:
    """Revalidate and atomically queue a preflight without repository writes."""

    job = _require_preflight(job_id)
    if job["status"] != STATUS_AWAITING_CONFIRMATION:
        raise PreflightTransitionError(
            "只有等待确认的预检任务可以提交。",
            job=job,
        )
    _check_creator(actor, job, creator_check)
    preflight = _preflight_metadata(job)
    blocking_errors = _sanitize_message_list(preflight.get("blocking_errors"))
    if blocking_errors:
        raise PreflightValidationError(
            "预检仍有阻断错误，不能进入导入队列。",
            errors=blocking_errors,
            job=job,
        )

    requirements = _requirements_from_job(job)
    denied = check_scope_permissions(actor, requirements, permission_check)
    if denied:
        raise PreflightPermissionError(
            "当前账号已无权处理预检中的全部赛区，整批未提交。",
            denied=denied,
            job=job,
        )
    expected_revision = int(preflight.get("data_revision", -1))
    try:
        current_revision = int(revision_getter())
    except Exception as exc:
        raise PreflightRevisionError(
            "无法重新检查数据版本，整批未提交。",
            job=job,
        ) from exc
    effective_now = sanitize_summary(now_label, max_length=80) or china_now_label()
    if current_revision != expected_revision:
        stale_job = _transition(
            job,
            from_statuses={STATUS_AWAITING_CONFIRMATION},
            to_status=STATUS_STALE,
            summary="数据已变化，请重新预检后再提交",
            completed_at=effective_now,
            preflight_updates={
                "stale_at": effective_now,
                "stale_expected_revision": expected_revision,
                "stale_current_revision": current_revision,
                "can_confirm": False,
            },
        )
        raise PreflightStaleError(
            "数据已在预检后发生变化，请重新预检。",
            expected_revision=expected_revision,
            current_revision=current_revision,
            job=stale_job,
        )
    return _transition(
        job,
        from_statuses={STATUS_AWAITING_CONFIRMATION},
        to_status=STATUS_QUEUED,
        summary="等待后台任务处理",
        preflight_updates={
            "confirmed_at": effective_now,
            "confirmed_by": str(actor or "").strip(),
            "confirmed_revision": current_revision,
            "can_confirm": False,
        },
    )


def cancel_preflight(
    job_id: str,
    *,
    actor: str,
    permission_check: PermissionCheck | None = None,
    revision_getter: RevisionGetter | None = None,
    creator_check: CreatorCheck | None = None,
    now_label: str = "",
) -> dict[str, Any]:
    """Cancel an unclaimed task and clear its staged payload.

    Cancellation always requires the creator (or an explicit creator override).
    Callers may also pass the same permission/revision callbacks used during
    confirmation.  Revision changes are recorded for audit but never prevent a
    safe cancellation.
    """

    job = _require_preflight(job_id)
    if job["status"] not in CANCELLABLE_STATUSES:
        raise PreflightTransitionError(
            "这个上传任务当前不能取消。",
            job=job,
        )
    _check_creator(actor, job, creator_check)
    requirements = _requirements_from_job(job)
    if permission_check is not None:
        denied = check_scope_permissions(actor, requirements, permission_check)
        if denied:
            raise PreflightPermissionError(
                "当前账号已无权取消预检中的全部赛区。",
                denied=denied,
                job=job,
            )
    preflight = _preflight_metadata(job)
    current_revision: int | None = None
    if revision_getter is not None:
        try:
            current_revision = int(revision_getter())
        except Exception as exc:
            raise PreflightRevisionError(
                "无法重新检查数据版本，任务未取消。",
                job=job,
            ) from exc
    expected_revision = int(preflight.get("data_revision", -1))
    effective_now = sanitize_summary(now_label, max_length=80) or china_now_label()
    payload_to_delete = Path(str(job.get("payload_path") or ""))
    delete_payload = bool(preflight.get("delete_payload_on_cancel", True))
    cancelled = _transition(
        job,
        from_statuses=CANCELLABLE_STATUSES,
        to_status=STATUS_CANCELLED,
        summary="已取消上传任务",
        completed_at=effective_now,
        clear_payload=True,
        preflight_updates={
            "cancelled_at": effective_now,
            "cancelled_by": str(actor or "").strip(),
            "cancelled_revision": current_revision,
            "revision_changed_before_cancel": (
                current_revision is not None and current_revision != expected_revision
            ),
            "can_confirm": False,
        },
    )
    if delete_payload and str(payload_to_delete) and (
        payload_to_delete.is_file() or payload_to_delete.is_symlink()
    ):
        payload_to_delete.unlink(missing_ok=True)
    return cancelled


# Verbose aliases make call sites self-documenting while keeping the compact
# integration names requested by the console routes.
create_upload_preflight = create_preflight
get_upload_preflight = get_preflight
confirm_upload_preflight = confirm_preflight
cancel_upload_preflight = cancel_preflight
