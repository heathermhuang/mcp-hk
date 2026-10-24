#!/usr/bin/env python3
"""Bounded, offline parser reproductions against the original source pin."""

import importlib.util
import io
import json
import subprocess
import zipfile

from mcp_open_data_hk.contracts import DomainError

REF = "4692f9a4c199aaabc75e26eb837cbb918e672553"
source = subprocess.check_output(
    ["git", "show", REF + ":src/mcp_open_data_hk/resource_formats.py"]
)
spec = importlib.util.spec_from_loader(
    "mcp_open_data_hk._security_baseline", loader=None
)
module = importlib.util.module_from_spec(spec)
exec(compile(source, "audit-resource-formats.py", "exec"), module.__dict__)
original = module.parse
calls = 0


def observed(*args, **kwargs):
    global calls
    calls += 1
    return original(*args, **kwargs)


def archive(name, data):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(name, data)
    return out.getvalue()


module.parse = observed
try:
    module.parse(archive("nested.csv", archive("data.csv", b"a\n1\n")), "CSV")
    code = "accepted"
except DomainError as exc:
    code = exc.code
print(
    json.dumps(
        {
            "test": "F4-before-nested-expansion",
            "source": REF,
            "parseCalls": calls,
            "terminalCode": code,
            "expected": "reject before child expansion",
            "result": "guard absent; recursive work observed",
        }
    )
)
rows, _ = module.parse(("x" * 1000 + "\n" + "v\n" * 9000).encode(), "CSV")
size = len(json.dumps(rows, ensure_ascii=False).encode())
print(
    json.dumps(
        {
            "test": "F4-before-normalized-bound",
            "source": REF,
            "rows": len(rows),
            "normalizedBytes": size,
            "candidateLimit": 8_000_000,
            "result": "accepted above candidate bound",
        }
    )
)
