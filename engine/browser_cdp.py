"""DOM browser driver over the Chrome DevTools Protocol (CDP).

The Codex teardown showed it drives DOM-only browser tabs through Playwright
locators, not pixels. This is the open-source equivalent: talk to Chrome's own
DevTools Protocol directly, so we act on the page's real element tree. For a web
EHR this is the most reliable and fastest path -- a click lands on a selector,
not a guessed coordinate, and reads come from the DOM, not from screen pixels.

Standard library only: a minimal WebSocket client (handshake + text frames) over
a raw socket, carrying CDP's JSON-RPC. Launch Chrome once with remote debugging:

    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \\
        --remote-debugging-port=9222 --user-data-dir=/tmp/uia-chrome

Then this connects to http://localhost:9222. No third-party dependency, so it
stays trivially installable for an open-source release.
"""
from __future__ import annotations

import base64
import json
import os
import socket
import struct
import urllib.request
from typing import Optional


class CDPError(Exception):
    pass


def list_tabs(host: str = "localhost", port: int = 9222) -> list:
    """HTTP discovery of open pages (CDP /json endpoint)."""
    with urllib.request.urlopen(f"http://{host}:{port}/json", timeout=5) as r:
        return [t for t in json.loads(r.read().decode()) if t.get("type") == "page"]


class _WS:
    """A minimal text-frame WebSocket client: handshake, send, recv. Stdlib only."""

    def __init__(self, ws_url: str):
        assert ws_url.startswith("ws://")
        rest = ws_url[len("ws://"):]
        hostport, _, path = rest.partition("/")
        host, _, port = hostport.partition(":")
        self.sock = socket.create_connection((host, int(port or 80)), timeout=10)
        key = base64.b64encode(os.urandom(16)).decode()
        req = (f"GET /{path} HTTP/1.1\r\nHost: {hostport}\r\n"
               "Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        resp = self._read_until(b"\r\n\r\n")
        if b"101" not in resp.split(b"\r\n")[0]:
            raise CDPError(f"websocket upgrade failed: {resp[:80]!r}")
        self._buf = b""

    def _read_until(self, marker: bytes) -> bytes:
        data = b""
        while marker not in data:
            chunk = self.sock.recv(4096)
            if not chunk:
                break
            data += chunk
        return data

    def send(self, text: str):
        payload = text.encode()
        header = bytearray([0x81])  # FIN + text opcode
        n = len(payload)
        mask_bit = 0x80
        if n < 126:
            header.append(mask_bit | n)
        elif n < 65536:
            header.append(mask_bit | 126)
            header += struct.pack(">H", n)
        else:
            header.append(mask_bit | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv(self) -> str:
        b1 = self._recv_n(1)[0]
        b2 = self._recv_n(1)[0]
        length = b2 & 0x7F
        if length == 126:
            length = struct.unpack(">H", self._recv_n(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", self._recv_n(8))[0]
        data = self._recv_n(length)
        return data.decode(errors="replace")

    def _recv_n(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise CDPError("websocket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


class CDPSession:
    """One CDP connection to one page. Enough to read and drive the DOM."""

    def __init__(self, ws_url: str):
        self.ws = _WS(ws_url)
        self._id = 0
        self.call("Runtime.enable")
        self.call("DOM.enable")
        self.call("Page.enable")

    def call(self, method: str, params: Optional[dict] = None, timeout_calls: int = 50) -> dict:
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        for _ in range(timeout_calls):
            msg = json.loads(self.ws.recv())
            if msg.get("id") == mid:
                if "error" in msg:
                    raise CDPError(f"{method}: {msg['error']}")
                return msg.get("result", {})
            # otherwise it is an event; keep reading for our reply
        raise CDPError(f"no reply for {method}")

    # --- page operations -----------------------------------------------------
    def navigate(self, url: str):
        self.call("Page.navigate", {"url": url})

    def eval(self, expr: str):
        r = self.call("Runtime.evaluate",
                      {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("value")

    def title(self) -> str:
        return self.eval("document.title")

    def text(self, selector: str) -> Optional[str]:
        js = f"(document.querySelector({json.dumps(selector)})||{{}}).innerText||null"
        return self.eval(js)

    def click(self, selector: str) -> bool:
        js = (f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
              "if(!e)return false;e.click();return true;}})()")
        return bool(self.eval(js))

    def type_into(self, selector: str, value: str) -> bool:
        js = (f"(()=>{{const e=document.querySelector({json.dumps(selector)});"
              f"if(!e)return false;e.focus();e.value={json.dumps(value)};"
              "e.dispatchEvent(new Event('input',{bubbles:true}));return true;}})()")
        return bool(self.eval(js))

    def close(self):
        self.ws.close()


def connect_first_tab(host: str = "localhost", port: int = 9222) -> CDPSession:
    tabs = list_tabs(host, port)
    if not tabs:
        raise CDPError("no open pages; launch Chrome with --remote-debugging-port")
    return CDPSession(tabs[0]["webSocketDebuggerUrl"])
