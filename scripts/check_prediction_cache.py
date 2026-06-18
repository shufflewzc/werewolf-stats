#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import benchmark_miniprogram_api
import web_app
from db_runtime import runtime_database_summary
from web.features.match_page import load_manual_score_predictions, save_manual_score_predictions


class PredictionCacheCheckError(RuntimeError):
    pass


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check prediction API cache hit and invalidation behavior.")
    parser.add_argument(
        "--require-data",
        action="store_true",
        help="Fail when there is no competition data to exercise the prediction cache.",
    )
    return parser.parse_args(argv)


def prediction_query(scope: dict[str, str]) -> dict[str, str]:
    return {**scope, "limit": "1", "offset": "0"}


def get_prediction_cache_hit(scope: dict[str, str]) -> bool:
    payload = benchmark_miniprogram_api.api_get_json("/api/predictions", prediction_query(scope))
    cache = payload.get("cache") if isinstance(payload.get("cache"), dict) else {}
    if "hit" not in cache:
        raise PredictionCacheCheckError("/api/predictions 缺少 cache.hit 字段")
    return bool(cache.get("hit"))


def assert_cache_hit(scope: dict[str, str], expected: bool, label: str) -> None:
    actual = get_prediction_cache_hit(scope)
    if actual != expected:
        raise PredictionCacheCheckError(
            f"{label} 缓存状态异常：期望 hit={expected}，实际 hit={actual}"
        )


def run_check(*, require_data: bool = False) -> None:
    scope = benchmark_miniprogram_api.build_scope()
    if not scope:
        if require_data:
            raise PredictionCacheCheckError("当前没有赛事数据，无法检查预测缓存一致性。")
        print("[SKIP] 预测缓存一致性：当前没有赛事数据。")
        return

    web_app.invalidate_prediction_api_cache()
    assert_cache_hit(scope, False, "首次请求")
    assert_cache_hit(scope, True, "重复请求")

    web_app.invalidate_validated_data_cache()
    assert_cache_hit(scope, False, "数据缓存失效后")
    assert_cache_hit(scope, True, "数据缓存失效后重复请求")

    current_settings = web_app.load_prediction_model_settings()
    web_app.save_prediction_model_settings(current_settings)
    assert_cache_hit(scope, False, "预测模型保存后")
    assert_cache_hit(scope, True, "预测模型保存后重复请求")

    current_manual = load_manual_score_predictions()
    save_manual_score_predictions(current_manual)
    assert_cache_hit(scope, False, "手动预测保存后")
    assert_cache_hit(scope, True, "手动预测保存后重复请求")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    summary = runtime_database_summary()
    print("预测缓存一致性检查：")
    print(f"- backend: {summary['backend']}")
    print(f"- database: {summary['database']}")
    try:
        run_check(require_data=args.require_data)
    except PredictionCacheCheckError as exc:
        print(f"检查未通过：{exc}", file=sys.stderr)
        return 1
    print("预测缓存一致性检查通过。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
