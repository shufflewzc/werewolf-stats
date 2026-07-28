#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json

import web_app
from season_grouping import (
    TARGET_COMPETITION_NAME,
    TARGET_SEASON_NAME,
    apply_placement_assignments,
    build_placement_assignment_preview,
)


CONFIRM_TEXT = "确认京城大师赛S2分组"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="预览或固定写入京城大师赛广州公开赛S2定级赛分组。"
    )
    parser.add_argument("--apply", action="store_true", help="写入分组；默认只预览")
    parser.add_argument("--revision", default="", help="预览输出的排行榜版本")
    parser.add_argument("--confirm", default="", help=f"写入时必须填写：{CONFIRM_TEXT}")
    args = parser.parse_args()

    data = web_app.load_validated_data()
    preview = build_placement_assignment_preview(data)
    print(
        json.dumps(
            {
                "competition_name": TARGET_COMPETITION_NAME,
                "season_name": TARGET_SEASON_NAME,
                "team_count": preview["team_count"],
                "ready": preview["ready"],
                "revision": preview["revision"],
            },
            ensure_ascii=False,
        )
    )
    for row in preview["rows"]:
        print(
            f"{int(row['rank']):02d}\t{row['team_name']}\t"
            f"{float(row['points_total']):.2f}\t"
            f"{row['current_group'] or '-'} -> {row['proposed_group']}"
        )
    if not args.apply:
        return 0 if preview["ready"] else 1
    if args.confirm != CONFIRM_TEXT:
        parser.error(f"--confirm 必须填写：{CONFIRM_TEXT}")
    updated_count, revision = apply_placement_assignments(data, args.revision)
    errors = web_app.save_repository_state(data, web_app.load_users())
    if errors:
        raise RuntimeError("分组保存失败：" + "；".join(errors[:3]))
    ctx = web_app.RequestContext(
        method="CLI",
        path="/scripts/apply_target_season_groups.py",
        query={},
        form={},
        files={},
        current_user={"username": "deployment"},
        now_label=web_app.china_now_label(),
        request_id=f"grouping-{revision[:12]}",
        remote_addr="127.0.0.1",
    )
    web_app.audit_action(
        ctx,
        "season.regular_groups_apply",
        target_type="competition",
        target_id=TARGET_COMPETITION_NAME,
        summary=f"固定写入 {TARGET_COMPETITION_NAME} / {TARGET_SEASON_NAME} 定级赛分组",
        metadata={
            "competition_name": TARGET_COMPETITION_NAME,
            "season_name": TARGET_SEASON_NAME,
            "updated_team_count": updated_count,
            "assignment_revision": revision,
            "source": "deployment_cli",
        },
    )
    print(f"已固定写入 {updated_count} 支战队，revision={revision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
