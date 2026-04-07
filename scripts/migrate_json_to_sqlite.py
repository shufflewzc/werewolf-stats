#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from sqlite_store import (
    DB_PATH,
    connect_db,
    create_schema,
    replace_repository_data,
)


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
TEAMS_JSON_PATH = DATA_DIR / "teams.json"
PLAYERS_JSON_PATH = DATA_DIR / "players.json"
MATCHES_JSON_PATH = DATA_DIR / "matches.json"
USERS_JSON_PATH = DATA_DIR / "users.json"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    try:
        teams = read_json(TEAMS_JSON_PATH)
        players = read_json(PLAYERS_JSON_PATH)
        matches = read_json(MATCHES_JSON_PATH)
        users = read_json(USERS_JSON_PATH)
    except FileNotFoundError as exc:
        print(f"迁移失败，缺少文件：{exc.filename}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"迁移失败，JSON 格式错误：{exc}", file=sys.stderr)
        return 1

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        create_schema(connection)
        replace_repository_data(
            connection,
            teams=teams,
            players=players,
            matches=matches,
            users=users,
        )

    print("JSON 数据已迁移到 SQLite：")
    print(f"- {DB_PATH}")
    print(f"- 战队 {len(teams)} 条")
    print(f"- 队员 {len(players)} 条")
    print(f"- 比赛 {len(matches)} 条")
    print(f"- 账号 {len(users)} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
