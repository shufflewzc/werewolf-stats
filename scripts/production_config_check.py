#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import shutil
import sys
from urllib.parse import urlparse


PLACEHOLDER_VALUES = {
    "",
    "changeme",
    "change-me",
    "your-appid",
    "your-secret",
    "你的小程序AppID",
    "你的小程序Secret",
}


class ConfigReport:
    def __init__(self) -> None:
        self.ok_items: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def ok(self, message: str) -> None:
        self.ok_items.append(message)

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    def fail(self, message: str) -> None:
        self.errors.append(message)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check production environment configuration before startup.")
    parser.add_argument("--database-url", default="", help="Override DATABASE_URL for this check.")
    parser.add_argument("--allow-sqlite", action="store_true", help="Allow production startup without PostgreSQL.")
    parser.add_argument("--skip-wechat", action="store_true", help="Do not require WeChat Mini Program credentials.")
    parser.add_argument("--strict-warnings", action="store_true", help="Treat warnings as failures.")
    return parser.parse_args(argv)


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def is_placeholder(value: str) -> bool:
    normalized = value.strip()
    return normalized in PLACEHOLDER_VALUES or normalized.lower() in PLACEHOLDER_VALUES


def parse_int_env(name: str, default: int, report: ConfigReport) -> int:
    raw_value = env(name, str(default))
    try:
        return int(raw_value)
    except ValueError:
        report.fail(f"{name} 必须是整数，当前为 {raw_value!r}。")
        return default


def check_database(report: ConfigReport, *, allow_sqlite: bool) -> None:
    database_url = env("DATABASE_URL")
    if not database_url:
        if allow_sqlite:
            report.warn("DATABASE_URL 未设置；已允许使用 SQLite，仅适合本地或应急。")
            return
        report.fail("DATABASE_URL 未设置；正式环境必须使用 PostgreSQL。")
        return
    parsed = urlparse(database_url)
    if parsed.scheme.lower() not in {"postgres", "postgresql"}:
        if allow_sqlite:
            report.warn("DATABASE_URL 不是 PostgreSQL；已允许继续。")
        else:
            report.fail("DATABASE_URL 必须是 postgresql:// 或 postgres:// 连接串。")
        return
    if not parsed.hostname or not parsed.path.strip("/"):
        report.fail("DATABASE_URL 缺少主机名或数据库名。")
    else:
        report.ok("DATABASE_URL 指向 PostgreSQL。")
    if env("ENABLE_POSTGRES_WRITES", "1") != "1":
        report.fail("ENABLE_POSTGRES_WRITES 必须为 1，避免生产环境读写不一致或回落 SQLite。")
    else:
        report.ok("ENABLE_POSTGRES_WRITES=1。")


def check_wechat(report: ConfigReport, *, skip_wechat: bool) -> None:
    appid = env("WECHAT_MINIPROGRAM_APPID")
    secret = env("WECHAT_MINIPROGRAM_SECRET")
    if skip_wechat:
        if not appid or not secret:
            report.warn("已跳过微信配置强校验；微信登录在缺少 AppID/Secret 时不可用。")
        return
    if is_placeholder(appid):
        report.fail("WECHAT_MINIPROGRAM_APPID 未配置或仍是占位值。")
    else:
        report.ok("WECHAT_MINIPROGRAM_APPID 已配置。")
    if is_placeholder(secret):
        report.fail("WECHAT_MINIPROGRAM_SECRET 未配置或仍是占位值。")
    else:
        report.ok("WECHAT_MINIPROGRAM_SECRET 已配置。")
    if env("ALLOW_WECHAT_DEV_LOGIN") == "1":
        report.fail("ALLOW_WECHAT_DEV_LOGIN=1 只允许本地调试，生产环境必须关闭。")
    else:
        report.ok("微信开发登录开关未开启。")
    if env("WECHAT_MINIPROGRAM_DEV_OPENID"):
        report.warn("WECHAT_MINIPROGRAM_DEV_OPENID 已设置；生产环境建议移除。")


def check_https_and_cookie(report: ConfigReport) -> None:
    base_url = env("WEB_LOGIN_BASE_URL", "https://wolf.metauniverse-cn.xyz")
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        report.fail("WEB_LOGIN_BASE_URL 必须使用 https://，否则网页登录和 Cookie 安全性不足。")
    elif parsed.hostname in {"localhost", "127.0.0.1", "0.0.0.0"}:
        report.fail("WEB_LOGIN_BASE_URL 不能是本地地址。")
    else:
        report.ok("WEB_LOGIN_BASE_URL 使用 HTTPS。")
    cookie_secure = env("COOKIE_SECURE", "1")
    if cookie_secure == "0":
        report.fail("COOKIE_SECURE=0 仅适合本地 HTTP 调试，生产环境必须开启。")
    else:
        report.ok("COOKIE_SECURE 已开启。")


def check_security_headers(report: ConfigReport) -> None:
    if env("SECURITY_HEADERS_ENABLED", "1") == "0":
        report.fail("SECURITY_HEADERS_ENABLED=0 会关闭安全响应头，生产环境必须开启。")
    else:
        report.ok("安全响应头开关已开启。")
    csp = env("CONTENT_SECURITY_POLICY", "default-src 'self'; frame-ancestors 'none'")
    if not csp:
        report.fail("CONTENT_SECURITY_POLICY 不能为空。")
    elif "frame-ancestors" not in csp:
        report.warn("CONTENT_SECURITY_POLICY 建议包含 frame-ancestors，防止页面被嵌套。")
    else:
        report.ok("CONTENT_SECURITY_POLICY 已配置 frame-ancestors。")
    if env("CSRF_PROTECTION_ENABLED", "1") == "0":
        report.fail("CSRF_PROTECTION_ENABLED=0 会关闭后台表单防护，生产环境必须开启。")
    else:
        report.ok("CSRF 防护开关已开启。")


def check_upload_and_runtime_limits(report: ConfigReport) -> None:
    request_bytes = parse_int_env("MAX_REQUEST_BODY_BYTES", 50 * 1024 * 1024, report)
    excel_bytes = parse_int_env("MAX_EXCEL_UPLOAD_BYTES", 10 * 1024 * 1024, report)
    zip_bytes = parse_int_env("MAX_ZIP_UPLOAD_BYTES", 50 * 1024 * 1024, report)
    zip_count = parse_int_env("MAX_ZIP_IMAGE_COUNT", 300, report)
    slow_ms = parse_int_env("SLOW_REQUEST_THRESHOLD_MS", 1500, report)
    rate_window = parse_int_env("REQUEST_RATE_LIMIT_WINDOW_SECONDS", 60, report)
    rate_default = parse_int_env("REQUEST_RATE_LIMIT_DEFAULT_MAX", 120, report)
    rate_sensitive = parse_int_env("REQUEST_RATE_LIMIT_SENSITIVE_MAX", 30, report)
    idempotency_ttl = parse_int_env("IDEMPOTENCY_PROTECTION_TTL_SECONDS", 8, report)
    if request_bytes < 1024 * 1024:
        report.warn("MAX_REQUEST_BODY_BYTES 小于 1MB，可能导致正常上传失败。")
    elif request_bytes > 100 * 1024 * 1024:
        report.warn("MAX_REQUEST_BODY_BYTES 大于 100MB，上传请求可能占用过多内存。")
    else:
        report.ok("MAX_REQUEST_BODY_BYTES 在合理范围。")
    if excel_bytes > request_bytes:
        report.fail("MAX_EXCEL_UPLOAD_BYTES 不能大于 MAX_REQUEST_BODY_BYTES。")
    else:
        report.ok("Excel 上传限制不超过总请求限制。")
    if zip_bytes > request_bytes:
        report.fail("MAX_ZIP_UPLOAD_BYTES 不能大于 MAX_REQUEST_BODY_BYTES。")
    else:
        report.ok("ZIP 上传限制不超过总请求限制。")
    if zip_count <= 0 or zip_count > 1000:
        report.warn("MAX_ZIP_IMAGE_COUNT 建议保持在 1 到 1000 之间。")
    else:
        report.ok("ZIP 图片数量限制在合理范围。")
    if slow_ms < 0:
        report.fail("SLOW_REQUEST_THRESHOLD_MS 不能为负数。")
    elif slow_ms == 0:
        report.warn("慢请求日志已关闭。")
    else:
        report.ok("慢请求日志阈值已配置。")
    if env("REQUEST_RATE_LIMIT_ENABLED", "1") == "0":
        report.warn("接口限流已关闭，异常流量可能影响服务稳定性。")
    elif rate_window < 10:
        report.warn("REQUEST_RATE_LIMIT_WINDOW_SECONDS 小于 10 秒，限流窗口过短。")
    elif rate_default < rate_sensitive:
        report.fail("REQUEST_RATE_LIMIT_DEFAULT_MAX 不能小于 REQUEST_RATE_LIMIT_SENSITIVE_MAX。")
    elif rate_sensitive < 5:
        report.warn("REQUEST_RATE_LIMIT_SENSITIVE_MAX 小于 5，可能影响正常登录或绑定。")
    else:
        report.ok("接口限流配置有效。")
    if env("IDEMPOTENCY_PROTECTION_ENABLED", "1") == "0":
        report.warn("重复提交保护已关闭，网络重试或连点可能造成重复写入。")
    elif idempotency_ttl < 2:
        report.warn("IDEMPOTENCY_PROTECTION_TTL_SECONDS 小于 2 秒，重复提交保护窗口偏短。")
    elif idempotency_ttl > 60:
        report.warn("IDEMPOTENCY_PROTECTION_TTL_SECONDS 大于 60 秒，可能影响用户修正后重新提交。")
    else:
        report.ok("重复提交保护配置有效。")


def check_gunicorn_and_logging(report: ConfigReport) -> None:
    workers = parse_int_env("GUNICORN_WORKERS", 2, report)
    threads = parse_int_env("GUNICORN_THREADS", 4, report)
    timeout = parse_int_env("GUNICORN_TIMEOUT", 120, report)
    access_days = parse_int_env("ACCESS_LOG_RETENTION_DAYS", 30, report)
    audit_days = parse_int_env("AUDIT_LOG_RETENTION_DAYS", 365, report)
    if workers <= 0 or threads <= 0:
        report.fail("GUNICORN_WORKERS 和 GUNICORN_THREADS 必须大于 0。")
    else:
        report.ok("Gunicorn worker/thread 配置有效。")
    if timeout < 30:
        report.warn("GUNICORN_TIMEOUT 小于 30 秒，导入或 AI 请求可能被过早中断。")
    else:
        report.ok("Gunicorn timeout 配置有效。")
    if access_days < 1:
        report.warn("ACCESS_LOG_RETENTION_DAYS 小于 1，访问日志会很快被清理。")
    else:
        report.ok("访问日志留存天数有效。")
    if audit_days < 90:
        report.warn("AUDIT_LOG_RETENTION_DAYS 建议至少 90 天。")
    else:
        report.ok("审计日志留存天数有效。")
    if env("STRUCTURED_ERROR_TRACEBACK") == "1":
        report.warn("STRUCTURED_ERROR_TRACEBACK=1 会输出完整堆栈，排障后建议关闭。")


def check_backup_tools(report: ConfigReport) -> None:
    if env("DATABASE_URL") and urlparse(env("DATABASE_URL")).scheme.lower() in {"postgres", "postgresql"}:
        missing = [name for name in ("pg_dump", "pg_restore") if not shutil.which(name)]
        if missing:
            report.warn("缺少 PostgreSQL 备份工具：" + ", ".join(missing) + "。备份恢复演练会受影响。")
        else:
            report.ok("PostgreSQL 备份工具可用。")


def print_report(report: ConfigReport) -> None:
    print("生产配置体检")
    for message in report.ok_items:
        print(f"[OK] {message}")
    for message in report.warnings:
        print(f"[WARN] {message}")
    for message in report.errors:
        print(f"[FAIL] {message}")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.database_url.strip():
        os.environ["DATABASE_URL"] = args.database_url.strip()
    report = ConfigReport()
    check_database(report, allow_sqlite=args.allow_sqlite)
    check_wechat(report, skip_wechat=args.skip_wechat)
    check_https_and_cookie(report)
    check_security_headers(report)
    check_upload_and_runtime_limits(report)
    check_gunicorn_and_logging(report)
    check_backup_tools(report)
    print_report(report)
    if report.errors or (args.strict_warnings and report.warnings):
        print("\n生产配置体检未通过，请先修正上述配置。", file=sys.stderr)
        return 1
    print("\n生产配置体检通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
