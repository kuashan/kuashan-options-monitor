"""Offline tests for the standalone read-only Web adapter."""
import json
import threading
import unittest
from http.server import ThreadingHTTPServer
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from standalone_web.server import Handler, make_tool_request


class RequestMappingTests(unittest.TestCase):
    def test_status(self):
        self.assertEqual(make_tool_request("status", {"market": ["us"]}), ("runtime_status", {"config_key": "us"}))

    def test_brief_account(self):
        self.assertEqual(
            make_tool_request("brief", {"market": ["hk"], "account": ["LX"]}),
            ("daily_decision_brief_read", {"market": "HK", "account": "lx"}),
        )

    def test_positions(self):
        self.assertEqual(
            make_tool_request("positions", {"market": ["us"], "account": ["acct-1"]}),
            ("option_positions_read", {"config_key": "us", "action": "list", "status": "open", "account": "acct-1"}),
        )

    def test_performance(self):
        self.assertEqual(
            make_tool_request("performance", {"period": ["ytd"]}),
            ("option_performance_report", {"config_key": "us", "period": "ytd", "include_rows": False}),
        )

    def test_reject_unknown_or_invalid_parameters(self):
        for view, query in (
            ("trade", {}),
            ("status", {"command": ["sell"]}),
            ("positions", {"account": ["../../etc/passwd"]}),
            ("performance", {"period": ["all"]}),
            ("brief", {"market": ["CN"]}),
            ("status", {"market": ["us", "hk"]}),
        ):
            with self.subTest(view=view, query=query), self.assertRaises(ValueError):
                make_tool_request(view, query)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def test_health(self):
        with urlopen(self.url + "/api/v1/health") as response:
            body = json.load(response)
            self.assertTrue(body["ok"])
            self.assertEqual(body["mode"], "read-only")
            self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_html_and_static_assets(self):
        for path, content_type in (
            ("/", "text/html"),
            ("/styles.css", "text/css"),
            ("/app.js", "text/javascript"),
        ):
            with self.subTest(path=path), urlopen(self.url + path) as response:
                self.assertIn(content_type, response.headers["Content-Type"])
                self.assertGreater(len(response.read()), 100)

    def test_broker_and_ledger_endpoints_disabled(self):
        with patch("standalone_web.server.invoke_tool") as runner:
            for route in ("positions?market=us&account=lx", "brief?market=us&account=lx",
                          "status?market=us", "performance?market=us"):
                with self.subTest(route=route), self.assertRaises(HTTPError) as context:
                    urlopen(self.url + "/api/v1/" + route)
                self.assertEqual(context.exception.code, 403)
            runner.assert_not_called()

    def test_reject_arbitrary_tool_and_bad_param(self):
        for path in ("/api/v1/send_order", "/api/v1/status?cmd=evil"):
            with self.subTest(path=path), self.assertRaises(HTTPError) as context:
                urlopen(self.url + path)
            self.assertEqual(context.exception.code, 403)

    def test_no_post_endpoint(self):
        from urllib.request import Request
        req = Request(self.url + "/api/v1/status", data=b"{}", method="POST")
        with self.assertRaises(HTTPError) as context:
            urlopen(req)
        self.assertEqual(context.exception.code, 501)


if __name__ == "__main__":
    unittest.main()
