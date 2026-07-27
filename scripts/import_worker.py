#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import socket
import time
from pathlib import Path

from sqlite_store import (
    claim_import_job,
    load_import_job_records,
    load_users,
    update_import_job_record,
)
from web.features.matches import run_match_excel_import_job
from web_app import RequestContext, UploadedFile, china_now_label


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Process durable Excel import jobs.")
    parser.add_argument("--once", action="store_true", help="Process at most one job and exit.")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--stale-after-seconds", type=int, default=600)
    return parser.parse_args()


def build_worker_context(job: dict) -> RequestContext:
    username = str(job.get("created_by") or "")
    current_user = next(
        (user for user in load_users() if user.get("username") == username),
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
    if job.get("action") != "matches.import_excel":
        update_import_job_record(
            job_id,
            status="failed",
            summary=f"不支持的后台任务类型：{job.get('action') or 'unknown'}",
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
    upload = UploadedFile(
        filename=str(job.get("filename") or payload_path.name),
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        data=payload_path.read_bytes(),
    )
    run_match_excel_import_job(
        build_worker_context(job),
        upload,
        str(metadata.get("group_label") or ""),
        job_id,
    )
    refreshed = next(
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
