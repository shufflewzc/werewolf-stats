#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import os
import socket
import time
from pathlib import Path

from sqlite_store import (
    RepositoryConflictError,
    claim_import_job,
    get_data_revision,
    load_import_job_records,
    load_users,
    reserve_data_revision,
    update_import_job_record,
)
from import_preflight import get_preflight
from web.features.matches import (
    run_dimension_excel_import_job,
    run_match_excel_import_job,
    run_player_photo_zip_import_job,
    run_team_logo_excel_import_job,
    validate_excel_upload,
    validate_zip_upload,
)
from web_app import (
    RequestContext,
    UploadedFile,
    china_now_label,
    invalidate_validated_data_cache,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process durable upload import jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--stale-after-seconds", type=int, default=600)
    return parser.parse_args()


def build_worker_context(job: dict) -> RequestContext:
    username = str(job.get("created_by") or "")
    current_user = next(
        (
            user
            for user in load_users()
            if user.get("username") == username and user.get("active", True)
        ),
        None,
    )
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    request_id = str(metadata.get("request_id") or f"worker_{job['batch_id']}")
    return RequestContext(
        method="POST",
        path="/matches/new",
        query={},
        form={},
        files={},
        current_user=current_user,
        now_label=china_now_label(),
        remote_addr="127.0.0.1",
        request_id=request_id,
        session_token="",
    )


def process_job(job: dict) -> None:
    job_id = str(job["batch_id"])
    action = str(job.get("action") or "")
    supported_actions = {
        "matches.import_excel",
        "dimension.import_excel",
        "team_logo.import_excel",
        "player_photo.import_zip",
    }
    if action not in supported_actions:
        update_import_job_record(
            job_id,
            status="failed",
            summary=f"不支持的后台任务类型：{action or 'unknown'}",
            completed_at=china_now_label(),
        )
        return
    payload_path = Path(str(job.get("payload_path") or ""))
    if not payload_path.is_file():
        update_import_job_record(
            job_id,
            status="failed",
            summary="Excel 后台任务文件不存在，请重新提交。",
            completed_at=china_now_label(),
        )
        return
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    preflight = metadata.get("preflight") if isinstance(metadata.get("preflight"), dict) else {}
    raw_confirmed_revision = preflight.get("confirmed_revision")
    if raw_confirmed_revision is None:
        raw_confirmed_revision = preflight.get("data_revision")
    try:
        confirmed_revision = int(raw_confirmed_revision)
    except (TypeError, ValueError):
        update_import_job_record(
            job_id,
            status="failed",
            summary="导入任务缺少有效的预检数据版本，请重新上传并确认。",
            completed_at=china_now_label(),
        )
        return
    expected_digest = str(preflight.get("payload_sha256") or "").strip()
    payload_data = payload_path.read_bytes()
    if expected_digest and hashlib.sha256(payload_data).hexdigest() != expected_digest:
        update_import_job_record(
            job_id,
            status="failed",
            summary="上传暂存文件校验失败，请取消任务后重新上传。",
            completed_at=china_now_label(),
        )
        return
    upload = UploadedFile(
        filename=str(job.get("filename") or payload_path.name),
        content_type=str(
            metadata.get("content_type")
            or (
                "application/zip"
                if action == "player_photo.import_zip"
                else "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        ),
        data=payload_data,
    )
    validation_error = (
        validate_zip_upload(upload)
        if action == "player_photo.import_zip"
        else validate_excel_upload(upload)
    )
    if validation_error:
        update_import_job_record(
            job_id,
            status="failed",
            summary="后台重新校验上传文件失败：" + validation_error,
            completed_at=china_now_label(),
        )
        return
    ctx = build_worker_context(job)
    if not ctx.current_user:
        update_import_job_record(
            job_id,
            status="failed",
            summary="导入账号不存在或已停用，任务未执行。",
            completed_at=china_now_label(),
        )
        return
    try:
        reserved_revision = reserve_data_revision(confirmed_revision)
    except RepositoryConflictError:
        update_import_job_record(
            job_id,
            status="stale",
            summary=(
                "数据已在确认后发生变化，请重新预检。"
                f"（确认版本 {confirmed_revision}，当前版本 {get_data_revision()}）"
            ),
            completed_at=china_now_label(),
        )
        return
    invalidate_validated_data_cache()
    competition_name = str(metadata.get("competition_name") or "")
    season_name = str(metadata.get("season_name") or "")
    if action == "matches.import_excel":
        run_match_excel_import_job(
            ctx,
            upload,
            str(metadata.get("group_label") or ""),
            job_id,
            expected_data_revision=reserved_revision,
        )
    elif action == "dimension.import_excel":
        run_dimension_excel_import_job(
            ctx,
            upload,
            competition_name,
            season_name,
            job_id,
            expected_data_revision=reserved_revision,
        )
    elif action == "team_logo.import_excel":
        run_team_logo_excel_import_job(
            ctx,
            upload,
            competition_name,
            season_name,
            job_id,
            expected_data_revision=reserved_revision,
        )
    else:
        run_player_photo_zip_import_job(
            ctx,
            upload,
            competition_name,
            season_name,
            job_id,
            expected_data_revision=reserved_revision,
        )
    refreshed = get_preflight(job_id) or next(
        (
            item
            for item in load_import_job_records(200)
            if item.get("batch_id") == job_id
        ),
        None,
    )
    if refreshed and refreshed.get("status") == "succeeded":
        payload_path.unlink(missing_ok=True)
        update_import_job_record(
            job_id,
            status="succeeded",
            payload_path="",
        )


def main() -> int:
    args = parse_args()
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    while True:
        job = claim_import_job(
            worker_id,
            stale_after_seconds=args.stale_after_seconds,
        )
        if job:
            process_job(job)
            if args.once:
                return 0
            continue
        if args.once:
            return 0
        time.sleep(max(0.2, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
