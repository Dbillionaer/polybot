"""HTTP admin surface for local PolyBot operator control."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any, cast

from loguru import logger

from ui.operator_page import render_operator_page


class OperatorControlSurface:
    """Serve a minimal HTML + JSON operator surface over HTTP."""

    def __init__(
        self,
        controller,
        *,
        host: str = "127.0.0.1",
        port: int = 8081,
        operator_token: str = "",
        title: str = "PolyBot Operator Console",
    ):
        self.controller = controller
        self.host = host
        self.port = port
        self.operator_token = operator_token
        self.title = title
        self._server: ThreadingHTTPServer | None = None
        self._thread: Thread | None = None

    def start(self) -> None:
        """Start the HTTP server in a daemon thread."""
        if self._server is not None:
            return

        server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        self._server = server
        self.port = server.server_port
        self._thread = Thread(target=server.serve_forever, name="polybot-operator-ui", daemon=True)
        self._thread.start()

        if self.host not in {"127.0.0.1", "localhost", "::1"}:
            logger.warning(
                f"[OperatorUI] Binding to non-loopback host {self.host}. "
                "Keep this surface private and protected."
            )
        logger.info(f"[OperatorUI] Listening on http://{self.host}:{self.port}/")

    def stop(self) -> None:
        """Stop the HTTP server if it is running."""
        server = self._server
        if server is None:
            return

        server.shutdown()
        server.server_close()
        self._server = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("[OperatorUI] Server stopped.")

    def _make_handler(self):
        controller = self.controller
        operator_token = self.operator_token
        title = self.title

        class Handler(BaseHTTPRequestHandler):
            def _write_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _write_html(self, body: str) -> None:
                encoded = body.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)

            def _read_json(self) -> dict[str, Any]:
                content_length = int(self.headers.get("Content-Length", "0") or "0")
                if content_length <= 0:
                    return {}
                raw_body = self.rfile.read(content_length).decode("utf-8")
                if not raw_body.strip():
                    return {}
                parsed = json.loads(raw_body)
                if isinstance(parsed, dict):
                    return cast(dict[str, Any], parsed)
                raise json.JSONDecodeError("Request body must decode to an object", raw_body, 0)

            def _require_operator_token(self) -> bool:
                if not operator_token:
                    self._write_json(
                        {
                            "success": False,
                            "message": "Mutating actions are disabled because OPERATOR_UI_TOKEN is unset.",
                        },
                        status=HTTPStatus.SERVICE_UNAVAILABLE,
                    )
                    return False

                supplied_token = self.headers.get("X-PolyBot-Operator-Token", "")
                if supplied_token != operator_token:
                    self._write_json(
                        {"success": False, "message": "Invalid operator token."},
                        status=HTTPStatus.FORBIDDEN,
                    )
                    return False
                return True

            def do_GET(self) -> None:
                if self.path == "/":
                    self._write_html(render_operator_page(title))
                    return

                if self.path == "/api/status":
                    self._write_json(controller.get_status_snapshot())
                    return

                self._write_json({"success": False, "message": "Not found."}, status=HTTPStatus.NOT_FOUND)

            def do_POST(self) -> None:
                if not self._require_operator_token():
                    return

                try:
                    payload = self._read_json()
                except json.JSONDecodeError:
                    self._write_json(
                        {"success": False, "message": "Request body must be valid JSON."},
                        status=HTTPStatus.BAD_REQUEST,
                    )
                    return

                if self.path == "/api/actions/cancel-all":
                    self._write_json(controller.cancel_all_open_orders())
                    return

                if self.path == "/api/actions/reconciliation/start":
                    interval = float(payload.get("poll_interval_seconds", 2.0))
                    self._write_json(controller.start_fill_reconciliation(interval))
                    return

                if self.path == "/api/actions/reconciliation/stop":
                    self._write_json(controller.stop_fill_reconciliation())
                    return

                if self.path == "/api/actions/trading/pause":
                    reason = str(payload.get("reason", ""))
                    self._write_json(controller.pause_trading(reason))
                    return

                if self.path == "/api/actions/trading/resume":
                    self._write_json(controller.resume_trading())
                    return

                self._write_json({"success": False, "message": "Not found."}, status=HTTPStatus.NOT_FOUND)

            def log_message(self, format: str, *args: object) -> None:  # pylint: disable=redefined-builtin
                del format, args

        return Handler
