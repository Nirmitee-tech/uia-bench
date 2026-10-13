"""Secrets vault: store and inject credentials without putting them in flows.

A flow must never carry a password. The vault keeps named secrets in a local
file, encrypted with a key the operator supplies (env UIA_VAULT_KEY), and injects
them into a step at run time through {{secret:name}} placeholders. The secret
value never appears in the flow file, the audit log, or a trace.

Encryption here is a keyed stream cipher over the standard library (HMAC-SHA256
in counter mode), chosen so the framework keeps its zero-dependency promise. It
protects a secret at rest from casual reading; it is not a substitute for an OS
keychain or a managed secrets service, and the README says so. For production,
point `UIA_VAULT_KEY` at a key delivered by your secrets manager.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
from typing import Optional


def _keystream(key: bytes, nonce: bytes, n: int) -> bytes:
    out = bytearray()
    counter = 0
    while len(out) < n:
        block = hmac.new(key, nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest()
        out.extend(block)
        counter += 1
    return bytes(out[:n])


def _derive(passphrase: str) -> bytes:
    return hashlib.sha256(("uia-vault:" + passphrase).encode()).digest()


class Vault:
    def __init__(self, path: str = "vault.json", key_env: str = "UIA_VAULT_KEY"):
        self.path = path
        passphrase = os.environ.get(key_env)
        if not passphrase:
            raise RuntimeError(
                f"set {key_env} to the vault key (from your secrets manager)")
        self.key = _derive(passphrase)

    def _load(self) -> dict:
        if not os.path.exists(self.path):
            return {}
        with open(self.path) as f:
            return json.load(f)

    def set(self, name: str, value: str):
        store = self._load()
        nonce = os.urandom(16)
        ct = bytes(b ^ k for b, k in zip(value.encode(), _keystream(self.key, nonce, len(value.encode()))))
        store[name] = {"nonce": base64.b64encode(nonce).decode(),
                       "ct": base64.b64encode(ct).decode()}
        with open(self.path, "w") as f:
            json.dump(store, f, indent=2)
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get(self, name: str) -> Optional[str]:
        rec = self._load().get(name)
        if not rec:
            return None
        nonce = base64.b64decode(rec["nonce"])
        ct = base64.b64decode(rec["ct"])
        pt = bytes(b ^ k for b, k in zip(ct, _keystream(self.key, nonce, len(ct))))
        return pt.decode()

    def names(self) -> list:
        return list(self._load().keys())


def inject(text: Optional[str], vault: Optional[Vault]) -> Optional[str]:
    """Replace {{secret:name}} with the vault value, at the last moment.

    Returns the text with secrets filled. If a secret is missing, the placeholder
    is left intact rather than silently blanked, so a misconfiguration is visible.
    """
    import re
    if text is None or vault is None or "{{secret:" not in text:
        return text
    def repl(m):
        v = vault.get(m.group(1))
        return v if v is not None else m.group(0)
    return re.sub(r"\{\{secret:(\w+)\}\}", repl, text)
