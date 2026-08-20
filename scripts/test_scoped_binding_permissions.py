from __future__ import annotations

from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import web_app
from web.features import bindings


SCOPE_A = "深圳市::league-a"
SCOPE_B = "北京市::league-b"
COMPETITION_SCOPE_KEYS = {
    "赛事A": SCOPE_A,
    "赛事B": SCOPE_B,
}


def make_user(
    username: str,
    *,
    scope_keys: tuple[str, ...] = (),
    is_scope_admin: bool = False,
    permissions: tuple[str, ...] = (),
    linked_player_ids: tuple[str, ...] = (),
    role: str = "event_manager",
) -> dict[str, object]:
    return {
        "username": username,
        "display_name": username,
        "role": role,
        "permissions": list(permissions),
        "player_id": None,
        "linked_player_ids": list(linked_player_ids),
        "scope_grants_authoritative": True,
        "scope_grants": [
            {
                "scope_key": scope_key,
                "permissions": [],
                "is_scope_admin": is_scope_admin,
            }
            for scope_key in scope_keys
        ],
    }


def make_context(
    user: dict[str, object],
    *,
    method: str = "GET",
    query: dict[str, list[str]] | None = None,
    form: dict[str, list[str]] | None = None,
) -> web_app.RequestContext:
    return web_app.RequestContext(
        method=method,
        path="/bindings",
        query=query or {},
        form=form or {},
        files={},
        current_user=user,
        now_label="2026-08-20 12:00:00 中国时间",
        session_token="test-session",
    )


class ScopedBindingPermissionTests(unittest.TestCase):
    def setUp(self):
        self.team_a = {
            "team_id": "team-a",
            "name": "战队A",
            "competition_name": "赛事A",
            "season_name": "S1",
            "members": ["player-a", "player-shared"],
            "captain_player_id": "player-a",
        }
        self.team_b = {
            "team_id": "team-b",
            "name": "战队B",
            "competition_name": "赛事B",
            "season_name": "S2",
            "members": ["player-b", "player-shared"],
            "captain_player_id": "player-b",
        }
        self.player_a = {
            "player_id": "player-a",
            "display_name": "选手A",
            "team_id": "team-a",
        }
        self.player_b = {
            "player_id": "player-b",
            "display_name": "选手B",
            "team_id": "team-b",
        }
        self.player_shared = {
            "player_id": "player-shared",
            "display_name": "共享选手",
            "team_id": "team-a",
        }
        self.data = {
            "players": [self.player_a, self.player_b, self.player_shared],
            "teams": [self.team_a, self.team_b],
            "matches": [
                {
                    "match_id": "a-1",
                    "competition_name": "赛事A",
                    "season": "S1",
                    "players": [{"player_id": "player-a"}],
                },
                {
                    "match_id": "b-1",
                    "competition_name": "赛事B",
                    "season": "S2",
                    "players": [
                        {"player_id": "player-b"},
                        {"player_id": "player-shared"},
                    ],
                },
            ],
            "season_player_dimension_stats": [],
        }
        self.scope_admin_a = make_user(
            "scope-admin-a",
            scope_keys=(SCOPE_A,),
            is_scope_admin=True,
        )
        self.scope_admin_ab = make_user(
            "scope-admin-ab",
            scope_keys=(SCOPE_A, SCOPE_B),
            is_scope_admin=True,
        )
        self.target_user = make_user(
            "target",
            linked_player_ids=("player-a", "player-b", "player-shared"),
            role="member",
        )

    def scope_key_for_competition(self, _data, competition_name):
        return COMPETITION_SCOPE_KEYS.get(competition_name, "")

    def scope_patch(self):
        return patch.object(
            web_app,
            "get_competition_scope_key",
            side_effect=self.scope_key_for_competition,
        )

    def test_scope_admin_must_own_every_scope_referencing_player_profile(self):
        with self.scope_patch():
            self.assertTrue(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    self.scope_admin_a,
                    self.player_a,
                )
            )
            self.assertFalse(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    self.scope_admin_a,
                    self.player_b,
                )
            )
            self.assertFalse(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    self.scope_admin_a,
                    self.player_shared,
                )
            )
            self.assertTrue(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    self.scope_admin_ab,
                    self.player_shared,
                )
            )

        scopes = web_app.get_player_binding_scopes(self.data, "player-shared")
        self.assertEqual(
            {
                (scope["competition_name"], scope["season_name"])
                for scope in scopes
            },
            {("赛事A", "S1"), ("赛事B", "S2")},
        )

    def test_scope_resolution_keeps_competition_when_season_name_is_missing(self):
        data = {
            "players": [
                {
                    "player_id": "player-unseasoned",
                    "display_name": "待补赛季选手",
                    "team_id": "",
                }
            ],
            "teams": [],
            "matches": [
                {
                    "match_id": "a-unseasoned",
                    "competition_name": "赛事A",
                    "season": "",
                    "players": [{"player_id": "player-unseasoned"}],
                }
            ],
            "season_player_dimension_stats": [],
        }
        source_player = data["players"][0]

        with self.scope_patch():
            self.assertTrue(
                web_app.can_manage_player_binding_scope(
                    data,
                    self.scope_admin_a,
                    source_player,
                )
            )

        self.assertEqual(
            web_app.get_player_binding_scope_labels(data, "player-unseasoned"),
            ["赛事A / 未命名赛季"],
        )

    def test_self_platform_admin_and_legacy_global_manager_keep_access(self):
        ordinary_user = make_user("ordinary", role="member")
        platform_admin = make_user("admin", role="admin")
        global_manager = make_user(
            "global-binding-manager",
            permissions=("player_binding_manage",),
            role="member",
        )
        with self.scope_patch():
            self.assertTrue(
                web_app.can_manage_player_bindings(
                    self.data,
                    ordinary_user,
                    ordinary_user,
                    self.player_b,
                )
            )
            self.assertTrue(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    platform_admin,
                    self.player_shared,
                )
            )
            self.assertTrue(
                web_app.can_manage_player_binding_scope(
                    self.data,
                    global_manager,
                    self.player_shared,
                )
            )
            self.assertFalse(
                bindings.can_review_binding_requests(
                    self.data,
                    ordinary_user,
                    ordinary_user,
                    self.player_a,
                )
            )

    def test_other_account_page_filters_bound_candidates_and_pending_requests(self):
        users = [self.scope_admin_a, self.target_user]
        requests = [
            {
                "request_id": "request-a",
                "request_type": "player_binding",
                "username": "target",
                "display_name": "目标账号",
                "player_id": "player-a",
                "created_on": "now",
            },
            {
                "request_id": "request-b",
                "request_type": "player_binding",
                "username": "target",
                "display_name": "目标账号",
                "player_id": "player-b",
                "created_on": "now",
            },
            {
                "request_id": "request-shared",
                "request_type": "player_binding",
                "username": "target",
                "display_name": "目标账号",
                "player_id": "player-shared",
                "created_on": "now",
            },
        ]
        candidates = [
            {
                "player_id": player["player_id"],
                "display_name": player["display_name"],
                "team_name": "候选-" + player["player_id"],
                "games_played": 1,
                "scope_labels": player["player_id"],
                "already_bound": False,
                "owner_username": "",
            }
            for player in (self.player_a, self.player_b, self.player_shared)
        ]
        ctx = make_context(
            self.scope_admin_a,
            query={"username": ["target"], "player_id": ["player-a"]},
        )

        with (
            self.scope_patch(),
            patch.object(bindings, "load_validated_data", return_value=self.data),
            patch.object(bindings, "load_users", return_value=users),
            patch.object(bindings, "load_membership_requests", return_value=requests),
            patch.object(bindings, "build_player_binding_candidates", return_value=candidates),
            patch.object(bindings, "build_bound_player_summary", return_value=None) as summary,
            patch.object(bindings, "layout", side_effect=lambda _title, body, _ctx, alert="": alert + body),
        ):
            html = bindings.get_player_bindings_page(ctx)

        self.assertIn("player-a", html)
        self.assertIn("request-a", html)
        self.assertNotIn("player-b", html)
        self.assertNotIn("request-b", html)
        self.assertNotIn("player-shared", html)
        self.assertNotIn("request-shared", html)
        summary_user = summary.call_args.args[1]
        self.assertEqual(summary_user["linked_player_ids"], ["player-a"])

    def test_get_other_account_rejects_cross_scope_selected_player(self):
        ctx = make_context(
            self.scope_admin_a,
            query={"username": ["target"], "player_id": ["player-b"]},
        )
        statuses: list[str] = []
        with (
            self.scope_patch(),
            patch.object(bindings, "load_validated_data", return_value=self.data),
            patch.object(bindings, "get_player_bindings_page") as render_page,
            patch.object(bindings, "layout", side_effect=lambda _title, body, _ctx: body),
        ):
            bindings.handle_player_bindings(
                ctx,
                lambda status, _headers: statuses.append(status),
            )

        self.assertEqual(statuses, ["403 Forbidden"])
        render_page.assert_not_called()

    def test_cross_scope_post_actions_are_rejected_before_any_write(self):
        request_b = {
            "request_id": "request-b",
            "request_type": "player_binding",
            "username": "target",
            "player_id": "player-b",
        }
        users = [self.scope_admin_a, self.target_user]
        cases = (
            (
                "direct_bind_player_id",
                {
                    "action": ["direct_bind_player_id"],
                    "target_username": ["target"],
                    "player_id": ["player-b"],
                },
            ),
            (
                "unbind_player_id",
                {
                    "action": ["unbind_player_id"],
                    "target_username": ["target"],
                    "player_id": ["player-b"],
                },
            ),
            (
                "approve_binding_request",
                {
                    "action": ["approve_binding_request"],
                    "request_id": ["request-b"],
                },
            ),
            (
                "reject_binding_request",
                {
                    "action": ["reject_binding_request"],
                    "request_id": ["request-b"],
                },
            ),
        )
        for action, form in cases:
            with self.subTest(action=action):
                ctx = make_context(self.scope_admin_a, method="POST", form=form)
                statuses: list[str] = []
                with (
                    self.scope_patch(),
                    patch.object(bindings, "load_validated_data", return_value=self.data),
                    patch.object(bindings, "load_users", return_value=users),
                    patch.object(bindings, "load_membership_requests", return_value=[request_b]),
                    patch.object(bindings, "save_repository_state") as save_state,
                    patch.object(bindings, "save_membership_requests") as save_requests,
                    patch.object(bindings, "audit_action") as audit,
                    patch.object(bindings, "layout", side_effect=lambda _title, body, _ctx: body),
                ):
                    bindings.handle_player_bindings(
                        ctx,
                        lambda status, _headers: statuses.append(status),
                    )

                self.assertEqual(statuses, ["403 Forbidden"])
                save_state.assert_not_called()
                save_requests.assert_not_called()
                audit.assert_not_called()

    def test_scope_admin_can_direct_bind_and_approve_in_scope_player(self):
        unbound_target = make_user("unbound-target", role="member")
        users = [self.scope_admin_a, unbound_target]
        request_a = {
            "request_id": "request-a",
            "request_type": "player_binding",
            "username": "unbound-target",
            "player_id": "player-a",
        }
        cases = (
            (
                {
                    "action": ["direct_bind_player_id"],
                    "target_username": ["unbound-target"],
                    "player_id": ["player-a"],
                },
                [],
            ),
            (
                {
                    "action": ["approve_binding_request"],
                    "request_id": ["request-a"],
                },
                [request_a],
            ),
        )
        for form, requests in cases:
            with self.subTest(action=form["action"][0]):
                ctx = make_context(self.scope_admin_a, method="POST", form=form)
                statuses: list[str] = []
                with (
                    self.scope_patch(),
                    patch.object(bindings, "load_validated_data", return_value=self.data),
                    patch.object(bindings, "load_users", return_value=users),
                    patch.object(bindings, "load_membership_requests", return_value=requests),
                    patch.object(bindings, "add_user_linked_player_id", return_value=users) as bind_player,
                    patch.object(bindings, "find_season_binding_conflict", return_value=None),
                    patch.object(bindings, "get_user_by_player_id", return_value=None),
                    patch.object(bindings, "save_repository_state", return_value=[]) as save_state,
                    patch.object(bindings, "save_membership_requests"),
                    patch.object(bindings, "audit_action"),
                    patch.object(bindings, "get_player_bindings_page", return_value="page"),
                ):
                    bindings.handle_player_bindings(
                        ctx,
                        lambda status, _headers: statuses.append(status),
                    )

                self.assertEqual(statuses, ["200 OK"])
                bind_player.assert_called_once_with(
                    users,
                    "unbound-target",
                    "player-a",
                )
                save_state.assert_called_once()

    def test_scope_admin_can_reject_and_unbind_in_scope_player(self):
        request_a = {
            "request_id": "request-a",
            "request_type": "player_binding",
            "username": "target",
            "player_id": "player-a",
        }

        reject_ctx = make_context(
            self.scope_admin_a,
            method="POST",
            form={
                "action": ["reject_binding_request"],
                "request_id": ["request-a"],
            },
        )
        reject_statuses: list[str] = []
        with (
            self.scope_patch(),
            patch.object(bindings, "load_validated_data", return_value=self.data),
            patch.object(
                bindings,
                "load_users",
                return_value=[self.scope_admin_a, self.target_user],
            ),
            patch.object(
                bindings,
                "load_membership_requests",
                return_value=[request_a],
            ),
            patch.object(bindings, "save_membership_requests") as save_requests,
            patch.object(bindings, "audit_action") as audit,
            patch.object(bindings, "get_player_bindings_page", return_value="page"),
        ):
            bindings.handle_player_bindings(
                reject_ctx,
                lambda status, _headers: reject_statuses.append(status),
            )

        self.assertEqual(reject_statuses, ["200 OK"])
        save_requests.assert_called_once_with([])
        audit.assert_called_once()

        unbind_ctx = make_context(
            self.scope_admin_a,
            method="POST",
            form={
                "action": ["unbind_player_id"],
                "target_username": ["target"],
                "player_id": ["player-a"],
            },
        )
        unbind_statuses: list[str] = []
        users = [self.scope_admin_a, self.target_user]
        with (
            self.scope_patch(),
            patch.object(bindings, "load_validated_data", return_value=self.data),
            patch.object(bindings, "load_users", return_value=users),
            patch.object(
                bindings,
                "remove_user_player_binding",
                return_value=users,
            ) as remove_binding,
            patch.object(
                bindings,
                "release_captaincy_for_player",
                return_value=[],
            ),
            patch.object(bindings, "save_repository_state", return_value=[]) as save_state,
            patch.object(bindings, "audit_action") as audit,
            patch.object(bindings, "get_player_bindings_page", return_value="page"),
        ):
            bindings.handle_player_bindings(
                unbind_ctx,
                lambda status, _headers: unbind_statuses.append(status),
            )

        self.assertEqual(unbind_statuses, ["200 OK"])
        remove_binding.assert_called_once_with(users, "target", "player-a")
        save_state.assert_called_once()
        audit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
