import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from web_app import APPLE_APP_BUNDLE_ID, APPLE_APP_LINK_PATHS, handle_apple_app_site_association


class AppleAppSiteAssociationTests(unittest.TestCase):
    @staticmethod
    def call(method="GET"):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        body = b"".join(handle_apple_app_site_association(SimpleNamespace(method=method), start_response))
        return captured, body

    @patch.dict("os.environ", {"APPLE_APP_TEAM_ID": "TEAM123456"}, clear=False)
    def test_serves_expected_universal_link_document(self):
        response, body = self.call()
        payload = json.loads(body)
        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["Content-Type"], "application/json")
        details = payload["applinks"]["details"][0]
        self.assertEqual(details["appID"], f"TEAM123456.{APPLE_APP_BUNDLE_ID}")
        self.assertEqual(details["paths"], list(APPLE_APP_LINK_PATHS))

    @patch.dict("os.environ", {}, clear=True)
    def test_missing_team_id_fails_without_cache(self):
        response, body = self.call()
        self.assertEqual(response["status"], "503 Service Unavailable")
        self.assertEqual(response["headers"]["Cache-Control"], "no-store")
        self.assertIn("APPLE_APP_TEAM_ID", json.loads(body)["error"])

    @patch.dict("os.environ", {"APPLE_APP_TEAM_ID": "TEAM123456"}, clear=False)
    def test_rejects_non_get_methods(self):
        response, _body = self.call("POST")
        self.assertEqual(response["status"], "405 Method Not Allowed")
        self.assertEqual(response["headers"]["Allow"], "GET")


if __name__ == "__main__":
    unittest.main()
