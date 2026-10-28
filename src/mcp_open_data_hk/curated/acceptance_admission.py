"""Shared operator pacing; public quotas remain owned by the service."""

import json
import os
import time
from pathlib import Path


class Admission:
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        return json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self, value):
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(value))
        temporary.chmod(0o600)
        os.replace(temporary, self.path)

    def before(self):
        state = self.read()
        now = time.time() * 1000
        delay = (
            max(
                state.get("lastDispatchMs", 0) + 2100,
                state.get("notBeforeMs", 0),
            )
            - now
        )
        if delay > 60000:
            raise ValueError("ACCEPTANCE_QUOTA_DEFERRED")
        if delay > 0:
            time.sleep(delay / 1000)
        self.save(dict(state, lastDispatchMs=time.time() * 1000))

    def observe(self, status, headers):
        state = self.read()
        now = time.time() * 1000
        headers = {k.lower(): v for k, v in headers.items()}
        remaining = headers.get("ratelimit-remaining", "")
        reset = headers.get("ratelimit-reset", "")
        retry = headers.get("retry-after", "")
        seconds = 0
        if remaining.isdigit() and int(remaining) <= 10 and reset.isdigit():
            seconds = min(86400, int(reset))
        if status == 429:
            seconds = max(seconds, min(86400, int(retry)) if retry.isdigit() else 60)
        if seconds:
            state["notBeforeMs"] = max(
                state.get("notBeforeMs", 0), now + seconds * 1000
            )
        self.save(state)
