#!/usr/bin/env python3

from __future__ import annotations

import argparse
import io
import json
import statistics
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlencode


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from db_runtime import runtime_database_summary
from web_app import app


@dataclass
class ApiTiming:
    name: str
    path: str
    status: str
    runs_ms: list[float]
    bytes_count: int

    @property
    def average_ms(self) -> float:
        return statistics.mean(self.runs_ms) if self.runs_ms else 0.0

    @property
    def max_ms(self) -> float:
        return max(self.runs_ms) if self.runs_ms else 0.0


class ApiBenchmarkError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark miniprogram-facing API endpoints without binding a web port.")
    parser.add_argument("--runs", type=int, default=3, help="Number of calls per endpoint.")
    parser.add_argument("--warmup-runs", type=int, default=1, help="Warmup calls per endpoint before measuring.")
    parser.add_argument("--warn-ms", type=float, default=800.0, help="Print warning when endpoint max latency exceeds this value.")
    parser.add_argument("--fail-ms", type=float, default=2000.0, help="Fail when endpoint max latency exceeds this value.")
    parser.add_argument(
        "--require-data",
        action="store_true",
        help="Fail when there is no competition data to benchmark scoped endpoints.",
    )
    return parser.parse_args(argv)


def call_wsgi(path: str, query: dict[str, str] | None = None) -> tuple[str, dict[str, str], bytes, float]:
    captured: dict[str, object] = {}

    def start_response(status: str, headers: list[tuple[str, str]], exc_info=None):
        captured["status"] = status
        captured["headers"] = dict(headers)

    environ = {
        "REQUEST_METHOD": "GET",
        "PATH_INFO": path,
        "QUERY_STRING": urlencode(query or {}),
        "REMOTE_ADDR": "127.0.0.1",
        "HTTP_USER_AGENT": "miniprogram-api-benchmark",
        "HTTP_COOKIE": "",
        "wsgi.input": io.BytesIO(b""),
        "CONTENT_LENGTH": "0",
        "CONTENT_TYPE": "application/x-www-form-urlencoded",
    }
    started_at = time.perf_counter()
    body = b"".join(app(environ, start_response))
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    return str(captured.get("status") or ""), captured.get("headers") or {}, body, elapsed_ms


def api_get_json(path: str, query: dict[str, str] | None = None) -> dict:
    status, _headers, body, _elapsed_ms = call_wsgi(path, query)
    if not status.startswith("200"):
        raise ApiBenchmarkError(f"{path} 返回异常状态：{status}；{body[:200].decode('utf-8', errors='replace')}")
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError as exc:
        raise ApiBenchmarkError(f"{path} 返回不是 JSON：{exc}") from exc
    if not isinstance(payload, dict):
        raise ApiBenchmarkError(f"{path} 返回 JSON 顶层不是对象")
    return payload


def benchmark_endpoint(name: str, path: str, query: dict[str, str], runs: int, warmup_runs: int) -> ApiTiming:
    for _index in range(max(0, warmup_runs)):
        status, _headers, body, _elapsed_ms = call_wsgi(path, query)
        if not status.startswith("200"):
            raise ApiBenchmarkError(f"{name} 预热返回异常状态：{status}；{body[:200].decode('utf-8', errors='replace')}")
    runs_ms: list[float] = []
    status = ""
    bytes_count = 0
    for _index in range(max(1, runs)):
        status, _headers, body, elapsed_ms = call_wsgi(path, query)
        if not status.startswith("200"):
            raise ApiBenchmarkError(f"{name} 返回异常状态：{status}；{body[:200].decode('utf-8', errors='replace')}")
        runs_ms.append(elapsed_ms)
        bytes_count = len(body)
    return ApiTiming(name=name, path=path, status=status, runs_ms=runs_ms, bytes_count=bytes_count)


def build_scope() -> dict[str, str] | None:
    competitions = api_get_json("/api/competitions")
    cards = competitions.get("cards") if isinstance(competitions.get("cards"), list) else []
    if not cards:
        return None
    first_card = cards[0] if isinstance(cards[0], dict) else {}
    competition_name = str(first_card.get("competition_name") or "").strip()
    if not competition_name:
        return None
    seasons = first_card.get("seasons") if isinstance(first_card.get("seasons"), list) else []
    scope = {
        "competition": competition_name,
        "season": str(seasons[0] if seasons else ""),
        "region": str(first_card.get("region_name") or ""),
    }
    return {key: value for key, value in scope.items() if value}


def build_benchmark_targets(scope: dict[str, str] | None) -> list[tuple[str, str, dict[str, str]]]:
    targets: list[tuple[str, str, dict[str, str]]] = [
        ("赛事入口", "/api/competitions", {}),
    ]
    if not scope:
        return targets
    dashboard = api_get_json("/api/dashboard", scope)
    targets.extend(
        [
            ("赛事首页", "/api/dashboard", scope),
            ("选手分页", "/api/players", {**scope, "limit": "30", "offset": "0"}),
            ("门派列表", "/api/guilds", scope),
            ("胜率预测", "/api/predictions", {**scope, "limit": "30", "offset": "0"}),
        ]
    )
    match_days = dashboard.get("match_days") if isinstance(dashboard.get("match_days"), list) else []
    if match_days:
        played_on = str((match_days[0] or {}).get("played_on") or "").strip()
        if played_on:
            targets.append(("比赛日详情", f"/api/days/{played_on}", scope))
    players = api_get_json("/api/players", {**scope, "limit": "1", "offset": "0"})
    player_rows = players.get("players") if isinstance(players.get("players"), list) else []
    if player_rows:
        player_id = str((player_rows[0] or {}).get("player_id") or "").strip()
        if player_id:
            targets.append(("选手详情", f"/api/players/{player_id}", scope))
    guilds = api_get_json("/api/guilds", scope)
    guild_rows = guilds.get("cards") if isinstance(guilds.get("cards"), list) else []
    if guild_rows:
        guild_id = str((guild_rows[0] or {}).get("guild_id") or "").strip()
        if guild_id:
            targets.append(("门派详情", f"/api/guilds/{guild_id}", scope))
    return targets


def run_benchmark(
    *,
    runs: int = 3,
    warmup_runs: int = 1,
    warn_ms: float = 800.0,
    fail_ms: float = 2000.0,
    require_data: bool = False,
) -> list[ApiTiming]:
    scope = build_scope()
    if not scope and require_data:
        raise ApiBenchmarkError("当前没有赛事数据，无法对小程序赛事内接口做基准测试。")
    if not scope:
        print("[SKIP] 小程序深度接口基准：当前没有赛事数据，只测试赛事入口。")
    timings = [
        benchmark_endpoint(name, path, query, runs, warmup_runs)
        for name, path, query in build_benchmark_targets(scope)
    ]
    slow = [timing for timing in timings if timing.max_ms > fail_ms]
    if slow:
        detail = "；".join(f"{item.name} max={item.max_ms:.1f}ms" for item in slow)
        raise ApiBenchmarkError(f"小程序接口耗时超过失败阈值 {fail_ms:.0f}ms：{detail}")
    warned = [timing for timing in timings if timing.max_ms > warn_ms]
    for timing in warned:
        print(f"[WARN] {timing.name} max={timing.max_ms:.1f}ms，超过提醒阈值 {warn_ms:.0f}ms。")
    return timings


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = runtime_database_summary()
    print("小程序接口基准测试：")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    try:
        timings = run_benchmark(
            runs=args.runs,
            warmup_runs=args.warmup_runs,
            warn_ms=args.warn_ms,
            fail_ms=args.fail_ms,
            require_data=args.require_data,
        )
    except ApiBenchmarkError as exc:
        print(f"基准测试未通过：{exc}", file=sys.stderr)
        return 1
    print("接口耗时：")
    for timing in timings:
        print(
            f"- {timing.name}: avg={timing.average_ms:.1f}ms, "
            f"max={timing.max_ms:.1f}ms, size={timing.bytes_count}B, path={timing.path}"
        )
    print("基准测试通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
