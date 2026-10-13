"""MCP server: expose every saved flow as a tool any agent can call.

    python3 -m server.mcp_server --flows ./flows --target macos

Speaks the Model Context Protocol over stdio (JSON-RPC). Each saved flow becomes
one tool named flow.<name>; calling it runs the flow and returns the structured
result. This is how a system with no API joins an agent's toolset: teach a flow
once, and it appears as a callable tool. Generic by design -- the flow name and
parameters carry all meaning; the engine knows no domain.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

from engine.flow_api import load_flow, run_flow


def make_adapter(target: str):
    if target == "macos":
        from engine.adapters.macos import MacosAdapter
        return MacosAdapter()
    if target == "fixture":
        from engine.adapters.fixture import FixtureAdapter
        return FixtureAdapter(os.environ.get("UIA_FIXTURE", "tests/gold/ehr_patient_summary.json"))
    raise ValueError(f"unknown target: {target}")


def list_flows(flows_dir: str):
    return [f[:-5] for f in os.listdir(flows_dir) if f.endswith(".json")]


def tools_for(flows_dir: str):
    tools = []
    for name in list_flows(flows_dir):
        tools.append({
            "name": f"flow.{name}",
            "description": f"Run the learned UI flow '{name}' and return its reads.",
            "inputSchema": {"type": "object", "properties": {
                "params": {"type": "object",
                           "description": "values for {{placeholders}} in the flow"}}},
        })
    return tools


def handle(msg, flows_dir, target):
    mid = msg.get("id")
    method = msg.get("method")
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "uia-flows", "version": "0.1.0"}}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": tools_for(flows_dir)}}
    if method == "tools/call":
        params = msg.get("params", {})
        name = params.get("name", "")
        if not name.startswith("flow."):
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": "unknown tool"}}
        flow_name = name[len("flow."):]
        path = os.path.join(flows_dir, flow_name + ".json")
        if not os.path.exists(path):
            return {"jsonrpc": "2.0", "id": mid,
                    "error": {"code": -32602, "message": f"no flow: {flow_name}"}}
        args = params.get("arguments", {}) or {}
        result = run_flow(load_flow(path), make_adapter(target), args.get("params", {}))
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(result.to_dict())}],
            "isError": result.status != "ok"}}
    if method and method.startswith("notifications/"):
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"unknown method: {method}"}}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flows", default="./flows")
    ap.add_argument("--target", default="macos")
    args = ap.parse_args()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        reply = handle(msg, args.flows, args.target)
        if reply is not None:
            sys.stdout.write(json.dumps(reply) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
