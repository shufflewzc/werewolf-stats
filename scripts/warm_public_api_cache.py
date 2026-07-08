#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
USER_AGENT = "werewolf-cache-warmer/1.0"


@dataclass
class WarmResult:
    label: str
    path: str
    status: int
    elapsed_ms: float
    bytes_count: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Warm public JSON API cache after a deploy or restart.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Application base URL. Default: http://127.0.0.1:8000")
    parser.add_argument("--rounds", type=int, default=2, help="How many passes to run. Use at least worker count.")
    parser.add_argument("--timeout", type=float, default=20.0, help="Per-request timeout seconds.")
    return parser.parse_args()


def build_url(base_url: str, path: str, query: dict[str, str] | None = None) -> str:
    url = urljoin(base_url.rstrip("/") + "/", path.lstrip("/"))
    if query:
        url += "?" + urlencode(query)
    return url


def fetch_json(base_url: str, path: str, query: dict[str, str] | None, timeout: float) -> tuple[dict, WarmResult]:
    url = build_url(base_url, path, query)
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    started_at = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout) as response:
            body = response.read()
            status = int(response.status)
    except HTTPError as exc:
        body = exc.read()
        status = int(exc.code)
    except URLError as exc:
        raise RuntimeError(f"{path} request failed: {exc}") from exc
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    try:
        payload = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        payload = {}
    return payload if isinstance(payload, dict) else {}, WarmResult(
        label="",
        path=path,
        status=status,
        elapsed_ms=elapsed_ms,
        bytes_count=len(body),
    )


def warm_endpoint(
    base_url: str,
    label: str,
    path: str,
    query: dict[str, str] | None,
    timeout: float,
) -> tuple[dict, WarmResult]:
    payload, result = fetch_json(base_url, path, query, timeout)
    result.label = label
    return payload, result


def first_scope(base_url: str, timeout: float) -> tuple[dict[str, str], list[WarmResult]]:
    competitions, result = warm_endpoint(base_url, "赛事入口", "/api/competitions", None, timeout)
    results = [result]
    cards = competitions.get("cards") if isinstance(competitions.get("cards"), list) else []
    first_card = cards[0] if cards and isinstance(cards[0], dict) else {}
    competition_name = str(first_card.get("competition_name") or "").strip()
    seasons = first_card.get("seasons") if isinstance(first_card.get("seasons"), list) else []
    season_name = str(seasons[0] if seasons else "").strip()
    region_name = str(first_card.get("region_name") or "").strip()
    scope = {
        "competition": competition_name,
        "season": season_name,
        "region": region_name,
    }
    return {key: value for key, value in scope.items() if value}, results


def build_targets(base_url: str, scope: dict[str, str], timeout: float) -> tuple[list[tuple[str, str, dict[str, str] | None]], list[WarmResult]]:
    results: list[WarmResult] = []
    targets: list[tuple[str, str, dict[str, str] | None]] = [
        ("赛事入口", "/api/competitions", None),
    ]
    if not scope:
        return targets, results

    dashboard, dashboard_result = warm_endpoint(base_url, "赛事首页", "/api/dashboard", scope, timeout)
    results.append(dashboard_result)
    targets.extend(
        [
            ("赛事首页", "/api/dashboard", scope),
            ("选手分页", "/api/players", {**scope, "limit": "30", "offset": "0"}),
            ("门派列表", "/api/guilds", scope),
            ("胜率预测", "/api/predictions", {**scope, "limit": "30", "offset": "0"}),
        ]
    )

    days = dashboard.get("match_days") if isinstance(dashboard.get("match_days"), list) else []
    if days:
        played_on = str((days[0] or {}).get("played_on") or "").strip()
        if played_on:
            targets.append(("比赛日详情", f"/api/days/{played_on}", scope))

    players, players_result = warm_endpoint(
        base_url,
        "选手探测",
        "/api/players",
        {**scope, "limit": "1", "offset": "0"},
        timeout,
    )
    results.append(players_result)
    player_rows = players.get("players") if isinstance(players.get("players"), list) else []
    if player_rows:
        player_id = str((player_rows[0] or {}).get("player_id") or "").strip()
        if player_id:
            targets.append(("选手详情", f"/api/players/{player_id}", scope))

    guilds, guilds_result = warm_endpoint(base_url, "门派探测", "/api/guilds", scope, timeout)
    results.append(guilds_result)
    guild_rows = guilds.get("cards") if isinstance(guilds.get("cards"), list) else []
    if guild_rows:
        guild_id = str((guild_rows[0] or {}).get("guild_id") or "").strip()
        if guild_id:
            targets.append(("门派详情", f"/api/guilds/{guild_id}", scope))

    return targets, results


def main() -> int:
    args = parse_args()
    scope, results = first_scope(args.base_url, args.timeout)
    targets, discovery_results = build_targets(args.base_url, scope, args.timeout)
    results.extend(discovery_results)

    for _round in range(max(1, args.rounds)):
        for label, path, query in targets:
            _payload, result = warm_endpoint(args.base_url, label, path, query, args.timeout)
            results.append(result)

    print("公共 API 缓存预热：")
    print(f"- base_url: {args.base_url.rstrip('/')}")
    print(f"- scope: {scope or '未找到赛事数据'}")
    for result in results:
        print(
            f"- {result.label}: HTTP {result.status}, "
            f"{result.elapsed_ms:.1f}ms, size={result.bytes_count}B, path={result.path}"
        )
    failed = [result for result in results if result.status >= 400 or result.status <= 0]
    if failed:
        print("预热未完全成功。")
        return 1
    print("预热完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
