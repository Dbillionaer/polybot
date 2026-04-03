import json
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from ui.operator_server import OperatorControlSurface


class StubController:
    def __init__(self):
        self.start_calls = []
        self.stop_calls = 0
        self.cancel_calls = 0
        self.pause_calls = []
        self.resume_calls = 0

    def get_status_snapshot(self):
        return {"mode": "DRY_RUN", "ok": True}

    def cancel_all_open_orders(self):
        self.cancel_calls += 1
        return {"success": True, "message": "Canceled all open orders."}

    def start_fill_reconciliation(self, poll_interval_seconds: float = 2.0):
        self.start_calls.append(poll_interval_seconds)
        return {"success": True, "message": "Started fill reconciliation."}

    def stop_fill_reconciliation(self):
        self.stop_calls += 1
        return {"success": True, "message": "Stopped fill reconciliation."}

    def pause_trading(self, reason: str = ""):
        self.pause_calls.append(reason)
        return {"success": True, "message": "Trading paused."}

    def resume_trading(self):
        self.resume_calls += 1
        return {"success": True, "message": "Trading resumed."}


class TestOperatorControlSurface:
    def setup_method(self):
        self.controller = StubController()
        self.surface = OperatorControlSurface(
            self.controller,
            host="127.0.0.1",
            port=0,
            operator_token="secret-token",
        )
        self.surface.start()
        self.base_url = f"http://127.0.0.1:{self.surface.port}"

    def teardown_method(self):
        self.surface.stop()

    def test_status_endpoint_returns_json(self):
        response = urlopen(f"{self.base_url}/api/status", timeout=5)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["mode"] == "DRY_RUN"
        assert payload["ok"] is True

    def test_post_actions_require_operator_token(self):
        request = Request(
            f"{self.base_url}/api/actions/cancel-all",
            data=b"{}",
            method="POST",
            headers={"Content-Type": "application/json"},
        )

        try:
            urlopen(request, timeout=5)
            raise AssertionError("Expected HTTPError")
        except HTTPError as exc:
            payload = json.loads(exc.read().decode("utf-8"))
            assert exc.code == 403
            assert payload["success"] is False

    def test_post_actions_work_with_valid_token(self):
        request = Request(
            f"{self.base_url}/api/actions/reconciliation/start",
            data=json.dumps({"poll_interval_seconds": 4.5}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-PolyBot-Operator-Token": "secret-token",
            },
        )
        response = urlopen(request, timeout=5)
        payload = json.loads(response.read().decode("utf-8"))

        assert payload["success"] is True
        assert self.controller.start_calls == [4.5]

    def test_pause_and_resume_actions_work_with_valid_token(self):
        pause_request = Request(
            f"{self.base_url}/api/actions/trading/pause",
            data=json.dumps({"reason": "live-canary hold"}).encode("utf-8"),
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-PolyBot-Operator-Token": "secret-token",
            },
        )
        pause_response = urlopen(pause_request, timeout=5)
        pause_payload = json.loads(pause_response.read().decode("utf-8"))

        resume_request = Request(
            f"{self.base_url}/api/actions/trading/resume",
            data=b"{}",
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-PolyBot-Operator-Token": "secret-token",
            },
        )
        resume_response = urlopen(resume_request, timeout=5)
        resume_payload = json.loads(resume_response.read().decode("utf-8"))

        assert pause_payload["success"] is True
        assert resume_payload["success"] is True
        assert self.controller.pause_calls == ["live-canary hold"]
        assert self.controller.resume_calls == 1
