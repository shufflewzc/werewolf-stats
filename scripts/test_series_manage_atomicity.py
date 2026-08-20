import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import competition_meta
import sqlite_store
import web_app
from web.features import series_manage


COMPETITION_NAME = "测试联赛"
OLD_SEASON_NAME = "测试联赛S1"
NEW_SEASON_NAME = "测试联赛S2"
SERIES_SLUG = "test-series"


def _start_response_recorder():
    statuses: list[str] = []

    def start_response(status, _headers):
        statuses.append(status)

    return statuses, start_response


class SeriesManageAtomicityTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_db_path = sqlite_store.DB_PATH
        self.previous_database_url = os.environ.pop("DATABASE_URL", None)
        self.previous_postgres_writes = os.environ.pop(
            "ENABLE_POSTGRES_WRITES", None
        )
        self.previous_postgres_reads = os.environ.pop(
            "ENABLE_POSTGRES_READS", None
        )
        sqlite_store.DB_PATH = Path(self.temp_dir.name) / "series-atomicity.db"
        sqlite_store.ensure_database()
        with sqlite_store.connect_db() as connection:
            connection.execute(
                "INSERT INTO app_meta (meta_key, meta_value) VALUES ('initialized', '1')"
            )

        competition_meta.save_series_catalog(
            [
                {
                    "competition_name": COMPETITION_NAME,
                    "region_name": "深圳",
                    "series_name": "测试系列赛",
                    "series_code": "TEST",
                    "series_slug": SERIES_SLUG,
                    "participation_mode": "team",
                    "created_by": "admin",
                    "created_on": "2026-01-01",
                }
            ]
        )
        competition_meta.save_season_catalog(
            [
                {
                    "series_slug": SERIES_SLUG,
                    "series_name": "测试系列赛",
                    "series_code": "TEST",
                    "competition_name": COMPETITION_NAME,
                    "season_name": OLD_SEASON_NAME,
                    "start_at": "2026-01-01T00:00",
                    "end_at": "2026-06-30T23:59",
                    "participation_mode": "inherit",
                    "scoring_rule": {"inherit": True},
                    "season_policy": {"inherit": True},
                    "notes": "原赛季配置",
                    "created_by": "admin",
                    "created_on": "2026-01-01",
                }
            ]
        )
        sqlite_store.save_users(
            [
                {
                    "username": "admin",
                    "display_name": "平台管理员",
                    "password_salt": "salt",
                    "password_hash": "hash",
                    "active": True,
                    "player_id": None,
                    "linked_player_ids": [],
                    "manager_scope_keys": [],
                    "permissions": [],
                    "role": "admin",
                    "account_create": True,
                }
            ]
        )
        data = sqlite_store.load_repository_data()
        data["teams"] = [
            {
                "team_id": "test-team",
                "name": "测试战队",
                "short_name": "测试",
                "logo": "/static/test-team.png",
                "active": True,
                "founded_on": "2026-01-01",
                "competition_name": COMPETITION_NAME,
                "season_name": OLD_SEASON_NAME,
                "guild_id": "",
                "captain_player_id": "test-player",
                "stage_groups": [],
                "members": ["test-player"],
                "notes": "",
            }
        ]
        data["players"] = [
            {
                "player_id": "test-player",
                "display_name": "测试选手",
                "team_id": "test-team",
                "photo": "/static/test-player.png",
                "aliases": [],
                "active": True,
                "is_star_player": False,
                "profile_status": "verified",
                "created_source": "test",
                "joined_on": "2026-01-01",
                "notes": "",
            }
        ]
        data["matches"] = [
            {
                "match_id": "sz-s1-260101-01",
                "competition_name": COMPETITION_NAME,
                "season": OLD_SEASON_NAME,
                "stage": "regular_season",
                "round": 1,
                "game_no": 1,
                "score_model": "standard",
                "scoring_rule": {},
                "exclude_from_team_scores": False,
                "played_on": "2026-01-01",
                "group_label": "",
                "table_label": "A桌",
                "format": "12人标准",
                "duration_minutes": 60,
                "winning_camp": "villagers",
                "mvp_player_id": "test-player",
                "svp_player_id": "",
                "scapegoat_player_id": "",
                "players": [
                    {
                        "player_id": "test-player",
                        "team_id": "test-team",
                        "seat": 1,
                        "role": "预言家",
                        "camp": "villagers",
                        "result": "win",
                        "points_earned": 1.0,
                        "result_points": 1.0,
                        "vote_points": 0.0,
                        "behavior_points": 0.0,
                        "special_points": 0.0,
                        "adjustment_points": 0.0,
                        "score_breakdown": {},
                        "stance_result": "correct",
                        "notes": "",
                    }
                ],
                "notes": "",
            }
        ]
        data["season_player_dimension_stats"] = [
            {
                "competition_name": COMPETITION_NAME,
                "season_name": OLD_SEASON_NAME,
                "played_on": "2026-01-01",
                "player_id": "test-player",
                "team_id": "test-team",
                "seat": 1,
                "metrics": {"发言": 8},
            }
        ]
        data["season_team_dimension_stats"] = [
            {
                "competition_name": COMPETITION_NAME,
                "season_name": OLD_SEASON_NAME,
                "played_on": "2026-01-01",
                "team_id": "test-team",
                "seat": 1,
                "metrics": {"团队": 9},
            }
        ]
        sqlite_store.save_repository_data(data, [])
        sqlite_store.save_membership_requests(
            [
                {
                    "request_id": "request-old-season",
                    "request_type": "team_claim",
                    "username": "admin",
                    "display_name": "平台管理员",
                    "player_id": "",
                    "source_team_id": "",
                    "target_team_id": "test-team",
                    "target_guild_id": "",
                    "scope_competition_name": COMPETITION_NAME,
                    "scope_season_name": OLD_SEASON_NAME,
                    "request_payload": {},
                    "created_on": "2026-01-01 10:00:00 中国时间",
                }
            ]
        )
        web_app.invalidate_validated_data_cache()
        self.admin = next(
            user
            for user in sqlite_store.load_users()
            if user["username"] == "admin"
        )

    def tearDown(self):
        web_app.invalidate_validated_data_cache()
        sqlite_store.DB_PATH = self.previous_db_path
        if self.previous_database_url is not None:
            os.environ["DATABASE_URL"] = self.previous_database_url
        if self.previous_postgres_writes is not None:
            os.environ["ENABLE_POSTGRES_WRITES"] = self.previous_postgres_writes
        if self.previous_postgres_reads is not None:
            os.environ["ENABLE_POSTGRES_READS"] = self.previous_postgres_reads
        self.temp_dir.cleanup()

    def _context(self, form: dict[str, list[str]]) -> web_app.RequestContext:
        return web_app.RequestContext(
            method="POST",
            path="/series-manage",
            query={},
            form=form,
            files={},
            current_user=self.admin,
            now_label="2026-08-20 12:00:00 中国时间",
            request_id="series-atomicity-test",
        )

    def _rename_form(self) -> dict[str, list[str]]:
        return {
            "action": ["save_season"],
            "edit_mode": ["season"],
            "competition_name": [COMPETITION_NAME],
            "original_season_name": [OLD_SEASON_NAME],
            "season_name": [NEW_SEASON_NAME],
            "start_at": ["2026-01-01T00:00"],
            "end_at": ["2026-06-30T23:59"],
            "participation_mode": ["inherit"],
            "season_scoring_inherit": ["1"],
            "season_policy_inherit": ["1"],
            "notes": ["改名后的赛季配置"],
        }

    def _delete_form(self) -> dict[str, list[str]]:
        return {
            "action": ["delete_season"],
            "competition_name": [COMPETITION_NAME],
            "season_name": [OLD_SEASON_NAME],
            "delete_confirmation": ["删除赛季"],
        }

    def _raw_catalogs(self) -> tuple[object, object]:
        return (
            json.loads(
                sqlite_store.load_meta_value(competition_meta.SERIES_CATALOG_META_KEY)
                or "[]"
            ),
            json.loads(
                sqlite_store.load_meta_value(competition_meta.SEASON_CATALOG_META_KEY)
                or "[]"
            ),
        )

    def _repository_projection(self) -> dict[str, object]:
        data = sqlite_store.load_repository_data()
        return {
            "teams": data["teams"],
            "players": data["players"],
            "matches": data["matches"],
            "guilds": data["guilds"],
            "season_player_dimension_stats": data[
                "season_player_dimension_stats"
            ],
            "season_team_dimension_stats": data[
                "season_team_dimension_stats"
            ],
        }

    def test_season_rename_commits_catalog_repository_and_request_once(self):
        before_revision = sqlite_store.get_data_revision()
        statuses, start_response = _start_response_recorder()

        series_manage.handle_series_manage(
            self._context(self._rename_form()), start_response
        )

        self.assertEqual(statuses[-1], "200 OK")
        self.assertEqual(sqlite_store.get_data_revision(), before_revision + 1)
        _, season_catalog = self._raw_catalogs()
        self.assertEqual(
            [entry["season_name"] for entry in season_catalog],
            [NEW_SEASON_NAME],
        )
        repository = self._repository_projection()
        self.assertEqual(repository["teams"][0]["season_name"], NEW_SEASON_NAME)
        self.assertEqual(repository["matches"][0]["season"], NEW_SEASON_NAME)
        self.assertEqual(
            repository["season_player_dimension_stats"][0]["season_name"],
            NEW_SEASON_NAME,
        )
        self.assertEqual(
            repository["season_team_dimension_stats"][0]["season_name"],
            NEW_SEASON_NAME,
        )
        self.assertEqual(
            sqlite_store.load_membership_requests()[0]["scope_season_name"],
            NEW_SEASON_NAME,
        )

    def test_stale_season_rename_rolls_back_catalog_repository_and_request(self):
        before_catalogs = self._raw_catalogs()
        before_repository = self._repository_projection()
        before_requests = sqlite_store.load_membership_requests()
        before_revision = sqlite_store.get_data_revision()
        original_version_scoring_rule = series_manage.version_scoring_rule
        bumped = False

        def race_revision(*args, **kwargs):
            nonlocal bumped
            result = original_version_scoring_rule(*args, **kwargs)
            if not bumped:
                bumped = True
                sqlite_store.bump_data_revision()
            return result

        statuses, start_response = _start_response_recorder()
        with patch.object(
            series_manage, "version_scoring_rule", side_effect=race_revision
        ), patch.object(series_manage, "get_series_manage_page", return_value="page"):
            series_manage.handle_series_manage(
                self._context(self._rename_form()), start_response
            )

        self.assertEqual(statuses[-1], "200 OK")
        self.assertEqual(sqlite_store.get_data_revision(), before_revision + 1)
        self.assertEqual(self._raw_catalogs(), before_catalogs)
        self.assertEqual(self._repository_projection(), before_repository)
        self.assertEqual(sqlite_store.load_membership_requests(), before_requests)

    def test_force_delete_commits_catalog_repository_and_request_once(self):
        before_revision = sqlite_store.get_data_revision()
        statuses, start_response = _start_response_recorder()

        series_manage.handle_series_manage(
            self._context(self._delete_form()), start_response
        )

        self.assertEqual(statuses[-1], "200 OK")
        self.assertEqual(sqlite_store.get_data_revision(), before_revision + 1)
        series_catalog, season_catalog = self._raw_catalogs()
        self.assertEqual(len(series_catalog), 1)
        self.assertEqual(season_catalog, [])
        repository = self._repository_projection()
        self.assertEqual(repository["matches"], [])
        self.assertEqual(repository["teams"][0]["season_name"], OLD_SEASON_NAME)
        self.assertEqual(repository["season_player_dimension_stats"], [])
        self.assertEqual(repository["season_team_dimension_stats"], [])
        self.assertEqual(sqlite_store.load_membership_requests(), [])

    def test_stale_force_delete_rolls_back_catalog_repository_and_request(self):
        before_catalogs = self._raw_catalogs()
        before_repository = self._repository_projection()
        before_requests = sqlite_store.load_membership_requests()
        before_revision = sqlite_store.get_data_revision()
        original_get_series_entry = series_manage.get_series_entry_by_competition
        bumped = False

        def race_revision(*args, **kwargs):
            nonlocal bumped
            result = original_get_series_entry(*args, **kwargs)
            if not bumped:
                bumped = True
                sqlite_store.bump_data_revision()
            return result

        statuses, start_response = _start_response_recorder()
        with patch.object(
            series_manage,
            "get_series_entry_by_competition",
            side_effect=race_revision,
        ), patch.object(series_manage, "get_series_manage_page", return_value="page"):
            series_manage.handle_series_manage(
                self._context(self._delete_form()), start_response
            )

        self.assertEqual(statuses[-1], "200 OK")
        self.assertEqual(sqlite_store.get_data_revision(), before_revision + 1)
        self.assertEqual(self._raw_catalogs(), before_catalogs)
        self.assertEqual(self._repository_projection(), before_repository)
        self.assertEqual(sqlite_store.load_membership_requests(), before_requests)


if __name__ == "__main__":
    unittest.main()
