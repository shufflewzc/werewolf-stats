import unittest
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import patch

from web_app import app, handle_privacy_policy


class PrivacyPolicyTests(unittest.TestCase):
    @staticmethod
    def call(method="GET"):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        body = b"".join(handle_privacy_policy(SimpleNamespace(method=method), start_response))
        return captured, body

    def test_serves_public_simplified_chinese_policy(self):
        response, body = self.call()
        page = body.decode("utf-8")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(response["headers"]["Content-Type"], "text/html; charset=utf-8")
        self.assertIn("一颗小草赛事隐私政策", page)
        self.assertIn("cn.metauniverse.werewolfstats", page)
        self.assertIn("不进行跨应用或跨网站跟踪", page)
        self.assertIn("照片图库", page)
        self.assertIn("通常不超过 90 天", page)
        self.assertNotIn("/login?next=", page)

    def test_supports_head_without_response_body(self):
        response, body = self.call("HEAD")

        self.assertEqual(response["status"], "200 OK")
        self.assertEqual(body, b"")
        self.assertGreater(int(response["headers"]["Content-Length"]), 0)

    def test_rejects_writes(self):
        response, _body = self.call("POST")

        self.assertEqual(response["status"], "405 Method Not Allowed")
        self.assertEqual(response["headers"]["Allow"], "GET, HEAD")

    def test_public_route_does_not_redirect_to_login(self):
        captured = {}

        def start_response(status, headers):
            captured["status"] = status
            captured["headers"] = dict(headers)

        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/privacy",
            "QUERY_STRING": "",
            "CONTENT_LENGTH": "0",
            "wsgi.input": BytesIO(b""),
            "REMOTE_ADDR": "127.0.0.1",
        }
        with patch("web_app.enqueue_access_log"):
            body = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual(captured["status"], "200 OK")
        self.assertNotIn("Location", captured["headers"])
        self.assertIn("一颗小草赛事隐私政策", body)


if __name__ == "__main__":
    unittest.main()
