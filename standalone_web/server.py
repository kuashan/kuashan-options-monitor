"""Read-only loopback dashboard for Options Monitor.

No order submission, strategy execution, configuration writes or public listener.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import parse_qs, urlsplit

REPO_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/styles.css": ("styles.css", "text/css; charset=utf-8"),
}
VALID_VIEWS = frozenset(("status", "brief", "positions", "performance"))
ACCOUNT_PATTERN = re.compile(r"^[a-z0-9_-]{1,48}$")
MAX_OUTPUT_BYTES = 3 * 1024 * 1024
TOOL_TIMEOUT_SECONDS = 25


def make_tool_request(view: str, query: dict[str, list[str]]) -> tuple[str, dict]:
    """Construct one fixed allowlisted, non-mutating Tool Gateway request."""
    if view not in VALID_VIEWS:
        raise ValueError("Unknown read view")
    if set(query) - {"market", "account", "period"}:
        raise ValueError("Unsupported query parameter")
    if any(len(values) != 1 for values in query.values()):
        raise ValueError("Only one value is allowed per parameter")
    market = query.get("market", ["us"])[0]
    account = query.get("account", [""])[0].strip().lower()
    period = query.get("period", ["mtd"])[0]
    if market not in ("us", "hk"):
        raise ValueError("market must be us or hk")
    if account and not ACCOUNT_PATTERN.fullmatch(account):
        raise ValueError("Invalid account label")
    if period not in ("mtd", "ytd"):
        raise ValueError("period must be mtd or ytd")
    if view == "status":
        return "runtime_status", {"config_key": market}
    if view == "brief":
        result = {"market": market.upper()}
        if account:
            result["account"] = account
        return "daily_decision_brief_read", result
    if view == "positions":
        result = {"config_key": market, "action": "list", "status": "open"}
        if account:
            result["account"] = account
        return "option_positions_read", result
    result = {"config_key": market, "period": period, "include_rows": False}
    if account:
        result["account"] = account
    return "option_performance_report", result


def invoke_tool(tool: str, payload: dict) -> dict:
    """Run only a tool provided by the fixed mapping above."""
    safe_env = os.environ.copy()
    safe_env["OM_AGENT_ENABLE_WRITE_TOOLS"] = "false"
    proc = subprocess.run(
        [str(REPO_ROOT / "om-agent"), "run", "--tool", tool,
         "--input-json", json.dumps(payload, ensure_ascii=False)],
        cwd=REPO_ROOT,
        env=safe_env,
        capture_output=True,
        text=True,
        timeout=TOOL_TIMEOUT_SECONDS,
        check=False,
    )
    if len(proc.stdout.encode("utf-8")) > MAX_OUTPUT_BYTES:
        raise RuntimeError("Tool response is too large")
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("Tool response is not valid JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Tool response shape is invalid")
    return result


class Handler(BaseHTTPRequestHandler):
    server_version = "OptionsMonitorWeb/0.1"

    def _reply(self, status: int, content: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self'; style-src 'self'; "
            "connect-src 'self'; img-src 'self'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'none'",
        )
        self.end_headers()
        self.wfile.write(content)

    def _json(self, status: int, value: dict) -> None:
        encoded = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
        self._reply(status, encoded, "application/json; charset=utf-8")

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlsplit(self.path)
        if parsed.path == "/api/v1/health":
            self._json(200, {"ok": True, "service": "options-monitor-web", "mode": "read-only"})
            return
        if parsed.path.startswith("/api/v1/"):
            view = parsed.path.removeprefix("/api/v1/")
            try:
                tool, payload = make_tool_request(view, parse_qs(parsed.query))
                envelope = invoke_tool(tool, payload)
            except ValueError as exc:
                self._json(400, {"ok": False, "error": str(exc)})
                return
            except (RuntimeError, OSError, subprocess.TimeoutExpired) as exc:
                self._json(503, {"ok": False, "error": "Tool gateway unavailable", "reason": type(exc).__name__})
                return
            self._json(200, {
                "ok": bool(envelope.get("ok")),
                "view": view,
                "market": payload.get("market", payload.get("config_key", "us")),
                "observed_at": datetime.now(timezone.utc).isoformat(),
                "data": envelope.get("data"),
                "warnings": envelope.get("warnings") or [],
                "error": envelope.get("error"),
            })
            return
        static = STATIC_FILES.get(parsed.path)
        if static is None:
            self._json(404, {"ok": False, "error": "Not found"})
            return
        file_name, content_type = static
        try:
            contents = (STATIC_DIR / file_name).read_bytes()
        except OSError:
            self._json(500, {"ok": False, "error": "Static asset missing"})
            return
        self._reply(200, contents, content_type)


def main() -> None:
    parser = argparse.ArgumentParser(description="Independent read-only Options Monitor Web UI")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if not (1024 <= args.port <= 65535):
        parser.error("port must be between 1024 and 65535")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"Options Monitor Web: http://127.0.0.1:{args.port} (read-only, loopback only)", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
