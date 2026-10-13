"""Single HTTP API: call any saved flow as an endpoint. Standard library only.

    python3 -m server.http_api --flows ./flows --target macos --port 8077

Then POST /flows/<name> with a JSON body of parameters:

    curl -s localhost:8077/flows/get-record -d '{"id":"123"}'

A system with no API now answers one HTTP call. The engine stays generic: the
flow name maps to a saved flow file; the target maps to an adapter. Healthcare is
just one caller -- a flow named get-record could read any record in any app.
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from engine.flow_api import load_flow, run_flow


def make_adapter(target: str):
    if target == "macos":
        from engine.adapters.macos import MacosAdapter
        return MacosAdapter()
    if target == "fixture":
        from engine.adapters.fixture import FixtureAdapter
        return FixtureAdapter(os.environ.get("UIA_FIXTURE", "tests/gold/ehr_patient_summary.json"))
    raise ValueError(f"unknown target: {target}")


def build_handler(flows_dir: str, target: str):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/flows":
                names = [f[:-5] for f in os.listdir(flows_dir) if f.endswith(".json")]
                return self._send(200, {"flows": names})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self.path.startswith("/flows/"):
                return self._send(404, {"error": "not found"})
            name = self.path[len("/flows/"):]
            path = os.path.join(flows_dir, name + ".json")
            if not os.path.exists(path):
                return self._send(404, {"error": f"no flow: {name}"})
            length = int(self.headers.get("Content-Length", 0) or 0)
            params = {}
            if length:
                try:
                    params = json.loads(self.rfile.read(length).decode() or "{}")
                except json.JSONDecodeError:
                    return self._send(400, {"error": "bad JSON body"})
            result = run_flow(load_flow(path), make_adapter(target), params)
            self._send(200 if result.status == "ok" else 502, result.to_dict())

        def log_message(self, *a):  # quiet
            pass
    return Handler


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default="./flows")
    ap.add_argument("--target", default="macos")
    ap.add_argument("--port", type=int, default=8077)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("127.0.0.1", args.port),
                              build_handler(args.flows, args.target))
    print(f"flow API on http://127.0.0.1:{args.port}  flows={args.flows}  target={args.target}")
    srv.serve_forever()


if __name__ == "__main__":
    main()
