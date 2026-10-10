"""Local same-origin HTTP host for the built Brainstorm web application."""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import threading
import time
from collections import defaultdict, deque
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence
from urllib.parse import unquote, urlsplit

PROJECT_ROOT = Path(__file__).parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from web_host.service import BrainstormService, ServiceError


DEFAULT_WEB_ROOT = PROJECT_ROOT / "web" / "dist"
DEFAULT_SESSION_ROOT = PROJECT_ROOT / "var" / "web-host" / "sessions"
MAX_REQUEST_BYTES = 64 * 1024
RATE_LIMIT_REQUESTS = 120
RATE_LIMIT_WINDOW_SECONDS = 60


class _RateLimiter:
    def __init__(self) -> None:
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allow(self, identity: str, *, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        cutoff = current - RATE_LIMIT_WINDOW_SECONDS
        with self._lock:
            entries = self._entries[identity]
            while entries and entries[0] <= cutoff:
                entries.popleft()
            if len(entries) >= RATE_LIMIT_REQUESTS:
                return False
            entries.append(current)
            return True


def make_handler(
    service: BrainstormService,
    web_root: Path,
    *,
    allowed_port: int | None = None,
) -> type[BaseHTTPRequestHandler]:
    limiter = _RateLimiter()
    resolved_web_root = web_root.resolve()

    class BrainstormRequestHandler(BaseHTTPRequestHandler):
        server_version = "BrainstormHost/1"
        sys_version = ""

        def log_message(self, _format: str, *_args: Any) -> None:
            # Do not log paths, request bodies, headers, or provider errors.
            return

        def do_GET(self) -> None:
            if not self._authorize_request():
                return
            path = urlsplit(self.path).path
            if path == "/api/v1/health":
                self._json(HTTPStatus.OK, {"status": "ok", "provider": "deepseek", "model": "deepseek-v4-pro"})
                return
            segments = _api_segments(path)
            if len(segments) == 2 and segments[0] == "sessions":
                self._service_call(lambda: service.get_session(segments[1]))
                return
            if len(segments) == 3 and segments[0] == "sessions" and segments[2] == "handoff":
                self._service_call(lambda: service.get_handoff(segments[1]))
                return
            if path.startswith("/api/"):
                self._json(HTTPStatus.NOT_FOUND, _error("VALIDATION_FAILURE", "API route not found."))
                return
            self._static(path)

        def do_POST(self) -> None:
            self._mutating_request("POST")

        def do_PUT(self) -> None:
            self._mutating_request("PUT")

        def _mutating_request(self, method: str) -> None:
            if not self._authorize_request(require_origin=True):
                return
            try:
                body = self._read_json()
            except ServiceError as exc:
                self._service_error(exc)
                return
            path = urlsplit(self.path).path
            segments = _api_segments(path)
            if method == "POST" and segments == ["sessions"]:
                self._service_call(lambda: service.create_session(body), status=HTTPStatus.CREATED)
                return
            if len(segments) != 3 or segments[0] != "sessions":
                self._json(HTTPStatus.NOT_FOUND, _error("VALIDATION_FAILURE", "API route not found."))
                return
            session_id, action = segments[1], segments[2]
            revision = body.get("revision")
            routes: dict[tuple[str, str], Callable[[], Any]] = {
                ("PUT", "frames"): lambda: service.save_frames(session_id, revision, body.get("frames")),
                ("POST", "run"): lambda: service.start_run(session_id, revision),
                ("POST", "resume"): lambda: service.resume_run(session_id, revision, body.get("input")),
                ("POST", "capabilities"): lambda: service.configure_capabilities(session_id, revision, body.get("request")),
                ("POST", "human-gate"): lambda: service.submit_human_gate(session_id, revision, body.get("decision")),
            }
            action_call = routes.get((method, action))
            if action_call is None:
                self._json(HTTPStatus.NOT_FOUND, _error("VALIDATION_FAILURE", "API route not found."))
                return
            self._service_call(action_call)

        def _authorize_request(self, *, require_origin: bool = False) -> bool:
            port = allowed_port or getattr(self.server, "server_port", 0)
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            host = self.headers.get("Host", "")
            if host not in allowed_hosts:
                self._json(HTTPStatus.FORBIDDEN, _error("FORBIDDEN", "Host is not allowed."))
                return False
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://{item}" for item in allowed_hosts}:
                self._json(HTTPStatus.FORBIDDEN, _error("FORBIDDEN", "Origin is not allowed."))
                return False
            if require_origin and origin is not None and origin != f"http://{host}":
                self._json(HTTPStatus.FORBIDDEN, _error("FORBIDDEN", "Origin does not match Host."))
                return False
            identity = self.client_address[0] if self.client_address else "unknown"
            if not limiter.allow(identity):
                self._json(HTTPStatus.TOO_MANY_REQUESTS, _error("PROVIDER_FAILURE", "Request rate limit exceeded.", retryable=True))
                return False
            return True

        def _read_json(self) -> Mapping[str, Any]:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
            if content_type != "application/json":
                raise ServiceError("VALIDATION_FAILURE", "Content-Type must be application/json.")
            try:
                length = int(self.headers.get("Content-Length", ""))
            except ValueError:
                raise ServiceError("VALIDATION_FAILURE", "Content-Length is invalid.") from None
            if not 0 <= length <= MAX_REQUEST_BYTES:
                # Closing with unread TCP data can discard the error response on Windows.
                # Drain only a bounded prefix; never accept or parse an oversized body.
                if length > MAX_REQUEST_BYTES:
                    previous_timeout = self.connection.gettimeout()
                    self.connection.settimeout(0.25)
                    try:
                        remaining = min(length, MAX_REQUEST_BYTES + 1)
                        while remaining:
                            chunk = self.rfile.read(min(remaining, 8192))
                            if not chunk:
                                break
                            remaining -= len(chunk)
                    except OSError:
                        pass
                    finally:
                        self.connection.settimeout(previous_timeout)
                raise ServiceError("VALIDATION_FAILURE", "Request body exceeds the size limit.")
            raw = self.rfile.read(length)
            try:
                value = json.loads(raw.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError):
                raise ServiceError("VALIDATION_FAILURE", "Request body is invalid JSON.") from None
            if not isinstance(value, Mapping):
                raise ServiceError("VALIDATION_FAILURE", "Request body must be a JSON object.")
            return value

        def _service_call(self, operation: Callable[[], Any], *, status: HTTPStatus = HTTPStatus.OK) -> None:
            try:
                self._json(status, operation())
            except ServiceError as exc:
                self._service_error(exc)
            except Exception:
                self._json(HTTPStatus.INTERNAL_SERVER_ERROR, _error("PROVIDER_FAILURE", "The host could not complete the request.", retryable=True))

        def _service_error(self, exc: ServiceError) -> None:
            status = {
                "REVISION_CONFLICT": HTTPStatus.CONFLICT,
                "FORBIDDEN": HTTPStatus.FORBIDDEN,
                "UNAUTHORIZED": HTTPStatus.UNAUTHORIZED,
                "VALIDATION_FAILURE": HTTPStatus.BAD_REQUEST,
                "PROVIDER_FAILURE": HTTPStatus.BAD_GATEWAY,
            }.get(exc.code, HTTPStatus.INTERNAL_SERVER_ERROR)
            self._json(status, exc.to_dict())

        def _json(self, status: HTTPStatus, value: Any) -> None:
            payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
            self.send_response(status.value)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _static(self, path: str) -> None:
            if not resolved_web_root.is_dir():
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, _error("PROVIDER_FAILURE", "Web build is unavailable."))
                return
            relative = unquote(path).lstrip("/") or "index.html"
            candidate = (resolved_web_root / relative).resolve()
            if candidate != resolved_web_root and resolved_web_root not in candidate.parents:
                self._json(HTTPStatus.NOT_FOUND, _error("VALIDATION_FAILURE", "Asset not found."))
                return
            if not candidate.is_file():
                candidate = resolved_web_root / "index.html"
            try:
                payload = candidate.read_bytes()
            except OSError:
                self._json(HTTPStatus.NOT_FOUND, _error("VALIDATION_FAILURE", "Asset not found."))
                return
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            self.send_response(HTTPStatus.OK.value)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self._security_headers()
            self.end_headers()
            self.wfile.write(payload)

        def _security_headers(self) -> None:
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
            self.send_header("Cross-Origin-Opener-Policy", "same-origin")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")

    return BrainstormRequestHandler


def _api_segments(path: str) -> list[str]:
    prefix = "/api/v1/"
    if path == "/api/v1":
        return []
    if not path.startswith(prefix):
        return []
    return [segment for segment in path[len(prefix):].split("/") if segment]


def _error(code: str, message: str, *, retryable: bool = False) -> dict[str, Any]:
    return {"code": code, "message": message, "retryable": retryable}


def serve(*, host: str, port: int, web_root: Path, session_root: Path) -> None:
    if host not in {"127.0.0.1", "localhost"}:
        raise ValueError("host must be local")
    service = BrainstormService(session_root)
    server = ThreadingHTTPServer((host, port), make_handler(service, web_root, allowed_port=port))
    print(f"Brainstorm host listening on http://{host}:{port} (DeepSeek deepseek-v4-pro)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", choices=("127.0.0.1", "localhost"))
    parser.add_argument("--port", type=int, default=4173)
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    parser.add_argument("--session-root", type=Path, default=DEFAULT_SESSION_ROOT)
    args = parser.parse_args(argv)
    if not 1024 <= args.port <= 65535:
        parser.error("--port must be between 1024 and 65535")
    serve(host=args.host, port=args.port, web_root=args.web_root, session_root=args.session_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
