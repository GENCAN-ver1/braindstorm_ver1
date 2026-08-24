from __future__ import annotations

import http.client
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

from web_host.server import MAX_REQUEST_BYTES, make_handler


class FakeService:
    def __init__(self) -> None:
        self.create_calls = 0

    def create_session(self, request):
        self.create_calls += 1
        return {
            "id": "session-0123456789abcdef0123456789abcdef",
            "revision": 0,
            "mode": request["mode"],
            "governorStatus": "NEEDS_INPUT",
            "frames": request["frames"],
            "stages": [],
            "review": None,
        }

    def get_session(self, _session_id):
        raise RuntimeError("canary-internal-stack")


class WebHostServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.service = FakeService()
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0),
            make_handler(cls.service, Path.cwd() / "web" / "dist"),
        )
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def _request(self, method: str, path: str, *, body: bytes | None = None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        result = response.status, dict(response.getheaders()), payload
        connection.close()
        return result

    def test_health_is_same_origin_and_hardened(self) -> None:
        status, headers, payload = self._request("GET", "/api/v1/health")
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(payload)["model"], "deepseek-v4-pro")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(headers["X-Frame-Options"], "DENY")
        self.assertIn("connect-src 'self'", headers["Content-Security-Policy"])

    def test_cross_origin_mutation_is_rejected_before_service(self) -> None:
        before = self.service.create_calls
        status, _headers, payload = self._request(
            "POST",
            "/api/v1/sessions",
            body=b"{}",
            headers={"Content-Type": "application/json", "Origin": "https://evil.example"},
        )
        self.assertEqual(status, 403)
        self.assertEqual(json.loads(payload)["code"], "FORBIDDEN")
        self.assertEqual(self.service.create_calls, before)

    def test_content_type_and_body_size_are_bounded(self) -> None:
        status, _headers, payload = self._request(
            "POST", "/api/v1/sessions", body=b"{}", headers={"Content-Type": "text/plain"}
        )
        self.assertEqual(status, 400)
        self.assertIn("Content-Type", json.loads(payload)["message"])

        status, _headers, payload = self._request(
            "POST",
            "/api/v1/sessions",
            body=b"x" * (MAX_REQUEST_BYTES + 1),
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertIn("size limit", json.loads(payload)["message"])

    def test_unhandled_errors_do_not_expose_stack_or_paths(self) -> None:
        session_id = "session-0123456789abcdef0123456789abcdef"
        status, _headers, payload = self._request("GET", f"/api/v1/sessions/{session_id}")
        text = payload.decode("utf-8")
        self.assertEqual(status, 500)
        self.assertNotIn("canary-internal-stack", text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn(str(Path.cwd()), text)


if __name__ == "__main__":
    unittest.main()
