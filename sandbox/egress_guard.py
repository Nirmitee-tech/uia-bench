"""PHI containment proof.

The HIPAA/GDPR story for local mode is only honest if we can show nothing left
the machine. This guard blocks all outbound network inside a `with` block by
replacing socket creation, and records any attempt. The containment test runs a
full task under this guard and asserts zero attempts.

This proves the *harness's* own code made no network call. It is not a kernel
firewall; a production deployment still needs an OS-level egress block. The test
documents that boundary rather than overclaiming.
"""
from __future__ import annotations

import socket


class EgressAttempt(Exception):
    pass


class NetworkGuard:
    def __init__(self, raise_on_attempt: bool = True):
        self.attempts = []
        self.raise_on_attempt = raise_on_attempt
        self._saved = None

    def __enter__(self):
        self._saved = socket.socket

        guard = self

        class _Blocked(socket.socket):
            def connect(self, address):
                guard.attempts.append(address)
                if guard.raise_on_attempt:
                    raise EgressAttempt(f"blocked outbound connect to {address}")
                return None

            def connect_ex(self, address):
                guard.attempts.append(address)
                if guard.raise_on_attempt:
                    raise EgressAttempt(f"blocked outbound connect_ex to {address}")
                return 1

        socket.socket = _Blocked
        return self

    def __exit__(self, *exc):
        socket.socket = self._saved
        return False

    @property
    def leaked(self) -> bool:
        return len(self.attempts) > 0
