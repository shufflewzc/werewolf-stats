import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import web_app
from web.features.guilds import build_guild_frontend_page


class GuildCsrfTests(unittest.TestCase):
    def test_frontend_bootstrap_contains_current_session_csrf_token(self):
        session_token = "guild-csrf-test-session"
        ctx = SimpleNamespace(
            current_user={
                "username": "admin",
                "display_name": "Admin",
                "role": "admin",
            },
            query={"view": ["manage"]},
            session_token=session_token,
        )

        body = build_guild_frontend_page(ctx, "guild-test")
        expected_token = web_app.csrf_token_for_session(session_token)

        self.assertIn(json.dumps("csrfToken") + ": " + json.dumps(expected_token), body)
        self.assertIn('/assets/guild-app.js?v=20260722-csrf', body)

    def test_dynamic_management_forms_include_csrf_field(self):
        script_path = Path(__file__).resolve().parents[1] / "assets" / "guild-app.js"
        script = script_path.read_text(encoding="utf-8")

        self.assertIn("bootstrap.csrfToken", script)
        self.assertIn('name="_csrf_token"', script)
        self.assertEqual(script.count("${csrfInput}"), 4)


if __name__ == "__main__":
    unittest.main()
